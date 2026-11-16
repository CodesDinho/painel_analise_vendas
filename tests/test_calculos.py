from datetime import date
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from combos import gerar_modelo_sql_configuracao_cotas, normalizar_codigos_combos
from dados import (
    adicionar_origem_analise, analisar_mix, clientes_dormentes,
    comparar_volume, filtrar_carteira_por_origem, indicadores_base_televendas,
    periodos_equivalentes,
)


def base_exemplo() -> pd.DataFrame:
    df = pd.DataFrame([
        ("2025-01-10", 1, 10, 100, 2.0, "Pernod"),
        ("2025-01-10", 1, 10, 101, 2.0, "Pernod"),
        ("2026-01-10", 1, 10, 100, 1.0, "Pernod"),
        ("2026-07-29", 2, 10, 200, 3.0, "Campari"),
    ], columns=["data_venda", "cliente_codigo", "equipe_codigo", "produto_codigo", "volume", "industria"])
    df["data_venda"] = pd.to_datetime(df.data_venda)
    df["unidades"] = df.volume
    df["faturamento"] = [100.0, 100.0, 80.0, 150.0]
    return df


def executar() -> None:
    df = base_exemplo()
    datas = (date(2025, 1, 1), date(2025, 7, 30), date(2026, 1, 1), date(2026, 7, 30))
    assert comparar_volume(df, datas).query("cliente_codigo == 1").iloc[0].classificacao == "QUEDA"
    mix_pernod = analisar_mix(df, datas).query("industria == 'Pernod'").iloc[0]
    assert mix_pernod.queda_mix == -1
    assert mix_pernod.queda_faturamento == -120.0
    assert mix_pernod.situacao == "QUEDA DE MIX E FATURAMENTO"
    dormentes_todas = clientes_dormentes(df, date(2026, 7, 30), 30)
    assert set(map(tuple, dormentes_todas[["cliente_codigo", "industria"]].to_numpy())) == {
        (1, "Pernod"), (1, "Campari"), (2, "Pernod"),
    }
    dormentes_pernod = clientes_dormentes(
        df, date(2026, 7, 30), 30, ["Pernod"]
    ).set_index("cliente_codigo")
    assert set(dormentes_pernod.index) == {1, 2}
    assert dormentes_pernod.loc[2, "industria"] == "Pernod"
    assert pd.isna(dormentes_pernod.loc[2, "ultima_compra"])
    assert dormentes_pernod.loc[2, "unidades_historicas"] == 0
    assert dormentes_pernod.loc[2, "dias_com_compra"] == 0
    assert periodos_equivalentes(date(2024, 2, 29))[1] == date(2023, 2, 28)

    vendas = pd.DataFrame({
        "cliente_codigo": pd.Series([1, 2, 3], dtype="Int64"),
        "quantidade_vendedores_carteira": pd.Series([1, 0, 1], dtype="Int64"),
    })
    televendas = pd.DataFrame({
        "cliente_codigo": pd.Series([1, 2], dtype="Int64"),
        "televendas_ultima_compra": pd.to_datetime(["2026-06-01", "2026-05-01"]),
        "televendas_tem_vendedor": pd.Series([1, 0], dtype="Int64"),
        "televendas_tem_rota": pd.Series([0, 0], dtype="Int64"),
    })
    origens = adicionar_origem_analise(vendas, televendas).set_index("cliente_codigo")
    assert origens.loc[1, "tipo_analise"] == "Indústria+televendas"
    assert origens.loc[2, "tipo_analise"] == "Base televendas"
    assert origens.loc[3, "tipo_analise"] == "Compra indústria"
    assert indicadores_base_televendas(televendas) == {
        "verde": 2, "verde_sem_vendedor": 1, "verde_sem_rota": 2,
    }
    resultado_origens = pd.DataFrame({
        "cliente_codigo": [1, 2, 3, 4],
        "tipo_analise": [
            "Compra indústria", "Compra indústria",
            "Base televendas", "Indústria+televendas",
        ],
        "quantidade_vendedores_carteira": [1, 0, 0, 1],
    })
    com_vendedor = filtrar_carteira_por_origem(
        resultado_origens, "Com vendedor alocado"
    )
    sem_vendedor = filtrar_carteira_por_origem(
        resultado_origens, "Sem vendedor alocado"
    )
    assert com_vendedor.cliente_codigo.tolist() == [1, 3, 4]
    assert sem_vendedor.cliente_codigo.tolist() == [2, 3, 4]
    assert normalizar_codigos_combos("240035590, 240035279\n240035590") == [
        240035279, 240035590,
    ]
    modelo_cotas = gerar_modelo_sql_configuracao_cotas([240035670, 240035669])
    assert "INSERT INTO COMBOFILIAL" in modelo_cotas
    assert "240035669" in modelo_cotas and "240035670" in modelo_cotas
    assert "<FILIAL>" in modelo_cotas
    assert "JOIN COTA" in modelo_cotas
    try:
        normalizar_codigos_combos("240035590, ABC")
        raise AssertionError("Código de combo inválido deveria falhar")
    except ValueError:
        pass


if __name__ == "__main__":
    executar()
    print("Testes de cálculo concluídos.")
