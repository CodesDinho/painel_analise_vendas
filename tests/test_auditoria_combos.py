from __future__ import annotations

import json
import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openpyxl import load_workbook

from analises_extras.auditoria_combos.calculos import (
    calcular_indicadores, filtrar_apontamentos, normalizar_apontamentos,
    normalizar_codigos,
)
from analises_extras.auditoria_combos.cliente_api import (
    ApiConfig, ComboAuditApiError, carregar_cache, consultar_auditoria,
    salvar_cache, validar_relatorio,
)
from analises_extras.auditoria_combos.exportacoes import exportar_auditoria_excel


def relatorio() -> dict:
    return {
        "schema_version": "1.0",
        "generated_at": "2026-11-16T13:00:00-03:00",
        "scope": "combos_informados",
        "summary": {"erro": 0, "conflito": 1, "alerta": 1, "informativo": 0},
        "total_findings": 2,
        "findings": [
            {
                "combo": 240035662,
                "nome": "VCT BLACK 12+1",
                "status": "CONFLITO",
                "regra": "COMBOS_ATIVOS_SOBREPOSTOS",
                "mensagem": "Combos podem disputar produtos.",
                "acao_recomendada": "Direção deve definir qual prevalece.",
                "evidencias": {
                    "combo_conflitante": 240035672,
                    "nome_conflitante": "VCT BLACK NOVO",
                    "produtos": [1901, 1902],
                    "filiais": [4],
                },
                "data_analise": "2026-11-16",
            },
            {
                "combo": 240034782,
                "nome": "SALTON GIN THEROS 12+1",
                "status": "ALERTA",
                "regra": "PRECO_COMBO_ACIMA_TABELA",
                "produto": 2793,
                "valor_combo": 26.77,
                "valor_referencia": 25.90,
                "mensagem": "Preço acima da referência.",
                "acao_recomendada": "Confirmar regra comercial.",
                "evidencias": {"tabela_preco": 170, "grupo": 6905},
                "data_analise": "2026-11-16",
            },
        ],
        "correction_workflow": {
            "channel": "slack",
            "command": "/combos-editar",
            "api_write_supported": False,
            "requires_human_approval": True,
        },
    }


def pagina(numero: int, total: int, codigos: list[int], findings: list[dict]) -> dict:
    resultado = relatorio()
    resultado["generated_at"] = f"2026-11-16T13:0{numero}:00-03:00"
    resultado["findings"] = findings
    resultado["total_findings"] = len(findings)
    resultado["combo_codes"] = codigos
    resultado["pagination"] = {
        "page": numero,
        "page_size": 25,
        "total_combos": total,
        "returned_combos": len(codigos),
    }
    return resultado


class AuditoriaCombosTests(unittest.TestCase):
    def test_normaliza_codigos_e_rejeita_invalidos(self):
        self.assertEqual(
            normalizar_codigos("240034782, 240034782; 240032879"),
            [240034782, 240032879],
        )
        with self.assertRaisesRegex(ValueError, "inválidos"):
            normalizar_codigos("240034782, ABC")

    def test_valida_schema_e_findings(self):
        self.assertEqual(validar_relatorio(relatorio())["schema_version"], "1.0")
        invalido = relatorio() | {"schema_version": "2.0"}
        with self.assertRaisesRegex(ComboAuditApiError, "incompatível"):
            validar_relatorio(invalido)

    def test_normaliza_e_filtra_apontamentos(self):
        dados = normalizar_apontamentos(relatorio())
        self.assertEqual(len(dados), 2)
        self.assertEqual(dados.iloc[0]["combo_conflitante"], 240035672)
        filtrado = filtrar_apontamentos(
            dados, severidades=["ALERTA"], busca="salton", produto="2793"
        )
        self.assertEqual(filtrado["combo"].tolist(), [240034782])
        indicadores = calcular_indicadores(dados)
        self.assertEqual(indicadores["combos"], 2)
        self.assertEqual(indicadores["conflito"], 1)

    def test_consulta_multiplos_combos_e_remove_duplicidade(self):
        config = ApiConfig("http://auditoria.test")
        resposta = relatorio()
        with patch(
            "analises_extras.auditoria_combos.cliente_api._get_json",
            side_effect=[resposta, resposta],
        ) as get:
            combinado = consultar_auditoria(config, [240034782, 240034782, 240032879])
        self.assertEqual(get.call_count, 2)
        self.assertEqual(combinado["total_findings"], 2)

    def test_consulta_geral_percorre_paginas_e_exporta_todos_os_achados(self):
        primeiro = relatorio()["findings"][0]
        segundo = relatorio()["findings"][1]
        respostas = [
            pagina(1, 27, list(range(1, 26)), [primeiro]),
            pagina(2, 27, [26, 27], [primeiro, segundo]),
        ]
        config = ApiConfig("http://auditoria.test", token="segredo")
        with patch(
            "analises_extras.auditoria_combos.cliente_api._get_json",
            side_effect=respostas,
        ) as get:
            combinado = consultar_auditoria(config)
        self.assertEqual(get.call_count, 2)
        self.assertEqual(combinado["pagination"]["returned_combos"], 27)
        self.assertEqual(combinado["pagination"]["pages_fetched"], 2)
        self.assertEqual(combinado["total_findings"], 2)
        self.assertEqual(combinado["generated_at"], respostas[1]["generated_at"])
        self.assertEqual(combinado["correction_workflow"]["command"], "/combos-editar")

    def test_falha_em_pagina_nao_retorna_resultado_parcial(self):
        config = ApiConfig("http://auditoria.test", token="segredo")
        with patch(
            "analises_extras.auditoria_combos.cliente_api._get_json",
            side_effect=[
                pagina(1, 27, list(range(1, 26)), relatorio()["findings"][:1]),
                ComboAuditApiError("HTTP 503"),
            ],
        ):
            with self.assertRaisesRegex(ComboAuditApiError, "503"):
                consultar_auditoria(config)

    def test_token_ausente_e_retentativa_controlada_sem_expor_credencial(self):
        from analises_extras.auditoria_combos.cliente_api import _get_json

        with self.assertRaisesRegex(ComboAuditApiError, "TOKEN") as erro:
            _get_json(ApiConfig("http://auditoria.test"), "/api/combo-rules/version")
        self.assertNotIn("segredo", str(erro.exception))

        config = ApiConfig("http://auditoria.test", token="segredo")
        for codigo in (429, 503, 504):
            falha = HTTPError("http://auditoria.test", codigo, "temporário", {}, None)
            with self.subTest(codigo=codigo), patch(
                "analises_extras.auditoria_combos.cliente_api.urlopen",
                side_effect=[falha, falha],
            ), patch("analises_extras.auditoria_combos.cliente_api.time.sleep") as espera:
                with self.assertRaisesRegex(ComboAuditApiError, str(codigo)):
                    _get_json(config, "/api/combo-rules/version")
                espera.assert_called_once_with(1.0)

    def test_cliente_nao_importa_firebird_nem_possui_escrita_erp(self):
        caminho = Path(__file__).parents[1] / "analises_extras" / "auditoria_combos" / "cliente_api.py"
        fonte = caminho.read_text(encoding="utf-8").upper()
        for importacao in ("IMPORT FDB", "IMPORT FIREBIRD", "FROM FDB", "FROM FIREBIRD"):
            self.assertNotIn(importacao, fonte)
        for comando in ("INSERT INTO", "UPDATE ", "DELETE FROM"):
            self.assertNotIn(comando, fonte)

    def test_cache_preserva_relatorio_valido(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "auditoria.json"
            salvar_cache(relatorio(), {"rules_version": "2026.11"}, caminho)
            cache = carregar_cache(caminho)
        self.assertIsNotNone(cache)
        self.assertEqual(cache["rules_version"]["rules_version"], "2026.11")
        self.assertEqual(cache["report"]["total_findings"], 2)
        self.assertIn("cached_at", cache)

    def test_exportacao_excel(self):
        dados = normalizar_apontamentos(relatorio())
        conteudo = exportar_auditoria_excel(
            dados, relatorio(), {"rules_version": "2026.11"}, False, None
        )
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "auditoria.xlsx"
            caminho.write_bytes(conteudo)
            workbook = load_workbook(caminho, read_only=True, data_only=True)
            try:
                self.assertEqual(workbook.sheetnames, ["Apontamentos", "Metadados"])
                self.assertEqual(workbook["Apontamentos"].max_row, 3)
                metadados = list(workbook["Metadados"].values)
                self.assertIn(("Comando de correção", "/combos-editar"), metadados)
            finally:
                workbook.close()


if __name__ == "__main__":
    unittest.main()
