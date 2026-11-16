from __future__ import annotations

from datetime import date
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable
import hashlib
import json
import os
import re
from pathlib import Path

import pandas as pd


COLUNAS_ITENS = [
    "grupo_combo", "quantidade_inicial", "quantidade_final",
    "produto_codigo", "valor", "produto_descricao",
]
TABELAS_PLANEJADAS = ["COMBO", "GRUPOCOMBO", "ITEMGRUPOCOMBO", "COMBOCLIFOR"]
BLOQUEIOS_SCHEMA = [
    "GRUPOCOMBO.CODIGO é obrigatório e não possui generator ou trigger no TOP.",
    "A regra para preencher GRUPOCOMBO.QTDE e BONIFICADO não é unívoca nos combos existentes.",
    "Combos do tipo desconto podem exigir GRUPOCOMBODESCONTO; o formulário informado não define desconto nem sua regra.",
    "Os valores funcionais de COMBO.TIPO, GERARFLEX e INSERIRAUTOMATICO precisam ser confirmados para cada modalidade.",
]
ARQUIVO_ERROS = Path(__file__).resolve().parent / "dados_locais" / "combo_criacao_erros.jsonl"


def registrar_erro_criacao(
    etapa: str, erro: Exception | str, usuario: str, caminho: Path = ARQUIVO_ERROS
) -> None:
    mensagem = str(erro)
    mensagem = re.sub(
        r"(?i)(password|senha|pwd)\s*[=:]\s*[^\s,;]+", r"\1=***", mensagem
    )
    evento = {
        "data_hora": datetime.now().astimezone().isoformat(),
        "etapa": etapa,
        "erro": mensagem[:2000],
        "usuario": usuario,
    }
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("a", encoding="utf-8", newline="\n") as arquivo:
        arquivo.write(json.dumps(evento, ensure_ascii=False) + "\n")
        arquivo.flush()
        os.fsync(arquivo.fileno())


def decimal_brasileiro(valor) -> Decimal | None:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return Decimal(texto)
    except InvalidOperation:
        return None


def normalizar_clientes(clientes: Iterable) -> list[int]:
    resultado = []
    for item in clientes:
        try:
            codigo = int(item)
        except (TypeError, ValueError):
            continue
        if codigo > 0:
            resultado.append(codigo)
    return sorted(set(resultado))


def preparar_contexto_clientes(origem: str, clientes: Iterable) -> dict:
    unicos = normalizar_clientes(clientes)
    return {
        "origem": origem,
        "clientes": unicos,
        "assinatura_clientes": tuple(unicos),
    }


def transportar_clientes_para_estado(estado, origem: str, clientes: Iterable) -> None:
    contexto = preparar_contexto_clientes(origem, clientes)
    estado["combo_form_aberto"] = True
    estado["combo_form_origem"] = contexto["origem"]
    estado["combo_form_clientes_iniciais"] = contexto["clientes"]
    estado["combo_form_clientes"] = contexto["clientes"]
    estado["combo_form_assinatura_clientes"] = contexto["assinatura_clientes"]


def assinatura_formulario(
    nome, data_inicio, data_fim, classificacao,
    itens: pd.DataFrame, clientes: Iterable[int], filiais: Iterable[int] = (),
    cotas_filiais: dict[int, int] | None = None,
) -> str:
    conteudo = repr((
        str(nome), str(data_inicio), str(data_fim), str(classificacao),
        itens.fillna("").astype(str).to_dict("records"), normalizar_clientes(clientes),
        normalizar_clientes(filiais),
        sorted((int(k), int(v)) for k, v in (cotas_filiais or {}).items()),
    ))
    return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()


def validar_cabecalho(nome: str, data_inicio: date, data_fim: date) -> list[str]:
    erros = []
    if not str(nome or "").strip():
        erros.append("Nome do combo é obrigatório.")
    elif len(str(nome).strip()) > 60:
        erros.append("Nome do combo deve ter no máximo 60 caracteres.")
    if not data_inicio or not data_fim:
        erros.append("Datas inicial e final são obrigatórias.")
    elif data_fim < data_inicio:
        erros.append("Data final não pode ser menor que a data inicial.")
    return erros


def validar_itens(itens: pd.DataFrame, produtos_validos: dict[int, str] | None = None):
    produtos_validos = produtos_validos or {}
    base = itens.copy().dropna(how="all")
    erros_gerais: list[str] = []
    registros = []
    for indice, linha in base.iterrows():
        erros = []
        grupo = str(linha.get("grupo_combo", "") or "").strip()
        qi = decimal_brasileiro(linha.get("quantidade_inicial"))
        qf = decimal_brasileiro(linha.get("quantidade_final"))
        valor = decimal_brasileiro(linha.get("valor"))
        try:
            produto = int(linha.get("produto_codigo"))
        except (TypeError, ValueError):
            produto = None
        if not grupo:
            erros.append("grupo obrigatório")
        if qi is None or qi <= 0:
            erros.append("quantidade inicial deve ser positiva")
        if qf is None or qf <= 0:
            erros.append("quantidade final deve ser positiva")
        if qi is not None and qf is not None and qf < qi:
            erros.append("quantidade final menor que a inicial")
        if valor is None or valor < 0:
            erros.append("valor inválido ou negativo")
        if produto is None or produto <= 0:
            erros.append("produto inválido")
        elif produtos_validos and produto not in produtos_validos:
            erros.append("produto não encontrado no TOP")
        registros.append({
            "linha": int(indice) + 1, "grupo_combo": grupo,
            "quantidade_inicial": qi, "quantidade_final": qf,
            "produto_codigo": produto, "valor": valor,
            "produto_descricao": produtos_validos.get(produto, ""),
            "erros": "; ".join(erros),
        })
    validado = pd.DataFrame(registros)
    if validado.empty:
        return validado, ["Informe ao menos uma linha de produto/faixa."]
    chaves = ["grupo_combo", "produto_codigo", "quantidade_inicial", "quantidade_final"]
    duplicadas = validado.duplicated(chaves, keep=False)
    for idx in validado.index[duplicadas]:
        validado.loc[idx, "erros"] = "; ".join(
            x for x in [validado.loc[idx, "erros"], "linha duplicada"] if x
        )
    for (_, produto), grupo in validado.groupby(["grupo_combo", "produto_codigo"], dropna=False):
        ordenado = grupo.sort_values("quantidade_inicial")
        fim_anterior = None
        for idx, linha in ordenado.iterrows():
            if linha.quantidade_inicial is None or linha.quantidade_final is None:
                continue
            if fim_anterior is not None and linha.quantidade_inicial <= fim_anterior:
                validado.loc[idx, "erros"] = "; ".join(
                    x for x in [validado.loc[idx, "erros"], "faixa conflitante"] if x
                )
            fim_anterior = max(fim_anterior or linha.quantidade_final, linha.quantidade_final)
    if validado["erros"].astype(bool).any():
        erros_gerais.append("Corrija as linhas destacadas antes de continuar.")
    return validado, erros_gerais


def preparar_plano(
    nome: str, data_inicio: date, data_fim: date,
    classificacao: str, itens_validados: pd.DataFrame, clientes: Iterable[int], origem: str,
    filiais: Iterable[int] = (), cotas_filiais: dict[int, int] | None = None,
) -> dict:
    clientes_unicos = normalizar_clientes(clientes)
    filiais_unicas = normalizar_clientes(filiais)
    cotas_filiais = {
        int(filial): int(cota) for filial, cota in (cotas_filiais or {}).items()
        if int(filial) in filiais_unicas
    }
    grupos = sorted(itens_validados["grupo_combo"].dropna().astype(str).unique().tolist())
    tabelas = list(TABELAS_PLANEJADAS)
    if filiais_unicas:
        tabelas.append("COMBOFILIAL")
    if clientes_unicos and cotas_filiais:
        tabelas.append("ITEMCOTACOMBOCLIENTE")
    return {
        "codigo": None, "codigo_gerado_pelo_erp": True, "nome": str(nome).strip(),
        "data_inicio": data_inicio, "data_fim": data_fim,
        "classificacao": classificacao, "origem": origem,
        "itens": itens_validados.to_dict("records"), "clientes": clientes_unicos,
        "quantidade_grupos": len(grupos), "quantidade_itens": len(itens_validados),
        "quantidade_clientes": len(clientes_unicos),
        "filiais": filiais_unicas, "quantidade_filiais": len(filiais_unicas),
        "cotas_filiais": cotas_filiais,
        "quantidade_cotas_filiais": len(cotas_filiais),
        "tabelas": tabelas,
        "bloqueios_schema": list(BLOQUEIOS_SCHEMA), "gravacao_habilitada": False,
    }


def executar_etapas_transacionais(conexao, etapas) -> None:
    """Utilitário testável; confirma tudo ou reverte tudo se qualquer etapa falhar."""
    try:
        for etapa in etapas:
            etapa(conexao)
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
