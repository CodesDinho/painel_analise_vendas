from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .pernod_reembolso import render_analise_pernod_reembolso
from .auditoria_combos import render_auditoria_combos


@dataclass(frozen=True)
class AnaliseExtra:
    """Contrato mínimo de uma análise acoplável ao painel."""

    chave: str
    titulo: str
    destino: str
    renderizar: Callable[[], None]


ANALISES_EXTRAS: tuple[AnaliseExtra, ...] = (
    AnaliseExtra(
        chave="pernod_reembolso",
        titulo="Análise Pernod Reembolso",
        destino="10. Análise Pernod Reembolso",
        renderizar=render_analise_pernod_reembolso,
    ),
    AnaliseExtra(
        chave="auditoria_combos",
        titulo="Auditoria de combos",
        destino="11. Auditoria de combos",
        renderizar=render_auditoria_combos,
    ),
)


def obter_analise_extra(destino: str) -> AnaliseExtra | None:
    return next(
        (analise for analise in ANALISES_EXTRAS if analise.destino == destino),
        None,
    )

