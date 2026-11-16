from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from .calculos import (
    SEVERIDADES, calcular_indicadores, filtrar_apontamentos,
    normalizar_apontamentos, normalizar_codigos,
)
from .cliente_api import (
    ComboAuditApiError, carregar_cache, consultar_auditoria, consultar_versao,
    obter_configuracao, salvar_cache,
)
from .exportacoes import exportar_auditoria_excel


PREFIXO = "auditoria_combos"


def _formatar_data(valor: object) -> str:
    if not valor:
        return "Não informada"
    try:
        return datetime.fromisoformat(str(valor)).astimezone().strftime("%d/%m/%Y %H:%M:%S")
    except (ValueError, TypeError):
        return str(valor)


def _registrar_resultado(
    relatorio: dict, versao: dict | None, origem_cache: bool, cache_em: str | None,
) -> None:
    st.session_state[f"{PREFIXO}_relatorio"] = relatorio
    st.session_state[f"{PREFIXO}_versao"] = versao or {}
    st.session_state[f"{PREFIXO}_origem_cache"] = origem_cache
    st.session_state[f"{PREFIXO}_cache_em"] = cache_em


def _carregar_api(codigos: list[int]) -> None:
    config = obter_configuracao()
    if config is None:
        raise ComboAuditApiError(
            "Configure ANALISE_VENDAS_COMBO_AUDIT_API_URL para habilitar a consulta."
        )
    relatorio = consultar_auditoria(config, codigos)
    try:
        versao = consultar_versao(config)
    except ComboAuditApiError:
        versao = {}
    salvar_cache(relatorio, versao)
    _registrar_resultado(relatorio, versao, False, None)


def render_auditoria_combos() -> None:
    st.title("Auditoria de combos")
    st.caption(
        "Resultados produzidos pelas regras oficiais do slack_combos. Esta tela é "
        "somente leitura; correções devem ser solicitadas pelo `/combos-editar`."
    )

    config = obter_configuracao()
    cache = carregar_cache()
    if config is None:
        st.warning(
            "API ainda não configurada. Defina `ANALISE_VENDAS_COMBO_AUDIT_API_URL` "
            "e, quando exigido, `ANALISE_VENDAS_COMBO_AUDIT_API_TOKEN`."
        )

    escopo = st.radio(
        "Escopo da consulta", ["Todos os combos atuais", "Combos informados"],
        horizontal=True, key=f"{PREFIXO}_escopo",
    )
    texto_codigos = ""
    if escopo == "Combos informados":
        texto_codigos = st.text_area(
            "Códigos dos combos",
            placeholder="240034782, 240032879, 240035106",
            key=f"{PREFIXO}_codigos", height=90,
        )
    consultar_col, cache_col = st.columns(2)
    if consultar_col.button(
        "Consultar auditoria", type="primary", use_container_width=True,
        disabled=config is None, key=f"{PREFIXO}_consultar",
    ):
        try:
            codigos = normalizar_codigos(texto_codigos) if texto_codigos else []
            if escopo == "Combos informados" and not codigos:
                raise ValueError("Informe ao menos um código de combo.")
            with st.spinner("Consultando a auditoria oficial de combos..."):
                _carregar_api(codigos)
        except (ValueError, ComboAuditApiError) as exc:
            st.error(str(exc))
            cache_disponivel = carregar_cache()
            if cache_disponivel:
                _registrar_resultado(
                    cache_disponivel["report"], cache_disponivel.get("rules_version"),
                    True, cache_disponivel.get("cached_at"),
                )
                st.warning("A API falhou; exibindo a última auditoria armazenada em cache.")
    if cache_col.button(
        "Carregar última auditoria em cache", use_container_width=True,
        disabled=cache is None, key=f"{PREFIXO}_carregar_cache",
    ) and cache:
        _registrar_resultado(
            cache["report"], cache.get("rules_version"), True, cache.get("cached_at")
        )

    relatorio = st.session_state.get(f"{PREFIXO}_relatorio")
    if not relatorio:
        st.info("Consulte a API ou carregue a última auditoria disponível em cache.")
        return
    versao = st.session_state.get(f"{PREFIXO}_versao", {})
    origem_cache = bool(st.session_state.get(f"{PREFIXO}_origem_cache"))
    cache_em = st.session_state.get(f"{PREFIXO}_cache_em")
    if origem_cache:
        st.warning(
            "Dados provenientes do cache local, salvos em " + _formatar_data(cache_em)
            + ". Eles podem estar desatualizados."
        )
    else:
        st.success("Dados recebidos diretamente da API oficial do slack_combos.")
    st.caption(
        f"Schema: {relatorio.get('schema_version', '—')} · "
        f"Regras: {versao.get('rules_version') or versao.get('version') or 'não informada'} · "
        f"Auditoria: {_formatar_data(relatorio.get('generated_at'))}"
    )
    paginacao = relatorio.get("pagination") or {}
    if paginacao:
        st.caption(
            f"Combos processados: {paginacao.get('returned_combos', 0)} de "
            f"{paginacao.get('total_combos', 0)} · "
            f"Páginas consultadas: {paginacao.get('pages_fetched', 1)}"
        )

    dados = normalizar_apontamentos(relatorio)
    indicadores = calcular_indicadores(dados)
    total_analisados = int(paginacao.get("returned_combos") or indicadores["combos"])
    sem_pendencias = max(total_analisados - indicadores["combos"], 0)
    metricas = st.columns(6)
    metricas[0].metric("Combos analisados", total_analisados)
    metricas[1].metric("Erros", indicadores["erro"])
    metricas[2].metric("Conflitos", indicadores["conflito"])
    metricas[3].metric("Alertas", indicadores["alerta"])
    metricas[4].metric("Informativos", indicadores["informativo"])
    metricas[5].metric("Sem pendências", sem_pendencias)

    fluxo = relatorio.get("correction_workflow") or {}
    capacidades = versao.get("capabilities") or {}
    comando = fluxo.get("command") or capacidades.get("correction_command") or "/combos-editar"
    exige_aprovacao = fluxo.get(
        "requires_human_approval", capacidades.get("human_approval_required", True)
    )
    st.info(
        f"Correções: use `{comando}` no Slack. "
        + ("A solicitação exige aprovação humana. " if exige_aprovacao else "")
        + "O painel não envia o comando e não altera o ERP."
    )

    if dados.empty:
        st.success("Nenhuma pendência foi encontrada pelas regras homologadas.")
        return

    c1, c2, c3 = st.columns(3)
    severidades = c1.multiselect(
        "Severidade", list(SEVERIDADES), default=list(SEVERIDADES),
        key=f"{PREFIXO}_severidade",
    )
    regras = c2.multiselect(
        "Regra", sorted(dados["regra"].dropna().astype(str).unique()),
        key=f"{PREFIXO}_regra", placeholder="Todas",
    )
    busca = c3.text_input(
        "Combo — código ou nome", key=f"{PREFIXO}_busca_combo"
    )
    c4, c5, c6 = st.columns(3)
    produto = c4.text_input("Produto", key=f"{PREFIXO}_produto")
    filial = c5.text_input("Filial", key=f"{PREFIXO}_filial")
    tipos_disponiveis = sorted(
        valor for valor in dados["tipo_combo"].dropna().astype(str).unique()
        if valor and valor.lower() != "none"
    )
    tipos = c6.multiselect(
        "Tipo de combo", tipos_disponiveis, key=f"{PREFIXO}_tipo",
        placeholder="Todos",
    )
    vigencias_disponiveis = sorted(
        valor for valor in dados["vigencia"].dropna().astype(str).unique()
        if valor and valor.lower() != "none"
    )
    vigencias = st.multiselect(
        "Vigência", vigencias_disponiveis, key=f"{PREFIXO}_vigencia",
        placeholder="Todas",
    )
    filtrados = filtrar_apontamentos(
        dados, severidades, regras, busca, produto, filial, tipos, vigencias
    )
    st.write(f"**{len(filtrados):,} apontamento(s) exibido(s)**")
    st.dataframe(
        filtrados,
        hide_index=True,
        use_container_width=True,
        height=520,
        column_config={
            "severidade": "Severidade", "combo": "Combo",
            "nome_combo": "Nome do combo", "regra": "Regra",
            "produto": "Produto", "produtos": "Produtos envolvidos",
            "combo_conflitante": "Combo conflitante",
            "nome_conflitante": "Nome conflitante", "filial": "Filial",
            "publico": "Público", "tipo_combo": "Tipo", "vigencia": "Vigência",
            "valor_combo": st.column_config.NumberColumn("Valor combo", format="R$ %.2f"),
            "valor_referencia": st.column_config.NumberColumn("Valor referência", format="R$ %.2f"),
            "mensagem": "Mensagem", "acao_recomendada": "Ação recomendada",
            "data_analise": "Data da análise", "evidencias": "Evidências JSON",
        },
    )
    st.download_button(
        "Baixar auditoria em Excel",
        data=exportar_auditoria_excel(
            filtrados, relatorio, versao, origem_cache, cache_em
        ),
        file_name="auditoria_combos.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key=f"{PREFIXO}_excel",
    )
    st.markdown("**Texto-base para copiar no Slack**")
    st.code(
        f"{comando}\nCombos a revisar: "
        + ", ".join(str(valor) for valor in filtrados["combo"].dropna().unique())
        + "\nMotivo: revisar os apontamentos exportados pela Auditoria de combos.",
        language=None,
    )
