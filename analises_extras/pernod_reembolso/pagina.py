from __future__ import annotations

import re
import os
import json
import unicodedata
import zipfile
from urllib.request import Request, urlopen
from calendar import monthrange
from datetime import date
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd
import streamlit as st

from conexoes import cliente_bigquery, cliente_firebird


ARQUIVO_PADRAO = Path(__file__).resolve().parent / "temporarios" / "reembolso.xlsx"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
MESES = {1: "JAN", 2: "FEV", 3: "MAR", 4: "ABR", 5: "MAI", 6: "JUN", 7: "JUL", 8: "AGO", 9: "SET", 10: "OUT", 11: "NOV", 12: "DEZ"}
PRODUTOS = {
    "BALLANTINES FINEST 40 100CL": (723, "Ballantine’s Finest 1 L"),
    "BALLANTINES SUNSHINE 6X700ML": (10469, "Ballantine’s Sunshine 700 ml"),
    "BEEFEATER 24 45 75CL": (2347, "Beefeater 24 750 ml"),
    "BEEFEATER BLACKBERRY 37.5 70CL": (9791, "Beefeater Blackberry 700 ml"),
    "BEEFEATER PINK 37.5 70CL": (8856, "Beefeater Pink 700 ml"),
    "BEEFEATER STANDARD 47 75CL": (1298, "Beefeater Standard 750 ml"),
    "CHIVAS REGAL 12YO 40 100CL": (740, "Chivas Regal 12 anos 1 L"),
    "CHIVAS REGAL 12YO 40 75CL": (1562, "Chivas Regal 12 anos 750 ml"),
    "CHIVAS REGAL 18YO 40 75CL": (1746, "Chivas Regal 18 anos 750 ml"),
    "JAMESON ORIGINAL 40 75CL": (1696, "Jameson 750 ml"),
    "ABSOLUT CITRON 40 75CL STD": (1524, "Absolut Citron 750 ml"),
    "BALLANTINES SWEET BLEND 6X700ML": (10910, "Ballantine’s Sweet Blend 700 ml"),
}
COLUNAS_TODOS_TIPOS = {
    "pedidos_48": "unidades_adicionais_todos_tipos_de_pedidos",
    "faturamento_48": "faturamento_adicional_todos_tipos_de_pedidos",
    "quantidade_com_48": "quantidade_todos_tipos_de_pedidos",
    "reembolso_pedidos_48": "diferenca_reembolso",
    "reembolso_com_48": "reembolso_calculado_todos_tipos_de_pedidos",
    "reembolso_dinho_com_48": "reembolso_dinho_todos_tipos_de_pedidos",
}


def _coluna(celula: str) -> str:
    return re.match(r"[A-Z]+", celula).group(0)


def _numero_coluna(coluna: str) -> int:
    valor = 0
    for caractere in coluna:
        valor = valor * 26 + ord(caractere) - 64
    return valor


def _linhas_xml(conteudo: bytes, caminho: str) -> list[dict[str, object]]:
    with zipfile.ZipFile(BytesIO(conteudo)) as arquivo:
        compartilhados: list[str] = []
        with arquivo.open("xl/sharedStrings.xml") as origem:
            for _, elemento in ET.iterparse(origem, events=("end",)):
                if elemento.tag == NS + "si":
                    compartilhados.append("".join(no.text or "" for no in elemento.iter(NS + "t")))
                    elemento.clear()

        def valor(celula: ET.Element) -> object:
            bruto = celula.find(NS + "v")
            if bruto is None or bruto.text is None:
                return None
            if celula.get("t") == "s":
                return compartilhados[int(bruto.text)]
            try:
                return float(bruto.text)
            except ValueError:
                return bruto.text

        linhas: list[dict[str, object]] = []
        with arquivo.open(caminho) as origem:
            for _, elemento in ET.iterparse(origem, events=("end",)):
                if elemento.tag == NS + "row":
                    linha = {_coluna(c.get("r", "")): valor(c) for c in elemento.findall(NS + "c")}
                    if linha:
                        linhas.append(linha)
                    elemento.clear()
        return linhas


def _mes_cabecalho(valor: object) -> tuple[int, int] | None:
    if not isinstance(valor, str) or "/" not in valor:
        return None
    ano, mes = valor.upper().strip().split("/", 1)
    inverso = {nome: numero for numero, nome in MESES.items()}
    return (int(ano), inverso[mes]) if ano.isdigit() and mes in inverso else None


def ler_calculo_reembolso(conteudo: bytes, competencia: date) -> pd.DataFrame:
    linhas = _linhas_xml(conteudo, "xl/worksheets/sheet2.xml")
    cabecalho = next((linha for linha in linhas if linha.get("B") == "Executivo"), None)
    if cabecalho is None:
        raise ValueError("Cabeçalho da aba CalculoReembolso não localizado.")
    alvo = (competencia.year, competencia.month)
    meses = {col: _mes_cabecalho(val) for col, val in cabecalho.items() if _mes_cabecalho(val)}
    varejo = [col for col, mes in meses.items() if mes == alvo and 25 <= _numero_coluna(col) <= 34]
    top_100 = [col for col, mes in meses.items() if mes == alvo and 35 <= _numero_coluna(col) <= 44]
    if not varejo and not top_100:
        raise ValueError(
            f"A competência {competencia.year}/{MESES[competencia.month]} não existe na planilha."
        )
    sellin_cols = [col for col, mes in meses.items() if 13 <= _numero_coluna(col) <= 24 and mes <= alvo]
    sellout_cols = [col for col, mes in meses.items() if 25 <= _numero_coluna(col) <= 44 and mes <= alvo]
    registros = []
    for linha in linhas:
        bqs = str(linha.get("L") or "").strip()
        chave = bqs.upper()
        if str(linha.get("H") or "").upper() != "DINHO" or chave not in PRODUTOS:
            continue
        codigo, produto = PRODUTOS[chave]
        numero = lambda col: float(linha.get(col) or 0)
        sv = sum(numero(col) for col in varejo)
        st100 = sum(numero(col) for col in top_100)
        si_acum = sum(numero(col) for col in sellin_cols)
        so_acum = sum(numero(col) for col in sellout_cols)
        tv, tt = numero("AS"), numero("AT") or numero("AS")
        registros.append({
            "codigo": codigo, "produto": produto, "descricao_pernod": bqs,
            "sellout_varejo": sv, "sellout_top_100": st100,
            "sellout_planilha": sv + st100, "tarifa_varejo": tv, "tarifa_top_100": tt,
            "reembolso_sem_48": sv * tv + st100 * tt,
            "sellin_acumulado": si_acum, "sellout_acumulado": so_acum,
            "formula_maior_ou_igual": si_acum > 0 and si_acum >= so_acum,
            "formula_estrita": si_acum > so_acum,
        })
    if not registros:
        raise ValueError("Nenhum dos produtos mapeados foi localizado para o distribuidor DINHO.")
    return pd.DataFrame(registros).sort_values("codigo").reset_index(drop=True)


@st.cache_data(ttl=900, show_spinner=False)
def consultar_vendas_reembolso(inicio: date, fim: date, codigos: tuple[int, ...]) -> pd.DataFrame:
    from google.cloud import bigquery
    sql = """
    WITH movimentos AS (
      SELECT CAST(produto_codigo AS INT64) codigo, CAST(quantidade AS FLOAT64) quantidade,
             CAST(valor_total AS FLOAT64) valor_total, 'REGULAR' origem
      FROM `dinho-dw.topsystem_silver.vendas`
      WHERE DATE(pedido_data_emissao) BETWEEN @inicio AND @fim
        AND CAST(produto_codigo AS INT64) IN UNNEST(@codigos)
      UNION ALL
      SELECT CAST(produto_codigo AS INT64), CAST(quantidade AS FLOAT64),
             CAST(valor_total AS FLOAT64), 'PEDIDO 48'
      FROM `dinho-dw.topsystem_silver.pedidos_48`
      WHERE DATE(pedido_data_emissao) BETWEEN @inicio AND @fim
        AND CAST(produto_codigo AS INT64) IN UNNEST(@codigos)
    )
    SELECT codigo,
      SUM(IF(origem='REGULAR', quantidade, 0)) vendas_regulares,
      SUM(IF(origem='PEDIDO 48', quantidade, 0)) pedidos_48,
      SUM(quantidade) unidades_total,
      SUM(IF(origem='REGULAR', valor_total, 0)) faturamento_regular,
      SUM(IF(origem='PEDIDO 48', valor_total, 0)) faturamento_48,
      SUM(valor_total) faturamento_total
    FROM movimentos GROUP BY codigo
    """
    config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("inicio", "DATE", inicio),
        bigquery.ScalarQueryParameter("fim", "DATE", fim),
        bigquery.ArrayQueryParameter("codigos", "INT64", list(codigos)),
    ])
    return cliente_bigquery().query(sql, job_config=config).to_dataframe()


@st.cache_data(ttl=900, show_spinner=False)
def consultar_vendas_clientes_reembolso(
    inicio: date, fim: date, codigos: tuple[int, ...]
) -> pd.DataFrame:
    """Retorna movimentos regulares e tipo 48 no nível cliente × produto."""
    from google.cloud import bigquery
    sql = """
    WITH clientes AS (
      SELECT CAST(cliente_codigo AS INT64) cliente_codigo,
             ANY_VALUE(cliente_nome) cliente_nome
      FROM `dinho-dw.topsystem_silver.cliente`
      GROUP BY 1
    ), movimentos AS (
      SELECT CAST(cliente_codigo AS INT64) cliente_codigo,
             DATE(pedido_data_emissao) DATA,
             CAST(pedido_filial AS INT64) FILIAL,
             CAST(produto_codigo AS INT64) codigo,
             CAST(quantidade AS FLOAT64) quantidade,
             CAST(valor_total AS FLOAT64) valor_total, 'REGULAR' origem
      FROM `dinho-dw.topsystem_silver.vendas`
      WHERE DATE(pedido_data_emissao) BETWEEN @inicio AND @fim
        AND CAST(produto_codigo AS INT64) IN UNNEST(@codigos)
      UNION ALL
      SELECT CAST(cliente_codigo AS INT64), DATE(pedido_data_emissao),
             CAST(pedido_filial AS INT64), CAST(produto_codigo AS INT64),
             CAST(quantidade AS FLOAT64), CAST(valor_total AS FLOAT64), 'PEDIDO 48'
      FROM `dinho-dw.topsystem_silver.pedidos_48`
      WHERE DATE(pedido_data_emissao) BETWEEN @inicio AND @fim
        AND CAST(produto_codigo AS INT64) IN UNNEST(@codigos)
    )
    SELECT m.cliente_codigo, COALESCE(c.cliente_nome, 'NÃO IDENTIFICADO') cliente_dinho,
           m.DATA, m.FILIAL, m.codigo,
           SUM(IF(origem='REGULAR', quantidade, 0)) vendas_regulares,
           SUM(IF(origem='PEDIDO 48', quantidade, 0)) pedidos_48,
           SUM(quantidade) unidades_dinho,
           SUM(IF(origem='REGULAR', valor_total, 0)) faturamento_regular,
           SUM(IF(origem='PEDIDO 48', valor_total, 0)) faturamento_48,
           SUM(valor_total) faturamento_total
    FROM movimentos m LEFT JOIN clientes c USING (cliente_codigo)
    GROUP BY 1, 2, 3, 4, 5
    """
    config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("inicio", "DATE", inicio),
        bigquery.ScalarQueryParameter("fim", "DATE", fim),
        bigquery.ArrayQueryParameter("codigos", "INT64", list(codigos)),
    ])
    return cliente_bigquery().query(sql, job_config=config).to_dataframe()


def adicionar_cnpjs_clientes(movimentos: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta o CNPJ do CLIFOR aos movimentos retornados pelo DW."""
    resultado = movimentos.copy()
    codigos = sorted(
        resultado["cliente_codigo"].dropna().astype(int).unique().tolist()
    )
    cnpjs: dict[int, str] = {}
    if codigos:
        conexao = cliente_firebird("WIN1252")
        try:
            cursor = conexao.cursor()
            for inicio in range(0, len(codigos), 500):
                lote = codigos[inicio:inicio + 500]
                marcadores = ",".join("?" for _ in lote)
                cursor.execute(
                    f"SELECT CODIGO, CNPJ FROM CLIFOR WHERE CODIGO IN ({marcadores})",
                    lote,
                )
                cnpjs.update({int(codigo): str(cnpj or "").strip() for codigo, cnpj in cursor})
        finally:
            conexao.close()
    resultado["CNPJ"] = resultado["cliente_codigo"].map(cnpjs).fillna("")
    return resultado


def _chave_nome(valor: object) -> str:
    texto = "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", str(valor or ""))
        if not unicodedata.combining(caractere)
    ).upper()
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", texto).split())


def ler_clientes_mtrix(conteudo: bytes, competencia: date) -> pd.DataFrame:
    """Lê a base cliente × SKU declarada pela Pernod na aba Base_Reembolso."""
    base = pd.read_excel(BytesIO(conteudo), sheet_name="Base_Reembolso", header=2)
    apoio = pd.read_excel(BytesIO(conteudo), sheet_name="Apoio", header=4)
    exigidas = {
        "An8", "Desc Perfil", "UF", "BQS", "Mês/Ano",
        "Vendas - Real/GF", "Vendas Real/GF Top100",
    }
    ausentes = exigidas - set(base.columns)
    if ausentes:
        raise ValueError(
            "Colunas da Base_Reembolso não localizadas: " + ", ".join(sorted(ausentes))
        )
    base["competencia"] = pd.to_datetime(base["Mês/Ano"], errors="coerce")
    base = base[
        base["competencia"].dt.to_period("M") == pd.Period(competencia, freq="M")
    ].copy()
    mapa_produtos = {descricao: codigo for descricao, (codigo, _) in PRODUTOS.items()}
    apoio["bqs_normalizado"] = apoio["BQS"].astype(str).str.strip().str.upper()
    apoio["codigo"] = apoio["bqs_normalizado"].map(mapa_produtos)
    apoio["sku_pernod"] = pd.to_numeric(apoio["SKU"], errors="coerce")
    mapa_skus = (
        apoio.dropna(subset=["sku_pernod", "codigo"])
        .drop_duplicates("sku_pernod")
        .set_index("sku_pernod")["codigo"]
        .to_dict()
    )
    base["sku_pernod"] = pd.to_numeric(
        base["BQS"].astype(str).str.extract(r"^\s*(\d+)", expand=False),
        errors="coerce",
    )
    base["codigo"] = base["sku_pernod"].map(mapa_skus)
    base = base[base["codigo"].notna()].copy()
    base["unidades_mtrix_varejo"] = pd.to_numeric(
        base["Vendas - Real/GF"], errors="coerce"
    ).fillna(0)
    base["unidades_mtrix_top_100"] = pd.to_numeric(
        base["Vendas Real/GF Top100"], errors="coerce"
    ).fillna(0)
    base["unidades_mtrix"] = (
        base["unidades_mtrix_varejo"] + base["unidades_mtrix_top_100"]
    )
    base["cliente_pernod"] = base["Desc Perfil"].fillna("").astype(str).str.strip()
    base["cliente_an8"] = base["An8"].fillna("").astype(str).str.replace(r"\.0$", "", regex=True)
    base["uf_pernod"] = base["UF"].fillna("").astype(str).str.strip()
    base["chave_cliente"] = base["cliente_pernod"].map(_chave_nome)
    return (
        base.groupby(
            ["chave_cliente", "cliente_an8", "cliente_pernod", "uf_pernod", "codigo"],
            as_index=False, dropna=False,
        )[["unidades_mtrix_varejo", "unidades_mtrix_top_100", "unidades_mtrix"]].sum()
    )


def montar_justificativa_clientes(
    movimentos: pd.DataFrame, clientes_mtrix: pd.DataFrame, produtos: pd.DataFrame
) -> pd.DataFrame:
    interno = movimentos.copy()
    interno["chave_cliente"] = interno["cliente_dinho"].map(_chave_nome)
    interno = interno.groupby(
        ["chave_cliente", "cliente_codigo", "cliente_dinho", "codigo"],
        as_index=False, dropna=False,
    ).agg({
        "vendas_regulares": "sum", "pedidos_48": "sum", "unidades_dinho": "sum",
        "faturamento_regular": "sum", "faturamento_48": "sum", "faturamento_total": "sum",
    })
    comparativo = interno.merge(
        clientes_mtrix, on=["chave_cliente", "codigo"], how="outer"
    )
    nomes_produtos = produtos[
        ["codigo", "produto", "tarifa_varejo", "tarifa_top_100"]
    ].drop_duplicates("codigo")
    comparativo = comparativo.merge(nomes_produtos, on="codigo", how="left")
    numericas = [
        "vendas_regulares", "pedidos_48", "unidades_dinho", "unidades_mtrix",
        "unidades_mtrix_varejo", "unidades_mtrix_top_100", "faturamento_regular",
        "faturamento_48", "faturamento_total", "tarifa_varejo", "tarifa_top_100",
    ]
    for coluna in numericas:
        comparativo[coluna] = pd.to_numeric(comparativo[coluna], errors="coerce").fillna(0)
    tem_dinho = comparativo["cliente_codigo"].notna()
    tem_mtrix = comparativo["cliente_an8"].fillna("").astype(str).str.strip().ne("")
    comparativo["situacao"] = "Atendido pelo Dinho e identificado no Mtrix"
    comparativo.loc[tem_dinho & ~tem_mtrix, "situacao"] = "Atendido pelo Dinho e ausente no Mtrix"
    comparativo.loc[~tem_dinho & tem_mtrix, "situacao"] = "Informado no Mtrix e não localizado no Dinho"
    comparativo["diferenca_unidades"] = comparativo["unidades_dinho"] - comparativo["unidades_mtrix"]
    comparativo["reembolso_dinho_com_48"] = (
        comparativo["unidades_dinho"] * comparativo["tarifa_varejo"]
    )
    comparativo["reembolso_informado_mtrix"] = (
        comparativo["unidades_mtrix_varejo"] * comparativo["tarifa_varejo"]
        + comparativo["unidades_mtrix_top_100"] * comparativo["tarifa_top_100"]
    )
    comparativo["diferenca_reembolso"] = (
        comparativo["reembolso_dinho_com_48"]
        - comparativo["reembolso_informado_mtrix"]
    )
    comparativo["valor_extra_cobrar"] = comparativo["diferenca_reembolso"].clip(lower=0)
    comparativo["resultado_comparacao"] = "VALORES BATEM"
    comparativo.loc[
        comparativo["diferenca_reembolso"].gt(0.01), "resultado_comparacao"
    ] = "VALOR EXTRA A COBRAR"
    comparativo.loc[
        comparativo["diferenca_reembolso"].lt(-0.01), "resultado_comparacao"
    ] = "VALOR INFORMADO PELA PERNOD É MAIOR"
    colunas = [
        "situacao", "resultado_comparacao", "cliente_codigo", "cliente_dinho",
        "cliente_an8", "cliente_pernod", "uf_pernod", "codigo", "produto",
        "vendas_regulares", "pedidos_48", "unidades_dinho", "unidades_mtrix_varejo",
        "unidades_mtrix_top_100", "unidades_mtrix", "diferenca_unidades",
        "tarifa_varejo", "tarifa_top_100", "reembolso_dinho_com_48",
        "reembolso_informado_mtrix", "diferenca_reembolso", "valor_extra_cobrar",
        "faturamento_regular", "faturamento_48", "faturamento_total",
    ]
    return comparativo[colunas].sort_values(
        ["valor_extra_cobrar", "situacao", "cliente_dinho", "cliente_pernod", "codigo"],
        ascending=[False, True, True, True, True], na_position="last",
    ).reset_index(drop=True)


def _quadros_exportacao(
    comparativo: pd.DataFrame, produtos: pd.DataFrame, competencia: date
) -> tuple[pd.DataFrame, pd.DataFrame]:
    por_produto = produtos[[
        "codigo", "produto", "sellout_planilha", "pedidos_48", "quantidade_com_48",
        "tarifa_varejo", "reembolso_sem_48", "reembolso_com_48",
        "reembolso_pedidos_48",
    ]].copy()
    por_produto = por_produto.rename(columns={
        "sellout_planilha": "quantidade_informada_pernod",
        "pedidos_48": "unidades_adicionais_todos_tipos_de_pedidos",
        "quantidade_com_48": "quantidade_calculada_todos_tipos_de_pedidos",
        "reembolso_sem_48": "reembolso_informado_pernod",
        "reembolso_com_48": "reembolso_calculado_todos_tipos_de_pedidos",
        "reembolso_pedidos_48": "diferenca_reembolso",
    })
    por_produto["valor_extra_cobrar"] = por_produto["diferenca_reembolso"].clip(lower=0)
    por_produto["resultado_comparacao"] = por_produto["diferenca_reembolso"].abs().le(0.01).map(
        {True: "VALORES BATEM", False: "VALOR EXTRA A COBRAR"}
    )
    informado = por_produto["reembolso_informado_pernod"].sum()
    calculado = por_produto["reembolso_calculado_todos_tipos_de_pedidos"].sum()
    diferenca = calculado - informado
    resumo = pd.DataFrame({
        "Indicador": [
            "Competência", "Reembolso informado pela Pernod",
            "Reembolso calculado considerando todos os tipos de pedidos", "Diferença total",
            "Valor extra total a cobrar", "Resultado da conferência",
            "Clientes Dinho", "Clientes Mtrix", "Unidades adicionais consideradas",
        ],
        "Valor": [
            competencia.strftime("%m/%Y"), informado, calculado, diferenca,
            max(diferenca, 0),
            "VALORES BATEM" if abs(diferenca) <= 0.01 else "HÁ DIFERENÇA",
            comparativo["cliente_codigo"].nunique(),
            comparativo.loc[comparativo["cliente_an8"].fillna("").ne(""), "cliente_an8"].nunique(),
            comparativo["pedidos_48"].sum(),
        ],
    })
    return resumo, por_produto


def exportar_justificativa_excel(
    comparativo: pd.DataFrame, produtos: pd.DataFrame, competencia: date
) -> bytes:
    resumo, por_produto = _quadros_exportacao(comparativo, produtos, competencia)
    arquivo = BytesIO()
    with pd.ExcelWriter(arquivo, engine="openpyxl") as writer:
        resumo.to_excel(writer, sheet_name="Resumo", index=False)
        por_produto.to_excel(writer, sheet_name="Conferência reembolso", index=False)
        comparativo.rename(columns=COLUNAS_TODOS_TIPOS).to_excel(
            writer, sheet_name="Clientes x Mtrix", index=False
        )
        for planilha in writer.book.worksheets:
            planilha.freeze_panes = "A2"
            planilha.auto_filter.ref = planilha.dimensions
            for coluna in planilha.columns:
                largura = min(max(len(str(celula.value or "")) for celula in coluna) + 2, 45)
                planilha.column_dimensions[coluna[0].column_letter].width = largura
    return arquivo.getvalue()


def exportar_justificativa_simplificada_excel(
    movimentos: pd.DataFrame,
    comparativo: pd.DataFrame,
    produtos: pd.DataFrame,
    competencia: date,
) -> bytes:
    """Gera a versão enxuta com a aba final no leiaute solicitado."""
    prioridades = {
        "VALORES BATEM": 1,
        "VALOR INFORMADO PELA PERNOD É MAIOR": 2,
        "VALOR EXTRA A COBRAR": 3,
    }
    estados = comparativo[
        ["cliente_codigo", "codigo", "resultado_comparacao"]
    ].dropna(subset=["cliente_codigo"]).copy()
    estados["prioridade"] = estados["resultado_comparacao"].map(prioridades).fillna(0)
    estados = (
        estados.sort_values("prioridade")
        .drop_duplicates(["cliente_codigo", "codigo"], keep="last")
        .drop(columns="prioridade")
    )
    nomes_produtos = produtos[["codigo", "produto"]].drop_duplicates("codigo")
    simplificado = movimentos.merge(
        estados, on=["cliente_codigo", "codigo"], how="left"
    ).merge(nomes_produtos, on="codigo", how="left")
    simplificado["resultado_comparacao"] = simplificado[
        "resultado_comparacao"
    ].fillna("SEM COMPARAÇÃO NO MTRIX")
    simplificado["DATA"] = pd.to_datetime(simplificado["DATA"], errors="coerce").dt.date
    simplificado = (
        simplificado.groupby(
            [
                "resultado_comparacao", "cliente_codigo", "cliente_dinho", "CNPJ",
                "DATA", "FILIAL", "codigo", "produto",
            ],
            as_index=False, dropna=False,
        )
        .agg(UNID=("unidades_dinho", "sum"), faturamento_total=("faturamento_total", "sum"))
    )
    colunas = [
        "resultado_comparacao", "cliente_codigo", "cliente_dinho", "CNPJ", "DATA",
        "FILIAL", "codigo", "produto", "UNID", "faturamento_total",
    ]
    simplificado = simplificado[colunas].sort_values(
        ["resultado_comparacao", "DATA", "FILIAL", "cliente_codigo", "codigo"]
    )
    resumo, por_produto = _quadros_exportacao(comparativo, produtos, competencia)
    arquivo = BytesIO()
    with pd.ExcelWriter(arquivo, engine="openpyxl") as writer:
        resumo.to_excel(writer, sheet_name="Resumo", index=False)
        por_produto.to_excel(writer, sheet_name="Conferência reembolso", index=False)
        simplificado.to_excel(writer, sheet_name="Dados simplificados", index=False)
        for planilha in writer.book.worksheets:
            planilha.freeze_panes = "A2"
            planilha.auto_filter.ref = planilha.dimensions
            for coluna in planilha.columns:
                largura = min(max(len(str(celula.value or "")) for celula in coluna) + 2, 45)
                planilha.column_dimensions[coluna[0].column_letter].width = largura
    return arquivo.getvalue()


def calcular_analise(conteudo: bytes, competencia: date) -> pd.DataFrame:
    planilha = ler_calculo_reembolso(conteudo, competencia)
    inicio = competencia.replace(day=1)
    fim = competencia.replace(day=monthrange(competencia.year, competencia.month)[1])
    vendas = consultar_vendas_reembolso(inicio, fim, tuple(planilha["codigo"].astype(int)))
    resultado = planilha.merge(vendas, on="codigo", how="left")
    cols = ["vendas_regulares", "pedidos_48", "unidades_total", "faturamento_regular", "faturamento_48", "faturamento_total"]
    resultado[cols] = resultado[cols].fillna(0)
    resultado["quantidade_com_48"] = resultado["sellout_planilha"] + resultado["pedidos_48"]
    resultado["reembolso_pedidos_48"] = resultado["pedidos_48"] * resultado["tarifa_varejo"]
    resultado["reembolso_com_48"] = resultado["reembolso_sem_48"] + resultado["reembolso_pedidos_48"]
    return resultado


def _brl(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _inteiro(valor: float) -> str:
    return f"{valor:,.0f}".replace(",", ".")


def gerar_email(r: pd.DataFrame, competencia: date, arquivo: str) -> str:
    sem = r.reembolso_sem_48.sum(); adicional = r.reembolso_pedidos_48.sum(); com = r.reembolso_com_48.sum()
    qtd_sem = r.sellout_planilha.sum(); qtd_48 = r.pedidos_48.sum(); invalidos = r.loc[~r.formula_estrita]
    inv_sem = invalidos.reembolso_sem_48.sum(); inv_com = invalidos.reembolso_com_48.sum()
    vendas = ["Cód.\tProduto\tUnidades\tFaturamento"]
    sem_48 = ["Cód. Dinho\tQuantidade informada\tR$/garrafa\tReembolso informado"]
    com_48 = ["Cód. Dinho\tQuantidade informada\tUnidades adicionais\tQuantidade total\tR$/garrafa\tReembolso informado\tAcréscimo\tReembolso calculado"]
    for linha in r.sort_values("codigo").itertuples(index=False):
        vendas.append(f"{linha.codigo}\t{linha.produto}\t{_inteiro(linha.vendas_regulares)}\t{_brl(linha.faturamento_regular)}")
        sem_48.append(f"{linha.codigo}\t{_inteiro(linha.sellout_planilha)}\t{_brl(linha.tarifa_varejo)}\t{_brl(linha.reembolso_sem_48)}")
        com_48.append(f"{linha.codigo}\t{_inteiro(linha.sellout_planilha)}\t{_inteiro(linha.pedidos_48)}\t{_inteiro(linha.quantidade_com_48)}\t{_brl(linha.tarifa_varejo)}\t{_brl(linha.reembolso_sem_48)}\t{_brl(linha.reembolso_pedidos_48)}\t{_brl(linha.reembolso_com_48)}")
    vendas.append(f"Total\t\t{_inteiro(r.vendas_regulares.sum())}\t{_brl(r.faturamento_regular.sum())}")
    sem_48.append(f"Total\t{_inteiro(qtd_sem)}\t\t{_brl(sem)}")
    com_48.append(f"Total\t{_inteiro(qtd_sem)}\t{_inteiro(qtd_48)}\t{_inteiro(qtd_sem + qtd_48)}\t\t{_brl(sem)}\t{_brl(adicional)}\t{_brl(com)}")
    reprovados = "\n".join(
        f"• {linha.produto}: {_brl(linha.reembolso_sem_48)}"
        for linha in invalidos.itertuples(index=False)
    )
    return f"""Solicitei o arquivo completo da Pernod, que está disponível em nosso SharePoint, caso necessário.

Inicialmente selecionei os produtos e verifiquei nossos códigos internos. Gustavo, esta seria a validação inicial necessária. Caso algum produto esteja incorreto, favor indicar.

Arquivo analisado: {arquivo}
Competência: {competencia:%m/%Y}

1. Vendas regulares registradas no Dinho

A tabela abaixo apresenta as vendas regulares. As demais origens são consolidadas no cálculo com todos os tipos de pedidos.

{chr(10).join(vendas)}

2. Auditoria do reembolso informado pela Pernod

Gustavo, esta seria a segunda validação necessária.

A planilha utiliza a seguinte lógica:
Reembolso = sell-out do mês em garrafas × valor unitário de reembolso.

Para o canal Top 100 existe uma tarifa separada. Nos produtos analisados, o volume desse canal para a competência selecionada está incorporado ao cálculo apresentado.

{chr(10).join(sem_48)}

Portanto, o valor bruto informado pela Pernod é de {_brl(sem)}.

Contudo, a fórmula de validação da planilha compara o sell-in acumulado com o sell-out acumulado. Aplicando literalmente a fórmula final, que utiliza comparação estrita, os seguintes produtos apresentam resultado “Não”:

{reprovados}

Esses itens representam {_brl(inv_sem)}. Assim:
• Reembolso bruto informado: {_brl(sem)};
• Valor dos produtos que não atendem à fórmula: {_brl(inv_sem)};
• Valor validado pela fórmula atual: {_brl(sem - inv_sem)}.

Verificamos também qual período é considerado na validação. A fórmula existente no arquivo não compara exclusivamente as movimentações do mês do reembolso. Ela soma o sell-in dos meses disponíveis no período e o compara com o sell-out acumulado do mesmo intervalo. O valor financeiro do reembolso, por sua vez, é calculado somente sobre o sell-out da competência selecionada.

Portanto, pela estrutura atual do arquivo, a regra aplicada é: reembolso calculado sobre o mês, condicionado à validação acumulada. Precisamos confirmar com a Pernod se essa é efetivamente a regra comercial pretendida.

Há ainda um ponto importante: a coluna intermediária aceita igualdade (sell-in >= sell-out), enquanto a validação final utiliza comparação estrita (sell-in > sell-out). Produtos com valores iguais podem ser aprovados em uma coluna e reprovados na outra. Esse critério também precisa ser confirmado.

3. Reembolso considerando todos os tipos de pedidos

Todas as origens de pedidos disponíveis foram consolidadas na quantidade utilizada para o cálculo do reembolso, aplicando o valor por garrafa definido para cada produto.

Foram localizadas {_inteiro(qtd_48)} unidades adicionais, no valor de {_brl(r.faturamento_48.sum())}.

{chr(10).join(com_48)}

Portanto, considerando todos os tipos de pedidos:
• Quantidade original da planilha: {_inteiro(qtd_sem)} garrafas;
• Quantidade adicional considerada: {_inteiro(qtd_48)} garrafas;
• Quantidade total para reembolso: {_inteiro(qtd_sem + qtd_48)} garrafas;
• Reembolso original: {_brl(sem)};
• Reembolso adicional: {_brl(adicional)};
• Reembolso bruto final com todos os tipos de pedidos: {_brl(com)}.

Para conferência do movimento comercial completo:
• Vendas regulares: {_inteiro(r.vendas_regulares.sum())} unidades — {_brl(r.faturamento_regular.sum())};
• Demais origens consideradas: {_inteiro(qtd_48)} unidades — {_brl(r.faturamento_48.sum())};
• Movimento consolidado: {_inteiro(r.unidades_total.sum())} unidades — {_brl(r.faturamento_total.sum())}.

Conclusão final

• Quantidade informada: {_inteiro(qtd_sem)} garrafas — {_brl(sem)};
• Todos os tipos de pedidos: {_inteiro(qtd_sem + qtd_48)} garrafas — {_brl(com)};
• Diferença identificada: {_inteiro(qtd_48)} garrafas — {_brl(adicional)}.

Se a mesma fórmula estrita de elegibilidade for aplicada ao cenário consolidado:
• Reembolso bruto com todos os tipos de pedidos: {_brl(com)};
• Valor dos itens que não atendem à fórmula: {_brl(inv_com)};
• Valor validado pela fórmula atual: {_brl(com - inv_com)}.

As validações finais necessárias são:
1. confirmar se a elegibilidade deve considerar somente o mês ou o acumulado;
2. confirmar se a comparação correta é maior que (>) ou maior ou igual a (>=).

Para justificar a necessidade de verba adicional, deve ser anexada a relação cliente × produto que compara todo o atendimento do Dinho com os clientes informados no Mtrix."""


def _contexto_pergunta(r: pd.DataFrame, competencia: date) -> str:
    linhas = []
    for item in r.sort_values("codigo").itertuples(index=False):
        linhas.append(
            f"{item.codigo} {item.produto}: vendas regulares={item.vendas_regulares:.0f}; "
            f"unidades adicionais={item.pedidos_48:.0f}; sell-out={item.sellout_planilha:.0f}; "
            f"tarifa={item.tarifa_varejo:.2f}; informado={item.reembolso_sem_48:.2f}; "
            f"todos os pedidos={item.reembolso_com_48:.2f}; validação estrita={item.formula_estrita}."
        )
    return (
        f"Competência {competencia:%m/%Y}. A tabela vendas contém vendas regulares; "
        "as demais origens de pedidos vêm de uma visão separada. O reembolso do mês é "
        "sell-out vezes tarifa. A elegibilidade encontrada compara acumulados; uma "
        "coluna usa >= e a final usa >. Todos os tipos de pedidos devem ser incluídos "
        "no cenário completo.\n" + "\n".join(linhas)
    )


def _resposta_local(pergunta: str, r: pd.DataFrame) -> str | None:
    texto = pergunta.casefold()
    sem = r.reembolso_sem_48.sum()
    adicional = r.reembolso_pedidos_48.sum()
    com = r.reembolso_com_48.sum()
    if "sem" in texto and "48" in texto and any(p in texto for p in ("valor", "total", "reembolso")):
        return f"O reembolso bruto informado é {_brl(sem)}, sobre {_inteiro(r.sellout_planilha.sum())} garrafas."
    if "com" in texto and "48" in texto and any(p in texto for p in ("valor", "total", "reembolso")):
        return f"Considerando todos os tipos de pedidos, o reembolso bruto é {_brl(com)}, sobre {_inteiro(r.quantidade_com_48.sum())} garrafas."
    if "48" in texto and any(p in texto for p in ("diferença", "acréscimo", "impacto")):
        return f"As unidades adicionais acrescentam {_inteiro(r.pedidos_48.sum())} garrafas e {_brl(adicional)} ao reembolso bruto."
    if "faturamento" in texto:
        return f"O faturamento consolidado é {_brl(r.faturamento_total.sum())}: {_brl(r.faturamento_regular.sum())} em vendas regulares e {_brl(r.faturamento_48.sum())} nas demais origens consideradas."
    if any(p in texto for p in ("maior ou igual", ">=", "maior que", "fórmula", "formula")):
        return "A planilha tem dois critérios diferentes: a coluna intermediária aceita sell-in acumulado maior ou igual ao sell-out acumulado (>=), enquanto a validação final exige que seja estritamente maior (>). Esse critério comercial precisa ser confirmado com a Pernod."
    return None


def responder_pergunta(pergunta: str, r: pd.DataFrame, competencia: date) -> str:
    local = _resposta_local(pergunta, r)
    if local:
        return local
    chave = os.getenv("OPENAI_API_KEY", "").strip()
    if not chave:
        return (
            "Não encontrei uma resposta determinística para essa pergunta nos cálculos "
            "exibidos. Para perguntas abertas, configure `OPENAI_API_KEY` no ambiente do "
            "servidor. Nenhuma planilha completa será enviada; somente o resumo visível e "
            "a pergunta serão usados como contexto."
        )
    try:
        payload = {
            "model": os.getenv("ANALISE_VENDAS_OPENAI_MODEL", "gpt-5-mini"),
            "instructions": (
                "Responda em português do Brasil como analista de dados. Use somente o "
                "contexto fornecido. Diferencie cálculo aritmético de validação comercial, "
                "não invente dados e diga claramente quando algo depende da Pernod. Seja "
                "objetivo e mostre a conta quando isso ajudar."
            ),
            "input": f"CONTEXTO AUDITADO:\n{_contexto_pergunta(r, competencia)}\n\nPERGUNTA:\n{pergunta}",
        }
        requisicao = Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(requisicao, timeout=60) as retorno:
            dados = json.loads(retorno.read().decode("utf-8"))
        partes = [
            bloco.get("text", "")
            for item in dados.get("output", [])
            for bloco in item.get("content", [])
            if bloco.get("type") == "output_text"
        ]
        resposta = "\n".join(parte for parte in partes if parte).strip()
        return resposta or "A IA não retornou texto para esta pergunta."
    except Exception as exc:
        return f"Não foi possível consultar a IA neste momento: {exc}"


def _render_perguntas(r: pd.DataFrame, competencia: date) -> None:
    st.subheader("Perguntas sobre a análise")
    st.caption(
        "As respostas usam os resultados desta competência. Perguntas objetivas são "
        "respondidas localmente; perguntas abertas usam IA somente se a chave estiver configurada."
    )
    historico = st.session_state.setdefault("pernod_reembolso_perguntas", [])
    for mensagem in historico:
        with st.chat_message(mensagem["papel"]):
            st.markdown(mensagem["texto"])
    pergunta = st.chat_input("Digite uma dúvida sobre os números ou as regras", key="pernod_reembolso_chat")
    if pergunta:
        historico.append({"papel": "user", "texto": pergunta})
        with st.chat_message("user"):
            st.markdown(pergunta)
        with st.chat_message("assistant"):
            with st.spinner("Consultando a análise..."):
                resposta = responder_pergunta(pergunta, r, competencia)
            st.markdown(resposta)
        historico.append({"papel": "assistant", "texto": resposta})


def render_analise_pernod_reembolso() -> None:
    st.title("Análise Pernod Reembolso")
    st.caption("Conferência da planilha Pernod considerando todos os tipos de pedidos e comparação dos clientes atendidos com a base Mtrix.")
    st.info("Arquivo padrão: `temporarios/reembolso.xlsx`. A análise consolida todas as origens de pedidos disponíveis no DW.")
    enviado = st.file_uploader("Nova planilha de reembolso Pernod", type=["xlsx"], key="pernod_reembolso_arquivo")
    competencia = st.date_input("Mês das vendas a validar", date(2026, 9, 1), format="DD/MM/YYYY", key="pernod_reembolso_mes", help="O dia é desconsiderado.").replace(day=1)
    if enviado is not None:
        conteudo, nome = enviado.getvalue(), enviado.name
    elif ARQUIVO_PADRAO.exists():
        conteudo, nome = ARQUIVO_PADRAO.read_bytes(), "temporarios/reembolso.xlsx"
    else:
        st.error("O arquivo padrão não foi encontrado."); return
    if st.button("Recalcular análise", type="primary", key="pernod_reembolso_recalcular"):
        try:
            with st.spinner("Lendo a planilha e consultando o BigQuery..."):
                contexto_anterior = (
                    st.session_state.get("pernod_reembolso_competencia"),
                    st.session_state.get("pernod_reembolso_nome"),
                )
                resultado = calcular_analise(conteudo, competencia)
                inicio = competencia.replace(day=1)
                fim = competencia.replace(
                    day=monthrange(competencia.year, competencia.month)[1]
                )
                movimentos_clientes = consultar_vendas_clientes_reembolso(
                    inicio, fim, tuple(resultado["codigo"].astype(int))
                )
                movimentos_clientes = adicionar_cnpjs_clientes(movimentos_clientes)
                clientes_mtrix = ler_clientes_mtrix(conteudo, competencia)
                justificativa = montar_justificativa_clientes(
                    movimentos_clientes, clientes_mtrix, resultado
                )
                st.session_state.pernod_reembolso_resultado = resultado
                st.session_state.pernod_reembolso_justificativa = justificativa
                st.session_state.pernod_reembolso_movimentos_clientes = movimentos_clientes
                st.session_state.pernod_reembolso_competencia = competencia
                st.session_state.pernod_reembolso_nome = nome
                if contexto_anterior != (competencia, nome):
                    st.session_state.pernod_reembolso_perguntas = []
        except Exception as exc:
            st.error(f"Não foi possível recalcular a análise: {exc}")
    if "pernod_reembolso_resultado" not in st.session_state:
        st.info("Clique em **Recalcular análise** para gerar a conferência."); return
    r = st.session_state.pernod_reembolso_resultado
    comp = st.session_state.pernod_reembolso_competencia
    nome = st.session_state.pernod_reembolso_nome
    st.caption(f"Resultado atual: {nome} · competência {comp:%m/%Y}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Vendas regulares", _inteiro(r.vendas_regulares.sum()))
    c2.metric("Unidades adicionais consideradas", _inteiro(r.pedidos_48.sum()))
    c3.metric("Movimento total", _inteiro(r.unidades_total.sum()))
    c4.metric("Faturamento total", _brl(r.faturamento_total.sum()))
    reembolso_informado = float(r.reembolso_sem_48.sum())
    reembolso_com_48 = float(r.reembolso_com_48.sum())
    diferenca_reembolso = reembolso_com_48 - reembolso_informado
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Reembolso informado pela Pernod", _brl(reembolso_informado))
    f2.metric("Reembolso com todos os tipos de pedidos", _brl(reembolso_com_48))
    f3.metric(
        "Diferença de reembolso",
        _brl(diferenca_reembolso),
        delta="Valor extra a cobrar" if diferenca_reembolso > 0.01 else "Sem diferença",
        delta_color="inverse" if diferenca_reembolso > 0.01 else "normal",
    )
    f4.metric(
        "Resultado da conferência",
        "HÁ DIFERENÇA" if abs(diferenca_reembolso) > 0.01 else "VALORES BATEM",
    )
    st.subheader("Cenários de reembolso")
    resumo = pd.DataFrame([
        ["Valor informado pela Pernod", r.sellout_planilha.sum(), r.reembolso_sem_48.sum()],
        ["Todos os tipos de pedidos", r.quantidade_com_48.sum(), r.reembolso_com_48.sum()],
        ["Diferença identificada", r.pedidos_48.sum(), r.reembolso_pedidos_48.sum()],
    ], columns=["Cenário", "Quantidade reembolsável", "Reembolso bruto"])
    st.dataframe(resumo, hide_index=True, use_container_width=True, column_config={"Quantidade reembolsável": st.column_config.NumberColumn(format="%.0f"), "Reembolso bruto": st.column_config.NumberColumn(format="R$ %.2f")})
    st.subheader("Detalhamento por produto")
    exibicao = r[["codigo", "produto", "vendas_regulares", "pedidos_48", "unidades_total", "sellout_planilha", "quantidade_com_48", "tarifa_varejo", "reembolso_sem_48", "reembolso_pedidos_48", "reembolso_com_48", "sellin_acumulado", "sellout_acumulado", "formula_maior_ou_igual", "formula_estrita"]].copy()
    exibicao["resultado_comparacao"] = exibicao["reembolso_pedidos_48"].abs().le(0.01).map(
        {True: "VALORES BATEM", False: "VALOR EXTRA A COBRAR"}
    )
    exibicao = exibicao.rename(columns={
        "sellout_planilha": "quantidade_informada_pernod",
        "pedidos_48": "unidades_adicionais_todos_tipos_de_pedidos",
        "quantidade_com_48": "quantidade_calculada_todos_tipos_de_pedidos",
        "reembolso_sem_48": "reembolso_informado_pernod",
        "reembolso_pedidos_48": "diferenca_reembolso",
        "reembolso_com_48": "reembolso_calculado_todos_tipos_de_pedidos",
    })
    st.dataframe(exibicao, hide_index=True, use_container_width=True)
    justificativa = st.session_state.get("pernod_reembolso_justificativa")
    if justificativa is not None:
        st.subheader("Clientes atendidos pelo Dinho × clientes informados no Mtrix")
        st.caption(
            "O cruzamento usa cliente e produto. Cada linha compara o reembolso do "
            "movimento Dinho, considerando todos os tipos de pedidos, com o valor correspondente no Mtrix."
        )
        j1, j2, j3, j4 = st.columns(4)
        j1.metric("Clientes atendidos", justificativa["cliente_codigo"].nunique())
        j2.metric(
            "Clientes no Mtrix",
            justificativa.loc[
                justificativa["cliente_an8"].fillna("").ne(""), "cliente_an8"
            ].nunique(),
        )
        j3.metric(
            "Linhas com valor extra",
            int(justificativa["valor_extra_cobrar"].gt(0.01).sum()),
        )
        j4.metric(
            "Extra identificado cliente a cliente",
            _brl(justificativa["valor_extra_cobrar"].sum()),
        )
        justificativa_exibicao = justificativa.rename(columns=COLUNAS_TODOS_TIPOS)
        st.dataframe(
            justificativa_exibicao,
            hide_index=True,
            use_container_width=True,
            height=620,
            column_config={
                "situacao": st.column_config.TextColumn("Situação", width="large"),
                "resultado_comparacao": st.column_config.TextColumn("Conferência", width="large"),
                "cliente_codigo": st.column_config.NumberColumn("Cód. cliente Dinho", format="%d"),
                "cliente_dinho": st.column_config.TextColumn("Cliente Dinho", width="large"),
                "cliente_an8": st.column_config.TextColumn("Cód. AN8 Pernod"),
                "cliente_pernod": st.column_config.TextColumn("Cliente Mtrix", width="large"),
                "uf_pernod": "UF Mtrix",
                "codigo": st.column_config.NumberColumn("Cód. produto", format="%d"),
                "produto": st.column_config.TextColumn("Produto", width="large"),
                "vendas_regulares": st.column_config.NumberColumn("Regular", format="%.0f"),
                "unidades_adicionais_todos_tipos_de_pedidos": st.column_config.NumberColumn("Unidades adicionais", format="%.0f"),
                "unidades_dinho": st.column_config.NumberColumn("Total Dinho", format="%.0f"),
                "unidades_mtrix_varejo": st.column_config.NumberColumn("Mtrix varejo", format="%.0f"),
                "unidades_mtrix_top_100": st.column_config.NumberColumn("Mtrix Top 100", format="%.0f"),
                "unidades_mtrix": st.column_config.NumberColumn("Total Mtrix", format="%.0f"),
                "diferenca_unidades": st.column_config.NumberColumn("Diferença", format="%.0f"),
                "tarifa_varejo": st.column_config.NumberColumn("Tarifa varejo", format="R$ %.2f"),
                "tarifa_top_100": st.column_config.NumberColumn("Tarifa Top 100", format="R$ %.2f"),
                "reembolso_dinho_todos_tipos_de_pedidos": st.column_config.NumberColumn("Reembolso Dinho — todos os pedidos", format="R$ %.2f"),
                "reembolso_informado_mtrix": st.column_config.NumberColumn("Reembolso Mtrix", format="R$ %.2f"),
                "diferenca_reembolso": st.column_config.NumberColumn("Diferença de reembolso", format="R$ %.2f"),
                "valor_extra_cobrar": st.column_config.NumberColumn("Valor extra a cobrar", format="R$ %.2f"),
            },
        )
        movimentos_clientes = st.session_state.get(
            "pernod_reembolso_movimentos_clientes"
        )
        baixar_completo, baixar_simplificado = st.columns(2)
        baixar_completo.download_button(
            "Gerar Excel — versão completa",
            data=exportar_justificativa_excel(justificativa, r, comp),
            file_name=f"justificativa_pernod_todos_tipos_completa_{comp:%Y_%m}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
        )
        if movimentos_clientes is not None:
            baixar_simplificado.download_button(
                "Gerar Excel — versão simplificada",
                data=exportar_justificativa_simplificada_excel(
                    movimentos_clientes, justificativa, r, comp
                ),
                file_name=f"justificativa_pernod_todos_tipos_simplificada_{comp:%Y_%m}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
    with st.expander("Regras identificadas no arquivo", expanded=True):
        st.markdown("""
- Reembolso: **sell-out do mês × tarifa por garrafa**.
- A elegibilidade usa **sell-in acumulado versus sell-out acumulado**.
- A coluna intermediária aceita `sell-in >= sell-out`; a final usa `sell-in > sell-out`.
- Todos os tipos de pedidos disponíveis são consolidados e considerados pela tarifa-base do SKU.
        """)
    st.subheader("Texto-base após análise de dados Pernod e regras de reembolso")
    email = gerar_email(r, comp, nome)
    st.text_area("Conteúdo", email, height=520, key="pernod_reembolso_email")
    st.download_button("Baixar texto do e-mail", email.encode("utf-8"), f"analise_pernod_reembolso_{comp:%Y_%m}.txt", "text/plain")
    _render_perguntas(r, comp)
