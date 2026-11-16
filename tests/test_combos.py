from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from combo_classificacoes import (
    carregar_classificacoes, salvar_classificacao, sugerir_classificacao,
)
from combo_regras import exige_vin_esp, validar_titulo_combo
from combos_dinamicos import _adicionar_filtro_ie
from combo_criacao import (
    assinatura_formulario, decimal_brasileiro, executar_etapas_transacionais, normalizar_clientes,
    preparar_contexto_clientes, preparar_plano, registrar_erro_criacao,
    transportar_clientes_para_estado, validar_cabecalho, validar_itens,
)


class ConexaoFalsa:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def executar() -> None:
    condicoes_ie: list[str] = []
    _adicionar_filtro_ie("Todos", condicoes_ie)
    assert condicoes_ie == []
    _adicionar_filtro_ie("Sim", condicoes_ie)
    assert condicoes_ie[-1].endswith("NOT IN ('', 'ISENTO')")
    condicoes_ie = []
    _adicionar_filtro_ie("Não", condicoes_ie)
    assert condicoes_ie[-1].endswith("IN ('', 'ISENTO')")

    assert validar_titulo_combo("REDE BISTEK PR", "Rede") == (True, "OK")
    assert not validar_titulo_combo("BISTEK REDE PR", "Rede")[0]
    assert validar_titulo_combo("VODKA CATEGORIA M SC", "Manutenção") == (True, "OK")
    assert validar_titulo_combo(
        "PRINGLES 10 X 1 M PR SC", "Manutenção"
    ) == (True, "OK")
    assert not validar_titulo_combo("VODKA CATEGORIA SC M", "Manutenção")[0]
    assert validar_titulo_combo("D POSITIVACAO SC", "Dormente positivação") == (True, "OK")
    assert validar_titulo_combo("D VOLUME PR", "Dormente volume") == (True, "OK")
    assert validar_titulo_combo("D VOLUME RS", "Dormente volume") == (True, "OK")
    assert validar_titulo_combo("D POSITIVACAO SP", "Dormente positivação") == (True, "OK")
    assert validar_titulo_combo("VODKA CATEGORIA M RS", "Manutenção") == (True, "OK")
    assert validar_titulo_combo(
        "ESPUMANTE CATEGORIA VIN/ESP SP", "Tabela", True
    ) == (True, "OK")
    falha_estado = validar_titulo_combo("D VOLUME RJ", "Dormente volume")
    assert not falha_estado[0]
    assert "Estado PR/SC/RS/SP deve estar no final" in falha_estado[1]
    assert validar_titulo_combo(
        "C2 PERNOD - D POSITIVACAO SC", "Dormente positivação"
    ) == (True, "OK")
    assert validar_titulo_combo(
        "C2 PERNOD - D VOLUME PR", "Dormente volume"
    ) == (True, "OK")
    assert validar_titulo_combo(
        "CASILLERO VIN/ESP PR", "Não classificado", True
    ) == (True, "OK")
    assert not validar_titulo_combo(
        "CASILLERO PR VIN/ESP", "Não classificado", True
    )[0]
    assert exige_vin_esp(["Xarope Monin 700 ml"])
    assert exige_vin_esp(["Categoria Água"])
    assert not exige_vin_esp(["Vodka Absolut"])
    assert sugerir_classificacao("REDE BISTEK") == "Rede"
    assert sugerir_classificacao("D POSITIVAÇÃO PR") == "Dormente positivação"
    assert sugerir_classificacao("D POSITICAVAO PR") == "Dormente positivação"
    assert sugerir_classificacao("C1 CAMPARI GROUP - D  POSITIVACAO - SC") == "Dormente positivação"
    assert sugerir_classificacao("D VOLUME SC") == "Dormente volume"
    assert sugerir_classificacao("PERNOD M 24 UNIDADES") == "Manutenção"
    assert sugerir_classificacao("M CAMPARI SC") == "Manutenção"
    assert sugerir_classificacao("COMBO CAMPARI M") == "Manutenção"
    assert sugerir_classificacao("COMBO CAMPARI T") == "Tabela"
    assert sugerir_classificacao("COMBO CAMPARI T   ") == "Tabela"
    assert sugerir_classificacao("D VOLUME T") == "Dormente volume"
    assert sugerir_classificacao("COMBO MIX CAMPARI") == "MIX"
    assert sugerir_classificacao("CAMPARI MIX") == "MIX"
    assert sugerir_classificacao("COMBO M MIX CAMPARI") == "Manutenção"
    assert sugerir_classificacao("M MIX CAMPARI") == "Manutenção"
    assert sugerir_classificacao("D POSITIVACAO MIX") == "Dormente positivação"
    assert sugerir_classificacao("COMBO NORMAL") == "Não classificado"
    assert sugerir_classificacao("D VOLUME M SC") == "Dormente volume"
    assert sugerir_classificacao("POSITIVAÇÃO PR") == "Não classificado"
    assert sugerir_classificacao("VOLUME SC") == "Não classificado"
    assert sugerir_classificacao("COMBO GENÉRICO") == "Não classificado"

    with TemporaryDirectory() as pasta:
        base = Path(pasta)
        arquivo = base / "classificacoes.json"
        auditoria = base / "auditoria.jsonl"
        instante = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
        salvar_classificacao(10, "Rede", "teste", arquivo, auditoria, instante)
        salvar_classificacao(20, "Não classificado", "teste", arquivo, auditoria, instante)
        salvar_classificacao(10, "Dormente volume", "teste2", arquivo, auditoria, instante)
        dados = carregar_classificacoes(arquivo)
        assert dados["10"]["classificacao"] == "Dormente volume"
        assert dados["20"]["classificacao"] == "Não classificado"
        assert not arquivo.with_suffix(".json.tmp").exists()
        eventos = [json.loads(linha) for linha in auditoria.read_text(encoding="utf-8").splitlines()]
        assert eventos[-1]["valor_anterior"] == "Rede"
        assert eventos[-1]["valor_novo"] == "Dormente volume"
        legado = base / "legado.json"
        legado.write_text(
            json.dumps({"30": {"classificacao": "Outro tipo"}}), encoding="utf-8"
        )
        assert carregar_classificacoes(legado)["30"]["classificacao"] == "Não classificado"
        legado_manutencao = base / "legado_manutencao.json"
        legado_manutencao.write_text(
            json.dumps({"31": {"classificacao": "Classificação"}}), encoding="utf-8"
        )
        assert carregar_classificacoes(legado_manutencao)["31"]["classificacao"] == "Manutenção"
        log_erros = base / "erros.jsonl"
        registrar_erro_criacao(
            "teste", "password=segredo falhou", "teste", log_erros
        )
        evento_erro = json.loads(log_erros.read_text(encoding="utf-8"))
        assert "segredo" not in evento_erro["erro"]

    assert validar_cabecalho("Combo", date(2026, 8, 1), date(2026, 8, 31)) == []
    assert validar_cabecalho("Combo", date(2026, 8, 31), date(2026, 8, 1))
    assert decimal_brasileiro("1.234,56") == decimal_brasileiro("1234.56")
    assert decimal_brasileiro("-1") < 0

    itens = pd.DataFrame([
        {"grupo_combo": "G1", "quantidade_inicial": "1", "quantidade_final": "5", "produto_codigo": 100, "valor": "10,50"},
        {"grupo_combo": "G1", "quantidade_inicial": "5", "quantidade_final": "8", "produto_codigo": 100, "valor": "11,00"},
        {"grupo_combo": "G1", "quantidade_inicial": "1", "quantidade_final": "5", "produto_codigo": 100, "valor": "10,50"},
        {"grupo_combo": "G2", "quantidade_inicial": "0", "quantidade_final": "2", "produto_codigo": 999, "valor": "-1"},
    ])
    validado, erros = validar_itens(itens, {100: "Produto válido"})
    assert erros
    assert validado["erros"].str.contains("duplicada").any()
    assert validado["erros"].str.contains("conflitante").any()
    assert validado["erros"].str.contains("positiva").any()
    assert validado["erros"].str.contains("negativo").any()
    assert validado["erros"].str.contains("não encontrado").any()

    clientes = normalizar_clientes([3, "2", 3, None, -1, "x"])
    assert clientes == [2, 3]
    contexto = preparar_contexto_clientes("Queda de volume anual", [3, 2, 3])
    assert contexto == {
        "origem": "Queda de volume anual", "clientes": [2, 3],
        "assinatura_clientes": (2, 3),
    }
    estado = {}
    transportar_clientes_para_estado(estado, "Queda de positivação", [3, 2, 3])
    assert estado["combo_form_aberto"] is True
    assert estado["combo_form_clientes"] == [2, 3]
    assert estado["combo_form_assinatura_clientes"] == (2, 3)
    assinatura_a = assinatura_formulario(
        "Combo", date(2026, 8, 1), date(2026, 8, 31),
        "Não classificado", pd.DataFrame([{"produto_codigo": 100}]), [2, 3],
    )
    assinatura_b = assinatura_formulario(
        "Combo alterado", date(2026, 8, 1), date(2026, 8, 31),
        "Não classificado", pd.DataFrame([{"produto_codigo": 100}]), [2, 3],
    )
    assert assinatura_a != assinatura_b

    itens_ok, erros_ok = validar_itens(pd.DataFrame([{
        "grupo_combo": "G1", "quantidade_inicial": "1",
        "quantidade_final": "2", "produto_codigo": 100, "valor": "9,90",
    }]), {100: "Produto válido"})
    assert not erros_ok
    plano = preparar_plano(
        "Teste", date(2026, 8, 1), date(2026, 8, 31),
        "Não classificado", itens_ok, [2, 2, 3], "Criação do zero", [1, 2, 2],
        {1: 101, 2: 102},
    )
    assert plano["quantidade_grupos"] == 1
    assert plano["quantidade_itens"] == 1
    assert plano["quantidade_clientes"] == 2
    assert plano["quantidade_filiais"] == 2
    assert plano["codigo"] is None
    assert plano["codigo_gerado_pelo_erp"] is True
    assert plano["filiais"] == [1, 2]
    assert plano["cotas_filiais"] == {1: 101, 2: 102}
    assert "COMBOFILIAL" in plano["tabelas"]
    assert "ITEMCOTACOMBOCLIENTE" in plano["tabelas"]
    assert plano["gravacao_habilitada"] is False

    conexao = ConexaoFalsa()
    try:
        executar_etapas_transacionais(
            conexao, [lambda _: None, lambda _: (_ for _ in ()).throw(RuntimeError("falha"))]
        )
        raise AssertionError("A falha deveria ser propagada")
    except RuntimeError:
        pass
    assert conexao.commits == 0 and conexao.rollbacks == 1

    conexao_ok = ConexaoFalsa()
    executar_etapas_transacionais(conexao_ok, [lambda _: None])
    assert conexao_ok.commits == 1 and conexao_ok.rollbacks == 0


if __name__ == "__main__":
    executar()
    print("Testes de combos concluídos.")
