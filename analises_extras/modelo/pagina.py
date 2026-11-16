from __future__ import annotations

import streamlit as st


def render_analise_modelo() -> None:
    """Ponto de entrada obrigatório de uma análise extra."""
    st.title("Nome da análise")
    st.caption("Explique a finalidade e as fontes utilizadas.")

    # Importe recursos compartilhados somente quando forem necessários:
    # from conexoes import cliente_bigquery, cliente_firebird
    # O módulo não deve criar outra autenticação nem armazenar credenciais próprias.
    st.info("Implemente aqui a interface independente da análise.")

