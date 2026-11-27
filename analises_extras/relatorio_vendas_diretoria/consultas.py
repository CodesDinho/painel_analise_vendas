from __future__ import annotations

from datetime import date

import pandas as pd

from conexoes import cliente_bigquery


SQL_RELATORIO = """
WITH equipes AS (
  SELECT CAST(equipe_codigo AS INT64) equipe_codigo, ANY_VALUE(equipe_nome) equipe_nome
  FROM `dinho-dw.topsystem_silver.equipe_comercial` GROUP BY 1
), clientes AS (
  SELECT CAST(cliente_codigo AS INT64) cliente_codigo,
    ANY_VALUE(CAST(cod_estabelecimento_tipo AS INT64)) tipo_estabelecimento,
    ANY_VALUE(estabelecimento_tipo) nome_tipo_estabelecimento
  FROM `dinho-dw.topsystem_silver.cliente` GROUP BY 1
), fornecedores AS (
  SELECT CAST(fornecedor_codigo AS INT64) fornecedor, ANY_VALUE(fornecedor_nome) nome_fornecedor
  FROM `dinho-dw.topsystem_silver.fornecedor` GROUP BY 1
), produtos AS (
  SELECT CAST(codigo AS INT64) produto, ANY_VALUE(nome) nome_produto
  FROM `dinho-dw.topsystem_bronze.produto` GROUP BY 1
), filiais AS (
  SELECT CAST(codigo AS INT64) filial, ANY_VALUE(nome) nome_filial
  FROM `dinho-dw.topsystem_bronze.filial` GROUP BY 1
)
SELECT
  CAST(v.pedido_filial AS INT64) filial,
  COALESCE(fi.nome_filial, 'NÃO IDENTIFICADO') nome_filial,
  EXTRACT(MONTH FROM DATE(v.pedido_data_emissao)) mes,
  EXTRACT(YEAR FROM DATE(v.pedido_data_emissao)) ano,
  COALESCE(c.tipo_estabelecimento, 0) tipo_estabelecimento,
  COALESCE(c.nome_tipo_estabelecimento, 'NÃO IDENTIFICADO') nome_tipo_estabelecimento,
  CAST(v.equipe_codigo AS INT64) equipe,
  COALESCE(e.equipe_nome, 'NÃO IDENTIFICADO') nome_equipe,
  CAST(v.produto_fornecedor_cod AS INT64) fornecedor,
  COALESCE(f.nome_fornecedor, 'NÃO IDENTIFICADO') nome_fornecedor,
  CAST(v.produto_codigo AS INT64) produto,
  COALESCE(p.nome_produto, 'NÃO IDENTIFICADO') nome_produto,
  SUM(CAST(v.quantidade AS FLOAT64)) qtde,
  SUM(CAST(v.valor_total AS FLOAT64)) venda_liquida,
  SUM(CAST(v.valor_total AS FLOAT64)
      - COALESCE(CAST(v.valor_custo AS FLOAT64), 0) * CAST(v.quantidade AS FLOAT64)) margem_bruta
FROM `dinho-dw.topsystem_silver.vendas` v
LEFT JOIN filiais fi ON fi.filial = v.pedido_filial
LEFT JOIN clientes c ON c.cliente_codigo = v.cliente_codigo
LEFT JOIN equipes e ON e.equipe_codigo = v.equipe_codigo
LEFT JOIN fornecedores f ON f.fornecedor = v.produto_fornecedor_cod
LEFT JOIN produtos p ON p.produto = v.produto_codigo
WHERE DATE(v.pedido_data_emissao) BETWEEN @data_inicio AND @data_fim
  AND v.cliente_codigo IS NOT NULL
  AND COALESCE(TRIM(v.tipo_pedido), '') <> '48'
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12
ORDER BY ano, mes, filial, equipe, fornecedor, produto
"""


def consultar_relatorio(data_inicio: date, data_fim: date) -> pd.DataFrame:
    """Executa uma consulta somente leitura e já agregada no BigQuery."""
    from google.cloud import bigquery

    config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("data_inicio", "DATE", data_inicio),
        bigquery.ScalarQueryParameter("data_fim", "DATE", data_fim),
    ])
    return cliente_bigquery().query(SQL_RELATORIO, job_config=config).to_dataframe()
