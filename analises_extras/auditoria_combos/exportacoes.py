from __future__ import annotations

from io import BytesIO
from typing import Any

import pandas as pd


def exportar_auditoria_excel(
    dados: pd.DataFrame, relatorio: dict[str, Any], versao: dict[str, Any] | None,
    origem_cache: bool, cache_em: str | None,
) -> bytes:
    arquivo = BytesIO()
    fluxo = relatorio.get("correction_workflow") or {}
    paginacao = relatorio.get("pagination") or {}
    resumo = pd.DataFrame([
        {"Indicador": "Schema", "Valor": relatorio.get("schema_version")},
        {"Indicador": "Escopo", "Valor": relatorio.get("scope")},
        {"Indicador": "Gerado em", "Valor": relatorio.get("generated_at")},
        {"Indicador": "Origem", "Valor": "Cache local" if origem_cache else "API"},
        {"Indicador": "Cache salvo em", "Valor": cache_em},
        {"Indicador": "Versão das regras", "Valor": (versao or {}).get("rules_version") or (versao or {}).get("version")},
        {"Indicador": "Total de apontamentos", "Valor": len(dados)},
        {"Indicador": "Combos processados", "Valor": paginacao.get("returned_combos")},
        {"Indicador": "Total de combos", "Valor": paginacao.get("total_combos")},
        {"Indicador": "Páginas consultadas", "Valor": paginacao.get("pages_fetched")},
        {"Indicador": "Comando de correção", "Valor": fluxo.get("command")},
        {"Indicador": "API de escrita disponível", "Valor": fluxo.get("api_write_supported")},
        {"Indicador": "Exige aprovação humana", "Valor": fluxo.get("requires_human_approval")},
    ])
    with pd.ExcelWriter(arquivo, engine="openpyxl") as writer:
        dados.to_excel(writer, sheet_name="Apontamentos", index=False)
        resumo.to_excel(writer, sheet_name="Metadados", index=False)
        for planilha in writer.book.worksheets:
            planilha.freeze_panes = "A2"
            planilha.auto_filter.ref = planilha.dimensions
            for coluna in planilha.columns:
                largura = max(
                    (len(str(celula.value)) for celula in coluna if celula.value is not None),
                    default=10,
                )
                planilha.column_dimensions[coluna[0].column_letter].width = min(
                    largura + 2, 60
                )
    return arquivo.getvalue()
