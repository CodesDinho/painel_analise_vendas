from __future__ import annotations

import os
import pickle
import csv
import io
import zipfile
import unicodedata
from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd

from conexoes import cliente_bigquery, cliente_firebird


BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)
CACHE_VERSION = "base_vendas_v9_industria_mais_televendas"
INDUSTRIAS = {"Pernod": (80166, 80066), "Campari": (80047,), "VCT": (4135,)}
CODIGO_INDUSTRIA = {codigo: nome for nome, codigos in INDUSTRIAS.items() for codigo in codigos}
TIPOS_ESTABELECIMENTO_RANKING = {
    "Conveniência": (24, 21, 22, 23),
    "Mercado de Bebidas": (39, 71),
    "Distribuidora": (72,),
    "Mercados": (33, 35, 38, 34),
}
TIPOS_ESTABELECIMENTO_MULTICANAL = {
    21, 22, 23, 24, 25, 26, 31, 32, 33, 34, 39, 49, 71, 72, 73, 93, 96, 97,
    201,
}
TIPOS_ESTABELECIMENTO_KEY_OFF = {35, 38}
TIPOS_ESTABELECIMENTO_SEM_BLOQUEIO_SEM_PRZ = {
    33, 34, 35, 36, 38, 39, 40, 47, 49,
}
TIPOS_ESTABELECIMENTO_KEY_ON = {
    41, 42, 43, 44, 45, 46, 51, 52, 53, 61, 62, 63, 65, 81, 82, 83, 84,
    85, 86, 91, 92,
}
VENDEDORES_PROTEGIDOS_PAGAMENTOS = {187, 1929}
TABELA_PRECO_ATACADO_PROTEGIDA = 480
CONDICAO_PAGAMENTO_A_VISTA_PROTEGIDA = 100
TIPOS_ESTABELECIMENTO_EXTRAS_RANKING = (
    TIPOS_ESTABELECIMENTO_MULTICANAL
    | TIPOS_ESTABELECIMENTO_KEY_ON
    | TIPOS_ESTABELECIMENTO_KEY_OFF
) - {
    codigo
    for codigos in TIPOS_ESTABELECIMENTO_RANKING.values()
    for codigo in codigos
}
UF_POR_ESTADO = {
    "ACRE": "AC", "ALAGOAS": "AL", "AMAPÁ": "AP", "AMAPA": "AP",
    "AMAZONAS": "AM", "BAHIA": "BA", "CEARÁ": "CE", "CEARA": "CE",
    "DISTRITO FEDERAL": "DF", "ESPÍRITO SANTO": "ES", "ESPIRITO SANTO": "ES",
    "GOIÁS": "GO", "GOIAS": "GO", "MARANHÃO": "MA", "MARANHAO": "MA",
    "MATO GROSSO": "MT", "MATO GROSSO DO SUL": "MS", "MINAS GERAIS": "MG",
    "PARÁ": "PA", "PARA": "PA", "PARAÍBA": "PB", "PARAIBA": "PB",
    "PARANÁ": "PR", "PARANA": "PR", "PERNAMBUCO": "PE", "PIAUÍ": "PI",
    "PIAUI": "PI", "RIO DE JANEIRO": "RJ", "RIO GRANDE DO NORTE": "RN",
    "RIO GRANDE DO SUL": "RS", "RONDÔNIA": "RO", "RONDONIA": "RO",
    "RORAIMA": "RR", "SANTA CATARINA": "SC", "SÃO PAULO": "SP",
    "SAO PAULO": "SP", "SERGIPE": "SE", "TOCANTINS": "TO",
}


SQL_BASE = """
WITH equipes AS (
  SELECT equipe_codigo, ANY_VALUE(equipe_nome) AS equipe_nome
  FROM `dinho-dw.topsystem_silver.equipe_comercial`
  GROUP BY equipe_codigo
),
clientes AS (
  SELECT
    cliente_codigo,
    ANY_VALUE(cod_estabelecimento_tipo) AS estabelecimento_tipo_codigo,
    ANY_VALUE(estabelecimento_tipo) AS estabelecimento_tipo_nome
  FROM `dinho-dw.topsystem_silver.cliente`
  GROUP BY cliente_codigo
),
carteiras AS (
  SELECT
    clifor AS cliente_codigo,
    COUNT(DISTINCT funcionario) AS quantidade_vendedores
  FROM `dinho-dw.topsystem_bronze.funcionarioclifor`
  WHERE clifor IS NOT NULL AND funcionario IS NOT NULL
  GROUP BY clifor
)
SELECT
  DATE(v.pedido_data_emissao) AS data_venda,
  CAST(v.cliente_codigo AS INT64) AS cliente_codigo,
  MAX(NULLIF(UPPER(TRIM(v.estado_cliente)), '')) AS cliente_estado,
  c.estabelecimento_tipo_codigo,
  c.estabelecimento_tipo_nome,
  COALESCE(ca.quantidade_vendedores, 0) AS quantidade_vendedores_carteira,
  IF(COALESCE(ca.quantidade_vendedores, 0) > 0, 'COM VENDEDOR ALOCADO', 'SEM VENDEDOR ALOCADO') AS situacao_carteira,
  CAST(v.equipe_codigo AS INT64) AS equipe_codigo,
  e.equipe_nome,
  CAST(v.funcionario_codigo AS INT64) AS vendedor_codigo,
  CAST(v.produto_fornecedor_cod AS INT64) AS fornecedor_codigo,
  CAST(v.produto_codigo AS INT64) AS produto_codigo,
  SUM(CAST(v.quantidade AS FLOAT64)) AS unidades,
  SUM(SAFE_DIVIDE(CAST(v.quantidade AS FLOAT64), NULLIF(CAST(p.quantidade_compra AS FLOAT64), 0))) AS volume,
  SUM(CAST(v.valor_total AS FLOAT64)) AS faturamento
FROM `dinho-dw.topsystem_silver.vendas` v
LEFT JOIN `dinho-dw.topsystem_bronze.produto` p ON p.codigo = v.produto_codigo
LEFT JOIN equipes e ON e.equipe_codigo = v.equipe_codigo
LEFT JOIN clientes c ON c.cliente_codigo = v.cliente_codigo
LEFT JOIN carteiras ca ON ca.cliente_codigo = v.cliente_codigo
WHERE DATE(v.pedido_data_emissao) BETWEEN @data_inicio AND @data_fim
  AND v.cliente_codigo IS NOT NULL
  AND COALESCE(TRIM(v.tipo_pedido), '') <> '48'
  AND v.produto_fornecedor_cod IN UNNEST(@fornecedores)
GROUP BY 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12
"""


SQL_BASE_TELEVENDAS = """
SELECT
    c.CODIGO AS cliente_codigo,
    c.DATAMOVIMENTO AS televendas_ultima_compra,
    CASE WHEN EXISTS (
        SELECT 1 FROM FUNCIONARIOCLIFOR fc WHERE fc.CLIFOR = c.CODIGO
    ) THEN 1 ELSE 0 END AS televendas_tem_vendedor,
    CASE WHEN EXISTS (
        SELECT 1 FROM ROTACLIFOR rc WHERE rc.CLIFOR = c.CODIGO
    ) THEN 1 ELSE 0 END AS televendas_tem_rota
FROM CLIFOR c
WHERE c.TIPO = 1
  AND COALESCE(c.ATIVO, 'N') = 'S'
  AND c.DATAMOVIMENTO BETWEEN CURRENT_DATE - 120 AND CURRENT_DATE - 30
  AND NOT EXISTS (
      SELECT 1
      FROM FUNCIONARIOCLIFOR fc_bees
      WHERE fc_bees.CLIFOR = c.CODIGO
        AND fc_bees.FUNCIONARIO = 2262
  )
"""


def _arquivo_cache(hoje: date) -> Path:
    return CACHE_DIR / f"{CACHE_VERSION}_{hoje:%Y%m%d}.pkl"


def _normalizar(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["data_venda"] = pd.to_datetime(df["data_venda"], errors="coerce")
    if "cliente_estado" not in df:
        df["cliente_estado"] = "NÃO IDENTIFICADO"
    estado_normalizado = (
        df["cliente_estado"].fillna("NÃO IDENTIFICADO").astype(str).str.strip().str.upper()
    )
    df["cliente_estado"] = estado_normalizado.map(UF_POR_ESTADO).fillna(estado_normalizado)
    for coluna in ("cliente_codigo", "estabelecimento_tipo_codigo", "quantidade_vendedores_carteira", "equipe_codigo", "vendedor_codigo", "fornecedor_codigo", "produto_codigo"):
        if coluna not in df:
            df[coluna] = pd.NA
        df[coluna] = pd.to_numeric(df[coluna], errors="coerce").astype("Int64")
    df["estabelecimento_tipo_codigo"] = df["estabelecimento_tipo_codigo"].fillna(0)
    df["quantidade_vendedores_carteira"] = df["quantidade_vendedores_carteira"].fillna(0)
    if "situacao_carteira" not in df:
        df["situacao_carteira"] = "SEM VENDEDOR ALOCADO"
    df["situacao_carteira"] = df["situacao_carteira"].fillna("SEM VENDEDOR ALOCADO")
    if "estabelecimento_tipo_nome" not in df:
        df["estabelecimento_tipo_nome"] = "NÃO IDENTIFICADO"
    df["estabelecimento_tipo_nome"] = (
        df["estabelecimento_tipo_nome"].fillna("NÃO IDENTIFICADO").astype(str).str.strip()
    )
    for coluna in ("unidades", "volume", "faturamento"):
        if coluna not in df:
            df[coluna] = 0.0
        df[coluna] = pd.to_numeric(df[coluna], errors="coerce").fillna(0.0)
    if "equipe_nome" not in df:
        df["equipe_nome"] = "SEM NOME"
    df["equipe_nome"] = df["equipe_nome"].fillna("SEM NOME").astype(str)
    df["industria"] = df["fornecedor_codigo"].map(CODIGO_INDUSTRIA).fillna("Outras")
    return df


def consultar_bigquery(hoje: date) -> pd.DataFrame:
    from google.cloud import bigquery

    parametros = [
        bigquery.ScalarQueryParameter("data_inicio", "DATE", date(hoje.year - 1, 1, 1)),
        bigquery.ScalarQueryParameter("data_fim", "DATE", hoje),
        bigquery.ArrayQueryParameter("fornecedores", "INT64", sorted(CODIGO_INDUSTRIA)),
    ]
    job_config = bigquery.QueryJobConfig(query_parameters=parametros)
    return _normalizar(cliente_bigquery().query(SQL_BASE, job_config=job_config).to_dataframe())


def consultar_base_televendas(hoje: date) -> pd.DataFrame:
    """Carrega o semáforo verde do Painel_vendas na mesma data de referência."""
    con = cliente_firebird()
    cursor = con.cursor()
    try:
        cursor.execute(SQL_BASE_TELEVENDAS)
        linhas = cursor.fetchall()
        colunas = [desc[0].strip().lower() for desc in cursor.description]
    finally:
        cursor.close()
        con.close()
    base = pd.DataFrame(linhas, columns=colunas)
    if base.empty:
        return pd.DataFrame(columns=[
            "cliente_codigo", "televendas_ultima_compra",
            "televendas_tem_vendedor", "televendas_tem_rota",
        ])
    base["cliente_codigo"] = pd.to_numeric(base["cliente_codigo"], errors="coerce").astype("Int64")
    base["televendas_ultima_compra"] = pd.to_datetime(
        base["televendas_ultima_compra"], errors="coerce"
    )
    for coluna in ("televendas_tem_vendedor", "televendas_tem_rota"):
        base[coluna] = pd.to_numeric(base[coluna], errors="coerce").fillna(0).astype("Int64")
    base["televendas_dias_sem_compra"] = (
        pd.Timestamp(hoje) - base["televendas_ultima_compra"]
    ).dt.days
    return base.drop_duplicates("cliente_codigo")


def consultar_ranking_skus(data_inicio: date, data_fim: date) -> pd.DataFrame:
    """Retorna somente os 50 SKUs mais e menos vendidos de cada grupo."""
    if data_inicio > data_fim:
        raise ValueError("A data inicial deve ser anterior ou igual à data final.")
    from google.cloud import bigquery

    sql = """
WITH clientes AS (
  SELECT
    cliente_codigo,
    ANY_VALUE(cod_estabelecimento_tipo) AS tipo_estabelecimento
  FROM `dinho-dw.topsystem_silver.cliente`
  GROUP BY cliente_codigo
),
produtos AS (
  SELECT codigo, ANY_VALUE(nome) AS nome
  FROM `dinho-dw.topsystem_bronze.produto`
  GROUP BY codigo
),
agregado AS (
  SELECT
    CASE
      WHEN c.tipo_estabelecimento IN (24, 21, 22, 23) THEN 'Conveniência'
      WHEN c.tipo_estabelecimento IN (39, 71) THEN 'Mercado de Bebidas'
      WHEN c.tipo_estabelecimento = 72 THEN 'Distribuidora'
      WHEN c.tipo_estabelecimento IN (33, 35, 38, 34) THEN 'Mercados'
    END AS grupo_estabelecimento,
    CAST(v.produto_codigo AS INT64) AS produto_codigo,
    ANY_VALUE(p.nome) AS produto_nome,
    SUM(CAST(v.quantidade AS FLOAT64)) AS quantidade_vendida,
    SAFE_DIVIDE(
      SUM(CAST(v.valor_total AS FLOAT64)),
      NULLIF(SUM(CAST(v.quantidade AS FLOAT64)), 0)
    ) AS valor_medio_venda
  FROM `dinho-dw.topsystem_silver.vendas` v
  JOIN clientes c ON c.cliente_codigo = v.cliente_codigo
  LEFT JOIN produtos p ON p.codigo = v.produto_codigo
  WHERE DATE(v.pedido_data_emissao) BETWEEN @data_inicio AND @data_fim
    AND c.tipo_estabelecimento IN (24, 21, 22, 23, 39, 71, 72, 33, 35, 38, 34)
    AND v.produto_codigo IS NOT NULL
    AND COALESCE(TRIM(v.tipo_pedido), '') <> '48'
  GROUP BY 1, 2
  HAVING SUM(CAST(v.quantidade AS FLOAT64)) > 0
),
ranqueado AS (
  SELECT *,
    ROW_NUMBER() OVER (
      PARTITION BY grupo_estabelecimento
      ORDER BY quantidade_vendida DESC, produto_codigo
    ) AS posicao_mais_vendidos,
    ROW_NUMBER() OVER (
      PARTITION BY grupo_estabelecimento
      ORDER BY quantidade_vendida ASC, produto_codigo
    ) AS posicao_menos_vendidos
  FROM agregado
)
SELECT
  grupo_estabelecimento, 'Mais vendidos' AS ranking,
  posicao_mais_vendidos AS posicao, produto_codigo, produto_nome,
  quantidade_vendida, valor_medio_venda
FROM ranqueado WHERE posicao_mais_vendidos <= 50
UNION ALL
SELECT
  grupo_estabelecimento, 'Menos vendidos' AS ranking,
  posicao_menos_vendidos AS posicao, produto_codigo, produto_nome,
  quantidade_vendida, valor_medio_venda
FROM ranqueado WHERE posicao_menos_vendidos <= 50
ORDER BY grupo_estabelecimento, ranking, posicao
"""
    parametros = [
        bigquery.ScalarQueryParameter("data_inicio", "DATE", data_inicio),
        bigquery.ScalarQueryParameter("data_fim", "DATE", data_fim),
    ]
    ranking = cliente_bigquery().query(
        sql, job_config=bigquery.QueryJobConfig(query_parameters=parametros)
    ).to_dataframe()
    if ranking.empty:
        return ranking

    codigos = sorted(ranking["produto_codigo"].dropna().astype(int).unique())
    custos: list[tuple] = []
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        for inicio in range(0, len(codigos), 500):
            lote = codigos[inicio:inicio + 500]
            cursor.execute(
                "SELECT PRODUTO, VALORMINIMO FROM ESTOQUE "
                "WHERE FILIAL = 4 AND PRODUTO IN ("
                + ",".join("?" for _ in lote) + ")",
                lote,
            )
            custos.extend(cursor.fetchall())
    finally:
        cursor.close()
        con.close()
    custo_produto = pd.DataFrame(
        custos, columns=["produto_codigo", "valor_minimo_4"]
    ).drop_duplicates("produto_codigo")
    resultado = ranking.merge(custo_produto, on="produto_codigo", how="left")
    resultado["produto_codigo"] = pd.to_numeric(
        resultado["produto_codigo"], errors="coerce"
    ).astype("Int64")
    for coluna in ("quantidade_vendida", "valor_medio_venda", "valor_minimo_4"):
        resultado[coluna] = pd.to_numeric(resultado[coluna], errors="coerce")
    return resultado


def subtrair_meses(data: date, meses: int) -> date:
    """Retorna a mesma referência em meses anteriores, ajustando o fim do mês."""
    indice = data.year * 12 + data.month - 1 - meses
    ano, mes_zero = divmod(indice, 12)
    mes = mes_zero + 1
    return date(ano, mes, min(data.day, monthrange(ano, mes)[1]))


def consultar_pagamentos_mais_usados(
    data_inicio: date, data_fim: date
) -> pd.DataFrame:
    """Retorna condição e forma mais usadas por cliente em pedidos do período."""
    if data_inicio > data_fim:
        raise ValueError("A data inicial deve ser anterior ou igual à data final.")
    from google.cloud import bigquery

    sql = """
WITH pedidos AS (
  SELECT
    CAST(v.cliente_codigo AS INT64) AS cliente_codigo,
    ANY_VALUE(c.cliente_nome) AS cliente_nome,
    CAST(v.pedido_id AS STRING) AS pedido_id,
    DATE(v.pedido_data_emissao) AS data_emissao,
    CAST(v.pedido_filial AS INT64) AS filial_codigo,
    CAST(v.pedido_condicao_pagamento AS INT64) AS condicao_codigo,
    CAST(v.pedido_cod_fp AS INT64) AS forma_codigo,
    ANY_VALUE(NULLIF(TRIM(v.pedido_forma_pagamento), '')) AS forma_pedido_nome
  FROM `dinho-dw.topsystem_silver.vendas` v
  LEFT JOIN `dinho-dw.topsystem_silver.cliente` c
    ON c.cliente_codigo = v.cliente_codigo
  WHERE DATE(v.pedido_data_emissao) BETWEEN @data_inicio AND @data_fim
    AND v.cliente_codigo IS NOT NULL
    AND v.pedido_id IS NOT NULL
    AND COALESCE(TRIM(v.tipo_pedido), '') <> '48'
  GROUP BY 1, 3, 4, 5, 6, 7
),
condicoes AS (
  SELECT
    CAST(codigo AS INT64) AS codigo,
    ANY_VALUE(nome) AS nome
  FROM `dinho-dw.topsystem_bronze.condicaopagamento`
  GROUP BY 1
),
formas AS (
  SELECT
    CAST(codigo AS INT64) AS codigo,
    CAST(filial AS INT64) AS filial,
    ANY_VALUE(nome) AS nome
  FROM `dinho-dw.topsystem_bronze.formapagamento`
  GROUP BY 1, 2
),
uso_condicao AS (
  SELECT
    p.cliente_codigo,
    p.condicao_codigo,
    ANY_VALUE(cp.nome HAVING MAX p.data_emissao) AS condicao_nome,
    COUNT(DISTINCT p.pedido_id) AS pedidos_condicao,
    MAX(p.data_emissao) AS ultimo_uso_condicao
  FROM pedidos p
  LEFT JOIN condicoes cp
    ON cp.codigo = p.condicao_codigo
  WHERE p.condicao_codigo IS NOT NULL
  GROUP BY 1, 2
),
condicao_rank AS (
  SELECT *, ROW_NUMBER() OVER (
    PARTITION BY cliente_codigo
    ORDER BY pedidos_condicao DESC, ultimo_uso_condicao DESC, condicao_codigo
  ) AS posicao
  FROM uso_condicao
),
uso_forma AS (
  SELECT
    p.cliente_codigo,
    p.forma_codigo,
    ARRAY_AGG(
      COALESCE(fp.nome, p.forma_pedido_nome) IGNORE NULLS
      ORDER BY p.data_emissao DESC LIMIT 1
    )[SAFE_OFFSET(0)] AS forma_nome,
    COUNT(DISTINCT p.pedido_id) AS pedidos_forma,
    MAX(p.data_emissao) AS ultimo_uso_forma
  FROM pedidos p
  LEFT JOIN formas fp
    ON fp.codigo = p.forma_codigo AND fp.filial = p.filial_codigo
  WHERE p.forma_codigo IS NOT NULL
  GROUP BY 1, 2
),
forma_rank AS (
  SELECT *, ROW_NUMBER() OVER (
    PARTITION BY cliente_codigo
    ORDER BY pedidos_forma DESC, ultimo_uso_forma DESC, forma_codigo
  ) AS posicao
  FROM uso_forma
),
clientes_periodo AS (
  SELECT
    cliente_codigo,
    ANY_VALUE(cliente_nome) AS cliente_nome,
    COUNT(DISTINCT pedido_id) AS pedidos_periodo,
    MAX(data_emissao) AS ultima_compra
  FROM pedidos
  GROUP BY 1
)
SELECT
  c.cliente_codigo,
  c.cliente_nome,
  cr.condicao_codigo,
  cr.condicao_nome,
  fr.forma_codigo,
  fr.forma_nome,
  c.pedidos_periodo,
  cr.pedidos_condicao,
  fr.pedidos_forma,
  c.ultima_compra
FROM clientes_periodo c
LEFT JOIN condicao_rank cr
  ON cr.cliente_codigo = c.cliente_codigo AND cr.posicao = 1
LEFT JOIN forma_rank fr
  ON fr.cliente_codigo = c.cliente_codigo AND fr.posicao = 1
ORDER BY c.cliente_codigo
"""
    parametros = [
        bigquery.ScalarQueryParameter("data_inicio", "DATE", data_inicio),
        bigquery.ScalarQueryParameter("data_fim", "DATE", data_fim),
    ]
    resultado = cliente_bigquery().query(
        sql, job_config=bigquery.QueryJobConfig(query_parameters=parametros)
    ).to_dataframe()
    for coluna in (
        "cliente_codigo", "condicao_codigo", "forma_codigo", "pedidos_periodo",
        "pedidos_condicao", "pedidos_forma",
    ):
        if coluna in resultado:
            resultado[coluna] = pd.to_numeric(
                resultado[coluna], errors="coerce"
            ).astype("Int64")
    if "ultima_compra" in resultado:
        resultado["ultima_compra"] = pd.to_datetime(
            resultado["ultima_compra"], errors="coerce"
        )
    return resultado


COLUNAS_ATUALIZACAO_PAGAMENTOS = [
    "cliente_codigo", "cliente_nome", "condicao_atual_codigo",
    "condicao_nova_codigo", "condicao_nova_nome", "forma_atual_codigo",
    "forma_nova_codigo", "forma_nova_nome", "atualizacao_necessaria",
]


def consultar_protecoes_pagamentos(clientes: Iterable[int]) -> pd.DataFrame:
    """Identifica clientes que nenhuma ação deste fluxo pode alterar."""
    clientes_unicos = sorted(set(int(item) for item in clientes))
    colunas = [
        "cliente_codigo", "cliente_nome", "vendedor_187_1929", "tabela_480",
    ]
    if not clientes_unicos:
        return pd.DataFrame(columns=colunas)
    linhas: list[dict] = []
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        for inicio in range(0, len(clientes_unicos), 500):
            lote = clientes_unicos[inicio:inicio + 500]
            marcadores = ",".join("?" for _ in lote)
            cursor.execute(
                "SELECT c.CODIGO, c.NOME, "
                "CASE WHEN EXISTS (SELECT 1 FROM FUNCIONARIOCLIFOR fc "
                "WHERE fc.CLIFOR = c.CODIGO AND fc.FUNCIONARIO IN (187, 1929)) "
                "THEN 1 ELSE 0 END, "
                "CASE WHEN EXISTS (SELECT 1 FROM CLIFORTABELAPRECO ctp "
                "WHERE ctp.CLIFOR = c.CODIGO AND ctp.TABELAPRECO = 480) "
                "THEN 1 ELSE 0 END "
                "FROM CLIFOR c WHERE c.TIPO = 1 AND c.CODIGO IN (" + marcadores + ")",
                lote,
            )
            for codigo, nome, vendedor, tabela in cursor.fetchall():
                if vendedor or tabela:
                    linhas.append({
                        "cliente_codigo": int(codigo),
                        "cliente_nome": nome,
                        "vendedor_187_1929": bool(vendedor),
                        "tabela_480": bool(tabela),
                    })
    finally:
        cursor.close()
        con.close()
    return pd.DataFrame(linhas, columns=colunas).sort_values(
        "cliente_codigo", ignore_index=True
    )


def consultar_clientes_nao_localizados_pagamentos(
    resultado: pd.DataFrame,
) -> pd.DataFrame:
    """Classifica códigos do histórico que não são clientes TIPO = 1."""
    if "cliente_codigo" not in resultado.columns:
        raise ValueError("O resultado não contém os códigos dos clientes.")
    base = resultado.dropna(subset=["cliente_codigo"]).copy()
    base["cliente_codigo"] = base["cliente_codigo"].astype(int)
    base = base.drop_duplicates("cliente_codigo")
    clientes = sorted(base["cliente_codigo"].tolist())
    tipos: dict[int, int] = {}
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        for inicio in range(0, len(clientes), 500):
            lote = clientes[inicio:inicio + 500]
            cursor.execute(
                "SELECT CODIGO, TIPO FROM CLIFOR WHERE CODIGO IN ("
                + ",".join("?" for _ in lote) + ")",
                lote,
            )
            for codigo, tipo in cursor.fetchall():
                codigo = int(codigo)
                tipo = int(tipo)
                if codigo not in tipos or tipo == 1:
                    tipos[codigo] = tipo
    finally:
        cursor.close()
        con.close()
    colunas = ["cliente_codigo", "cliente_nome", "tipo_clifor", "classificacao"]
    if "cliente_nome" not in base.columns:
        base["cliente_nome"] = ""
    base["tipo_clifor"] = base["cliente_codigo"].map(tipos).astype("Int64")
    base["classificacao"] = base["tipo_clifor"].map({1: "Cliente", 2: "Fornecedor"})
    base["classificacao"] = base["classificacao"].fillna("Não localizado no CLIFOR")
    outros_tipos = base["tipo_clifor"].notna() & ~base["tipo_clifor"].isin([1, 2])
    base.loc[outros_tipos, "classificacao"] = (
        "Outro tipo CLIFOR (" + base.loc[outros_tipos, "tipo_clifor"].astype(str) + ")"
    )
    return base.loc[base["tipo_clifor"].ne(1).fillna(True), colunas].sort_values(
        "cliente_codigo", ignore_index=True
    )


def planejar_bloqueio_condicoes_cliente(cliente: int) -> pd.DataFrame:
    """Detalha cada bloqueio que seria preservado ou inserido para um cliente."""
    cliente = int(cliente)
    colunas = [
        "cliente_codigo", "cliente_nome", "tipo_estabelecimento", "regra",
        "condicao_codigo", "condicao_nome", "situacao",
    ]
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        if cliente in _codigos_protegidos_pagamentos(con, [cliente]):
            raise ValueError(
                "Cliente protegido por vínculo com o vendedor 1929 ou 187 — Atacado."
            )
        cadastros, _, _, _ = _dados_bloqueios_pagamentos(con, [cliente])
        cadastro = cadastros.get(cliente)
        if cadastro is None:
            raise ValueError("Código não localizado como cliente CLIFOR TIPO = 1.")
        regra = _classificar_regra_bloqueio(cadastro[2], cadastro[3])
        if not regra:
            raise ValueError("Cliente não se enquadra em nenhuma regra de bloqueio.")
        cursor.execute("SELECT CODIGO, NOME, ATIVO FROM CONDICAOPAGAMENTO")
        catalogo = [
            (int(codigo), str(nome or ""), str(ativo or "").strip().upper() == "S")
            for codigo, nome, ativo in cursor.fetchall()
        ]
        condicoes = [
            codigo for codigo, nome, _ in catalogo
            if codigo != CONDICAO_PAGAMENTO_A_VISTA_PROTEGIDA
            and ("PRZ" in nome.upper()) == regra.startswith("Key Off")
            and not (
                regra.startswith(("Multicanal", "Key On/On Trade"))
                and _nome_condicao_a_vista(nome)
            )
        ]
        if not condicoes:
            return pd.DataFrame(columns=colunas)
        nomes = {codigo: nome for codigo, nome, _ in catalogo}
        ativas = {codigo for codigo, _, ativa in catalogo if ativa}
        cursor.execute(
            "SELECT CONDICAOPAGAMENTO FROM CLIFORCONDICAOPAGAMENTO WHERE CLIFOR = ? "
            "AND CONDICAOPAGAMENTO IN (" + ",".join("?" for _ in condicoes) + ")",
            [cliente] + condicoes,
        )
        existentes = {int(item[0]) for item in cursor.fetchall()}
        linhas = [{
            "cliente_codigo": cliente,
            "cliente_nome": cadastro[1],
            "tipo_estabelecimento": cadastro[3],
            "regra": regra,
            "condicao_codigo": condicao,
            "condicao_nome": nomes.get(condicao, ""),
            "situacao": (
                "Inativa — não inserir" if condicao not in ativas
                else "Já existe — preservar" if condicao in existentes
                else "Inserir"
            ),
        } for condicao in sorted(condicoes)]
        return pd.DataFrame(linhas, columns=colunas)
    finally:
        cursor.close()
        con.close()


def _codigos_protegidos_pagamentos(con, clientes: Iterable[int]) -> set[int]:
    """Revalida a proteção dos vendedores na transação da gravação."""
    clientes_unicos = sorted(set(int(item) for item in clientes))
    protegidos: set[int] = set()
    cursor = con.cursor()
    try:
        for inicio in range(0, len(clientes_unicos), 500):
            lote = clientes_unicos[inicio:inicio + 500]
            marcadores = ",".join("?" for _ in lote)
            cursor.execute(
                "SELECT c.CODIGO FROM CLIFOR c WHERE c.CODIGO IN (" + marcadores + ") "
                "AND EXISTS (SELECT 1 FROM FUNCIONARIOCLIFOR fc WHERE "
                "fc.CLIFOR = c.CODIGO AND fc.FUNCIONARIO IN (187, 1929))",
                lote,
            )
            protegidos.update(int(item[0]) for item in cursor.fetchall())
    finally:
        cursor.close()
    return protegidos


def planejar_atualizacao_pagamentos(
    resultado: pd.DataFrame,
    progresso: Callable[[int, int], None] | None = None,
) -> pd.DataFrame:
    """Compara os padrões atuais do CLIFOR com os mais usados calculados."""
    obrigatorias = {
        "cliente_codigo", "cliente_nome", "condicao_codigo", "condicao_nome",
        "forma_codigo", "forma_nome",
    }
    ausentes = obrigatorias - set(resultado.columns)
    if ausentes:
        raise ValueError(
            "Resultado sem colunas obrigatórias: " + ", ".join(sorted(ausentes))
        )
    desejados = resultado.dropna(
        subset=["cliente_codigo", "condicao_codigo", "forma_codigo"]
    ).drop_duplicates("cliente_codigo")
    if desejados.empty:
        return pd.DataFrame(columns=COLUNAS_ATUALIZACAO_PAGAMENTOS)

    codigos = desejados["cliente_codigo"].astype(int).tolist()
    atuais: list[tuple] = []
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        protegidos = _codigos_protegidos_pagamentos(con, codigos)
        codigos = [codigo for codigo in codigos if codigo not in protegidos]
        for inicio in range(0, len(codigos), 500):
            lote = codigos[inicio:inicio + 500]
            cursor.execute(
                "SELECT CODIGO, CONDICAOPAGAMENTO, FORMAPAGAMENTO FROM CLIFOR "
                "WHERE TIPO = 1 AND CODIGO IN ("
                + ",".join("?" for _ in lote) + ")",
                lote,
            )
            atuais.extend(cursor.fetchall())
            if progresso:
                progresso(min(inicio + len(lote), len(codigos)), len(codigos))
    finally:
        cursor.close()
        con.close()

    cadastro = pd.DataFrame(
        atuais,
        columns=[
            "cliente_codigo", "condicao_atual_codigo", "forma_atual_codigo",
        ],
    )
    plano = desejados[[
        "cliente_codigo", "cliente_nome", "condicao_codigo", "condicao_nome",
        "forma_codigo", "forma_nome",
    ]].rename(columns={
        "condicao_codigo": "condicao_nova_codigo",
        "condicao_nome": "condicao_nova_nome",
        "forma_codigo": "forma_nova_codigo",
        "forma_nome": "forma_nova_nome",
    }).merge(cadastro, on="cliente_codigo", how="inner")
    for coluna in (
        "cliente_codigo", "condicao_atual_codigo", "condicao_nova_codigo",
        "forma_atual_codigo", "forma_nova_codigo",
    ):
        plano[coluna] = pd.to_numeric(plano[coluna], errors="coerce").astype("Int64")
    plano["atualizacao_necessaria"] = (
        plano["condicao_atual_codigo"].fillna(-1)
        .ne(plano["condicao_nova_codigo"].fillna(-1))
        | plano["forma_atual_codigo"].fillna(-1)
        .ne(plano["forma_nova_codigo"].fillna(-1))
    )
    return plano.reindex(columns=COLUNAS_ATUALIZACAO_PAGAMENTOS).sort_values(
        "cliente_codigo", ignore_index=True
    )


def aplicar_atualizacao_pagamentos(
    plano: pd.DataFrame,
    progresso: Callable[[int, int], None] | None = None,
) -> dict[str, int]:
    """Revalida e atualiza os padrões de pagamento em uma única transação."""
    obrigatorias = {
        "cliente_codigo", "condicao_nova_codigo", "forma_nova_codigo",
    }
    if plano.empty or not obrigatorias.issubset(plano.columns):
        raise ValueError("Não há clientes válidos para atualizar.")
    desejados = plano.dropna(subset=list(obrigatorias)).drop_duplicates(
        "cliente_codigo"
    )
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    alterados = 0
    sem_alteracao = 0
    try:
        protegidos = _codigos_protegidos_pagamentos(
            con, desejados["cliente_codigo"].astype(int).tolist()
        )
        total = len(desejados)
        for posicao, item in enumerate(desejados.itertuples(index=False), start=1):
            cliente = int(item.cliente_codigo)
            if cliente in protegidos:
                if progresso and (posicao % 100 == 0 or posicao == total):
                    progresso(posicao, total)
                continue
            condicao = int(item.condicao_nova_codigo)
            forma = int(item.forma_nova_codigo)
            cursor.execute(
                "SELECT CONDICAOPAGAMENTO, FORMAPAGAMENTO FROM CLIFOR "
                "WHERE CODIGO = ? AND TIPO = 1",
                [cliente],
            )
            atual = cursor.fetchone()
            if atual is None:
                if progresso and (posicao % 100 == 0 or posicao == total):
                    progresso(posicao, total)
                continue
            if atual[0] == condicao and atual[1] == forma:
                sem_alteracao += 1
                if progresso and (posicao % 100 == 0 or posicao == total):
                    progresso(posicao, total)
                continue
            cursor.execute(
                "UPDATE CLIFOR SET CONDICAOPAGAMENTO = ?, FORMAPAGAMENTO = ? "
                "WHERE CODIGO = ? AND TIPO = 1",
                [condicao, forma, cliente],
            )
            alterados += 1
            if progresso and (posicao % 100 == 0 or posicao == total):
                progresso(posicao, total)
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        cursor.close()
        con.close()
    return {
        "clientes": len(desejados),
        "alterados": alterados,
        "sem_alteracao": sem_alteracao,
        "protegidos": len(protegidos),
    }


def _classificar_regra_bloqueio(cnpj: object, tipo: object) -> str | None:
    documento = "".join(caractere for caractere in str(cnpj or "") if caractere.isdigit())
    try:
        tipo_codigo = int(tipo)
    except (TypeError, ValueError):
        tipo_codigo = None
    if tipo_codigo in TIPOS_ESTABELECIMENTO_KEY_OFF:
        return "Key Off — bloquear condições com PRZ"
    if tipo_codigo in TIPOS_ESTABELECIMENTO_SEM_BLOQUEIO_SEM_PRZ:
        return None
    if len(documento) == 11:
        return "CPF — bloquear condições sem PRZ"
    if tipo_codigo in TIPOS_ESTABELECIMENTO_MULTICANAL:
        return "Multicanal — bloquear condições sem PRZ"
    if tipo_codigo in TIPOS_ESTABELECIMENTO_KEY_ON:
        return "Key On/On Trade — bloquear condições sem PRZ"
    return None


def _nome_condicao_a_vista(nome: object) -> bool:
    normalizado = unicodedata.normalize("NFKD", str(nome or ""))
    normalizado = "".join(
        caractere for caractere in normalizado if not unicodedata.combining(caractere)
    ).upper()
    return "A VISTA" in normalizado


def _condicoes_por_regra(
    regra: str, com_prz: list[int], sem_prz: list[int], a_vista: set[int]
) -> list[int]:
    if regra.startswith("Key Off"):
        return com_prz
    if regra.startswith(("Multicanal", "Key On/On Trade")):
        return [codigo for codigo in sem_prz if codigo not in a_vista]
    return sem_prz


def _dados_bloqueios_pagamentos(
    con, clientes: list[int]
) -> tuple[dict, list[int], list[int], set[int]]:
    cursor = con.cursor()
    try:
        cursor.execute(
            "SELECT CODIGO, NOME FROM CONDICAOPAGAMENTO "
            "WHERE COALESCE(ATIVO, 'N') = 'S'"
        )
        condicoes = [
            (int(codigo), str(nome or ""))
            for codigo, nome in cursor.fetchall()
            if int(codigo) != CONDICAO_PAGAMENTO_A_VISTA_PROTEGIDA
        ]
        com_prz = [codigo for codigo, nome in condicoes if "PRZ" in nome.upper()]
        sem_prz = [codigo for codigo, nome in condicoes if "PRZ" not in nome.upper()]
        a_vista = {codigo for codigo, nome in condicoes if _nome_condicao_a_vista(nome)}
        cadastros: dict[int, tuple] = {}
        for inicio in range(0, len(clientes), 500):
            lote = clientes[inicio:inicio + 500]
            cursor.execute(
                "SELECT CODIGO, NOME, CNPJ, TIPOESTABELECIMENTO FROM CLIFOR "
                "WHERE TIPO = 1 AND CODIGO IN ("
                + ",".join("?" for _ in lote) + ")",
                lote,
            )
            cadastros.update({int(item[0]): item for item in cursor.fetchall()})
        return cadastros, com_prz, sem_prz, a_vista
    finally:
        cursor.close()


def planejar_bloqueios_condicoes_inativas(resultado: pd.DataFrame) -> pd.DataFrame:
    """Lista bloqueios ausentes que seriam candidatos, mas cuja condição está inativa."""
    clientes = sorted(resultado["cliente_codigo"].dropna().astype(int).unique())
    colunas = [
        "regra", "condicao_codigo", "condicao_nome", "status_condicao",
        "clientes_afetados", "registros_nao_inseridos", "acao",
    ]
    if not clientes:
        return pd.DataFrame(columns=colunas)
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        protegidos = _codigos_protegidos_pagamentos(con, clientes)
        clientes = [codigo for codigo in clientes if codigo not in protegidos]
        cadastros, _, _, _ = _dados_bloqueios_pagamentos(con, clientes)
        cursor.execute(
            "SELECT CODIGO, NOME FROM CONDICAOPAGAMENTO "
            "WHERE COALESCE(ATIVO, 'N') <> 'S'"
        )
        inativas = [(int(codigo), str(nome or "")) for codigo, nome in cursor.fetchall()]
        resumo: dict[tuple[str, int, str], set[int]] = {}
        for inicio in range(0, len(clientes), 250):
            lote = clientes[inicio:inicio + 250]
            candidatos: list[tuple[int, tuple, str, int, str]] = []
            for cliente in lote:
                cadastro = cadastros.get(cliente)
                if not cadastro:
                    continue
                regra = _classificar_regra_bloqueio(cadastro[2], cadastro[3])
                if not regra:
                    continue
                exige_prz = regra.startswith("Key Off")
                candidatos.extend(
                    (cliente, cadastro, regra, codigo, nome)
                    for codigo, nome in inativas
                    if codigo != CONDICAO_PAGAMENTO_A_VISTA_PROTEGIDA
                    and ("PRZ" in nome.upper()) == exige_prz
                    and not (
                        regra.startswith(("Multicanal", "Key On/On Trade"))
                        and _nome_condicao_a_vista(nome)
                    )
                )
            if not candidatos:
                continue
            pares = {(cliente, condicao) for cliente, _, _, condicao, _ in candidatos}
            clientes_sql = sorted({cliente for cliente, _ in pares})
            condicoes_sql = sorted({condicao for _, condicao in pares})
            cursor.execute(
                "SELECT CLIFOR, CONDICAOPAGAMENTO FROM CLIFORCONDICAOPAGAMENTO "
                "WHERE CLIFOR IN (" + ",".join("?" for _ in clientes_sql) + ") "
                "AND CONDICAOPAGAMENTO IN (" + ",".join("?" for _ in condicoes_sql) + ")",
                clientes_sql + condicoes_sql,
            )
            existentes = {(int(a), int(b)) for a, b in cursor.fetchall()}
            for cliente, cadastro, regra, condicao, nome in candidatos:
                if (cliente, condicao) not in existentes:
                    resumo.setdefault((regra, condicao, nome), set()).add(cliente)
        linhas = [{
            "regra": regra,
            "condicao_codigo": condicao,
            "condicao_nome": nome,
            "status_condicao": "Inativa",
            "clientes_afetados": len(clientes_afetados),
            "registros_nao_inseridos": len(clientes_afetados),
            "acao": "Não inserir",
        } for (regra, condicao, nome), clientes_afetados in resumo.items()]
        return pd.DataFrame(linhas, columns=colunas).sort_values(
            ["regra", "condicao_codigo"], ignore_index=True
        )
    finally:
        cursor.close()
        con.close()


def resumir_protecao_condicao_100(resultado: pd.DataFrame) -> pd.DataFrame:
    """Quantifica os bloqueios evitados pela proteção global da condição 100."""
    colunas = [
        "regra", "clientes_enquadrados", "bloqueios_existentes_preservados",
        "bloqueios_novos_evitados",
    ]
    if "cliente_codigo" not in resultado.columns:
        raise ValueError("O resultado não contém os códigos dos clientes.")
    clientes = sorted(resultado["cliente_codigo"].dropna().astype(int).unique())
    if not clientes:
        return pd.DataFrame(columns=colunas)
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        protegidos = _codigos_protegidos_pagamentos(con, clientes)
        clientes = [codigo for codigo in clientes if codigo not in protegidos]
        cadastros, _, _, _ = _dados_bloqueios_pagamentos(con, clientes)
        cursor.execute(
            "SELECT NOME, COALESCE(ATIVO, 'N') FROM CONDICAOPAGAMENTO "
            "WHERE CODIGO = ?",
            [CONDICAO_PAGAMENTO_A_VISTA_PROTEGIDA],
        )
        cadastro_condicao = cursor.fetchone()
        if not cadastro_condicao or str(cadastro_condicao[1]).strip().upper() != "S":
            return pd.DataFrame(columns=colunas)
        nome = str(cadastro_condicao[0] or "")
        com_prz = "PRZ" in nome.upper()
        a_vista = _nome_condicao_a_vista(nome)
        elegiveis: dict[str, set[int]] = {}
        for cliente in clientes:
            cadastro = cadastros.get(cliente)
            if not cadastro:
                continue
            regra = _classificar_regra_bloqueio(cadastro[2], cadastro[3])
            if not regra:
                continue
            seria_bloqueada = (
                com_prz if regra.startswith("Key Off")
                else not com_prz and not (
                    regra.startswith(("Multicanal", "Key On/On Trade"))
                    and a_vista
                )
            )
            if seria_bloqueada:
                elegiveis.setdefault(regra, set()).add(cliente)
        todos_elegiveis = sorted(set().union(*elegiveis.values())) if elegiveis else []
        existentes: set[int] = set()
        for inicio in range(0, len(todos_elegiveis), 500):
            lote = todos_elegiveis[inicio:inicio + 500]
            cursor.execute(
                "SELECT CLIFOR FROM CLIFORCONDICAOPAGAMENTO WHERE "
                "CONDICAOPAGAMENTO = ? AND CLIFOR IN ("
                + ",".join("?" for _ in lote) + ")",
                [CONDICAO_PAGAMENTO_A_VISTA_PROTEGIDA] + lote,
            )
            existentes.update(int(item[0]) for item in cursor.fetchall())
        linhas = []
        for regra, codigos in sorted(elegiveis.items()):
            preservados = len(codigos & existentes)
            linhas.append({
                "regra": regra,
                "clientes_enquadrados": len(codigos),
                "bloqueios_existentes_preservados": preservados,
                "bloqueios_novos_evitados": len(codigos) - preservados,
            })
        return pd.DataFrame(linhas, columns=colunas)
    finally:
        cursor.close()
        con.close()


DESCRICOES_REGRAS_BLOQUEIOS = {
    "CPF — bloquear condições sem PRZ": (
        "Cliente com documento CPF: bloquear condições ativas cujo nome não "
        "contém PRZ, exceto nos tipos protegidos pela regra 7 e a condição 100."
    ),
    "Multicanal — bloquear condições sem PRZ": (
        "Cliente Multicanal: bloquear condições ativas cujo nome não contém PRZ, "
        "exceto nos tipos protegidos pela regra 7 e condições à vista; a condição "
        "100 é protegida globalmente."
    ),
    "Key On/On Trade — bloquear condições sem PRZ": (
        "Cliente Key On/On Trade: bloquear condições ativas cujo nome não contém "
        "PRZ, exceto condições à vista; a condição 100 é protegida globalmente."
    ),
    "Key Off — bloquear condições com PRZ": (
        "Cliente Key Off dos tipos 35 ou 38: bloquear condições ativas cujo nome "
        "contém PRZ, exceto a condição 100."
    ),
}


def gerar_documentacao_bloqueios_zip(
    resultado: pd.DataFrame,
    progresso: Callable[[int, int], None] | None = None,
) -> tuple[bytes, int]:
    """Gera ZIP documental dos bloqueios elegíveis, sem realizar gravações."""
    clientes = sorted(resultado["cliente_codigo"].dropna().astype(int).unique())
    arquivo = io.BytesIO()
    total_registros = 0
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        protegidos = _codigos_protegidos_pagamentos(con, clientes)
        clientes = [codigo for codigo in clientes if codigo not in protegidos]
        cadastros, com_prz, sem_prz, a_vista = _dados_bloqueios_pagamentos(
            con, clientes
        )
        cursor.execute(
            "SELECT CODIGO, NOME FROM CONDICAOPAGAMENTO "
            "WHERE COALESCE(ATIVO, 'N') = 'S'"
        )
        nomes_condicoes = {
            int(codigo): str(nome or "") for codigo, nome in cursor.fetchall()
        }
        with zipfile.ZipFile(
            arquivo, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as compactado:
            with compactado.open("bloqueios_a_inserir.csv", "w") as binario:
                texto = io.TextIOWrapper(binario, encoding="utf-8-sig", newline="")
                escritor = csv.writer(texto, delimiter=";")
                escritor.writerow([
                    "cliente_codigo", "cliente_nome", "tipo_estabelecimento",
                    "regra_aplicada", "descricao_regra", "condicao_codigo",
                    "condicao_nome", "status_condicao", "acao",
                ])
                for inicio in range(0, len(clientes), 250):
                    lote = clientes[inicio:inicio + 250]
                    candidatos: dict[int, tuple[tuple, str, list[int]]] = {}
                    pares: set[tuple[int, int]] = set()
                    for cliente in lote:
                        cadastro = cadastros.get(cliente)
                        if not cadastro:
                            continue
                        regra = _classificar_regra_bloqueio(cadastro[2], cadastro[3])
                        if not regra:
                            continue
                        condicoes = _condicoes_por_regra(
                            regra, com_prz, sem_prz, a_vista
                        )
                        candidatos[cliente] = (cadastro, regra, condicoes)
                        pares.update((cliente, condicao) for condicao in condicoes)
                    existentes: set[tuple[int, int]] = set()
                    if pares:
                        clientes_sql = sorted({cliente for cliente, _ in pares})
                        condicoes_sql = sorted({condicao for _, condicao in pares})
                        cursor.execute(
                            "SELECT CLIFOR, CONDICAOPAGAMENTO FROM "
                            "CLIFORCONDICAOPAGAMENTO WHERE CLIFOR IN ("
                            + ",".join("?" for _ in clientes_sql) + ") AND "
                            "CONDICAOPAGAMENTO IN ("
                            + ",".join("?" for _ in condicoes_sql) + ")",
                            clientes_sql + condicoes_sql,
                        )
                        existentes = {(int(a), int(b)) for a, b in cursor.fetchall()}
                    for cliente, (cadastro, regra, condicoes) in candidatos.items():
                        for condicao in condicoes:
                            if (cliente, condicao) in existentes:
                                continue
                            escritor.writerow([
                                cliente, cadastro[1], cadastro[3], regra,
                                DESCRICOES_REGRAS_BLOQUEIOS.get(regra, ""),
                                condicao, nomes_condicoes.get(condicao, ""),
                                "Ativa", "Inserir bloqueio",
                            ])
                            total_registros += 1
                    if progresso:
                        progresso(min(inicio + len(lote), len(clientes)), len(clientes))
                texto.flush()
                texto.detach()
            regras = (
                "DOCUMENTAÇÃO DOS BLOQUEIOS DE CONDIÇÕES DE PAGAMENTO\n\n"
                + "\n".join(
                    f"- {regra}: {descricao}"
                    for regra, descricao in DESCRICOES_REGRAS_BLOQUEIOS.items()
                )
                + "\n\nEXCLUSÕES DE SEGURANÇA\n"
                "- Bloqueios já existentes são preservados e não aparecem no CSV.\n"
                "- Condições inativas não aparecem no CSV e nunca são inseridas.\n"
                "- Clientes dos vendedores 1929 ou 187 — Atacado não aparecem no CSV.\n"
                "- Condições sem PRZ não são bloqueadas nos tipos 40, 49, 36, "
                "34, 47, 35, 38, 33 e 39.\n"
                "- Condições à vista não são bloqueadas para Multicanal e "
                "Key On/On Trade.\n"
                "- A condição 100 (A VISTA) não é bloqueada para nenhum cliente.\n"
                "- A tabela de preço 480 e seus vínculos não são alterados.\n"
                f"\nTOTAL DE REGISTROS DOCUMENTADOS: {total_registros}\n"
            )
            compactado.writestr("descricao_das_regras.txt", regras.encode("utf-8-sig"))
    finally:
        cursor.close()
        con.close()
    return arquivo.getvalue(), total_registros


def planejar_bloqueios_condicoes(
    resultado: pd.DataFrame,
    progresso: Callable[[int, int], None] | None = None,
) -> pd.DataFrame:
    """Conta bloqueios ausentes sem remover os que já existem no CLIFOR."""
    if "cliente_codigo" not in resultado:
        raise ValueError("O resultado não contém os códigos dos clientes.")
    clientes = sorted(resultado["cliente_codigo"].dropna().astype(int).unique())
    if not clientes:
        return pd.DataFrame()
    con = cliente_firebird("WIN1252")
    try:
        protegidos = _codigos_protegidos_pagamentos(con, clientes)
        clientes = [cliente for cliente in clientes if cliente not in protegidos]
        cadastros, com_prz, sem_prz, a_vista = _dados_bloqueios_pagamentos(
            con, clientes
        )
        linhas = []
        cursor = con.cursor()
        try:
            for inicio in range(0, len(clientes), 250):
                lote = clientes[inicio:inicio + 250]
                candidatos: dict[int, tuple[str, list[int], tuple]] = {}
                condicoes_lote: set[int] = set()
                for cliente in lote:
                    cadastro = cadastros.get(cliente)
                    if not cadastro:
                        continue
                    regra = _classificar_regra_bloqueio(cadastro[2], cadastro[3])
                    if not regra:
                        continue
                    condicoes = _condicoes_por_regra(
                        regra, com_prz, sem_prz, a_vista
                    )
                    candidatos[cliente] = (regra, condicoes, cadastro)
                    condicoes_lote.update(condicoes)
                existentes: set[tuple[int, int]] = set()
                if candidatos and condicoes_lote:
                    clientes_sql = list(candidatos)
                    condicoes_sql = sorted(condicoes_lote)
                    cursor.execute(
                        "SELECT CLIFOR, CONDICAOPAGAMENTO FROM CLIFORCONDICAOPAGAMENTO "
                        "WHERE CLIFOR IN (" + ",".join("?" for _ in clientes_sql)
                        + ") AND CONDICAOPAGAMENTO IN ("
                        + ",".join("?" for _ in condicoes_sql) + ")",
                        clientes_sql + condicoes_sql,
                    )
                    existentes = {(int(a), int(b)) for a, b in cursor.fetchall()}
                for cliente, (regra, condicoes, cadastro) in candidatos.items():
                    quantidade_existente = sum(
                        (cliente, condicao) in existentes for condicao in condicoes
                    )
                    linhas.append({
                        "cliente_codigo": cliente,
                        "cliente_nome": cadastro[1],
                        "tipo_estabelecimento": cadastro[3],
                        "regra": regra,
                        "bloqueios_existentes": quantidade_existente,
                        "bloqueios_novos": len(condicoes) - quantidade_existente,
                    })
                if progresso:
                    progresso(min(inicio + len(lote), len(clientes)), len(clientes))
        finally:
            cursor.close()
    finally:
        con.close()
    return pd.DataFrame(linhas, columns=[
        "cliente_codigo", "cliente_nome", "tipo_estabelecimento", "regra",
        "bloqueios_existentes", "bloqueios_novos",
    ]).sort_values("cliente_codigo", ignore_index=True)


def aplicar_bloqueios_condicoes(
    clientes: Iterable[int],
    progresso: Callable[[int, int], None] | None = None,
) -> dict[str, int]:
    """Insere apenas bloqueios ausentes, preservando todos os existentes."""
    clientes_unicos = sorted(set(int(item) for item in clientes))
    if not clientes_unicos:
        raise ValueError("Não há clientes válidos para bloquear.")
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    inseridos = 0
    classificados = 0
    try:
        protegidos = _codigos_protegidos_pagamentos(con, clientes_unicos)
        clientes_unicos = [
            cliente for cliente in clientes_unicos if cliente not in protegidos
        ]
        cadastros, com_prz, sem_prz, a_vista = _dados_bloqueios_pagamentos(
            con, clientes_unicos
        )
        for inicio in range(0, len(clientes_unicos), 250):
            lote = clientes_unicos[inicio:inicio + 250]
            candidatos: set[tuple[int, int]] = set()
            for cliente in lote:
                cadastro = cadastros.get(cliente)
                if not cadastro:
                    continue
                regra = _classificar_regra_bloqueio(cadastro[2], cadastro[3])
                if not regra:
                    continue
                classificados += 1
                condicoes = _condicoes_por_regra(
                    regra, com_prz, sem_prz, a_vista
                )
                candidatos.update((cliente, condicao) for condicao in condicoes)
            if not candidatos:
                continue
            clientes_sql = sorted({cliente for cliente, _ in candidatos})
            condicoes_sql = sorted({condicao for _, condicao in candidatos})
            cursor.execute(
                "SELECT CLIFOR, CONDICAOPAGAMENTO FROM CLIFORCONDICAOPAGAMENTO "
                "WHERE CLIFOR IN (" + ",".join("?" for _ in clientes_sql)
                + ") AND CONDICAOPAGAMENTO IN ("
                + ",".join("?" for _ in condicoes_sql) + ")",
                clientes_sql + condicoes_sql,
            )
            existentes = {(int(a), int(b)) for a, b in cursor.fetchall()}
            novos = sorted(candidatos - existentes)
            if novos:
                cursor.executemany(
                    "INSERT INTO CLIFORCONDICAOPAGAMENTO "
                    "(CLIFOR, CONDICAOPAGAMENTO, REPLICAR) VALUES (?, ?, ?)",
                    [(cliente, condicao, "N") for cliente, condicao in novos],
                )
            inseridos += len(novos)
            if progresso:
                progresso(
                    min(inicio + len(lote), len(clientes_unicos)),
                    len(clientes_unicos),
                )
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        cursor.close()
        con.close()
    return {
        "clientes_classificados": classificados,
        "bloqueios_inseridos": inseridos,
        "protegidos": len(protegidos),
    }


def adicionar_origem_analise(vendas: pd.DataFrame, televendas: pd.DataFrame) -> pd.DataFrame:
    """Marca a coorte de origem sem alterar as vendas usadas nos cálculos."""
    resultado = vendas.merge(televendas, on="cliente_codigo", how="left")
    resultado["cliente_base_televendas"] = resultado["televendas_ultima_compra"].notna()
    compra_industria = resultado["quantidade_vendedores_carteira"].fillna(0).gt(0)
    resultado["tipo_analise"] = "Compra indústria"
    resultado.loc[resultado["cliente_base_televendas"] & ~compra_industria, "tipo_analise"] = "Base televendas"
    resultado.loc[
        resultado["cliente_base_televendas"] & compra_industria, "tipo_analise"
    ] = "Indústria+televendas"
    return resultado


def indicadores_base_televendas(televendas: pd.DataFrame) -> dict[str, int]:
    return {
        "verde": int(televendas["cliente_codigo"].nunique()),
        "verde_sem_vendedor": int(televendas.loc[
            televendas["televendas_tem_vendedor"].eq(0), "cliente_codigo"
        ].nunique()),
        "verde_sem_rota": int(televendas.loc[
            televendas["televendas_tem_rota"].eq(0), "cliente_codigo"
        ].nunique()),
    }


def carregar_base(forcar: bool = False, hoje: date | None = None) -> tuple[pd.DataFrame, dict]:
    hoje = hoje or date.today()
    arquivo = _arquivo_cache(hoje)
    if arquivo.exists() and not forcar:
        with arquivo.open("rb") as entrada:
            cache = pickle.load(entrada)
        # A base é normalizada antes de ser gravada. Normalizá-la novamente aqui
        # cria uma cópia completa e vários vetores temporários, elevando muito o
        # pico de memória durante a leitura do cache diário.
        return cache["vendas"], {
            "origem": "BigQuery + Firebird — cache diário",
            "atualizado_em": datetime.fromtimestamp(arquivo.stat().st_mtime),
            "indicadores_televendas": cache["indicadores_televendas"],
        }

    televendas = consultar_base_televendas(hoje)
    df = adicionar_origem_analise(consultar_bigquery(hoje), televendas)
    indicadores = indicadores_base_televendas(televendas)
    temporario = arquivo.with_suffix(".tmp")
    with temporario.open("wb") as saida:
        pickle.dump(
            {"vendas": df, "indicadores_televendas": indicadores},
            saida,
            protocol=pickle.HIGHEST_PROTOCOL,
        )
    temporario.replace(arquivo)
    # Mantém poucos caches para recuperação e remove apenas arquivos deste painel.
    antigos = sorted(CACHE_DIR.glob(f"{CACHE_VERSION}_*.pkl"), reverse=True)[7:]
    for antigo in antigos:
        antigo.unlink(missing_ok=True)
    return df, {
        "origem": "BigQuery + Firebird",
        "atualizado_em": datetime.now(),
        "indicadores_televendas": indicadores,
    }


def filtrar(
    df: pd.DataFrame,
    industrias: list[str],
    equipes: list[int],
    estados: list[str] | None = None,
    tipos_estabelecimento: list[int] | None = None,
    situacao_carteira: str = "Todos",
) -> pd.DataFrame:
    resultado = df
    if industrias:
        resultado = resultado[resultado["industria"].isin(industrias)]
    if equipes:
        resultado = resultado[resultado["equipe_codigo"].isin(equipes)]
    if estados:
        resultado = resultado[resultado["cliente_estado"].isin(estados)]
    if tipos_estabelecimento:
        resultado = resultado[
            resultado["estabelecimento_tipo_codigo"].isin(tipos_estabelecimento)
        ]
    if situacao_carteira == "Com vendedor alocado":
        resultado = resultado[resultado["quantidade_vendedores_carteira"].gt(0)]
    elif situacao_carteira == "Sem vendedor alocado":
        resultado = resultado[resultado["quantidade_vendedores_carteira"].eq(0)]
    # Os filtros booleanos acima já materializam um novo DataFrame. Quando
    # nenhum filtro é informado, copiar toda a base apenas para leitura duplica
    # desnecessariamente o pico de memória.
    return resultado


def filtrar_carteira_por_origem(df: pd.DataFrame, filtro: str) -> pd.DataFrame:
    """Aplica carteira apenas à Compra indústria e preserva as origens Televendas."""
    if filtro == "Todos" or "tipo_analise" not in df.columns:
        return df
    dados_televendas = df["tipo_analise"].isin(
        ["Base televendas", "Indústria+televendas"]
    )
    dados_industria = df["tipo_analise"].eq("Compra indústria")
    if filtro == "Com vendedor alocado":
        mascara = dados_televendas | (
            dados_industria & df["quantidade_vendedores_carteira"].gt(0)
        )
        return df[mascara]
    if filtro == "Sem vendedor alocado":
        mascara = dados_televendas | (
            dados_industria & df["quantidade_vendedores_carteira"].eq(0)
        )
        return df[mascara]
    return df


def periodos_equivalentes(hoje: date) -> tuple[date, date, date, date]:
    atual_inicio = date(hoje.year, 1, 1)
    atual_fim = hoje
    anterior_inicio = date(hoje.year - 1, 1, 1)
    try:
        anterior_fim = hoje.replace(year=hoje.year - 1)
    except ValueError:
        anterior_fim = date(hoje.year - 1, 2, 28)
    return anterior_inicio, anterior_fim, atual_inicio, atual_fim


def comparar_volume(df: pd.DataFrame, datas: tuple[date, date, date, date]) -> pd.DataFrame:
    ai, af, bi, bf = map(pd.Timestamp, datas)
    base = df.assign(periodo=pd.NA)
    if "cliente_estado" not in base:
        base["cliente_estado"] = "NÃO IDENTIFICADO"
    if "estabelecimento_tipo_codigo" not in base:
        base["estabelecimento_tipo_codigo"] = 0
    if "estabelecimento_tipo_nome" not in base:
        base["estabelecimento_tipo_nome"] = "NÃO IDENTIFICADO"
    if "quantidade_vendedores_carteira" not in base:
        base["quantidade_vendedores_carteira"] = 0
    if "situacao_carteira" not in base:
        base["situacao_carteira"] = "SEM VENDEDOR ALOCADO"
    if "tipo_analise" not in base:
        base["tipo_analise"] = "Compra indústria"
    base.loc[base.data_venda.between(ai, af), "periodo"] = "ANTERIOR"
    base.loc[base.data_venda.between(bi, bf), "periodo"] = "ATUAL"
    base = base.dropna(subset=["periodo"])
    tabela = base.pivot_table(index=["cliente_codigo", "cliente_estado", "estabelecimento_tipo_codigo", "estabelecimento_tipo_nome", "quantidade_vendedores_carteira", "situacao_carteira", "tipo_analise", "industria"], columns="periodo", values="volume", aggfunc="sum", fill_value=0).reset_index()
    for coluna in ("ANTERIOR", "ATUAL"):
        if coluna not in tabela:
            tabela[coluna] = 0.0
    tabela = tabela.rename(columns={"ANTERIOR": "volume_anterior", "ATUAL": "volume_atual"})
    tabela["diferenca"] = tabela.volume_atual - tabela.volume_anterior
    tabela["variacao_percentual"] = tabela.diferenca.div(tabela.volume_anterior.where(tabela.volume_anterior.ne(0))).mul(100)
    tabela["classificacao"] = "ESTÁVEL"
    tabela.loc[(tabela.volume_anterior.eq(0)) & (tabela.volume_atual.gt(0)), "classificacao"] = "CLIENTE NOVO"
    tabela.loc[(tabela.volume_anterior.gt(0)) & (tabela.volume_atual.eq(0)), "classificacao"] = "SEM COMPRA NO PERÍODO ATUAL"
    tabela.loc[(tabela.volume_atual.gt(tabela.volume_anterior)) & tabela.volume_anterior.gt(0), "classificacao"] = "CRESCIMENTO"
    tabela.loc[tabela.volume_atual.lt(tabela.volume_anterior), "classificacao"] = "QUEDA"
    return tabela.sort_values("diferenca")


def analisar_mix(df: pd.DataFrame, datas: tuple[date, date, date, date]) -> pd.DataFrame:
    ai, af, bi, bf = map(pd.Timestamp, datas)
    base = df.assign(periodo=pd.NA)
    if "equipe_nome" not in base:
        base["equipe_nome"] = "SEM NOME"
    if "faturamento" not in base:
        base["faturamento"] = 0.0
    base.loc[base.data_venda.between(ai, af), "periodo"] = "ANTERIOR"
    base.loc[base.data_venda.between(bi, bf), "periodo"] = "ATUAL"
    base = base.dropna(subset=["periodo"])
    if base.empty:
        return pd.DataFrame(columns=[
            "equipe_codigo", "equipe_nome", "industria", "mix_anterior",
            "mix_atual", "queda_mix", "variacao_mix_percentual",
            "faturamento_anterior", "faturamento_atual", "queda_faturamento",
            "variacao_faturamento_percentual",
        ])
    chaves = ["equipe_codigo", "equipe_nome", "industria"]
    agrupado = base.groupby(chaves + ["periodo"], dropna=False).agg(
        mix=("produto_codigo", "nunique"),
        faturamento=("faturamento", "sum"),
    ).reset_index()
    mix = agrupado.pivot_table(index=chaves, columns="periodo", values="mix", aggfunc="sum", fill_value=0).reset_index()
    for coluna in ("ANTERIOR", "ATUAL"):
        if coluna not in mix:
            mix[coluna] = 0
    mix = mix.rename(columns={"ANTERIOR": "mix_anterior", "ATUAL": "mix_atual"})
    mix["queda_mix"] = mix.mix_atual - mix.mix_anterior
    mix["variacao_mix_percentual"] = mix.queda_mix.div(mix.mix_anterior.where(mix.mix_anterior.ne(0))).mul(100)

    faturamento = agrupado.pivot_table(index=chaves, columns="periodo", values="faturamento", aggfunc="sum", fill_value=0).reset_index()
    for coluna in ("ANTERIOR", "ATUAL"):
        if coluna not in faturamento:
            faturamento[coluna] = 0.0
    faturamento = faturamento.rename(columns={
        "ANTERIOR": "faturamento_anterior",
        "ATUAL": "faturamento_atual",
    })
    resultado = mix.merge(faturamento, on=chaves, how="outer").fillna(0)
    resultado["queda_faturamento"] = resultado.faturamento_atual - resultado.faturamento_anterior
    resultado["variacao_faturamento_percentual"] = resultado.queda_faturamento.div(
        resultado.faturamento_anterior.where(resultado.faturamento_anterior.ne(0))
    ).mul(100)
    resultado["situacao"] = "SEM QUEDA"
    resultado.loc[resultado.queda_mix.lt(0), "situacao"] = "QUEDA DE MIX"
    resultado.loc[resultado.queda_faturamento.lt(0), "situacao"] = "QUEDA DE FATURAMENTO"
    resultado.loc[
        resultado.queda_mix.lt(0) & resultado.queda_faturamento.lt(0), "situacao"
    ] = "QUEDA DE MIX E FATURAMENTO"
    return resultado.sort_values(["queda_faturamento", "queda_mix"])


def clientes_dormentes(
    df: pd.DataFrame,
    hoje: date,
    dias: int = 30,
    industrias: list[str] | None = None,
) -> pd.DataFrame:
    if "cliente_estado" not in df:
        df = df.assign(cliente_estado="NÃO IDENTIFICADO")
    if "estabelecimento_tipo_codigo" not in df:
        df = df.assign(estabelecimento_tipo_codigo=0)
    if "estabelecimento_tipo_nome" not in df:
        df = df.assign(estabelecimento_tipo_nome="NÃO IDENTIFICADO")
    if "quantidade_vendedores_carteira" not in df:
        df = df.assign(quantidade_vendedores_carteira=0)
    if "situacao_carteira" not in df:
        df = df.assign(situacao_carteira="SEM VENDEDOR ALOCADO")
    if "tipo_analise" not in df:
        df = df.assign(tipo_analise="Compra indústria")
    chaves_cliente = [
        "cliente_codigo", "cliente_estado", "estabelecimento_tipo_codigo",
        "estabelecimento_tipo_nome", "quantidade_vendedores_carteira",
        "situacao_carteira", "tipo_analise",
    ]
    limite = pd.Timestamp(hoje - timedelta(days=dias))
    industrias_analisadas = (
        list(dict.fromkeys(industrias))
        if industrias
        else df["industria"].dropna().drop_duplicates().tolist()
    )
    if not industrias_analisadas or df.empty:
        return pd.DataFrame(columns=chaves_cliente + [
            "industria", "ultima_compra", "unidades_historicas",
            "dias_com_compra", "dias_sem_compra",
        ])

    # O universo vem dos clientes apÃ³s os filtros cadastrais/carteira, e nÃ£o
    # apenas das vendas da indÃºstria. Assim, nunca ter comprado a indÃºstria
    # selecionada tambÃ©m Ã© uma situaÃ§Ã£o elegÃ­vel.
    clientes = df[chaves_cliente].drop_duplicates("cliente_codigo").copy()
    clientes["_cruzamento"] = 1
    catalogo_industrias = pd.DataFrame({"industria": industrias_analisadas})
    catalogo_industrias["_cruzamento"] = 1
    universo = clientes.merge(catalogo_industrias, on="_cruzamento").drop(
        columns="_cruzamento"
    )

    # Restrinja a cópia às colunas usadas no cálculo. Copiar todos os blocos da
    # base aqui elevava o pico de memória e podia impedir a abertura das cotas.
    colunas_venda = ["cliente_codigo", "industria", "data_venda", "unidades"]
    mascara_industria = df["industria"].isin(industrias_analisadas)
    vendas_industrias = df.loc[mascara_industria, colunas_venda]
    historico = vendas_industrias.loc[vendas_industrias["data_venda"].lt(limite)]
    resumo_historico = historico.groupby(
        ["cliente_codigo", "industria"], as_index=False, dropna=False
    ).agg(
        ultima_compra=("data_venda", "max"),
        unidades_historicas=("unidades", "sum"),
        dias_com_compra=("data_venda", "nunique"),
    )
    recentes = vendas_industrias.loc[
        vendas_industrias["data_venda"].ge(limite),
        ["cliente_codigo", "industria"],
    ].drop_duplicates()
    resumo = universo.merge(
        resumo_historico, on=["cliente_codigo", "industria"], how="left"
    ).merge(
        recentes.assign(_compra_recente=True),
        on=["cliente_codigo", "industria"], how="left",
    )
    resumo = resumo[resumo["_compra_recente"].ne(True)].drop(
        columns="_compra_recente"
    )
    resumo["unidades_historicas"] = resumo["unidades_historicas"].fillna(0.0)
    resumo["dias_com_compra"] = resumo["dias_com_compra"].fillna(0).astype(int)
    resumo["dias_sem_compra"] = (pd.Timestamp(hoje) - resumo.ultima_compra).dt.days
    return resumo.sort_values(
        ["ultima_compra", "unidades_historicas"],
        ascending=[True, False], na_position="first",
    )
