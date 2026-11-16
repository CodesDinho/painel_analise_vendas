from __future__ import annotations

import json
import re
from typing import Any, Iterable

import pandas as pd


SEVERIDADES = ("ERRO", "CONFLITO", "ALERTA", "INFORMATIVO")


def normalizar_codigos(texto: str) -> list[int]:
    codigos = []
    invalidos = []
    for item in re.split(r"[\s,;]+", texto.strip()):
        if not item:
            continue
        if not item.isdigit() or int(item) <= 0:
            invalidos.append(item)
            continue
        codigo = int(item)
        if codigo not in codigos:
            codigos.append(codigo)
    if invalidos:
        raise ValueError("Códigos inválidos: " + ", ".join(invalidos))
    return codigos


def _valor(evidencias: dict[str, Any], *chaves: str) -> Any:
    for chave in chaves:
        if chave in evidencias and evidencias[chave] not in (None, "", []):
            return evidencias[chave]
    return None


def normalizar_apontamentos(relatorio: dict[str, Any]) -> pd.DataFrame:
    linhas = []
    for item in relatorio.get("findings") or []:
        evidencias = item.get("evidencias") if isinstance(item.get("evidencias"), dict) else {}
        produtos = evidencias.get("produtos") or (
            [item["produto"]] if item.get("produto") is not None else []
        )
        filiais = _valor(evidencias, "filiais", "filial")
        if filiais is None and item.get("filial") is not None:
            filiais = item.get("filial")
        linhas.append({
            "severidade": str(item.get("status") or "INFORMATIVO").upper(),
            "combo": item.get("combo"),
            "nome_combo": item.get("nome") or "",
            "regra": item.get("regra") or "",
            "produto": item.get("produto"),
            "produtos": ", ".join(str(valor) for valor in produtos),
            "combo_conflitante": evidencias.get("combo_conflitante"),
            "nome_conflitante": evidencias.get("nome_conflitante") or "",
            "filial": filiais,
            "publico": _valor(evidencias, "publico", "clientes", "audiencia"),
            "tipo_combo": _valor(evidencias, "tipo_combo", "tipo"),
            "vigencia": _valor(evidencias, "vigencia", "periodo"),
            "valor_combo": item.get("valor_combo"),
            "valor_referencia": item.get("valor_referencia"),
            "mensagem": item.get("mensagem") or "",
            "acao_recomendada": item.get("acao_recomendada") or "",
            "data_analise": item.get("data_analise") or relatorio.get("generated_at"),
            "evidencias": json.dumps(evidencias, ensure_ascii=False, default=str),
        })
    colunas = [
        "severidade", "combo", "nome_combo", "regra", "produto", "produtos",
        "combo_conflitante", "nome_conflitante", "filial", "publico",
        "tipo_combo", "vigencia", "valor_combo", "valor_referencia",
        "mensagem", "acao_recomendada", "data_analise", "evidencias",
    ]
    resultado = pd.DataFrame(linhas, columns=colunas)
    if not resultado.empty:
        ordem = {valor: indice for indice, valor in enumerate(SEVERIDADES)}
        resultado["_ordem"] = resultado["severidade"].map(ordem).fillna(99)
        resultado = resultado.sort_values(
            ["_ordem", "combo", "regra"], ignore_index=True
        ).drop(columns="_ordem")
    return resultado


def filtrar_apontamentos(
    dados: pd.DataFrame,
    severidades: Iterable[str] = (),
    regras: Iterable[str] = (),
    busca: str = "",
    produto: str = "",
    filial: str = "",
    tipos: Iterable[str] = (),
    vigencias: Iterable[str] = (),
) -> pd.DataFrame:
    resultado = dados.copy()
    if severidades:
        resultado = resultado[resultado["severidade"].isin(severidades)]
    if regras:
        resultado = resultado[resultado["regra"].isin(regras)]
    if tipos:
        resultado = resultado[resultado["tipo_combo"].astype(str).isin(tipos)]
    if vigencias:
        resultado = resultado[resultado["vigencia"].astype(str).isin(vigencias)]
    if busca.strip():
        termo = busca.strip().casefold()
        texto = (
            resultado["combo"].astype(str) + " "
            + resultado["nome_combo"].fillna("").astype(str)
        ).str.casefold()
        resultado = resultado[texto.str.contains(termo, regex=False)]
    if produto.strip():
        termo = produto.strip()
        texto = (
            resultado["produto"].fillna("").astype(str) + ","
            + resultado["produtos"].fillna("").astype(str)
        )
        resultado = resultado[texto.str.contains(termo, regex=False)]
    if filial.strip():
        resultado = resultado[
            resultado["filial"].fillna("").astype(str).str.contains(
                filial.strip(), regex=False
            )
        ]
    return resultado.reset_index(drop=True)


def calcular_indicadores(dados: pd.DataFrame) -> dict[str, int]:
    return {
        "combos": int(dados["combo"].nunique()) if not dados.empty else 0,
        **{
            status.lower(): int(dados["severidade"].eq(status).sum())
            if not dados.empty else 0
            for status in SEVERIDADES
        },
    }
