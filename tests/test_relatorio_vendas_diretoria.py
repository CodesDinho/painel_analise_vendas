from datetime import date
from io import BytesIO
from pathlib import Path
import sys
import unittest

import pandas as pd
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analises_extras.relatorio_vendas_diretoria.calculos import (
    calcular_resumo, data_limite_disponivel, periodo_padrao, periodo_por_meses,
    validar_periodo, validar_periodo_autorizado,
)
from analises_extras.relatorio_vendas_diretoria.exportacoes import exportar_excel
from analises_extras.relatorio_vendas_diretoria.consultas import SQL_RELATORIO


class RelatorioVendasDiretoriaTest(unittest.TestCase):
    def test_tipo_48_so_entra_pela_fonte_separada_e_com_autorizacao(self):
        self.assertIn("topsystem_silver.pedidos_48", SQL_RELATORIO)
        self.assertIn("WHERE @incluir_tipo_48", SQL_RELATORIO)

    def test_periodo_padrao_usa_dia_20_mais_recente(self):
        self.assertEqual(periodo_padrao(date(2026, 11, 27)), (date(2026, 11, 1), date(2026, 11, 20)))
        self.assertEqual(data_limite_disponivel(date(2026, 11, 10)), date(2026, 10, 20))

    def test_periodos_autorizaveis_e_limite_de_doze_meses(self):
        self.assertEqual(periodo_por_meses(date(2026, 11, 27), 6), (date(2026, 6, 1), date(2026, 11, 20)))
        self.assertEqual(periodo_por_meses(date(2026, 11, 27), 12), (date(2025, 12, 1), date(2026, 11, 20)))
        erro = validar_periodo(date(2025, 11, 1), date(2026, 11, 20), date(2026, 11, 27))
        self.assertIn("12 meses", erro)
        self.assertIsNone(validar_periodo(date(2025, 12, 1), date(2026, 11, 20), date(2026, 11, 27)))

    def test_datas_livres_respeitam_volume_autorizado(self):
        self.assertIsNone(validar_periodo_autorizado(date(2024, 1, 1), date(2024, 12, 31), 12))
        erro = validar_periodo_autorizado(date(2024, 1, 1), date(2024, 12, 31), 6)
        self.assertIn("12 meses", erro)
        self.assertIn("6 meses", erro)

    def test_resumo_recalcula_percentual_sobre_totais(self):
        dados = pd.DataFrame({
            "qtde": [2, 3], "venda_liquida": [100.0, 300.0],
            "custo_total": [80.0, 240.0], "margem_bruta": [25.0, 25.0],
        })
        resumo = calcular_resumo(dados)
        self.assertEqual(resumo["quantidade"], 5)
        self.assertEqual(resumo["margem"], 80.0)
        self.assertEqual(resumo["margem_pct"], 25.0)

    def test_excel_destaca_campos_pendentes(self):
        linha = {"filial": 1, "nome_filial": "Filial", "mes": 1, "ano": 2026,
                 "tipo_estabelecimento": 21, "nome_tipo_estabelecimento": "Tipo",
                 "equipe": 1, "nome_equipe": "Equipe", "fornecedor": 2,
                 "nome_fornecedor": "Fornecedor", "produto": 3, "nome_produto": "Produto",
                 "qtde": 4.0, "venda_liquida": 100.0, "custo_total": 80.0,
                 "margem_bruta": 25.0}
        wb = load_workbook(BytesIO(exportar_excel(pd.DataFrame([linha]))))
        ws = wb["Dados"]
        cabecalhos = [c.value for c in ws[1]]
        self.assertNotIn("Nome Filial", cabecalhos)
        margem = ws.cell(1, cabecalhos.index("Margem Bruta (%) — VALIDAR") + 1)
        self.assertEqual(margem.fill.fgColor.rgb[-6:], "F4B183")
        self.assertIn("Regras_e_escopo", wb.sheetnames)
        self.assertEqual(wb["Regras_e_escopo"].max_row, 7)

    def test_excel_registra_inclusao_do_tipo_48(self):
        linha = {"filial": 1, "nome_filial": "Filial", "mes": 1, "ano": 2026,
                 "tipo_estabelecimento": 21, "nome_tipo_estabelecimento": "Tipo",
                 "equipe": 1, "nome_equipe": "Equipe", "fornecedor": 2,
                 "nome_fornecedor": "Fornecedor", "produto": 3, "nome_produto": "Produto",
                 "qtde": 4.0, "venda_liquida": 100.0, "custo_total": 80.0,
                 "margem_bruta": 25.0}
        wb = load_workbook(BytesIO(exportar_excel(pd.DataFrame([linha]), incluir_tipo_48=True)))
        regras = wb["Regras_e_escopo"]
        valores = [[celula.value for celula in linha] for linha in regras.iter_rows()]
        self.assertTrue(any("Incluídos por escolha" in str(valor) for linha in valores for valor in linha))


if __name__ == "__main__":
    unittest.main()
