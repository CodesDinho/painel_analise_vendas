from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from .calculos import calcular_resumo, periodo_padrao, validar_periodo
from .consultas import consultar_relatorio
from .exportacoes import exportar_excel


@st.cache_data(ttl=3600, show_spinner=False)
def _carregar(inicio: date, fim: date) -> pd.DataFrame:
    return consultar_relatorio(inicio, fim)


def _moeda(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _filtro_dimensao(
    container, dados: pd.DataFrame, coluna_codigo: str, coluna_nome: str, rotulo: str, chave: str,
) -> list[int]:
    catalogo = (
        dados[[coluna_codigo, coluna_nome]].dropna(subset=[coluna_codigo])
        .drop_duplicates(subset=[coluna_codigo]).sort_values(coluna_codigo)
    )
    nomes = dict(zip(catalogo[coluna_codigo].astype(int), catalogo[coluna_nome].astype(str)))
    opcoes = list(nomes)
    return container.multiselect(
        rotulo, opcoes, format_func=lambda codigo: f"{codigo} — {nomes.get(codigo, 'NÃO IDENTIFICADO')}",
        key=chave,
    )


def render_relatorio_vendas_diretoria() -> None:
    st.title("Relatório de vendas — Diretoria")
    st.caption("Consulta agregada no BigQuery. Período detalhado limitado a três meses.")
    padrao_inicio, padrao_fim = periodo_padrao(date.today())
    c1, c2 = st.columns(2)
    inicio = c1.date_input("Data inicial", padrao_inicio, key="rvd_data_inicio")
    fim = c2.date_input("Data final", padrao_fim, key="rvd_data_fim")
    erro = validar_periodo(inicio, fim, date.today())
    if erro:
        st.error(erro)
        return
    st.markdown(
        """
        <div style="background:#F4B183;padding:12px;border-radius:6px;color:#3b2a12">
        <b>Pendente definição/confirmação:</b> Venda Líquida usa provisoriamente
        <code>SUM(valor_total)</code>. Margem Bruta usa provisoriamente
        <code>SUM(valor_total - valor_custo × quantidade)</code>.
        Os campos permanecem disponíveis na tela e no Excel, destacados em laranja.
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Gerar relatório", type="primary", key="rvd_gerar"):
        try:
            with st.spinner("Consultando e agregando os dados no BigQuery..."):
                st.session_state["rvd_dados"] = _carregar(inicio, fim)
                st.session_state["rvd_periodo"] = (inicio, fim)
        except Exception as exc:
            st.error(f"Não foi possível consultar o BigQuery: {exc}")
            return
    if st.session_state.get("rvd_periodo") != (inicio, fim):
        st.info("Selecione o período e clique em Gerar relatório.")
        return
    dados = st.session_state.get("rvd_dados")
    if dados is None:
        return
    if dados.empty:
        st.warning("Não foram encontrados dados no período selecionado.")
        return
    with st.expander("Filtros do relatório", expanded=True):
        f1, f2 = st.columns(2)
        filiais = _filtro_dimensao(f1, dados, "filial", "nome_filial", "Filial", "rvd_filiais")
        tipos = _filtro_dimensao(
            f2, dados, "tipo_estabelecimento", "nome_tipo_estabelecimento",
            "Tipo de estabelecimento", "rvd_tipos",
        )
        equipes = _filtro_dimensao(f1, dados, "equipe", "nome_equipe", "Equipe", "rvd_equipes")
        fornecedores = _filtro_dimensao(
            f2, dados, "fornecedor", "nome_fornecedor", "Fornecedor", "rvd_fornecedores",
        )
        produtos = _filtro_dimensao(f1, dados, "produto", "nome_produto", "Produto", "rvd_produtos")
    for coluna, selecionados in (
        ("filial", filiais), ("tipo_estabelecimento", tipos), ("equipe", equipes),
        ("fornecedor", fornecedores), ("produto", produtos),
    ):
        if selecionados:
            dados = dados[dados[coluna].isin(selecionados)]
    if dados.empty:
        st.warning("Nenhum registro atende aos filtros selecionados.")
        return
    resumo = calcular_resumo(dados)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Linhas agregadas", f"{resumo['linhas']:,}".replace(",", "."))
    m2.metric("Quantidade", f"{resumo['quantidade']:,.0f}".replace(",", "."))
    m3.metric("🟠 Venda líquida — pendente", _moeda(float(resumo["venda"])))
    m4.metric("🟠 Margem bruta — pendente", _moeda(float(resumo["margem"])))
    exibicao = dados.rename(columns={
        "filial": "Filial", "nome_filial": "Nome Filial", "mes": "Mês", "ano": "Ano",
        "tipo_estabelecimento": "Tipo Estabelecimento",
        "nome_tipo_estabelecimento": "Nome Tipo Estabelecimento",
        "equipe": "Equipe", "nome_equipe": "Nome Equipe",
        "fornecedor": "Fornecedor", "nome_fornecedor": "Nome Fornecedor",
        "produto": "Produto", "nome_produto": "Nome Produto", "qtde": "Qtde",
        "venda_liquida": "🟠 Venda Líquida — pendente",
        "margem_bruta": "🟠 Margem Bruta — pendente",
    })
    st.dataframe(
        exibicao, hide_index=True, use_container_width=True,
        column_config={
            "Qtde": st.column_config.NumberColumn(format="%.0f"),
            "🟠 Venda Líquida — pendente": st.column_config.NumberColumn(format="R$ %.2f"),
            "🟠 Margem Bruta — pendente": st.column_config.NumberColumn(format="R$ %.2f"),
        },
    )
    if st.button("Preparar exportação Excel", key="rvd_preparar_excel"):
        with st.spinner("Preparando o Excel..."):
            excel = exportar_excel(dados)
        st.download_button(
            "Baixar Excel detalhado", data=excel,
            file_name=f"relatorio_vendas_diretoria_{inicio:%Y%m%d}_{fim:%Y%m%d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="rvd_download",
        )
