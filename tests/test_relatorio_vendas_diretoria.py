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


class RelatorioVendasDiretoriaTest(unittest.TestCase):
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
        dados = pd.DataFrame({"qtde": [2, 3], "venda_liquida": [100.0, 300.0], "margem_bruta": [10.0, 90.0]})
        resumo = calcular_resumo(dados)
        self.assertEqual(resumo["quantidade"], 5)
        self.assertEqual(resumo["margem_pct"], 0.25)

    def test_excel_destaca_campos_pendentes(self):
        linha = {"filial": 1, "nome_filial": "Filial", "mes": 1, "ano": 2026,
                 "tipo_estabelecimento": 21, "nome_tipo_estabelecimento": "Tipo",
                 "equipe": 1, "nome_equipe": "Equipe", "fornecedor": 2,
                 "nome_fornecedor": "Fornecedor", "produto": 3, "nome_produto": "Produto",
                 "qtde": 4.0, "venda_liquida": 100.0, "margem_bruta": 20.0}
        wb = load_workbook(BytesIO(exportar_excel(pd.DataFrame([linha]))))
        ws = wb["Dados"]
        cabecalhos = [c.value for c in ws[1]]
        for titulo in ("Venda Líquida — PENDENTE CONFIRMAÇÃO", "Margem Bruta — PENDENTE CONFIRMAÇÃO"):
            celula = ws.cell(1, cabecalhos.index(titulo) + 1)
            self.assertEqual(celula.fill.fgColor.rgb[-6:], "F4B183")
        self.assertEqual(wb["Pendencias"].max_row, 7)


if __name__ == "__main__":
    unittest.main()
