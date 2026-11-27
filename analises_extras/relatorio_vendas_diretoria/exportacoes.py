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
    "venda_liquida": "Venda Líquida — PENDENTE CONFIRMAÇÃO",
    "margem_bruta": "Margem Bruta — PENDENTE CONFIRMAÇÃO",
}
LARANJA = "F4B183"


def exportar_excel(dados: pd.DataFrame) -> bytes:
    arquivo = BytesIO()
    detalhe = dados.rename(columns=COLUNAS_EXCEL)[list(COLUNAS_EXCEL.values())]
    resumo = calcular_resumo(dados)
    resumo_df = pd.DataFrame([
        {"Indicador": "Linhas detalhadas", "Valor": resumo["linhas"]},
        {"Indicador": "Quantidade", "Valor": resumo["quantidade"]},
        {"Indicador": "Venda líquida — PENDENTE CONFIRMAÇÃO", "Valor": resumo["venda"]},
        {"Indicador": "Margem bruta — PENDENTE CONFIRMAÇÃO", "Valor": resumo["margem"]},
        {"Indicador": "Margem bruta % — PENDENTE CONFIRMAÇÃO", "Valor": resumo["margem_pct"]},
    ])
    pendencias = pd.DataFrame([
        {"Tema": "Venda Líquida", "Pergunta para homologação":
         "valor_total já representa venda líquida contábil ou ainda exige descontos e impostos?",
         "Tratamento provisório": "SUM(vendas.valor_total)"},
        {"Tema": "Fórmula da Margem Bruta", "Pergunta para homologação":
         "o custo correto é valor_custo × quantidade e a margem deve ser antes ou depois dos impostos?",
         "Tratamento provisório": "SUM(valor_total - valor_custo × quantidade)"},
        {"Tema": "Bonificações", "Pergunta para homologação":
         "itens bonificados devem reduzir a margem, ser excluídos ou aparecer em indicador separado?",
         "Tratamento provisório": "permanecem no resultado conforme valor e custo registrados"},
        {"Tema": "Devoluções", "Pergunta para homologação":
         "qual origem identifica devoluções e elas devem estornar venda, custo e quantidade?",
         "Tratamento provisório": "não há tratamento adicional além do sinal gravado na fato"},
        {"Tema": "Impostos", "Pergunta para homologação":
         "quais tributos devem ser deduzidos: ICMS, ICMS-ST, PIS, COFINS, IPI ou outros?",
         "Tratamento provisório": "nenhuma dedução adicional"},
        {"Tema": "Pedidos tipo 48", "Pergunta para homologação":
         "devem ser excluídos, incorporados à venda regular ou apresentados separadamente?",
         "Tratamento provisório": "excluídos do relatório"},
    ])
    with pd.ExcelWriter(arquivo, engine="openpyxl") as writer:
        resumo_df.to_excel(writer, sheet_name="Resumo", index=False)
        detalhe.to_excel(writer, sheet_name="Dados", index=False)
        pendencias.to_excel(writer, sheet_name="Pendencias", index=False)
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
        for titulo in ("Venda Líquida — PENDENTE CONFIRMAÇÃO", "Margem Bruta — PENDENTE CONFIRMAÇÃO"):
            indice = list(COLUNAS_EXCEL.values()).index(titulo) + 1
            ws_dados.cell(1, indice).fill = PatternFill("solid", fgColor=LARANJA)
            for coluna in ws_dados.iter_cols(min_col=indice, max_col=indice, min_row=2):
                for celula in coluna:
                    celula.number_format = 'R$ #,##0.00'
        for planilha_nome in ("Resumo", "Pendencias"):
            ws = writer.book[planilha_nome]
            for linha in ws.iter_rows():
                if planilha_nome == "Pendencias" or any("PENDENTE" in str(c.value or "").upper() for c in linha):
                    for celula in linha:
                        celula.fill = PatternFill("solid", fgColor=LARANJA)
    return arquivo.getvalue()
