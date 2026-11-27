from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from .calculos import (
    calcular_resumo, data_limite_disponivel, periodo_por_meses,
    quantidade_meses, validar_periodo, validar_periodo_autorizado,
)
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


def _atualizar_datas_do_periodo() -> None:
    meses = st.session_state["rvd_meses_autorizados"]
    inicio, fim = periodo_por_meses(date.today(), meses)
    st.session_state["rvd_data_inicio"] = inicio
    st.session_state["rvd_data_fim"] = fim


def render_relatorio_vendas_diretoria() -> None:
    st.title("Relatório de vendas — Diretoria")
    st.caption("Escolha e autorize o volume antes de consultar o BigQuery e preparar o Excel.")
    tempos = {
        1: "consulta ~7 s; Excel ~6 s; total ~13 s",
        3: "consulta ~7 s; Excel ~20 s; total ~27 s",
        6: "consulta ~8 s; Excel ~52 s; total ~60 s",
        12: "consulta ~9 s; Excel ~95 s; total ~104 s",
    }
    if "rvd_meses_autorizados" not in st.session_state:
        st.session_state["rvd_meses_autorizados"] = 1
    if "rvd_data_inicio" not in st.session_state or "rvd_data_fim" not in st.session_state:
        _atualizar_datas_do_periodo()
    meses = st.radio(
        "Qual período você autoriza gerar?",
        options=[1, 3, 6, 12], horizontal=True,
        format_func=lambda valor: f"{valor} {'mês' if valor == 1 else 'meses'}",
        key="rvd_meses_autorizados",
        on_change=_atualizar_datas_do_periodo,
    )
    st.caption(
        "Tempos médios — 1 mês: ~13 s  |  3 meses: ~27 s  |  "
        "6 meses: ~60 s  |  12 meses: ~104 s"
    )
    d1, d2, d3 = st.columns([1, 1, 1.35])
    inicio = d1.date_input(
        "Data inicial", key="rvd_data_inicio", max_value=data_limite_disponivel(date.today()),
    )
    fim = d2.date_input(
        "Data final", key="rvd_data_fim", max_value=data_limite_disponivel(date.today()),
    )
    meses_solicitados = quantidade_meses(inicio, fim)
    d3.markdown(
        f"""
        <div style="margin-top:1.75rem;padding:.55rem .75rem;background:#e8f1fb;
                    border-radius:.4rem;line-height:1.25">
        <small><b>Período que será consultado</b><br>
        {inicio:%d/%m/%Y} a {fim:%d/%m/%Y}<br>
        {meses_solicitados} mês(es) de {meses} autorizado(s)</small>
        </div>
        """,
        unsafe_allow_html=True,
    )
    erro = validar_periodo(inicio, fim, date.today()) or validar_periodo_autorizado(
        inicio, fim, meses,
    )
    if erro:
        st.error(erro)
        return
    with st.expander("🟠 Pendências de definição/confirmação da Controladoria", expanded=False):
        st.markdown(
            """
            <div style="background:#F4B183;padding:10px;border-radius:6px;color:#3b2a12">
            <b>Venda Líquida:</b> confirmar se <code>valor_total</code> já é líquido contábil.<br>
            <b>Margem Bruta:</b> confirmar custo × quantidade e se a margem é antes ou após impostos.<br>
            <b>Bonificações:</b> decidir se reduzem a margem, são excluídas ou exibidas separadamente.<br>
            <b>Devoluções:</b> definir a origem e se estornam venda, custo e quantidade.<br>
            <b>Impostos:</b> definir quais tributos serão deduzidos.<br>
            <b>Pedidos tipo 48:</b> decidir entre excluir, incorporar ou apresentar separadamente.<br>
            Tratamento provisório: venda = <code>SUM(valor_total)</code>; margem =
            <code>SUM(valor_total - valor_custo × quantidade)</code>; tipo 48 excluído.
            </div>
            """,
            unsafe_allow_html=True,
        )
    autorizado = True
    if meses >= 6:
        autorizado = st.checkbox(
            f"Autorizo gerar {meses} meses, ciente do tempo médio total de {tempos[meses].split('total ~')[1]}",
            key=f"rvd_confirmacao_volume_{meses}",
        )
    if st.button("Gerar relatório autorizado", type="primary", key="rvd_gerar", disabled=not autorizado):
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
