from __future__ import annotations

from io import BytesIO

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill

from .calculos import calcular_resumo


COLUNAS_EXCEL = {
    "filial": "Filial", "nome_filial": "Nome Filial", "mes": "Mês", "ano": "Ano",
    "tipo_estabelecimento": "Tipo Estabelecimento",
    "nome_tipo_estabelecimento": "Nome Tipo Estabelecimento",
    "equipe": "Equipe", "nome_equipe": "Nome Equipe",
    "fornecedor": "Fornecedor", "nome_fornecedor": "Nome Fornecedor",
    "produto": "Produto", "nome_produto": "Nome Produto", "qtde": "Qtde",
    "venda_liquida": "Venda Líquida",
    "margem_bruta": "Margem Bruta (%) — VALIDAR",
}
LARANJA = "F4B183"
VERDE = "C6E0B4"
CINZA = "D9E1F2"
VERMELHO = "F4CCCC"


def exportar_excel(dados: pd.DataFrame, incluir_tipo_48: bool = False) -> bytes:
    arquivo = BytesIO()
    detalhe = dados.rename(columns=COLUNAS_EXCEL)[list(COLUNAS_EXCEL.values())]
    resumo = calcular_resumo(dados)
    resumo_df = pd.DataFrame([
        {"Indicador": "Linhas detalhadas", "Valor": resumo["linhas"]},
        {"Indicador": "Quantidade", "Valor": resumo["quantidade"]},
        {"Indicador": "Venda líquida", "Valor": resumo["venda"]},
        {"Indicador": "Margem bruta (%) — VALIDAR", "Valor": resumo["margem_pct"]},
        {"Indicador": "Pedidos tipo 48", "Valor": "INCLUÍDOS" if incluir_tipo_48 else "EXCLUÍDOS"},
    ])
    regras = pd.DataFrame([
        {"Status": "CONFIRMADO", "Tema": "Venda Líquida",
         "Regra aplicada / observação": "Valor total é considerado venda líquida: SUM(valor_total)."},
        {"Status": "VALIDAR", "Tema": "Margem Bruta",
         "Regra aplicada / observação":
         "Campo identificado: VIEW_ITEMPEDIDO.MARGEMBRUTA. Como todas as filiais ativas usam custo bruto, o agregado aplica ((SUM(venda) / SUM(custo total)) - 1) × 100. Validar uma amostra com o relatório TOP."},
        {"Status": "A VERIFICAR", "Tema": "Bonificações",
         "Regra aplicada / observação":
         "Permanecem na base e reduzem a margem conforme valor e custo registrados; tratamento definitivo pendente."},
        {"Status": "CONFIRMADO", "Tema": "Devoluções",
         "Regra aplicada / observação": "Não entram no relatório; a origem considerada contém somente vendas."},
        {"Status": "INFORMATIVO", "Tema": "Impostos",
         "Regra aplicada / observação": "Não há dedução ou tratamento adicional de impostos."},
        {"Status": "ALERTA" if incluir_tipo_48 else "CONFIRMADO", "Tema": "Pedidos tipo 48",
         "Regra aplicada / observação":
         ("Incluídos por escolha do usuário; podem afetar a leitura da margem."
          if incluir_tipo_48 else "Excluídos por padrão para não afetar a margem real.")},
    ])
    with pd.ExcelWriter(arquivo, engine="openpyxl") as writer:
        resumo_df.to_excel(writer, sheet_name="Resumo", index=False)
        detalhe.to_excel(writer, sheet_name="Dados", index=False)
        regras.to_excel(writer, sheet_name="Regras_e_escopo", index=False)
        for planilha in writer.book.worksheets:
            planilha.freeze_panes = "A2"
            planilha.auto_filter.ref = planilha.dimensions
            for celula in planilha[1]:
                celula.font = Font(bold=True)
                celula.alignment = Alignment(horizontal="center")
            for coluna in planilha.columns:
                letra = coluna[0].column_letter
                largura = min(max(len(str(c.value or "")) for c in coluna[:200]) + 2, 45)
                planilha.column_dimensions[letra].width = max(largura, 12)
        ws_dados = writer.book["Dados"]
        for titulo in ("Venda Líquida", "Margem Bruta (%) — VALIDAR"):
            indice = list(COLUNAS_EXCEL.values()).index(titulo) + 1
            if titulo.startswith("Margem"):
                ws_dados.cell(1, indice).fill = PatternFill("solid", fgColor=LARANJA)
            for coluna in ws_dados.iter_cols(min_col=indice, max_col=indice, min_row=2):
                for celula in coluna:
                    celula.number_format = '0.00"%"' if titulo.startswith("Margem") else 'R$ #,##0.00'
        ws_resumo = writer.book["Resumo"]
        for linha in ws_resumo.iter_rows():
            if any("VALIDAR" in str(c.value or "").upper() for c in linha):
                for celula in linha:
                    celula.fill = PatternFill("solid", fgColor=LARANJA)
        ws_regras = writer.book["Regras_e_escopo"]
        cores = {"CONFIRMADO": VERDE, "A VERIFICAR": LARANJA, "VALIDAR": LARANJA,
                 "INFORMATIVO": CINZA, "ALERTA": VERMELHO}
        for linha in ws_regras.iter_rows(min_row=2):
            cor = cores.get(str(linha[0].value), CINZA)
            for celula in linha:
                celula.fill = PatternFill("solid", fgColor=cor)
    return arquivo.getvalue()
