from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parents[2]
CACHE_PATH = BASE_DIR / "cache" / "auditoria_combos_api.json"


class ComboAuditApiError(RuntimeError):
    """Falha previsível de configuração, transporte ou contrato da API."""


@dataclass(frozen=True)
class ApiConfig:
    base_url: str
    token: str | None = None
    timeout: float = 45.0
    auth_header: str = "Authorization"
    auth_prefix: str = "Bearer"


def obter_configuracao() -> ApiConfig | None:
    base_url = os.getenv("ANALISE_VENDAS_COMBO_AUDIT_API_URL", "").strip().rstrip("/")
    if not base_url:
        return None
    timeout_raw = os.getenv("ANALISE_VENDAS_COMBO_AUDIT_API_TIMEOUT", "45").strip()
    try:
        timeout = max(float(timeout_raw), 1.0)
    except ValueError as exc:
        raise ComboAuditApiError(
            "ANALISE_VENDAS_COMBO_AUDIT_API_TIMEOUT deve ser numérico."
        ) from exc
    return ApiConfig(
        base_url=base_url,
        token=os.getenv("ANALISE_VENDAS_COMBO_AUDIT_API_TOKEN", "").strip() or None,
        timeout=timeout,
        auth_header=os.getenv(
            "ANALISE_VENDAS_COMBO_AUDIT_API_AUTH_HEADER", "Authorization"
        ).strip() or "Authorization",
        auth_prefix=os.getenv(
            "ANALISE_VENDAS_COMBO_AUDIT_API_AUTH_PREFIX", "Bearer"
        ).strip(),
    )


def _headers(config: ApiConfig) -> dict[str, str]:
    headers = {"Accept": "application/json", "User-Agent": "PainelAnaliseVendas/1.0"}
    if config.token:
        valor = f"{config.auth_prefix} {config.token}".strip()
        headers[config.auth_header] = valor
    return headers


def _get_json(config: ApiConfig, path: str) -> dict[str, Any]:
    if not config.token:
        raise ComboAuditApiError(
            "Configure ANALISE_VENDAS_COMBO_AUDIT_API_TOKEN para autenticar a consulta."
        )
    payload: Any = None
    # Uma retentativa curta e limitada reduz falhas transitórias sem pressionar o ERP.
    for tentativa in range(2):
        request = Request(
            f"{config.base_url}{path}", headers=_headers(config), method="GET"
        )
        try:
            with urlopen(request, timeout=config.timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                payload = json.loads(response.read().decode(charset))
            break
        except HTTPError as exc:
            mensagens = {
                400: "A API recusou os parâmetros da consulta (HTTP 400).",
                401: "A API recusou a autenticação do painel. Confira o token interno.",
                403: "A API recusou a autenticação do painel. Confira o token interno.",
                405: "A API não permite o método solicitado (HTTP 405).",
                429: "A API está ocupada com outras auditorias (HTTP 429).",
                503: "A auditoria ou o Firebird está temporariamente indisponível (HTTP 503).",
                504: "A auditoria excedeu o tempo permitido pela API (HTTP 504).",
            }
            if exc.code in {429, 503, 504} and tentativa == 0:
                time.sleep(1.0)
                continue
            raise ComboAuditApiError(
                mensagens.get(exc.code, f"A API respondeu HTTP {exc.code}.")
            ) from exc
        except URLError as exc:
            motivo = getattr(exc, "reason", exc)
            raise ComboAuditApiError(f"Não foi possível acessar a API: {motivo}.") from exc
        except (TimeoutError, json.JSONDecodeError) as exc:
            raise ComboAuditApiError(
                "A API não respondeu no prazo ou devolveu JSON inválido."
            ) from exc
    if not isinstance(payload, dict):
        raise ComboAuditApiError("A API devolveu um formato diferente do objeto JSON esperado.")
    return payload


def validar_relatorio(payload: dict[str, Any]) -> dict[str, Any]:
    schema = str(payload.get("schema_version") or "")
    if schema != "1.0":
        raise ComboAuditApiError(
            f"Versão de schema incompatível: {schema or 'não informada'}; esperado 1.0."
        )
    findings = payload.get("findings")
    if not isinstance(findings, list):
        raise ComboAuditApiError("A resposta não contém a lista `findings`.")
    if any(not isinstance(item, dict) for item in findings):
        raise ComboAuditApiError("A resposta contém apontamento em formato inválido.")
    return payload


def _combinar_relatorios(relatorios: Iterable[dict[str, Any]]) -> dict[str, Any]:
    itens = list(relatorios)
    findings: list[dict[str, Any]] = []
    for relatorio in itens:
        findings.extend(relatorio.get("findings") or [])
    unicos: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for finding in findings:
        evidencias = finding.get("evidencias") or {}
        conflitante = evidencias.get("combo_conflitante")
        if finding.get("regra") == "COMBOS_ATIVOS_SOBREPOSTOS" and conflitante:
            assinatura = json.dumps(
                [finding.get("regra"), sorted([int(finding["combo"]), int(conflitante)])]
            )
        else:
            assinatura = json.dumps(finding, ensure_ascii=False, sort_keys=True, default=str)
        if assinatura not in vistos:
            vistos.add(assinatura)
            unicos.append(finding)
    severidades = ("ERRO", "CONFLITO", "ALERTA", "INFORMATIVO")
    combinado = {
        "schema_version": "1.0",
        "generated_at": max(
            (str(item.get("generated_at") or "") for item in itens), default=""
        ),
        "scope": "combos_informados",
        "summary": {
            status.lower(): sum(
                str(item.get("status") or "").upper() == status for item in unicos
            )
            for status in severidades
        },
        "total_findings": len(unicos),
        "findings": unicos,
    }
    fluxos = [item.get("correction_workflow") for item in itens]
    combinado["correction_workflow"] = next((item for item in fluxos if item), {})
    codigos = [codigo for item in itens for codigo in (item.get("combo_codes") or [])]
    combinado["combo_codes"] = list(dict.fromkeys(codigos))
    return combinado


def _consultar_todas_paginas(config: ApiConfig, page_size: int = 25) -> dict[str, Any]:
    relatorios: list[dict[str, Any]] = []
    processados = 0
    total: int | None = None
    pagina = 1
    while total is None or processados < total:
        relatorio = validar_relatorio(
            _get_json(config, f"/api/combo-audit?page={pagina}&page_size={page_size}")
        )
        paginacao = relatorio.get("pagination")
        if not isinstance(paginacao, dict):
            raise ComboAuditApiError("A resposta geral não contém paginação válida.")
        try:
            total_pagina = int(paginacao["total_combos"])
            retornados = int(paginacao["returned_combos"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ComboAuditApiError("A API devolveu paginação incompleta ou inválida.") from exc
        if total is not None and total_pagina != total:
            raise ComboAuditApiError("O total de combos mudou durante a consulta; tente novamente.")
        total = total_pagina
        if retornados < 0 or retornados > page_size:
            raise ComboAuditApiError("A API devolveu quantidade paginada inválida.")
        if retornados == 0 and processados < total:
            raise ComboAuditApiError("A API encerrou a paginação antes de retornar todos os combos.")
        relatorios.append(relatorio)
        processados += retornados
        pagina += 1
    combinado = _combinar_relatorios(relatorios)
    combinado["scope"] = "combos_ativos"
    combinado["pagination"] = {
        "page_size": page_size,
        "total_combos": total or 0,
        "returned_combos": processados,
        "pages_fetched": len(relatorios),
    }
    return combinado


def consultar_auditoria(
    config: ApiConfig, codigos: Iterable[int] | None = None
) -> dict[str, Any]:
    codigos_unicos = list(dict.fromkeys(int(codigo) for codigo in (codigos or [])))
    if not codigos_unicos:
        return _consultar_todas_paginas(config)
    relatorios = [
        validar_relatorio(
            _get_json(config, f"/api/combo-audit/{quote(str(codigo), safe='')}")
        )
        for codigo in codigos_unicos
    ]
    return _combinar_relatorios(relatorios)


def consultar_versao(config: ApiConfig) -> dict[str, Any]:
    versao = _get_json(config, "/api/combo-rules/version")
    schema = str(versao.get("schema_version") or "")
    if schema != "1.0":
        raise ComboAuditApiError(
            f"Versão de schema incompatível no endpoint de versão: {schema or 'não informada'}."
        )
    return versao


def salvar_cache(
    relatorio: dict[str, Any], versao: dict[str, Any] | None = None,
    caminho: Path = CACHE_PATH,
) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conteudo = {
        "cached_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "report": relatorio,
        "rules_version": versao or {},
    }
    temporario = caminho.with_suffix(".tmp")
    temporario.write_text(
        json.dumps(conteudo, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    temporario.replace(caminho)


def carregar_cache(caminho: Path = CACHE_PATH) -> dict[str, Any] | None:
    if not caminho.exists():
        return None
    try:
        conteudo = json.loads(caminho.read_text(encoding="utf-8"))
        if not isinstance(conteudo, dict) or not isinstance(conteudo.get("report"), dict):
            return None
        validar_relatorio(conteudo["report"])
        return conteudo
    except (OSError, json.JSONDecodeError, ComboAuditApiError):
        return None
