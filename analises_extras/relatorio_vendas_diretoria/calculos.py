from __future__ import annotations

from datetime import date

import pandas as pd


MAX_MESES_DETALHADOS = 12
PERIODOS_PERMITIDOS = (1, 3, 6, 12)


def data_limite_disponivel(hoje: date) -> date:
    """Retorna o dia 20 mais recente disponível para o relatório."""
    if hoje.day >= 20:
        return date(hoje.year, hoje.month, 20)
    if hoje.month == 1:
        return date(hoje.year - 1, 12, 20)
    return date(hoje.year, hoje.month - 1, 20)


def periodo_padrao(hoje: date) -> tuple[date, date]:
    fim = data_limite_disponivel(hoje)
    return date(fim.year, fim.month, 1), fim


def periodo_por_meses(hoje: date, meses: int) -> tuple[date, date]:
    if meses not in PERIODOS_PERMITIDOS:
        raise ValueError("O período deve ser de 1, 3, 6 ou 12 meses.")
    fim = data_limite_disponivel(hoje)
    indice = fim.year * 12 + fim.month - 1 - (meses - 1)
    inicio = date(indice // 12, indice % 12 + 1, 1)
    return inicio, fim


def quantidade_meses(inicio: date, fim: date) -> int:
    return (fim.year - inicio.year) * 12 + fim.month - inicio.month + 1


def validar_periodo(inicio: date, fim: date, hoje: date) -> str | None:
    if inicio > fim:
        return "A data inicial não pode ser posterior à data final."
    if fim > data_limite_disponivel(hoje):
        return "A data final não pode ultrapassar o dia 20 mais recente disponível."
    if quantidade_meses(inicio, fim) > MAX_MESES_DETALHADOS:
        return "A consulta e a exportação detalhadas estão limitadas a 12 meses."
    return None


def calcular_resumo(dados: pd.DataFrame) -> dict[str, float | int]:
    if dados.empty:
        return {"linhas": 0, "quantidade": 0.0, "venda": 0.0, "margem": 0.0, "margem_pct": 0.0}
    venda = float(dados["venda_liquida"].sum())
    margem = float(dados["margem_bruta"].sum())
    return {
        "linhas": len(dados),
        "quantidade": float(dados["qtde"].sum()),
        "venda": venda,
        "margem": margem,
        "margem_pct": margem / venda if venda else 0.0,
    }
