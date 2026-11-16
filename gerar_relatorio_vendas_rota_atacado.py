from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
from google.cloud import bigquery
from openpyxl.styles import Font, PatternFill

from conexoes import cliente_bigquery, cliente_firebird


DATA_INICIO = date(2026, 5, 1)
DATA_FIM = date(2026, 10, 31)
VENDEDORES_ATACADO = (187, 1929)
ARQUIVO_SAIDA = (
    Path(__file__).resolve().parent
    / "relatorios"
    / "vendas_produtos_6_meses_fechados_por_filial_rota_atacado_202605_202610.xlsx"
)

COLUNAS = [
    "Filial", "Canal", "Código", "Descrição", "Tipo", "Unidade", "Ano_mes",
    "Quant por caixa", "Quantidade Vendida (caixas + unidades parciais)",
    "Quantidade Vendida caixas fechadas", "Quantidade Vendida unidades parciais",
    "Quantidade Vendida unidades totais", "Quantidade Devolvida",
    "Quantidade Estornada",
]


def consultar_movimentos() -> pd.DataFrame:
    sql = """
    SELECT
      p.filial AS filial,
      CASE WHEN p.funcionario IN UNNEST(@vendedores_atacado)
           THEN 'ATACADO' ELSE 'ROTA' END AS canal,
      i.produto AS produto,
      FORMAT_DATE('%Y%m', p.data_emissao) AS ano_mes,
      SUM(CASE
          WHEN COALESCE(p.cancelado, 'N') <> 'S'
           AND COALESCE(i.cancelado, 'N') <> 'S'
          THEN COALESCE(i.quantidade, 0) ELSE 0 END) AS vendida,
      SUM(COALESCE(i.qtdedevolvido, 0)) AS devolvida,
      SUM(CASE
          WHEN COALESCE(p.cancelado, 'N') <> 'S'
           AND COALESCE(i.cancelado, 'N') = 'S'
          THEN COALESCE(i.quantidade, 0) ELSE 0 END) AS estornada
    FROM `dinho-dw.topsystem_bronze.pedido` p
    JOIN `dinho-dw.topsystem_bronze.itempedido` i ON i.idpedido = p.id
    WHERE p.data_emissao BETWEEN @data_inicio AND @data_fim
      AND COALESCE(p.tipo_pedido, 0) <> 48
      AND p.filial IS NOT NULL
      AND i.produto IS NOT NULL
    GROUP BY 1, 2, 3, 4
    HAVING vendida > 0
    ORDER BY 1, 2, 3, 4
    """
    parametros = [
        bigquery.ScalarQueryParameter("data_inicio", "DATE", DATA_INICIO),
        bigquery.ScalarQueryParameter("data_fim", "DATE", DATA_FIM),
        bigquery.ArrayQueryParameter(
            "vendedores_atacado", "INT64", list(VENDEDORES_ATACADO)
        ),
    ]
    return cliente_bigquery().query(
        sql, job_config=bigquery.QueryJobConfig(query_parameters=parametros)
    ).to_dataframe()


def consultar_produtos() -> pd.DataFrame:
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        cursor.execute(
            "SELECT CODIGO,NOME,'PA',UNCOMPRA,"
            "CASE WHEN COALESCE(QTDECOMPRA,0)=0 THEN 1 ELSE QTDECOMPRA END "
            "FROM PRODUTO ORDER BY CODIGO"
        )
        linhas = cursor.fetchall()
    finally:
        cursor.close()
        con.close()
    return pd.DataFrame(
        linhas, columns=["produto", "descricao", "tipo", "unidade", "quant_caixa"]
    )


def preparar_base(movimentos: pd.DataFrame, produtos: pd.DataFrame) -> pd.DataFrame:
    base = movimentos.merge(produtos, on="produto", how="left")
    base["descricao"] = base["descricao"].fillna("PRODUTO SEM CADASTRO")
    base["tipo"] = base["tipo"].fillna("PA")
    base["unidade"] = base["unidade"].fillna("UND")
    base["quant_caixa"] = pd.to_numeric(base["quant_caixa"], errors="coerce").fillna(1)
    base.loc[base["quant_caixa"].eq(0), "quant_caixa"] = 1
    for coluna in ("vendida", "devolvida", "estornada"):
        base[coluna] = pd.to_numeric(base[coluna], errors="coerce").fillna(0)
    base["caixas_equivalentes"] = base["vendida"] / base["quant_caixa"]
    base["caixas_fechadas"] = (base["vendida"] // base["quant_caixa"]).astype(int)
    base["unidades_parciais"] = (
        base["vendida"] - base["caixas_fechadas"] * base["quant_caixa"]
    ).astype(int)
    base["devolvida_equivalente"] = base["devolvida"] / base["quant_caixa"]
    base["estornada_equivalente"] = base["estornada"] / base["quant_caixa"]
    base = base.rename(columns={
        "filial": "Filial", "canal": "Canal", "produto": "Código",
        "descricao": "Descrição", "tipo": "Tipo", "unidade": "Unidade",
        "ano_mes": "Ano_mes", "quant_caixa": "Quant por caixa",
        "caixas_equivalentes": "Quantidade Vendida (caixas + unidades parciais)",
        "caixas_fechadas": "Quantidade Vendida caixas fechadas",
        "unidades_parciais": "Quantidade Vendida unidades parciais",
        "vendida": "Quantidade Vendida unidades totais",
        "devolvida_equivalente": "Quantidade Devolvida",
        "estornada_equivalente": "Quantidade Estornada",
    })
    return base[COLUNAS].sort_values(
        ["Filial", "Canal", "Código", "Ano_mes"], ignore_index=True
    )


def nome_aba(filial: int) -> str:
    return f"Filial {filial}"[:31]


def criterios(base: pd.DataFrame) -> pd.DataFrame:
    maior_diferenca = (
        base["Quantidade Vendida unidades totais"]
        - (
            base["Quantidade Vendida caixas fechadas"] * base["Quant por caixa"]
            + base["Quantidade Vendida unidades parciais"]
        )
    ).abs().max()
    linhas = [
        ("Período", "01/05/2026 a 31/10/2026: os seis últimos meses completos."),
        ("Separação por filial e canal", "A base reúne tudo; cada filial possui uma única aba e a coluna Canal separa ROTA de ATACADO."),
        ("ROTA", "Vendas cujo vendedor do pedido não é 187 nem 1929."),
        ("ATACADO", "Vendas dos vendedores 187 ou 1929."),
        ("Produtos", "Todos os produtos com quantidade vendida maior que zero no período, filial e canal."),
        ("Bonificações", "Incluídas nos totais de venda."),
        ("Quant por caixa", "QTDECOMPRA do cadastro; zero ou nulo tratado como 1."),
        ("Caixas equivalentes", "Unidades totais ÷ Quant por caixa."),
        ("Caixas fechadas", "Parte inteira de unidades totais ÷ Quant por caixa."),
        ("Unidades parciais", "Resto depois de separar as caixas fechadas."),
        ("Devoluções e estornos", "Exibidos separadamente em caixas equivalentes e não abatidos da venda bruta."),
        ("Validação", f"{len(base):,} linhas; maior diferença na reconciliação: {maior_diferenca:.10f}."),
    ]
    return pd.DataFrame(linhas, columns=["Critério", "Definição"])


def formatar_planilha(caminho: Path) -> None:
    from openpyxl import load_workbook

    workbook = load_workbook(caminho)
    preenchimento = PatternFill("solid", fgColor="1F4E78")
    for planilha in workbook.worksheets:
        planilha.freeze_panes = "A2"
        planilha.auto_filter.ref = planilha.dimensions
        for celula in planilha[1]:
            celula.fill = preenchimento
            celula.font = Font(color="FFFFFF", bold=True)
        for coluna in planilha.columns:
            valores = [len(str(celula.value)) for celula in coluna if celula.value is not None]
            largura = min((max(valores) if valores else 10) + 2, 48)
            planilha.column_dimensions[coluna[0].column_letter].width = largura
    workbook.save(caminho)


def gerar() -> Path:
    movimentos = consultar_movimentos()
    base = preparar_base(movimentos, consultar_produtos())
    resumo = (
        base.groupby(["Filial", "Canal"], as_index=False)
        .agg(
            Produtos=("Código", "nunique"),
            Linhas=("Código", "size"),
            Unidades_vendidas=("Quantidade Vendida unidades totais", "sum"),
            Caixas_equivalentes=("Quantidade Vendida (caixas + unidades parciais)", "sum"),
            Devoluções=("Quantidade Devolvida", "sum"),
            Estornos=("Quantidade Estornada", "sum"),
        )
        .sort_values(["Filial", "Canal"])
    )
    ARQUIVO_SAIDA.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(ARQUIVO_SAIDA, engine="openpyxl") as writer:
        base.to_excel(writer, sheet_name="Base filial e canal", index=False)
        resumo.to_excel(writer, sheet_name="Resumo", index=False)
        for filial, recorte in base.groupby("Filial", sort=True):
            recorte.to_excel(
                writer, sheet_name=nome_aba(int(filial)), index=False
            )
        criterios(base).to_excel(writer, sheet_name="Critérios", index=False)
    formatar_planilha(ARQUIVO_SAIDA)
    print(ARQUIVO_SAIDA)
    print(resumo.to_string(index=False))
    return ARQUIVO_SAIDA


if __name__ == "__main__":
    gerar()
