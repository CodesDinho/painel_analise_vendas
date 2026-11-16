from __future__ import annotations

import importlib
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from time import monotonic

import pandas as pd
import streamlit as st

import dados as _dados
import autenticacao as _autenticacao

# O Streamlit reutiliza módulos já importados entre reruns. Ao adicionar estas
# funções com o servidor aberto, a versão anterior de ``dados`` pode permanecer
# em memória e causar ImportError até o processo ser reiniciado.
if not hasattr(_dados, "gerar_documentacao_bloqueios_zip"):
    importlib.reload(_dados)
if not hasattr(_autenticacao, "ARQUIVO_USUARIOS_FATURAMENTO"):
    importlib.reload(_autenticacao)

autenticar = _autenticacao.autenticar
pode_criar_combo = _autenticacao.pode_criar_combo
from combo_classificacoes import (
    CLASSIFICACOES, carregar_classificacoes, classificar_combos,
)
from combo_regras import exige_vin_esp, normalizar, validar_titulo_combo
from combo_criacao import (
    BLOQUEIOS_SCHEMA, COLUNAS_ITENS, normalizar_clientes, preparar_plano,
    assinatura_formulario, validar_cabecalho, validar_itens,
    registrar_erro_criacao, transportar_clientes_para_estado,
)
from combos import (
    aplicar_alteracao_combos,
    consultar_clientes_cotas_combos, consultar_clientes_por_codigo,
    consultar_detalhes_combos, consultar_filiais_cotas_combos,
    consultar_produtos_por_codigo, inserir_clientes_em_combos,
    exportar_detalhes_combos_excel, gerar_modelo_sql_configuracao_cotas,
    listar_combos_vigentes, listar_filiais_cotas_ativas,
    normalizar_codigos_combos, planejar_alteracao_combos, planejar_insercao,
    consultar_evidencias_produtos_combos,
)
from combos_dinamicos import consultar_clientes as consultar_clientes_dinamicos
from combos_dinamicos import listar_catalogos as listar_catalogos_dinamicos
from bloqueios_temporarios import (
    auditar_operacao, executar_liberacao, executar_reaplicacao,
    listar_operacoes, normalizar_clientes as normalizar_clientes_bloqueios,
    preparar_liberacao, preparar_reaplicacao,
)
from analises_extras.registro import ANALISES_EXTRAS, obter_analise_extra
from dados import (
    CACHE_VERSION, INDUSTRIAS, TIPOS_ESTABELECIMENTO_EXTRAS_RANKING,
    TIPOS_ESTABELECIMENTO_KEY_OFF, TIPOS_ESTABELECIMENTO_KEY_ON,
    TIPOS_ESTABELECIMENTO_MULTICANAL, TIPOS_ESTABELECIMENTO_RANKING,
    analisar_mix, aplicar_atualizacao_pagamentos, aplicar_bloqueios_condicoes,
    carregar_base, clientes_dormentes, comparar_volume,
    gerar_documentacao_bloqueios_zip,
    consultar_clientes_nao_localizados_pagamentos,
    consultar_pagamentos_mais_usados, consultar_protecoes_pagamentos,
    consultar_ranking_skus, filtrar,
    filtrar_carteira_por_origem, periodos_equivalentes,
    planejar_atualizacao_pagamentos, planejar_bloqueio_condicoes_cliente,
    planejar_bloqueios_condicoes, planejar_bloqueios_condicoes_inativas,
    resumir_protecao_condicao_100,
    subtrair_meses,
)
from project_paths import (
    DOCUMENTACAO_REGRAS_COMBOS, POP_LIBERACAO_COMBOS,
    SNAPSHOT_RESTORE_ETAPAS,
)


TITULO_PAINEL = "Painel análise de vendas e combos"

st.set_page_config(page_title=TITULO_PAINEL, page_icon="📊", layout="wide")
st.markdown(
    """
    <style>
    section[data-testid="stSidebar"] {
        width: 310px !important;
        min-width: 310px !important;
        max-width: 310px !important;
    }
    section[data-testid="stSidebar"] > div {
        width: 310px !important;
    }
    div[data-testid="stButton"] > button {
        min-height: 1.75rem;
        padding: 0.1rem 0.35rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def login() -> bool:
    if st.session_state.get("usuario"):
        return True
    area_login = st.empty()
    with area_login.container():
        st.title(TITULO_PAINEL)
        st.caption("Positivação, volume, mix por equipe e Pernod × Mtrix")
        with st.form("login"):
            usuario = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            entrar = st.form_submit_button("Entrar", type="primary")
    if entrar:
        autenticado = autenticar(usuario, senha)
        if autenticado:
            st.session_state.usuario = autenticado
            area_login.empty()
            st.rerun()
        st.error("Usuário ou senha inválidos.")
    return False


def filtro_datas(chave: str, padrao: tuple[date, date, date, date]) -> tuple[date, date, date, date]:
    ai, af, bi, bf = padrao
    st.markdown("**Períodos equivalentes**")
    c1, c2, c3, c4 = st.columns(4)
    ai = c1.date_input("Início anterior", ai, key=f"{chave}_ai", format="DD/MM/YYYY")
    af = c2.date_input("Fim anterior", af, key=f"{chave}_af", format="DD/MM/YYYY")
    bi = c3.date_input("Início atual", bi, key=f"{chave}_bi", format="DD/MM/YYYY")
    bf = c4.date_input("Fim atual", bf, key=f"{chave}_bf", format="DD/MM/YYYY")
    return ai, af, bi, bf


@st.cache_data(ttl=300, show_spinner=False)
def carregar_combos_vigentes() -> pd.DataFrame:
    return listar_combos_vigentes(date.today())


@st.cache_data(ttl=300, show_spinner=False)
def carregar_filiais_cotas_combos(
    combos: tuple[int, ...], versao_consulta: int = 2
) -> pd.DataFrame:
    del versao_consulta
    return consultar_filiais_cotas_combos(combos)


@st.cache_data(ttl=300, show_spinner=False)
def carregar_clientes_cotas_combos(
    combos: tuple[int, ...], versao_consulta: int = 3
) -> pd.DataFrame:
    del versao_consulta
    return consultar_clientes_cotas_combos(combos)


@st.cache_data(ttl=3600, show_spinner=False)
def carregar_ranking_skus(
    data_inicio: date, data_fim: date, versao_consulta: int = 2
) -> pd.DataFrame:
    del versao_consulta
    return consultar_ranking_skus(data_inicio, data_fim)


def exportar_ranking_skus_excel(resultado: pd.DataFrame) -> bytes:
    arquivo = BytesIO()
    colunas = [
        "grupo_estabelecimento", "ranking", "posicao", "produto_codigo",
        "produto_nome", "quantidade_vendida", "valor_minimo_4",
        "valor_medio_venda",
    ]
    nomes = {
        "grupo_estabelecimento": "Tipo de estabelecimento",
        "ranking": "Ranking",
        "posicao": "Posição",
        "produto_codigo": "Código produto",
        "produto_nome": "Nome produto",
        "quantidade_vendida": "Quantidade vendida",
        "valor_minimo_4": "Valor mínimo (filial 4)",
        "valor_medio_venda": "Valor médio venda",
    }
    with pd.ExcelWriter(arquivo, engine="openpyxl") as writer:
        resultado.reindex(columns=colunas).rename(columns=nomes).to_excel(
            writer, sheet_name="Todos os rankings", index=False
        )
        planilha = writer.sheets["Todos os rankings"]
        planilha.freeze_panes = "A2"
        planilha.auto_filter.ref = planilha.dimensions
        for coluna in planilha.columns:
            largura = max(
                (len(str(celula.value)) for celula in coluna if celula.value is not None),
                default=10,
            )
            planilha.column_dimensions[coluna[0].column_letter].width = min(
                largura + 2, 45
            )
    return arquivo.getvalue()


@st.cache_data(ttl=3600, show_spinner=False)
def carregar_pagamentos_mais_usados(
    data_inicio: date, data_fim: date, versao_consulta: int = 1
) -> pd.DataFrame:
    del versao_consulta
    return consultar_pagamentos_mais_usados(data_inicio, data_fim)


def exportar_pagamentos_excel(resultado: pd.DataFrame) -> bytes:
    arquivo = BytesIO()
    nomes = {
        "cliente_codigo": "Código CLIFOR",
        "cliente_nome": "Nome CLIFOR",
        "condicao_codigo": "Código condição mais usada",
        "condicao_nome": "Condição de pagamento mais usada",
        "forma_codigo": "Código forma mais usada",
        "forma_nome": "Forma de pagamento mais usada",
        "pedidos_periodo": "Pedidos nos últimos 6 meses",
        "pedidos_condicao": "Pedidos com a condição",
        "pedidos_forma": "Pedidos com a forma",
        "ultima_compra": "Última compra",
    }
    with pd.ExcelWriter(arquivo, engine="openpyxl") as writer:
        resultado.rename(columns=nomes).to_excel(
            writer, sheet_name="Pagamentos mais usados", index=False
        )
        planilha = writer.sheets["Pagamentos mais usados"]
        planilha.freeze_panes = "A2"
        planilha.auto_filter.ref = planilha.dimensions
        for coluna in planilha.columns:
            largura = max(
                (len(str(celula.value)) for celula in coluna if celula.value is not None),
                default=10,
            )
            planilha.column_dimensions[coluna[0].column_letter].width = min(
                largura + 2, 45
            )
    return arquivo.getvalue()


def exportar_previa_pagamentos_excel(
    resultado: pd.DataFrame, aba: str, nomes: dict[str, str]
) -> bytes:
    arquivo = BytesIO()
    with pd.ExcelWriter(arquivo, engine="openpyxl") as writer:
        resultado.rename(columns=nomes).to_excel(writer, sheet_name=aba, index=False)
        planilha = writer.sheets[aba]
        planilha.freeze_panes = "A2"
        planilha.auto_filter.ref = planilha.dimensions
        for coluna in planilha.columns:
            largura = max(
                (len(str(celula.value)) for celula in coluna if celula.value is not None),
                default=10,
            )
            planilha.column_dimensions[coluna[0].column_letter].width = min(
                largura + 2, 45
            )
    return arquivo.getvalue()


def gerar_resumo_dinamico_pagamentos(
    resultado: pd.DataFrame,
    plano_atualizacao: pd.DataFrame,
    plano_bloqueios: pd.DataFrame,
    plano_inativas: pd.DataFrame,
    protecoes: pd.DataFrame,
    cadastros_nao_clientes: pd.DataFrame,
    periodo: tuple[date, date],
    resumo_condicao_100: pd.DataFrame,
) -> str:
    """Monta o texto documental usando exclusivamente as prévias atuais."""
    formato = lambda valor: f"{int(valor):,}".replace(",", ".")
    total_pedidos = int(resultado["pedidos_periodo"].fillna(0).sum())
    media_pedidos = total_pedidos / len(resultado) if len(resultado) else 0
    alteracoes = plano_atualizacao[plano_atualizacao["atualizacao_necessaria"]]
    protegidos = protecoes[protecoes["vendedor_187_1929"]]
    fornecedores = cadastros_nao_clientes[
        cadastros_nao_clientes["classificacao"].eq("Fornecedor")
    ]
    nao_localizados = cadastros_nao_clientes[
        cadastros_nao_clientes["classificacao"].eq("Não localizado no CLIFOR")
    ]
    novos_por_regra = plano_bloqueios.groupby("regra")["bloqueios_novos"].sum()
    ordem_regras = [
        "CPF — bloquear condições sem PRZ",
        "Key Off — bloquear condições com PRZ",
        "Key On/On Trade — bloquear condições sem PRZ",
        "Multicanal — bloquear condições sem PRZ",
    ]
    linhas_regras = "\n".join(
        f"{indice}. {regra}: {formato(novos_por_regra.get(regra, 0))}"
        for indice, regra in enumerate(ordem_regras, start=1)
    )
    novos = int(plano_bloqueios["bloqueios_novos"].sum())
    existentes = int(plano_bloqueios["bloqueios_existentes"].sum())
    inativos = (
        int(plano_inativas["registros_nao_inseridos"].sum())
        if not plano_inativas.empty else 0
    )
    condicao_100_evitados = (
        int(resumo_condicao_100["bloqueios_novos_evitados"].sum())
        if not resumo_condicao_100.empty else 0
    )
    condicao_100_existentes = (
        int(resumo_condicao_100["bloqueios_existentes_preservados"].sum())
        if not resumo_condicao_100.empty else 0
    )
    return f"""ETAPA 1 — ATUALIZAÇÃO DOS PADRÕES DE PAGAMENTO

A Etapa 1 identifica, para cada cliente com compras no período, a condição e a forma de pagamento mais utilizadas.

O sistema:
1. Conta os pedidos distintos de cada cliente.
2. Identifica a condição e a forma de pagamento mais usadas.
3. Em caso de empate, considera o uso mais recente e depois o menor código.
4. Compara o resultado com CLIFOR.CONDICAOPAGAMENTO e CLIFOR.FORMAPAGAMENTO.
5. Apresenta uma prévia dos clientes que precisam de atualização.
6. Somente após confirmação, atualiza os valores diferentes em uma única transação.

Campos de padrão atualizados:
- CLIFOR.CONDICAOPAGAMENTO
- CLIFOR.FORMAPAGAMENTO

Histórico analisado: {periodo[0]:%d/%m/%Y} a {periodo[1]:%d/%m/%Y}

Resumo da Etapa 1:
- Clientes encontrados no histórico: {formato(len(resultado))}
- Pedidos no período: {formato(total_pedidos)}
- Média de pedidos por cliente: {media_pedidos:.1f}
- Condições / formas usadas: {resultado['condicao_codigo'].nunique()} / {resultado['forma_codigo'].nunique()}
- Clientes válidos conferidos no CLIFOR: {formato(len(plano_atualizacao))}
- Clientes que terão condição e/ou forma alterada: {formato(len(alteracoes))}
- Clientes que já possuem os padrões corretos: {formato(len(plano_atualizacao) - len(alteracoes))}
- Clientes protegidos pelos vendedores 1929/187 — Atacado: {formato(len(protegidos))}
- Registros classificados como fornecedores: {formato(len(fornecedores))}
- Códigos realmente não localizados no CLIFOR: {formato(len(nao_localizados))}
- Clientes vinculados à tabela 480: {formato(protecoes['tabela_480'].sum())}

Os clientes protegidos não serão atualizados. Os fornecedores permanecem identificados para conferência e não serão atualizados como clientes. A tabela 480 e seus vínculos serão preservados.

ETAPA 2 — BLOQUEIOS DE CONDIÇÕES DE PAGAMENTO

A Etapa 2 identifica os clientes que se enquadram nas regras de bloqueio conforme CPF e os grupos comerciais definidos pelo tipo de estabelecimento.

O sistema:
1. Classifica os clientes elegíveis como CPF, Multicanal, Key Off ou Key On/On Trade.
2. Define se devem ser bloqueadas condições com ou sem PRZ.
3. Considera somente condições de pagamento ativas.
4. Consulta os bloqueios existentes em CLIFORCONDICAOPAGAMENTO.
5. Preserva todos os bloqueios existentes.
6. Apresenta uma prévia com cliente, regra aplicada e quantidade de bloqueios.
7. Separa as condições inativas para conferência, sem inseri-las.
8. Permite gerar um arquivo documental detalhado antes da execução.
9. Somente após confirmação, insere os bloqueios ausentes em uma única transação.

Quantidade final de novos bloqueios por regra:
{linhas_regras}

Total final de novos bloqueios ativos a inserir: {formato(novos)}

Regras e proteções da Etapa 2:
1. Para CPF, Multicanal e Key On/On Trade, condições com PRZ permanecem liberadas.
2. Para Key Off, tipos 35 e 38, condições com PRZ serão bloqueadas.
3. Para CPF, Multicanal e Key On/On Trade, condições sem PRZ serão bloqueadas, respeitando as regras 7 e 10.
4. Bloqueios existentes serão preservados e nunca removidos.
5. A tabela de preço 480 e seus vínculos não serão inseridos, alterados ou removidos.
6. Clientes vinculados aos vendedores 1929 ou 187 — Atacado não receberão atualizações, bloqueios ou restrições.
7. Condições sem PRZ não serão bloqueadas nos tipos 40, 49, 36, 34, 47, 35, 38, 33 e 39. Os tipos Key Off 35 e 38 continuam bloqueando somente condições com PRZ.
8. Condições inativas serão classificadas para conferência e nunca inseridas.
9. Para Multicanal e Key On/On Trade, condições PRZ — inclusive prazos até 28 dias — e condições à vista permanecem liberadas e não são recriadas como bloqueio.
10. A condição 100 (A VISTA) é protegida globalmente e nunca será inserida como bloqueio para nenhum cliente.

Impacto da proteção da condição 100:
- Novos bloqueios evitados: {formato(condicao_100_evitados)}
- Bloqueios preexistentes preservados: {formato(condicao_100_existentes)}

Revisão das condições inativas:
- Total potencial antes da retirada das condições inativas: {formato(novos + inativos)}
- Registros retirados por condição inativa: {formato(inativos)}
- Saldo final com condições ativas a inserir: {formato(novos)}
- Bloqueios ativos que já existem e serão preservados: {formato(existentes)}

Nenhuma alteração é executada durante a preparação deste resumo. Os valores representam as prévias atuais e podem mudar se o período ou os cadastros forem alterados.
"""


def criar_acompanhamento_progresso(descricao: str):
    inicio = monotonic()
    barra = st.progress(0)
    mensagem = st.empty()

    def atualizar(concluidos: int, total: int) -> None:
        total = max(int(total), 1)
        concluidos = min(max(int(concluidos), 0), total)
        decorrido = monotonic() - inicio
        percentual = concluidos / total
        restante = (
            decorrido * (total - concluidos) / concluidos if concluidos else 0
        )
        previsao = datetime.now() + timedelta(seconds=restante)
        barra.progress(percentual)
        mensagem.info(
            f"{descricao} {concluidos:,}/{total:,} ({percentual:.1%}) · "
            f"decorrido: {str(timedelta(seconds=int(decorrido)))} · "
            f"estimativa: {previsao:%H:%M:%S} "
            f"(faltam aproximadamente {str(timedelta(seconds=int(restante)))})"
        )

    def concluir() -> None:
        decorrido = monotonic() - inicio
        barra.progress(1.0)
        mensagem.success(
            f"{descricao} concluído em {str(timedelta(seconds=int(decorrido)))}."
        )

    return atualizar, concluir


def render_insercao_combos(df: pd.DataFrame, chave: str) -> None:
    estado_aberto = f"{chave}_combos_aberto"
    estado_plano = f"{chave}_combos_plano"
    if not st.session_state.get(estado_aberto):
        return
    with st.container(border=True):
        st.subheader("Inserir clientes e cotas do resultado em combos")
        clientes = sorted(
            pd.to_numeric(df.get("cliente_codigo"), errors="coerce")
            .dropna().astype(int).unique().tolist()
        )
        st.caption(
            f"Serão considerados exatamente os {len(clientes)} clientes únicos "
            "do último resultado exibido na tabela."
        )
        try:
            vigentes = classificar_combos(
                carregar_combos_vigentes(), carregar_classificacoes()
            )
        except Exception as exc:
            st.error(f"Não foi possível consultar os combos vigentes: {exc}")
            return
        nomes = {
            int(item.combo): str(item.nome or "SEM NOME")
            for item in vigentes.itertuples(index=False)
        }
        st.caption(
            "Regra: clientes podem ser cadastrados em todos os combos dormentes, "
            "incluindo Dormente positivação e Dormente volume. As cotas já "
            "configuradas no combo serão herdadas."
        )
        selecionados = st.multiselect(
            "Combos vigentes",
            list(nomes),
            format_func=lambda codigo: f"{codigo} — {nomes[codigo]}",
            key=f"{chave}_combos_selecionados",
        )
        if selecionados:
            try:
                filiais_cotas_selecionadas = carregar_filiais_cotas_combos(
                    tuple(sorted(set(selecionados))), 2
                )
                st.markdown("**Filiais ativas e cotas dos combos selecionados**")
                if filiais_cotas_selecionadas.empty:
                    st.warning(
                        "Os combos selecionados não possuem filiais ativas com cotas "
                        "configuradas."
                    )
                else:
                    st.dataframe(
                        filiais_cotas_selecionadas,
                        hide_index=True,
                        use_container_width=True,
                        column_config={
                            "combo": st.column_config.NumberColumn("Combo", format="%d"),
                            "filial_codigo": st.column_config.NumberColumn("Filial", format="%d"),
                            "filial_nome": "Nome da filial",
                            "cota": st.column_config.NumberColumn("Cota", format="%d"),
                            "cota_nome": "Nome da cota",
                        },
                    )
                with st.expander("Clientes cadastrados atualmente nestes combos"):
                    st.caption(
                        "Esta lista mostra somente quem já está gravado no combo; não são "
                        "os clientes candidatos do resultado acima. A consulta é carregada "
                        "somente ao clicar abaixo para evitar lentidão."
                    )
                    if st.button(
                        "Consultar clientes atuais",
                        key=f"{chave}_consultar_clientes_atuais",
                        use_container_width=True,
                    ):
                        st.session_state[f"{chave}_mostrar_clientes_atuais"] = tuple(
                            sorted(set(selecionados))
                        )
                    assinatura_clientes = st.session_state.get(
                        f"{chave}_mostrar_clientes_atuais"
                    )
                    if assinatura_clientes == tuple(sorted(set(selecionados))):
                        with st.spinner("Consultando clientes e cotas atuais..."):
                            clientes_atuais = carregar_clientes_cotas_combos(
                                assinatura_clientes
                            )
                        if clientes_atuais.empty:
                            st.info(
                                "Este combo ainda não possui clientes cadastrados. Os clientes "
                                "do resultado serão incluídos somente após preparar e confirmar."
                            )
                        else:
                            m1, m2, m3 = st.columns(3)
                            m1.metric(
                                "Clientes únicos",
                                clientes_atuais["cliente_codigo"].nunique(),
                            )
                            m2.metric(
                                "Filiais",
                                clientes_atuais["filial_codigo"].nunique(),
                            )
                            m3.metric("Registros", len(clientes_atuais))
                            st.dataframe(
                                clientes_atuais,
                                hide_index=True,
                                use_container_width=True,
                                height=320,
                            )
            except Exception as exc:
                st.warning(f"Não foi possível consultar as filiais dos combos: {exc}")
        digitados = st.text_area(
            "Adicionar códigos manualmente",
            placeholder="Ex.: 240035279, 240035590",
            help="Separe vários códigos por vírgula, espaço, ponto e vírgula ou quebra de linha.",
            key=f"{chave}_combos_digitados",
        )
        quantidade_cota = st.number_input(
            "Quantidade de cotas por cliente",
            min_value=1, value=1, step=1,
            key=f"{chave}_quantidade_cota",
            help=(
                "Preenche ITEMCOTACOMBOCLIENTE.QUANTIDADE. Os códigos de COTA "
                "são obtidos automaticamente das cotas já configuradas em cada combo."
            ),
        )
        inserir_somente_elegiveis_ie = False
        if chave in {"positivacao", "volume"}:
            inserir_somente_elegiveis_ie = st.checkbox(
                "Inserir os clientes válidos e desconsiderar somente os clientes "
                "sem IE nos combos com produtos restritos",
                value=True,
                key=f"{chave}_inserir_somente_elegiveis_ie",
                help=(
                    "Para combos com vinho, espumante, água ou xarope, os clientes "
                    "sem IE válida continuarão fora da gravação. Os demais clientes "
                    "serão preparados normalmente."
                ),
            )
        preparar, fechar = st.columns(2)
        if fechar.button("Fechar", key=f"{chave}_combos_fechar", use_container_width=True):
            st.session_state[estado_aberto] = False
            st.session_state.pop(estado_plano, None)
            st.rerun()
        if preparar.button(
            "Preparar inserção", key=f"{chave}_combos_preparar",
            type="primary", use_container_width=True,
        ):
            try:
                codigos_digitados = normalizar_codigos_combos(digitados)
                combos = sorted(set(selecionados) | set(codigos_digitados))
                nao_vigentes = [codigo for codigo in combos if codigo not in nomes]
                if nao_vigentes:
                    raise ValueError(
                        "Combos inexistentes ou não vigentes hoje: "
                        + ", ".join(map(str, nao_vigentes))
                    )
                if not clientes:
                    raise ValueError("O resultado atual não possui clientes para inserir.")
                if not combos:
                    raise ValueError("Selecione ou digite ao menos um combo vigente.")
                with st.spinner("Verificando vínculos já existentes..."):
                    plano_preparado = planejar_insercao(
                        clientes, combos, int(quantidade_cota),
                        inserir_somente_elegiveis_ie=inserir_somente_elegiveis_ie,
                    )
                    if (
                        plano_preparado.get("bloqueios_ie")
                        and not inserir_somente_elegiveis_ie
                    ):
                        bloqueios = plano_preparado["bloqueios_ie"]
                        raise ValueError(
                            "Regra universal de IE: combos com vinho, espumante, água "
                            "ou xarope não podem ser liberados para clientes sem IE. "
                            "Clientes bloqueados: "
                            + ", ".join(map(str, sorted({c for _, c in bloqueios})))
                        )
                    if plano_preparado["combos_sem_cotas"]:
                        raise ValueError(
                            "Combos sem cotas configuradas no TOP: "
                            + ", ".join(map(str, plano_preparado["combos_sem_cotas"]))
                        )
                    if plano_preparado["filiais_sem_cota"]:
                        detalhes = ", ".join(
                            f"combo {item['combo']} / filial {item['filial_codigo']}"
                            for item in plano_preparado["filiais_sem_cota"]
                        )
                        raise ValueError(
                            "Filiais ativas sem cota vigente configurada: " + detalhes
                        )
                    st.session_state[estado_plano] = plano_preparado
            except Exception as exc:
                st.session_state.pop(estado_plano, None)
                st.error(str(exc))

        plano = st.session_state.get(estado_plano)
        if plano and (
            plano["clientes"] != clientes
            or plano["quantidade_cota"] != int(quantidade_cota)
            or plano.get("inserir_somente_elegiveis_ie", False)
            != inserir_somente_elegiveis_ie
        ):
            st.session_state.pop(estado_plano, None)
            plano = None
            st.info("O resultado da tabela mudou. Prepare novamente a inserção.")
        if plano:
            bloqueios_ie = plano.get("bloqueios_ie", [])
            if bloqueios_ie and plano.get("inserir_somente_elegiveis_ie"):
                clientes_sem_ie = sorted({cliente for _, cliente in bloqueios_ie})
                st.warning(
                    f"{len(clientes_sem_ie)} cliente(s) sem IE válida serão "
                    f"desconsiderados em {len(bloqueios_ie)} vínculo(s) com combos "
                    "que possuem vinho, espumante, água ou xarope. Os clientes "
                    "válidos continuarão na preparação."
                )
                with st.expander("Clientes sem IE que não serão inseridos"):
                    st.dataframe(
                        pd.DataFrame(
                            bloqueios_ie,
                            columns=["combo", "cliente_codigo"],
                        ),
                        hide_index=True,
                        use_container_width=True,
                    )
            st.markdown("**Filiais ativas e cotas que serão aplicadas**")
            st.dataframe(
                plano["filiais_cotas"], hide_index=True, use_container_width=True,
                column_config={
                    "combo": st.column_config.NumberColumn("Combo", format="%d"),
                    "filial_codigo": st.column_config.NumberColumn("Filial", format="%d"),
                    "filial_nome": "Nome da filial",
                    "cota": st.column_config.NumberColumn("Cota", format="%d"),
                    "cota_nome": "Nome da cota",
                },
            )
            novos = plano["vinculos_novos"]
            clientes_novos = len({cliente for _, cliente in novos})
            clientes_elegiveis = len({
                cliente
                for _, cliente in plano["vinculos_novos"] + plano["ja_existentes"]
            })
            p1, p2, p3, p4 = st.columns(4)
            p1.metric("Clientes a inserir", clientes_novos)
            p2.metric("Combos selecionados", len(plano["combos"]))
            p3.metric("Vínculos já existentes", len(plano["ja_existentes"]))
            p4.metric("Cotas a inserir", len(plano["vinculos_cota_novos"]))
            if not novos and not plano["vinculos_cota_novos"]:
                if bloqueios_ie and plano.get("inserir_somente_elegiveis_ie"):
                    st.info(
                        "Não há vínculos ou cotas elegíveis pendentes. Os clientes "
                        "sem IE permanecerão fora dos combos restritos."
                    )
                else:
                    st.info(
                        "Todos os clientes e suas cotas já estão vinculados aos "
                        "combos selecionados."
                    )
            else:
                st.warning(
                    f"Deseja processar {clientes_elegiveis} clientes elegíveis nos "
                    f"{len(plano['combos'])} combos selecionados? Serão criados "
                    f"{len(novos)} vínculos em COMBOCLIFOR e "
                    f"{len(plano['vinculos_cota_novos'])} registros de cota com "
                    f"quantidade {plano['quantidade_cota']}."
                )
                confirmar, cancelar = st.columns(2)
                if confirmar.button(
                    "Confirmar inserção", key=f"{chave}_combos_confirmar",
                    type="primary", use_container_width=True,
                ):
                    try:
                        with st.spinner("Inserindo clientes nos combos..."):
                            resumo = inserir_clientes_em_combos(
                                plano["clientes"], plano["combos"],
                                plano["quantidade_cota"],
                                inserir_somente_elegiveis_ie=plano.get(
                                    "inserir_somente_elegiveis_ie", False
                                ),
                            )
                        st.session_state.pop(estado_plano, None)
                        st.success(
                            f"Concluído: {resumo['inseridos']} vínculos inseridos; "
                            f"{resumo['cotas_inseridas']} cotas inseridas; "
                            f"{resumo['ja_existentes']} vínculos já existiam; "
                            f"{resumo.get('bloqueios_ie_ignorados', 0)} vínculo(s) "
                            "sem IE foram mantidos fora da operação."
                        )
                    except Exception as exc:
                        st.error(f"Nenhuma alteração foi confirmada devido ao erro: {exc}")
                if cancelar.button(
                    "Cancelar", key=f"{chave}_combos_cancelar", use_container_width=True
                ):
                    st.session_state.pop(estado_plano, None)
                    st.rerun()


def abrir_formulario_combo(origem: str, clientes: list[int] | None = None) -> None:
    transportar_clientes_para_estado(st.session_state, origem, clientes or [])
    st.session_state.combo_form_itens = pd.DataFrame(
        [{coluna: None for coluna in COLUNAS_ITENS}]
    )
    st.session_state.pop("combo_form_plano", None)
    st.session_state.tela_principal = "5. Combos ativos"


def formatar_tabela(df: pd.DataFrame, chave: str):
    exibicao = df.copy()
    for coluna in exibicao.columns:
        if coluna == "cliente_codigo":
            exibicao[coluna] = exibicao[coluna].map(
                lambda valor: f"{int(valor):,}".replace(",", ".") if pd.notna(valor) else ""
            )
        if "data" in coluna or coluna == "ultima_compra":
            convertida = pd.to_datetime(exibicao[coluna], errors="coerce")
            exibicao[coluna] = convertida.dt.strftime("%d/%m/%Y").fillna("")
    st.dataframe(exibicao, use_container_width=True, hide_index=True)
    permite_criar = chave in {"positivacao", "volume"}
    colunas_acoes = st.columns(3 if permite_criar else 2)
    baixar, inserir = colunas_acoes[:2]
    baixar.download_button(
        "Baixar CSV", exibicao.to_csv(index=False).encode("utf-8-sig"),
        "analise.csv", "text/csv", key=f"{chave}_baixar", use_container_width=True,
    )
    possui_clientes = "cliente_codigo" in df.columns
    if inserir.button(
        "Inserir clientes e cotas em combos existentes", key=f"{chave}_abrir_combos",
        use_container_width=True, disabled=not possui_clientes,
        help=None if possui_clientes else "Este resultado não possui clientes individuais.",
    ):
        st.session_state[f"{chave}_combos_aberto"] = True
        st.session_state.pop(f"{chave}_combos_plano", None)
    if permite_criar:
        clientes_resultado = sorted(
            pd.to_numeric(df["cliente_codigo"], errors="coerce")
            .dropna().astype(int).unique().tolist()
        )
        autorizado = pode_criar_combo(st.session_state.get("usuario"))
        colunas_acoes[2].button(
            "Criar novo combo com estes clientes",
            key=f"{chave}_criar_combo",
            use_container_width=True,
            disabled=not autorizado or not clientes_resultado,
            help=(
                None if autorizado
                else "Seu usuário não está autorizado a criar combos."
            ),
            on_click=abrir_formulario_combo,
            args=(
                "Queda de positivação" if chave == "positivacao" else "Queda de volume anual",
                clientes_resultado,
            ),
        )
    if possui_clientes:
        render_insercao_combos(df, chave)


def resumo_carteira(df: pd.DataFrame) -> tuple[int, int, int]:
    clientes = df[["cliente_codigo", "quantidade_vendedores_carteira"]].drop_duplicates("cliente_codigo")
    com_vendedor = int(clientes.quantidade_vendedores_carteira.gt(0).sum())
    sem_vendedor = int(clientes.quantidade_vendedores_carteira.eq(0).sum())
    return com_vendedor, sem_vendedor, int(len(clientes))


def aplicar_filtro_carteira(df: pd.DataFrame, filtro: str) -> pd.DataFrame:
    return filtrar_carteira_por_origem(df, filtro)


def informar_escopo_filtro_carteira() -> None:
    st.caption(
        "O filtro de carteira é aplicado somente à análise Compra indústria. "
        "Base televendas e Indústria+televendas permanecem na análise em qualquer opção."
    )


def render_indicadores_televendas(meta: dict) -> None:
    st.markdown("**Indicadores — Base televendas**")
    indicadores = meta.get("indicadores_televendas", {})
    tv1, tv2, tv3 = st.columns(3)
    tv1.metric("Verde — última compra 30 a 120 dias", indicadores.get("verde", 0))
    tv2.metric("Verde e sem vendedor", indicadores.get("verde_sem_vendedor", 0))
    tv3.metric("Verde e sem rota", indicadores.get("verde_sem_rota", 0))


def render_resumo_origens(df: pd.DataFrame) -> None:
    st.divider()
    st.markdown("**Totais finais por tipo de análise**")
    totais = (
        df[["cliente_codigo", "tipo_analise"]]
        .drop_duplicates()
        .groupby("tipo_analise")["cliente_codigo"]
        .nunique()
    )
    industria, televendas, combinada = st.columns(3)
    industria.metric("Total Compra indústria", int(totais.get("Compra indústria", 0)))
    televendas.metric("Total apenas Base televendas", int(totais.get("Base televendas", 0)))
    combinada.metric(
        "Total Indústria+televendas", int(totais.get("Indústria+televendas", 0))
    )


def multiselect_com_acoes(
    container,
    label: str,
    opcoes,
    chave: str,
    padrao=None,
    format_func=None,
):
    opcoes = list(opcoes)
    if chave in st.session_state:
        st.session_state[chave] = [
            item for item in st.session_state[chave] if item in opcoes
        ]
    rotulo, todos, limpar, _ = container.columns(
        [6, 0.8, 0.8, 2.4],
        vertical_alignment="center",
        gap="small",
    )
    rotulo.markdown(
        f"<div style='line-height:1.05'><strong>{label}</strong>"
        "<div style='font-size:.68rem;color:#6b7280;margin-top:.2rem'>"
        "selecione uma ou várias</div></div>",
        unsafe_allow_html=True,
    )
    if todos.button(
        "＋", key=f"{chave}_todos", help=f"Selecionar todos: {label}",
        use_container_width=True,
    ):
        st.session_state[chave] = opcoes
    if limpar.button(
        "×", key=f"{chave}_limpar", help=f"Limpar seleção: {label}",
        use_container_width=True,
    ):
        st.session_state[chave] = []
    default_widget = list(padrao or []) if chave not in st.session_state else None
    argumentos = {
        "default": default_widget,
        "key": chave,
        "placeholder": "Selecione",
    }
    if format_func is not None:
        argumentos["format_func"] = format_func
    return container.multiselect(
        label, opcoes, label_visibility="collapsed", **argumentos
    )


def render_formulario_criacao_combo() -> None:
    usuario = st.session_state.get("usuario", {})
    autorizado = pode_criar_combo(usuario)
    origem = st.session_state.get("combo_form_origem", "Criação do zero")
    clientes = normalizar_clientes(st.session_state.get("combo_form_clientes", []))
    topo, fechar = st.columns([5, 1])
    topo.subheader("Criar novo combo")
    if fechar.button("Fechar formulário", use_container_width=True):
        st.session_state.combo_form_aberto = False
        st.session_state.pop("combo_form_plano", None)
        st.rerun()
    st.info(f"Origem: **{origem}** · {len(clientes)} clientes únicos carregados.")
    if not autorizado:
        st.error(
            "Seu usuário pode visualizar o formulário, mas não está autorizado a criar combos. "
            "Configure ANALISE_VENDAS_USUARIOS_CRIAR_COMBO ou um perfil administrativo."
        )
    nome = st.text_input("Nome do combo", max_chars=60, key="combo_novo_nome")
    st.caption("O código do novo combo será gerado automaticamente pelo ERP.")
    d1, d2, d3 = st.columns(3)
    inicio = d1.date_input("Data inicial", date.today(), key="combo_novo_inicio", format="DD/MM/YYYY")
    fim = d2.date_input("Data final", date.today(), key="combo_novo_fim", format="DD/MM/YYYY")
    classificacao = d3.selectbox(
        "Classificação local", CLASSIFICACOES,
        index=CLASSIFICACOES.index("Não classificado"),
        key="combo_novo_classificacao",
    )
    try:
        cadastro_filiais = listar_filiais_cotas_ativas()
        opcoes_filiais = {
            int(linha.filial_codigo): linha
            for linha in cadastro_filiais.itertuples(index=False)
        }
        filiais = st.multiselect(
            "Filiais em que o combo e seus clientes ficarão ativos",
            list(opcoes_filiais),
            format_func=lambda codigo_filial: (
                f"{codigo_filial} — {opcoes_filiais[codigo_filial].filial_nome} | "
                f"cota {int(opcoes_filiais[codigo_filial].cota)} — "
                f"{opcoes_filiais[codigo_filial].cota_nome}"
            ),
            key="combo_novo_filiais",
            placeholder="Nenhuma filial específica",
            help=(
                "Cada filial selecionada será planejada em COMBOFILIAL e todos os "
                "clientes receberão sua cota em ITEMCOTACOMBOCLIENTE."
            ),
        )
        cotas_filiais = {
            filial: int(opcoes_filiais[filial].cota) for filial in filiais
        }
    except Exception as exc:
        filiais = []
        cotas_filiais = {}
        st.error(f"Não foi possível carregar as filiais ativas: {exc}")

    st.markdown("**Produtos e faixas**")
    st.caption(
        "Use uma linha por produto/faixa. É possível adicionar/remover linhas e colar células de uma planilha. "
        "Valores aceitam formato brasileiro, por exemplo 1.234,56."
    )
    itens_iniciais = st.session_state.get("combo_form_itens")
    if not isinstance(itens_iniciais, pd.DataFrame):
        itens_iniciais = pd.DataFrame([{coluna: None for coluna in COLUNAS_ITENS}])
    itens_editados = st.data_editor(
        itens_iniciais,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="combo_novo_itens_editor",
        column_config={
            "grupo_combo": st.column_config.TextColumn("Grupo do combo", required=True),
            "quantidade_inicial": st.column_config.TextColumn("Quantidade inicial", required=True),
            "quantidade_final": st.column_config.TextColumn("Quantidade final", required=True),
            "produto_codigo": st.column_config.NumberColumn("Código do produto", min_value=1, step=1, required=True),
            "valor": st.column_config.TextColumn("Valor", required=True),
            "produto_descricao": st.column_config.TextColumn("Descrição do produto", disabled=True),
        },
    )
    st.session_state.combo_form_itens = itens_editados

    st.markdown("**Clientes vinculados**")
    manual = st.text_area(
        "Adicionar clientes por código",
        placeholder="Ex.: 12345, 67890",
        key="combo_novo_clientes_texto",
    )
    adicionar, limpar = st.columns(2)
    if adicionar.button("Adicionar clientes", use_container_width=True):
        try:
            novos = normalizar_codigos_combos(manual)
            st.session_state.combo_form_clientes = normalizar_clientes(clientes + novos)
            st.session_state.pop("combo_form_plano", None)
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    if limpar.button("Remover todos os clientes", use_container_width=True):
        st.session_state.combo_form_clientes = []
        st.session_state.pop("combo_form_plano", None)
        st.rerun()
    try:
        cadastro_clientes = consultar_clientes_por_codigo(clientes)
    except Exception as exc:
        cadastro_clientes = pd.DataFrame(columns=["cliente_codigo", "cliente_nome", "ativo"])
        st.error(f"Não foi possível validar os clientes: {exc}")
    if clientes:
        revisao = pd.DataFrame({"manter": True, "cliente_codigo": clientes}).merge(
            cadastro_clientes, on="cliente_codigo", how="left"
        )
        revisado = st.data_editor(
            revisao, hide_index=True, use_container_width=True,
            key="combo_novo_clientes_editor",
            column_config={
                "manter": st.column_config.CheckboxColumn("Manter"),
                "cliente_codigo": st.column_config.NumberColumn("Cliente", disabled=True),
                "cliente_nome": st.column_config.TextColumn("Nome", disabled=True),
                "ativo": st.column_config.TextColumn("Ativo", disabled=True),
            },
        )
        clientes_mantidos = normalizar_clientes(
            revisado.loc[revisado["manter"], "cliente_codigo"].tolist()
        )
        if clientes_mantidos != clientes:
            st.session_state.combo_form_clientes = clientes_mantidos
            st.session_state.pop("combo_form_plano", None)
            st.rerun()
    else:
        st.caption("Nenhum cliente será vinculado. Isso é permitido na prévia.")

    assinatura_atual = assinatura_formulario(
        nome, inicio, fim, classificacao, itens_editados, clientes, filiais, cotas_filiais
    )
    if st.button("Validar e preparar prévia", type="primary", use_container_width=True):
        erros = validar_cabecalho(nome, inicio, fim)
        codigos_produtos = pd.to_numeric(
            itens_editados.get("produto_codigo"), errors="coerce"
        ).dropna().astype(int).tolist()
        try:
            produtos = consultar_produtos_por_codigo(codigos_produtos)
        except Exception as exc:
            produtos = {}
            erros.append(f"Falha ao revalidar dados no TOP: {exc}")
            registrar_erro_criacao(
                "validação da prévia", exc, usuario.get("username", "desconhecido")
            )
        itens_validados, erros_itens = validar_itens(itens_editados, produtos)
        erros.extend(erros_itens)
        encontrados = set(cadastro_clientes.get("cliente_codigo", pd.Series(dtype=int)).dropna().astype(int))
        ausentes = sorted(set(clientes) - encontrados)
        inativos = cadastro_clientes.loc[
            cadastro_clientes["ativo"].fillna("N").astype(str).str.upper().ne("S"),
            "cliente_codigo",
        ].astype(int).tolist() if not cadastro_clientes.empty else []
        if ausentes:
            erros.append(f"Clientes não encontrados no TOP: {', '.join(map(str, ausentes[:20]))}")
        if inativos:
            erros.append(f"Clientes inativos: {', '.join(map(str, inativos[:20]))}")
        if erros:
            st.session_state.pop("combo_form_plano", None)
            for erro in erros:
                st.error(erro)
            if not itens_validados.empty:
                st.dataframe(itens_validados, use_container_width=True, hide_index=True)
        else:
            st.session_state.combo_form_plano = preparar_plano(
                nome, inicio, fim, classificacao,
                itens_validados, clientes, origem, filiais, cotas_filiais,
            )
            st.session_state.combo_form_assinatura_plano = assinatura_atual

    plano = st.session_state.get("combo_form_plano")
    if plano and st.session_state.get("combo_form_assinatura_plano") != assinatura_atual:
        st.session_state.pop("combo_form_plano", None)
        plano = None
        st.info("Os dados do formulário mudaram. Valide e prepare uma nova prévia.")
    if not plano:
        return
    st.divider()
    st.subheader("Prévia da criação")
    st.write(
        f"**{plano['nome']}** · código gerado automaticamente pelo ERP · "
        f"{plano['data_inicio']:%d/%m/%Y} a {plano['data_fim']:%d/%m/%Y} · "
        f"{plano['classificacao']}"
    )
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Grupos", plano["quantidade_grupos"])
    p2.metric("Produtos/faixas", plano["quantidade_itens"])
    p3.metric("Clientes", plano["quantidade_clientes"])
    p4.metric("Filiais", plano["quantidade_filiais"])
    if plano["filiais"]:
        st.write(
            "Filiais e cotas: " + ", ".join(
                f"{filial} (cota {plano['cotas_filiais'][filial]})"
                for filial in plano["filiais"]
            )
        )
    st.dataframe(pd.DataFrame(plano["itens"]), use_container_width=True, hide_index=True)
    st.write("Tabelas planejadas: " + ", ".join(plano["tabelas"]))
    st.warning("A gravação está bloqueada até a confirmação das seguintes regras do TOP:")
    for bloqueio in plano["bloqueios_schema"]:
        st.write(f"- {bloqueio}")
    confirmou = st.checkbox(
        "Revisei a prévia e confirmo os dados acima.", key="combo_novo_confirmacao"
    )
    st.button(
        "Criar combo no TOP",
        type="primary",
        use_container_width=True,
        disabled=True,
        help="Desabilitado: ainda faltam confirmações estruturais do TOP listadas acima.",
    )
    if confirmou:
        st.info("A confirmação foi registrada apenas na interface; nenhuma gravação será executada enquanto os bloqueios existirem.")


def render_combos_ativos() -> None:
    titulo_col, total_col, ok_col, pendentes_col = st.columns([4, 1, 1, 1.25])
    titulo_col.title("Validação de regras de títulos de combos ativos")
    st.caption(
        "Tela somente para conferência dos combos vigentes e dos padrões de título. "
        "Alterações cadastrais e classificações devem ser feitas diretamente no ERP."
    )
    acoes = st.columns([1, 1, 3])
    if acoes[0].button("Atualizar agora", use_container_width=True):
        carregar_combos_vigentes.clear()
        st.rerun()
    autorizado = pode_criar_combo(st.session_state.get("usuario"))
    acoes[1].button(
        "Criar novo combo", type="primary", use_container_width=True,
        disabled=not autorizado,
        help=None if autorizado else "Seu usuário não está autorizado a criar combos.",
        on_click=abrir_formulario_combo, args=("Criação do zero", []),
    )
    if st.session_state.get("combo_form_aberto"):
        render_formulario_criacao_combo()
        return
    try:
        combos = classificar_combos(
            carregar_combos_vigentes(), carregar_classificacoes()
        )
        evidencias = consultar_evidencias_produtos_combos(
            combos["combo"].dropna().astype(int).tolist()
        )
        validacoes = []
        classes_sem_vin_esp = {
            "REDE", "MANUTENCAO", "DORMENTE POSITIVACAO", "DORMENTE VOLUME"
        }
        for item in combos.itertuples(index=False):
            codigo = int(item.combo)
            vin_esp = (
                normalizar(item.classificacao) not in classes_sem_vin_esp
                and exige_vin_esp([item.nome] + evidencias.get(codigo, []))
            )
            ok, detalhe = validar_titulo_combo(
                item.nome, item.classificacao, vin_esp
            )
            validacoes.append((ok, detalhe, "Sim" if vin_esp else "Não"))
        combos[["titulo_ok", "regra_titulo", "vin_esp"]] = pd.DataFrame(
            validacoes, index=combos.index
        )
    except Exception as exc:
        st.error(f"Não foi possível carregar os combos ativos: {exc}")
        return
    total_combos = len(combos)
    titulos_ok = int(combos["titulo_ok"].fillna(False).sum())
    titulos_pendentes = total_combos - titulos_ok
    total_col.metric("Total de combos", total_combos)
    ok_col.metric("Títulos OK", titulos_ok)
    pendentes_col.metric(
        "⚠️ Pendentes de correção" if titulos_pendentes else "✅ Pendentes",
        titulos_pendentes,
        delta=(
            f"-{titulos_pendentes} requerem ação"
            if titulos_pendentes
            else "Tudo padronizado"
        ),
        delta_color="normal",
    )
    busca_col, classe_col = st.columns(2)
    busca = busca_col.text_input(
        "Pesquisar", placeholder="Código, nome ou situação do título"
    ).strip().lower()
    quantidades_classes = combos["classificacao"].value_counts().to_dict()
    classes = classe_col.multiselect(
        "Filtrar classificação",
        CLASSIFICACOES,
        default=CLASSIFICACOES,
        format_func=lambda classe: (
            f"{classe} ({int(quantidades_classes.get(classe, 0))})"
        ),
    )
    filtrado = (
        combos[combos["classificacao"].isin(classes)].copy()
        if classes else combos.copy()
    )
    if busca:
        mascara = (
            filtrado["combo"].astype(str).str.lower().str.contains(busca, na=False)
            | filtrado["nome"].astype(str).str.lower().str.contains(busca, na=False)
            | filtrado["regra_titulo"].astype(str).str.lower().str.contains(busca, na=False)
        )
        filtrado = filtrado[mascara]
    exibicao = filtrado[[
        "combo", "nome", "data_inicio", "data_fim",
        "titulo_ok", "regra_titulo", "vin_esp",
    ]].copy()
    exibicao["titulo_ok"] = exibicao["titulo_ok"].map(
        {True: "OK", False: "NÃO PADRONIZADO"}
    )
    exibicao["combo"] = exibicao["combo"].map(
        lambda valor: str(int(valor)) if pd.notna(valor) else ""
    )
    estilo = exibicao.style.map(
        lambda valor: "background-color: #ffcccc; color: #8b0000; font-weight: bold"
        if valor == "NÃO PADRONIZADO" else "",
        subset=["titulo_ok"],
    )
    st.dataframe(
        estilo, hide_index=True, use_container_width=True,
        height=700,
        column_config={
            "combo": st.column_config.TextColumn(
                "Código", disabled=True, width="small"
            ),
            "nome": st.column_config.TextColumn("Nome", disabled=True),
            "data_inicio": st.column_config.DateColumn("Data inicial", disabled=True, format="DD/MM/YYYY"),
            "data_fim": st.column_config.DateColumn("Data final", disabled=True, format="DD/MM/YYYY"),
            "titulo_ok": st.column_config.TextColumn("Título OK"),
            "regra_titulo": st.column_config.TextColumn("Validação", width="large"),
            "vin_esp": st.column_config.TextColumn("VIN/ESP", width="small"),
        },
    )


def render_conferencia_combos() -> None:
    st.title("Conferência de combos")
    st.caption("Consulte clientes, cotas, produtos, faixas e valores dos combos vigentes.")
    try:
        vigentes = carregar_combos_vigentes()
    except Exception as exc:
        st.error(f"Não foi possível carregar os combos vigentes: {exc}")
        return
    nomes = {
        int(item.combo): str(item.nome or "SEM NOME")
        for item in vigentes.itertuples(index=False)
    }
    selecionados = st.multiselect(
        "Combos vigentes",
        list(nomes),
        format_func=lambda codigo: f"{codigo:,} — {nomes[codigo]}".replace(",", "."),
        placeholder="Selecione um ou mais combos",
        key="conferencia_combos_selecionados",
    )
    consultar, atualizar = st.columns([1, 1])
    if atualizar.button("Atualizar combos", use_container_width=True):
        carregar_combos_vigentes.clear()
        st.rerun()
    if not consultar.button(
        "Consultar detalhes", type="primary", use_container_width=True,
        disabled=not selecionados,
    ):
        return
    try:
        with st.spinner("Consultando clientes, cotas, produtos e valores..."):
            detalhes = consultar_detalhes_combos(selecionados)
    except Exception as exc:
        st.error(f"Não foi possível consultar os detalhes: {exc}")
        return

    clientes = detalhes["clientes_cotas"]
    produtos = detalhes["produtos_valores"]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Combos", len(selecionados))
    m2.metric(
        "Clientes", clientes["cliente_codigo"].nunique() if not clientes.empty else 0
    )
    m3.metric("Cotas", clientes["cota"].nunique() if not clientes.empty else 0)
    m4.metric(
        "Produtos", produtos["produto_codigo"].nunique() if not produtos.empty else 0
    )
    st.download_button(
        "Exportar para Excel",
        data=exportar_detalhes_combos_excel(detalhes),
        file_name=f"conferencia_combos_{date.today():%Y%m%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    st.subheader("Clientes e cotas")
    if clientes.empty:
        st.info("Nenhum cliente vinculado foi encontrado para os combos selecionados.")
    else:
        st.dataframe(
            clientes, use_container_width=True, hide_index=True, height=480,
            column_config={
                "combo": st.column_config.NumberColumn("Combo", format="%d"),
                "combo_nome": "Nome do combo",
                "cliente_codigo": st.column_config.NumberColumn("Cliente", format="%d"),
                "cliente_nome": "Nome do cliente",
                "cota": st.column_config.NumberColumn("Cota", format="%d"),
                "cota_nome": "Nome da cota",
                "filial": st.column_config.NumberColumn("Filial", format="%d"),
                "quantidade_cota": st.column_config.NumberColumn("Quantidade", format="%d"),
            },
        )
    st.subheader("Produtos e valores")
    if produtos.empty:
        st.info("Nenhum produto foi encontrado para os combos selecionados.")
    else:
        st.dataframe(
            produtos, use_container_width=True, hide_index=True, height=480,
            column_config={
                "combo": st.column_config.NumberColumn("Combo", format="%d"),
                "combo_nome": "Nome do combo",
                "grupo_codigo": st.column_config.NumberColumn("Grupo", format="%d"),
                "grupo_nome": "Nome do grupo",
                "grupo_quantidade": "Quantidade do grupo",
                "bonificado": "Bonificado",
                "produto_codigo": st.column_config.NumberColumn("Produto", format="%d"),
                "produto_nome": "Nome do produto",
                "quantidade_inicial": "Quantidade inicial",
                "quantidade_final": "Quantidade final",
                "valor_venda": st.column_config.NumberColumn(
                    "Valor de venda", format="R$ %.2f"
                ),
            },
        )


def render_ranking_skus() -> None:
    st.title("Ranking de SKUs por tipo de estabelecimento")
    st.caption(
        "Top 50 mais vendidos e 50 menos vendidos. A consulta é agregada no banco "
        "e retorna no máximo 400 linhas."
    )
    hoje = date.today()
    col_inicio, col_fim, col_acao = st.columns([1, 1, 1])
    data_inicio = col_inicio.date_input(
        "Data inicial", hoje - timedelta(days=30),
        key="ranking_skus_data_inicio", format="DD/MM/YYYY",
    )
    data_fim = col_fim.date_input(
        "Data final", hoje, key="ranking_skus_data_fim", format="DD/MM/YYYY",
    )
    consultar = col_acao.button(
        "Consultar ranking", type="primary", use_container_width=True
    )
    st.caption(
        "Tipos de estabelecimento considerados — "
        + " · ".join(
            f"{grupo}: {', '.join(map(str, codigos))}"
            for grupo, codigos in TIPOS_ESTABELECIMENTO_RANKING.items()
        )
    )
    st.caption(
        "Tipos informados que ainda não são contemplados neste ranking — "
        "Farmácia (25), Zé Delivery (26), Panificadora (31, 32), Cash Carry "
        "(49), Empório (73), Consumidor final (93), Delicatessen (96), "
        "Academia (97), Gula (201) e Key On/On Trade ("
        + ", ".join(map(str, sorted(TIPOS_ESTABELECIMENTO_KEY_ON))) + ")."
    )
    if consultar:
        if data_inicio > data_fim:
            st.error("A data inicial deve ser anterior ou igual à data final.")
        else:
            try:
                with st.spinner("Calculando rankings agregados..."):
                    resultado = carregar_ranking_skus(data_inicio, data_fim)
                st.session_state.ranking_skus_resultado = resultado
                st.session_state.ranking_skus_periodo = (data_inicio, data_fim)
            except Exception as exc:
                st.error(f"Não foi possível consultar o ranking de SKUs: {exc}")

    resultado = st.session_state.get("ranking_skus_resultado")
    periodo = st.session_state.get("ranking_skus_periodo")
    if resultado is None:
        st.info("Escolha o período e clique em Consultar ranking.")
        return
    if resultado.empty:
        st.info("Nenhuma venda foi encontrada para os grupos no período consultado.")
        return
    if periodo:
        st.caption(f"Resultado de {periodo[0]:%d/%m/%Y} a {periodo[1]:%d/%m/%Y}.")
        st.download_button(
            "Baixar todos os dados em Excel",
            data=exportar_ranking_skus_excel(resultado),
            file_name=(
                f"ranking_skus_{periodo[0]:%Y%m%d}_a_{periodo[1]:%Y%m%d}.xlsx"
            ),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    abas = st.tabs(list(TIPOS_ESTABELECIMENTO_RANKING))
    for aba, (grupo, tipos) in zip(abas, TIPOS_ESTABELECIMENTO_RANKING.items()):
        with aba:
            st.caption("Tipos de estabelecimento: " + ", ".join(map(str, tipos)))
            dados_grupo = resultado[resultado["grupo_estabelecimento"].eq(grupo)]
            mais, menos = st.columns(2)
            for area, titulo, ranking in (
                (mais, "50 mais vendidos", "Mais vendidos"),
                (menos, "50 menos vendidos", "Menos vendidos"),
            ):
                with area:
                    st.subheader(titulo)
                    dados = dados_grupo[dados_grupo["ranking"].eq(ranking)][[
                        "posicao", "produto_codigo", "produto_nome",
                        "quantidade_vendida", "valor_minimo_4", "valor_medio_venda",
                    ]]
                    st.dataframe(
                        dados, hide_index=True, use_container_width=True, height=650,
                        column_config={
                            "posicao": st.column_config.NumberColumn("Posição", format="%d"),
                            "produto_codigo": st.column_config.NumberColumn("Cód. produto", format="%d"),
                            "produto_nome": "Nome do produto",
                            "quantidade_vendida": st.column_config.NumberColumn(
                                "Quantidade vendida", format="%.2f"
                            ),
                            "valor_minimo_4": st.column_config.NumberColumn(
                                "Valor mínimo (filial 4)", format="R$ %.2f"
                            ),
                            "valor_medio_venda": st.column_config.NumberColumn(
                                "Valor médio venda", format="R$ %.2f"
                            ),
                        },
                    )


def render_quadro_regras_bloqueios_pagamento() -> None:
    st.subheader("Etapa 2 - Bloquear condições por tipo de estabelecimento/equipe")
    st.warning(
        "**Regras que serão aplicadas aos bloqueios de condições de pagamento**\n\n"
        "- **Equipe Multicanal:** Conveniência (`21`, `22`, `23`, `24`), "
        "Farmácia (`25`), Zé Delivery (`26`), Panificadora (`31`, `32`), "
        "Mercados (`33`, `34`), Mercado de Bebidas (`39`, `71`), Cash Carry "
        "(`49`), Distribuidora (`72`), Empório (`73`), Consumidor final (`93`), "
        "Delicatessen (`96`), Academia (`97`) e Gula (`201`).\n"
        "- **Equipe Key Off:** tipos de estabelecimento `35` e `38`.\n"
        "- **Equipe Key On/On Trade:** tipos de estabelecimento `41`, `42`, "
        "`43`, `44`, `45`, `46`, `51`, `52`, `53`, `61`, `62`, `63`, `65`, "
        "`81`, `82`, `83`, `84`, `85`, `86`, `91` e `92`.\n\n"
        "**Aplicação das restrições:**\n\n"
        "1. Para clientes **CPF**, **Multicanal** e **Key On/On Trade**, condições "
        "cujo nome contém `PRZ` permanecem liberadas e **não serão bloqueadas**.\n"
        "2. Para clientes da equipe **Key Off**, condições cujo nome contém `PRZ` "
        "**serão bloqueadas**.\n"
        "3. Para clientes **CPF**, **Multicanal** e **Key On/On Trade**, condições "
        "cujo nome não contém `PRZ` **serão bloqueadas**. CPF tem precedência "
        "sobre o tipo de estabelecimento cadastrado, sempre preservando a "
        "condição 100 conforme a regra 10.\n"
        "4. Bloqueios que já existirem em `CLIFORCONDICAOPAGAMENTO` serão "
        "**preservados e nunca removidos**. O processo insere somente os bloqueios "
        "ausentes.\n"
        "5. A tabela de preço **480 (Atacado)** e seus vínculos serão "
        "preservados: este fluxo não insere, altera nem remove seus registros.\n"
        "6. Clientes vinculados aos vendedores **1929** ou **187** — **Atacado** não receberão "
        "nenhuma atualização, bloqueio ou restrição.\n"
        "7. Condições **sem `PRZ` não serão bloqueadas** nos tipos de "
        "estabelecimento `40`, `49`, `36`, `34`, `47`, `35`, `38`, `33` e `39`. "
        "Os tipos Key Off `35` e `38` continuam bloqueando somente condições com `PRZ`.\n"
        "8. Condições de pagamento inativas serão classificadas em uma aba "
        "separada e **nunca serão inseridas**.\n"
        "9. Para **Multicanal** e **Key On/On Trade**, condições `PRZ` — inclusive "
        "as de prazo até 28 dias — e condições **à vista** permanecem liberadas "
        "e não serão recriadas como bloqueio.\n"
        "10. A condição **100 (A VISTA)** não será bloqueada para nenhum cliente. "
        "Bloqueios preexistentes são preservados por este fluxo.\n\n"
        "Prepare e confira a prévia antes de confirmar a inserção."
    )


def render_bloqueios_condicoes_pagamento(
    resultado: pd.DataFrame, assinatura_resultado: tuple
) -> None:
    st.divider()
    st.subheader("Etapa 2 — Bloquear condições por tipo de estabelecimento/equipe")
    st.markdown("#### Atualização de um único cliente")
    coluna_codigo, coluna_preparar = st.columns([2, 1])
    cliente_individual = int(coluna_codigo.number_input(
        "Código do cliente (CLIFOR)",
        min_value=1,
        step=1,
        key="pagamentos_cliente_bloqueio_individual",
    ))
    if coluna_preparar.button(
        "Preparar cliente",
        key="pagamentos_preparar_bloqueio_individual",
        use_container_width=True,
    ):
        try:
            with st.spinner("Conferindo cadastro, regra e bloqueios existentes..."):
                plano_individual = planejar_bloqueio_condicoes_cliente(
                    cliente_individual
                )
            st.session_state.pagamentos_plano_bloqueio_individual = plano_individual
            st.session_state.pagamentos_codigo_bloqueio_individual = cliente_individual
            st.session_state.pagamentos_confirmar_bloqueio_individual = False
        except Exception as exc:
            st.session_state.pop("pagamentos_plano_bloqueio_individual", None)
            st.error(f"Não foi possível preparar o cliente: {exc}")

    plano_individual = st.session_state.get("pagamentos_plano_bloqueio_individual")
    if plano_individual is not None:
        if st.session_state.get("pagamentos_codigo_bloqueio_individual") != cliente_individual:
            st.info("O código foi alterado. Clique em Preparar cliente novamente.")
        elif plano_individual.empty:
            st.info("Nenhuma condição de pagamento foi encontrada para essa regra.")
        else:
            a_inserir = plano_individual[plano_individual["situacao"].eq("Inserir")]
            inativas_individual = plano_individual[
                plano_individual["situacao"].eq("Inativa — não inserir")
            ]
            existentes_individual = len(plano_individual) - len(a_inserir) - len(
                inativas_individual
            )
            resumo1, resumo2, resumo3, resumo4 = st.columns(4)
            resumo1.metric("Cliente preparado", cliente_individual)
            resumo2.metric("Bloqueios a inserir", len(a_inserir))
            resumo3.metric("Bloqueios já existentes", existentes_individual)
            resumo4.metric("Condições inativas — não inserir", len(inativas_individual))
            st.dataframe(
                plano_individual,
                hide_index=True,
                use_container_width=True,
                height=360,
                column_config={
                    "cliente_codigo": st.column_config.NumberColumn(
                        "Cód. cliente", format="%d"
                    ),
                    "cliente_nome": "Nome do cliente",
                    "tipo_estabelecimento": st.column_config.NumberColumn(
                        "Tipo estabelecimento", format="%d"
                    ),
                    "regra": "Regra aplicada",
                    "condicao_codigo": st.column_config.NumberColumn(
                        "Cód. condição", format="%d"
                    ),
                    "condicao_nome": "Condição de pagamento",
                    "situacao": "Ação",
                },
            )
            if a_inserir.empty:
                if not inativas_individual.empty:
                    st.warning(
                        "Não há bloqueios ativos para inserir. As condições "
                        "inativas exibidas não serão inseridas."
                    )
                else:
                    st.success("Todos os bloqueios calculados já existem para o cliente.")
            else:
                regras_individuais = "; ".join(
                    sorted(a_inserir["regra"].dropna().astype(str).unique())
                )
                st.checkbox(
                    f"Confirmo a inserção de {len(a_inserir)} bloqueio(s) para "
                    f"o cliente {cliente_individual}. Regra(s) aplicada(s): "
                    f"{regras_individuais}.",
                    key="pagamentos_confirmar_bloqueio_individual",
                )
                if st.button(
                    "Inserir bloqueios deste cliente",
                    type="primary",
                    disabled=not st.session_state.get(
                        "pagamentos_confirmar_bloqueio_individual", False
                    ),
                    key="pagamentos_aplicar_bloqueio_individual",
                    use_container_width=True,
                ):
                    try:
                        with st.spinner("Inserindo bloqueios em uma única transação..."):
                            resumo = aplicar_bloqueios_condicoes([cliente_individual])
                        st.session_state.pop(
                            "pagamentos_plano_bloqueio_individual", None
                        )
                        st.success(
                            f"Concluído: {resumo['bloqueios_inseridos']} bloqueio(s) "
                            "inserido(s)."
                        )
                    except Exception as exc:
                        st.error(
                            "A transação foi revertida devido ao erro: " + str(exc)
                        )

    st.markdown("#### Atualização em lote")
    if st.button(
        "Preparar bloqueios das condições de pagamento",
        key="pagamentos_preparar_bloqueios",
        use_container_width=True,
    ):
        try:
            progresso, concluir_progresso = criar_acompanhamento_progresso(
                "Conferindo bloqueios existentes em lotes..."
            )
            with st.spinner("Conferindo bloqueios existentes em lotes..."):
                plano = planejar_bloqueios_condicoes(resultado, progresso)
                plano_inativas = planejar_bloqueios_condicoes_inativas(resultado)
                resumo_condicao_100 = resumir_protecao_condicao_100(resultado)
            concluir_progresso()
            st.session_state.pagamentos_plano_bloqueios = plano
            st.session_state.pagamentos_plano_bloqueios_inativas = plano_inativas
            st.session_state.pagamentos_resumo_condicao_100 = resumo_condicao_100
            st.session_state.pagamentos_assinatura_bloqueios = assinatura_resultado
            st.session_state.pagamentos_confirmar_bloqueios = False
            st.session_state.pop("pagamentos_documentacao_bloqueios_zip", None)
        except Exception as exc:
            st.session_state.pop("pagamentos_plano_bloqueios", None)
            st.error(f"Não foi possível preparar os bloqueios: {exc}")

    plano = st.session_state.get("pagamentos_plano_bloqueios")
    if plano is None:
        return
    if st.session_state.get("pagamentos_assinatura_bloqueios") != assinatura_resultado:
        st.session_state.pop("pagamentos_plano_bloqueios", None)
        st.session_state.pop("pagamentos_plano_bloqueios_inativas", None)
        st.session_state.pop("pagamentos_resumo_condicao_100", None)
        st.info("O resultado mudou. Prepare novamente os bloqueios.")
        return
    if plano.empty:
        st.info("Nenhum cliente do resultado se enquadra nas regras informadas.")
        return
    novos = int(plano["bloqueios_novos"].sum())
    existentes = int(plano["bloqueios_existentes"].sum())
    plano_inativas = st.session_state.get("pagamentos_plano_bloqueios_inativas")
    if plano_inativas is None:
        plano_inativas = planejar_bloqueios_condicoes_inativas(resultado)
        st.session_state.pagamentos_plano_bloqueios_inativas = plano_inativas
    total_registros_inativos = int(
        plano_inativas["registros_nao_inseridos"].sum()
    ) if not plano_inativas.empty else 0
    resumo_condicao_100 = st.session_state.get("pagamentos_resumo_condicao_100")
    if resumo_condicao_100 is None:
        resumo_condicao_100 = resumir_protecao_condicao_100(resultado)
        st.session_state.pagamentos_resumo_condicao_100 = resumo_condicao_100
    condicao_100_evitados = int(
        resumo_condicao_100["bloqueios_novos_evitados"].sum()
    ) if not resumo_condicao_100.empty else 0
    condicao_100_existentes = int(
        resumo_condicao_100["bloqueios_existentes_preservados"].sum()
    ) if not resumo_condicao_100.empty else 0
    b1, b2, b3, b4, b5 = st.columns(5)
    b1.metric("Clientes classificados", len(plano))
    b2.metric("Novos bloqueios", f"{novos:,}".replace(",", "."))
    b3.metric("Bloqueios preservados", f"{existentes:,}".replace(",", "."))
    b4.metric(
        "Condições inativas — não inserir",
        f"{total_registros_inativos:,}".replace(",", "."),
    )
    b5.metric(
        "Condição 100 protegida — novos evitados",
        f"{condicao_100_evitados:,}".replace(",", "."),
        help=(
            f"Há {condicao_100_existentes:,} bloqueio(s) preexistente(s) da condição "
            "100 entre os clientes enquadrados; eles são preservados e não removidos "
            "por esta operação."
        ).replace(",", "."),
    )
    if not resumo_condicao_100.empty:
        with st.expander("Detalhamento numérico — proteção da condição 100"):
            st.dataframe(
                resumo_condicao_100,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "regra": "Regra em que seria enquadrada",
                    "clientes_enquadrados": "Clientes enquadrados",
                    "bloqueios_existentes_preservados": "Já bloqueados — preservar",
                    "bloqueios_novos_evitados": "Novos bloqueios evitados",
                },
            )
    bloqueios_por_regra = (
        plano.groupby("regra", dropna=False)["bloqueios_novos"]
        .sum()
        .astype(int)
        .sort_index()
    )
    if not bloqueios_por_regra.empty:
        st.caption("Novos bloqueios por regra aplicada")
        colunas_regras = st.columns(len(bloqueios_por_regra))
        for coluna, (regra, quantidade) in zip(
            colunas_regras, bloqueios_por_regra.items()
        ):
            coluna.metric(
                str(regra),
                f"{quantidade:,}".replace(",", "."),
            )
    aba_ativos, aba_inativos = st.tabs([
        "Bloqueios com condições ativas",
        f"Condições inativas — não inserir ({total_registros_inativos})",
    ])
    with aba_ativos:
        st.download_button(
            "Exportar prévia dos bloqueios ativos para Excel",
            data=exportar_previa_pagamentos_excel(
                plano,
                "Prévia de bloqueios",
                {
                    "cliente_codigo": "Código CLIFOR",
                    "cliente_nome": "Nome CLIFOR",
                    "tipo_estabelecimento": "Tipo de estabelecimento",
                    "regra": "Regra aplicada",
                    "bloqueios_existentes": "Bloqueios preservados",
                    "bloqueios_novos": "Bloqueios a inserir",
                },
            ),
            file_name="previa_bloqueios_condicoes_pagamento.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="pagamentos_exportar_bloqueios",
            use_container_width=True,
        )
        st.dataframe(
            plano,
            hide_index=True,
            use_container_width=True,
            height=420,
            column_config={
                "cliente_codigo": st.column_config.NumberColumn("Cód. CLIFOR", format="%d"),
                "cliente_nome": "Nome CLIFOR",
                "tipo_estabelecimento": st.column_config.NumberColumn(
                    "Tipo estabelecimento", format="%d"
                ),
                "regra": "Regra aplicada",
                "bloqueios_existentes": st.column_config.NumberColumn(
                    "Bloqueios preservados", format="%d"
                ),
                "bloqueios_novos": st.column_config.NumberColumn(
                    "Bloqueios a inserir", format="%d"
                ),
            },
        )
    with aba_inativos:
        st.warning(
            f"Foram identificados {total_registros_inativos:,} registros potenciais "
            "com condições inativas. A tabela resume por condição e regra; "
            "nenhum deles será inserido.".replace(",", ".")
        )
        st.download_button(
            "Exportar condições inativas para Excel",
            data=exportar_previa_pagamentos_excel(
                plano_inativas, "Condições inativas", {}
            ),
            file_name="condicoes_inativas_nao_inserir.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="pagamentos_exportar_bloqueios_inativos",
            use_container_width=True,
        )
        st.dataframe(
            plano_inativas,
            hide_index=True,
            use_container_width=True,
            height=420,
            column_config={
                "regra": "Regra aplicada",
                "condicao_codigo": st.column_config.NumberColumn(
                    "Cód. condição", format="%d"
                ),
                "condicao_nome": "Condição de pagamento",
                "status_condicao": "Status no cadastro",
                "clientes_afetados": st.column_config.NumberColumn(
                    "Clientes afetados", format="%d"
                ),
                "registros_nao_inseridos": st.column_config.NumberColumn(
                    "Registros não inseridos", format="%d"
                ),
                "acao": "Ação",
            },
        )
    st.markdown("#### Documentação detalhada dos registros a inserir")
    st.caption(
        "Gera um ZIP somente de leitura com um CSV detalhado e um arquivo de texto "
        "descrevendo as regras. Nenhum insert é executado."
    )
    if st.button(
        "Montar arquivo documental dos bloqueios a inserir",
        key="pagamentos_montar_documentacao_bloqueios",
        use_container_width=True,
    ):
        try:
            progresso_doc, concluir_doc = criar_acompanhamento_progresso(
                "Montando arquivo documental..."
            )
            with st.spinner("Consultando e compactando os registros detalhados..."):
                arquivo_doc, total_doc = gerar_documentacao_bloqueios_zip(
                    resultado, progresso_doc
                )
            concluir_doc()
            st.session_state.pagamentos_documentacao_bloqueios_zip = arquivo_doc
            st.session_state.pagamentos_documentacao_bloqueios_total = total_doc
            st.session_state.pagamentos_documentacao_bloqueios_assinatura = (
                assinatura_resultado
            )
        except Exception as exc:
            st.session_state.pop("pagamentos_documentacao_bloqueios_zip", None)
            st.error(f"Não foi possível montar a documentação: {exc}")
    arquivo_doc = st.session_state.get("pagamentos_documentacao_bloqueios_zip")
    assinatura_doc = st.session_state.get(
        "pagamentos_documentacao_bloqueios_assinatura"
    )
    if arquivo_doc is not None and assinatura_doc == assinatura_resultado:
        total_doc = st.session_state.get("pagamentos_documentacao_bloqueios_total", 0)
        st.success(
            f"Arquivo pronto com {total_doc:,} registros detalhados."
            .replace(",", ".")
        )
        st.download_button(
            "⬇️ Baixar documentação detalhada dos bloqueios (ZIP)",
            data=arquivo_doc,
            file_name="documentacao_bloqueios_condicoes_pagamento.zip",
            mime="application/zip",
            key="pagamentos_baixar_documentacao_bloqueios",
            use_container_width=True,
        )
    plano_atualizacao_doc = st.session_state.get("pagamentos_plano_atualizacao")
    protecoes_doc = st.session_state.get("pagamentos_protecoes")
    cadastros_nao_clientes_doc = st.session_state.get("pagamentos_nao_localizados")
    if (
        plano_atualizacao_doc is not None
        and protecoes_doc is not None
        and cadastros_nao_clientes_doc is not None
    ):
        resumo_dinamico = gerar_resumo_dinamico_pagamentos(
            resultado,
            plano_atualizacao_doc,
            plano,
            plano_inativas,
            protecoes_doc,
            cadastros_nao_clientes_doc,
            assinatura_resultado[0],
            resumo_condicao_100,
        )
        with st.expander("Resumo documental dinâmico das Etapas 1 e 2"):
            st.text(resumo_dinamico)
            st.download_button(
                "⬇️ Baixar resumo atualizado para e-mail (TXT)",
                data=resumo_dinamico.encode("utf-8-sig"),
                file_name="resumo_etapas_1_e_2_pagamentos.txt",
                mime="text/plain",
                key="pagamentos_baixar_resumo_dinamico",
                use_container_width=True,
            )
    if novos == 0:
        st.success("Todos os bloqueios calculados já existem.")
        return
    st.checkbox(
        f"Confirmo a inserção de até {novos:,} bloqueios.".replace(",", "."),
        key="pagamentos_confirmar_bloqueios",
    )
    if st.button(
        "Inserir bloqueios das condições de pagamento",
        type="primary",
        disabled=not st.session_state.get("pagamentos_confirmar_bloqueios", False),
        key="pagamentos_aplicar_bloqueios",
        use_container_width=True,
    ):
        try:
            progresso, concluir_progresso = criar_acompanhamento_progresso(
                "Inserindo bloqueios das condições de pagamento..."
            )
            with st.spinner("Inserindo bloqueios ausentes em uma única transação..."):
                resumo = aplicar_bloqueios_condicoes(
                    plano["cliente_codigo"].astype(int).tolist(), progresso
                )
            concluir_progresso()
            st.session_state.pop("pagamentos_plano_bloqueios", None)
            st.session_state.pop("pagamentos_plano_bloqueios_inativas", None)
            st.session_state.pop("pagamentos_resumo_condicao_100", None)
            st.success(
                f"Concluído: {resumo['bloqueios_inseridos']:,} bloqueios inseridos "
                f"para {resumo['clientes_classificados']:,} clientes; "
                f"{resumo['protegidos']:,} protegidos na revalidação."
                .replace(",", ".")
            )
        except Exception as exc:
            st.error("A transação inteira foi revertida devido ao erro: " + str(exc))


def render_pagamentos_mais_usados() -> None:
    st.title(
        "Pagamentos + usados e bloqueios de condições de pagamento por tipo "
        "estabelecimento X equipe"
    )
    hoje = date.today()
    filtro_inicio, filtro_fim, filtro_acao = st.columns([1, 1, 1])
    data_inicio = filtro_inicio.date_input(
        "Data inicial",
        subtrair_meses(hoje, 6),
        key="pagamentos_data_inicio",
        format="DD/MM/YYYY",
    )
    data_fim = filtro_fim.date_input(
        "Data final",
        hoje,
        key="pagamentos_data_fim",
        format="DD/MM/YYYY",
    )
    st.caption(
        f"Clientes que fizeram compras de {data_inicio:%d/%m/%Y} a "
        f"{data_fim:%d/%m/%Y}. O uso é contado por pedidos distintos; em caso de "
        "empate, prevalece o uso mais recente."
    )
    st.markdown(
        "<small><b>Tipos por equipe:</b><br>"
        "<b>Multicanal:</b> Conveniência (21, 22, 23, 24); Farmácia (25); "
        "Zé Delivery (26); Panificadora (31, 32); Mercados (33, 34); "
        "Mercado de Bebidas (39, 71); Cash Carry (49); Distribuidora (72); "
        "Empório (73); Consumidor final (93); Delicatessen (96); Academia "
        "(97); Gula (201).<br><b>Key Off:</b> "
        + ", ".join(map(str, sorted(TIPOS_ESTABELECIMENTO_KEY_OFF)))
        + ".<br><b>Key On/On Trade:</b> "
        + ", ".join(map(str, sorted(TIPOS_ESTABELECIMENTO_KEY_ON)))
        + ".<br><b>Regras de bloqueio:</b> (1) condições com PRZ não são "
        "bloqueadas para CPF, Multicanal ou Key On/On Trade; (2) condições com "
        "PRZ são bloqueadas para Key Off; (3) condições sem PRZ são bloqueadas "
        "para CPF, Multicanal e Key On/On Trade; (4) bloqueios existentes nunca "
        "são removidos; (5) a tabela 480 (Atacado) e seus vínculos não são alterados; "
        "(6) clientes dos vendedores 1929 ou 187 — Atacado ficam fora de qualquer ação, "
        "bloqueio ou restrição; (7) condições sem PRZ não são bloqueadas "
        "nos tipos 40, 49, 36, 34, 47, 35, 38, 33 e 39; "
        "(8) condições inativas nunca são inseridas; "
        "(9) PRZ e à vista permanecem liberadas para Multicanal e Key On/On Trade; "
        "(10) a condição 100 (A VISTA) nunca é bloqueada para nenhum cliente.</small>",
        unsafe_allow_html=True,
    )
    st.subheader("Etapa 1 - Atualizar padrões no cadastro dos clientes")
    st.warning(
        "Esta operação altera CONDICAOPAGAMENTO e FORMAPAGAMENTO em CLIFOR para "
        "todos os clientes do resultado que estiverem com valores diferentes. "
        "Prepare e confira a prévia antes de confirmar."
    )
    render_quadro_regras_bloqueios_pagamento()
    consultar = filtro_acao.button(
        "Gerar analise de dados para etapas 1 e 2", type="primary",
        use_container_width=True,
    )
    pasta_restore = SNAPSHOT_RESTORE_ETAPAS
    restore_etapa_1 = pasta_restore / "restore_etapa_1_20260831.sql"
    restore_etapa_2 = pasta_restore / "restore_etapa_2_20260831.sql"
    if restore_etapa_1.exists() and restore_etapa_2.exists():
        st.caption(
            "Restores de referência da virada para 01/09/2026 00:00. "
            "Captura técnica concluída em 31/08/2026 às 23:56:07. "
            "Os botões apenas baixam os arquivos; nenhum SQL é executado."
        )
        coluna_restore_1, coluna_restore_2 = st.columns(2)
        coluna_restore_1.download_button(
            "⬇️ Restore Etapa 1 — 01/09/2026 00:00",
            data=restore_etapa_1.read_bytes(),
            file_name="restore_etapa_1_referencia_20260901_0000.sql",
            mime="application/sql",
            key="pagamentos_baixar_restore_etapa_1_20260901",
            use_container_width=True,
        )
        coluna_restore_2.download_button(
            "⬇️ Restore Etapa 2 — 01/09/2026 00:00",
            data=restore_etapa_2.read_bytes(),
            file_name="restore_etapa_2_referencia_20260901_0000.sql",
            mime="application/sql",
            key="pagamentos_baixar_restore_etapa_2_20260901",
            use_container_width=True,
        )
    else:
        st.warning("Os arquivos de restore documentados não foram encontrados.")
    if consultar:
        if data_inicio > data_fim:
            st.error("A data inicial deve ser anterior ou igual à data final.")
        else:
            try:
                atualizar_tempo, concluir_tempo = criar_acompanhamento_progresso(
                    "Calculando condição e forma mais usadas por cliente..."
                )
                atualizar_tempo(0, 1)
                with st.spinner("Calculando condição e forma mais usadas por cliente..."):
                    resultado = carregar_pagamentos_mais_usados(
                        data_inicio, data_fim
                    )
                st.session_state.pagamentos_mais_usados_resultado = resultado
                st.session_state.pagamentos_mais_usados_periodo = (
                    data_inicio, data_fim
                )
                st.session_state.pagamentos_protecoes = consultar_protecoes_pagamentos(
                    resultado["cliente_codigo"].dropna().astype(int).tolist()
                )
                st.session_state.pagamentos_nao_localizados = (
                    consultar_clientes_nao_localizados_pagamentos(resultado)
                )
                st.session_state.pagamentos_nao_localizados_periodo = (
                    data_inicio, data_fim
                )
                concluir_tempo()
                st.session_state.pagamentos_protecoes_periodo = (data_inicio, data_fim)
                st.session_state.pop("pagamentos_plano_atualizacao", None)
                st.session_state.pop("pagamentos_plano_bloqueios", None)
                st.session_state.pop("pagamentos_plano_bloqueios_inativas", None)
                st.session_state.pop("pagamentos_resumo_condicao_100", None)
            except Exception as exc:
                st.error(f"Não foi possível consultar os pagamentos mais usados: {exc}")

    resultado = st.session_state.get("pagamentos_mais_usados_resultado")
    periodo = st.session_state.get("pagamentos_mais_usados_periodo")
    if resultado is None:
        st.info("Clique em Consultar pagamentos mais usados para gerar o resultado.")
        return
    if periodo != (data_inicio, data_fim):
        st.info("O período mudou. Clique em consultar para atualizar o resultado.")
        return
    if resultado.empty:
        st.info("Nenhum cliente com compras foi encontrado no período selecionado.")
        return

    protecoes = st.session_state.get("pagamentos_protecoes")
    if protecoes is None or st.session_state.get("pagamentos_protecoes_periodo") != periodo:
        try:
            protecoes = consultar_protecoes_pagamentos(
                resultado["cliente_codigo"].dropna().astype(int).tolist()
            )
            st.session_state.pagamentos_protecoes = protecoes
            st.session_state.pagamentos_protecoes_periodo = periodo
        except Exception as exc:
            st.error(f"Não foi possível conferir as proteções dos clientes: {exc}")
            return
    clientes_vendedores_protegidos = protecoes[protecoes["vendedor_187_1929"]].copy()
    clientes_tabela_480 = int(protecoes["tabela_480"].sum())
    nao_localizados_df = st.session_state.get("pagamentos_nao_localizados")
    if (
        nao_localizados_df is None
        or st.session_state.get("pagamentos_nao_localizados_periodo") != periodo
    ):
        try:
            nao_localizados_df = consultar_clientes_nao_localizados_pagamentos(resultado)
            st.session_state.pagamentos_nao_localizados = nao_localizados_df
            st.session_state.pagamentos_nao_localizados_periodo = periodo
        except Exception as exc:
            st.error(f"Não foi possível conferir os clientes não localizados: {exc}")
            return
    fornecedores_df = nao_localizados_df[
        nao_localizados_df["classificacao"].eq("Fornecedor")
    ].copy()
    realmente_nao_localizados_df = nao_localizados_df[
        nao_localizados_df["classificacao"].eq("Não localizado no CLIFOR")
    ].copy()

    total_pedidos = int(resultado["pedidos_periodo"].fillna(0).sum())
    total_condicoes = int(resultado["condicao_codigo"].nunique())
    total_formas = int(resultado["forma_codigo"].nunique())
    media_pedidos = total_pedidos / len(resultado) if len(resultado) else 0
    i1, i2, i3, i4, i5 = st.columns(5)
    i1.metric("Clientes com compras", f"{len(resultado):,}".replace(",", "."))
    i2.metric("Pedidos no período", f"{total_pedidos:,}".replace(",", "."))
    i3.metric("Média de pedidos/cliente", f"{media_pedidos:.1f}".replace(".", ","))
    i4.metric("Condições / formas usadas", f"{total_condicoes} / {total_formas}")
    i5.metric(
        "Clientes protegidos dos vend. 1929/187 — Atacado",
        len(clientes_vendedores_protegidos),
    )
    st.caption(
        f"Regra 5: {clientes_tabela_480:,} cliente(s) do resultado está(ão) "
        "vinculado(s) à tabela 480 (Atacado). Esses vínculos serão preservados."
        .replace(",", ".")
    )
    st.info(
        f"Cadastros do histórico classificados como fornecedores: "
        f"{len(fornecedores_df):,}. Códigos realmente não localizados no CLIFOR: "
        f"{len(realmente_nao_localizados_df):,}.".replace(",", ".")
    )
    aba_resultado, aba_vendedores, aba_nao_localizados = st.tabs([
        "Todos os clientes",
        "Revisão — vendedores 1929/187 — Atacado",
        f"Fornecedores e outros cadastros ({len(nao_localizados_df)})",
    ])
    with aba_resultado:
        st.download_button(
            "⬇️ Baixar a lista de todos os clientes em Excel",
            data=exportar_pagamentos_excel(resultado),
            file_name=(
                f"todos_clientes_pagamentos_{data_inicio:%Y%m%d}_a_"
                f"{data_fim:%Y%m%d}.xlsx"
            ),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="pagamentos_baixar_todos_clientes",
            use_container_width=True,
        )
        st.dataframe(
            resultado,
            hide_index=True,
            use_container_width=True,
            height=650,
            column_config={
                "cliente_codigo": st.column_config.NumberColumn(
                    "Cód. CLIFOR", format="%d"
                ),
                "cliente_nome": "Nome CLIFOR",
                "condicao_codigo": st.column_config.NumberColumn(
                    "Cód. condição", format="%d"
                ),
                "condicao_nome": "Condição de pagamento mais usada",
                "forma_codigo": st.column_config.NumberColumn(
                    "Cód. forma", format="%d"
                ),
                "forma_nome": "Forma de pagamento mais usada",
                "pedidos_periodo": st.column_config.NumberColumn(
                    "Pedidos no período", format="%d"
                ),
                "pedidos_condicao": st.column_config.NumberColumn(
                    "Pedidos com condição", format="%d"
                ),
                "pedidos_forma": st.column_config.NumberColumn(
                    "Pedidos com forma", format="%d"
                ),
                "ultima_compra": st.column_config.DateColumn(
                    "Última compra", format="DD/MM/YYYY"
                ),
            },
        )
    with aba_vendedores:
        st.caption(
            "Estes clientes ficam fora de todas as atualizações, restrições e "
            "inclusões de bloqueios deste fluxo."
        )
        st.download_button(
            "⬇️ Baixar a lista de clientes protegidos em Excel",
            data=exportar_previa_pagamentos_excel(
                clientes_vendedores_protegidos[["cliente_codigo", "cliente_nome"]],
                "Clientes protegidos",
                {
                    "cliente_codigo": "Código CLIFOR",
                    "cliente_nome": "Nome CLIFOR",
                },
            ),
            file_name=(
                f"clientes_protegidos_vendedores_1929_187_atacado_"
                f"{data_inicio:%Y%m%d}_a_{data_fim:%Y%m%d}.xlsx"
            ),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="pagamentos_baixar_clientes_protegidos",
            use_container_width=True,
        )
        st.dataframe(
            clientes_vendedores_protegidos[["cliente_codigo", "cliente_nome"]],
            hide_index=True,
            use_container_width=True,
            column_config={
                "cliente_codigo": st.column_config.NumberColumn(
                    "Cód. CLIFOR", format="%d"
                ),
                "cliente_nome": "Nome CLIFOR",
            },
        )
    with aba_nao_localizados:
        st.caption(
            f"Entre estes registros, {len(fornecedores_df)} está(ão) cadastrado(s) "
            "como fornecedor. A coluna Classificação identifica cada caso. Eles "
            "permanecem na lista para conferência, mas não são atualizados como clientes."
        )
        st.download_button(
            "⬇️ Baixar fornecedores e outros cadastros em Excel",
            data=exportar_previa_pagamentos_excel(
                nao_localizados_df,
                "Não localizados",
                {
                    "cliente_codigo": "Código do histórico",
                    "cliente_nome": "Nome no histórico",
                    "tipo_clifor": "Tipo no CLIFOR",
                    "classificacao": "Classificação",
                },
            ),
            file_name=(
                f"clientes_nao_localizados_{data_inicio:%Y%m%d}_a_"
                f"{data_fim:%Y%m%d}.xlsx"
            ),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="pagamentos_baixar_nao_localizados",
            use_container_width=True,
        )
        st.dataframe(
            nao_localizados_df,
            hide_index=True,
            use_container_width=True,
            column_config={
                "cliente_codigo": st.column_config.NumberColumn(
                    "Código do histórico", format="%d"
                ),
                "cliente_nome": "Nome no histórico",
                "tipo_clifor": st.column_config.NumberColumn(
                    "Tipo no CLIFOR", format="%d"
                ),
                "classificacao": "Classificação",
            },
        )
    st.divider()
    st.subheader(
        "Etapa 1 — Atualizar condições e formas de pagamento dos clientes"
    )
    st.caption(
        "Serão comparados e, após confirmação, atualizados os campos "
        "CLIFOR.CONDICAOPAGAMENTO e CLIFOR.FORMAPAGAMENTO."
    )
    assinatura_atualizacao = (
        periodo,
        tuple(
            resultado[["cliente_codigo", "condicao_codigo", "forma_codigo"]]
            .fillna(-1).astype(int).itertuples(index=False, name=None)
        ),
    )
    if st.button(
        "Preparar atualização dos padrões",
        key="pagamentos_preparar_atualizacao",
        use_container_width=True,
    ):
        try:
            progresso, concluir_progresso = criar_acompanhamento_progresso(
                "Comparando os padrões atuais no cadastro..."
            )
            with st.spinner("Comparando os padrões atuais no cadastro..."):
                plano = planejar_atualizacao_pagamentos(resultado, progresso)
            concluir_progresso()
            st.session_state.pagamentos_plano_atualizacao = plano
            st.session_state.pagamentos_assinatura_atualizacao = (
                assinatura_atualizacao
            )
            st.session_state.pagamentos_confirmar_atualizacao = False
        except Exception as exc:
            st.session_state.pop("pagamentos_plano_atualizacao", None)
            st.error(f"Não foi possível preparar a atualização: {exc}")

    plano = st.session_state.get("pagamentos_plano_atualizacao")
    if plano is None:
        render_bloqueios_condicoes_pagamento(resultado, assinatura_atualizacao)
        return
    if st.session_state.get("pagamentos_assinatura_atualizacao") != assinatura_atualizacao:
        st.session_state.pop("pagamentos_plano_atualizacao", None)
        st.info("O resultado mudou. Prepare novamente a atualização.")
        render_bloqueios_condicoes_pagamento(resultado, assinatura_atualizacao)
        return

    alteracoes = plano[plano["atualizacao_necessaria"]].copy()
    protegidos_vendedores = len(clientes_vendedores_protegidos)
    nao_localizados = len(realmente_nao_localizados_df)
    p1, p2, p3, p4, p5 = st.columns(5)
    p1.metric("Clientes conferidos", len(plano))
    p2.metric("Clientes a atualizar", len(alteracoes))
    p3.metric("Já estavam corretos", len(plano) - len(alteracoes))
    p4.metric("Fornecedores no resultado", len(fornecedores_df))
    p5.metric(
        "Clientes protegidos dos vend. 1929/187 — Atacado",
        protegidos_vendedores,
    )
    if nao_localizados:
        st.caption(
            f"{nao_localizados} códigos do histórico não estão atualmente cadastrados "
            "no CLIFOR e, por segurança, não serão atualizados."
        )
    st.download_button(
        "Exportar prévia da atualização para Excel",
        data=exportar_previa_pagamentos_excel(
            alteracoes,
            "Prévia de atualização",
            {
                "cliente_codigo": "Código CLIFOR",
                "cliente_nome": "Nome CLIFOR",
                "condicao_atual_codigo": "Código condição atual",
                "condicao_nova_codigo": "Código nova condição",
                "condicao_nova_nome": "Nome da nova condição",
                "forma_atual_codigo": "Código forma atual",
                "forma_nova_codigo": "Código nova forma",
                "forma_nova_nome": "Nome da nova forma",
                "atualizacao_necessaria": "Atualização necessária",
            },
        ),
        file_name=(
            f"previa_atualizacao_pagamentos_{periodo[0]:%Y%m%d}_a_"
            f"{periodo[1]:%Y%m%d}.xlsx"
        ),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="pagamentos_exportar_atualizacao",
        use_container_width=True,
    )
    if alteracoes.empty:
        st.success("Todos os clientes já possuem os padrões calculados.")
        render_bloqueios_condicoes_pagamento(resultado, assinatura_atualizacao)
        return
    st.dataframe(
        alteracoes,
        hide_index=True,
        use_container_width=True,
        height=420,
        column_config={
            "cliente_codigo": st.column_config.NumberColumn("Cód. CLIFOR", format="%d"),
            "cliente_nome": "Nome CLIFOR",
            "condicao_atual_codigo": st.column_config.NumberColumn(
                "Condição atual", format="%d"
            ),
            "condicao_nova_codigo": st.column_config.NumberColumn(
                "Nova condição", format="%d"
            ),
            "condicao_nova_nome": "Nome da nova condição",
            "forma_atual_codigo": st.column_config.NumberColumn(
                "Forma atual", format="%d"
            ),
            "forma_nova_codigo": st.column_config.NumberColumn(
                "Nova forma", format="%d"
            ),
            "forma_nova_nome": "Nome da nova forma",
            "atualizacao_necessaria": None,
        },
    )
    st.checkbox(
        f"Confirmo a atualização de até {len(alteracoes)} clientes.",
        key="pagamentos_confirmar_atualizacao",
    )
    if st.button(
        "Etapa 1 - Atualizar condições e formas de pagamento padrões",
        type="primary",
        disabled=not st.session_state.get("pagamentos_confirmar_atualizacao", False),
        key="pagamentos_aplicar_atualizacao",
        use_container_width=True,
    ):
        try:
            progresso, concluir_progresso = criar_acompanhamento_progresso(
                "Atualizando condições e formas de pagamento padrões..."
            )
            with st.spinner("Atualizando os cadastros em uma única transação..."):
                resumo = aplicar_atualizacao_pagamentos(alteracoes, progresso)
            concluir_progresso()
            st.session_state.pop("pagamentos_plano_atualizacao", None)
            carregar_pagamentos_mais_usados.clear()
            st.success(
                f"Atualização concluída: {resumo['alterados']} clientes alterados; "
                f"{resumo['sem_alteracao']} já estavam corretos; "
                f"{resumo['protegidos']} protegidos na revalidação."
            )
        except Exception as exc:
            st.error(
                "A transação inteira foi revertida devido ao erro: " + str(exc)
            )
    render_bloqueios_condicoes_pagamento(resultado, assinatura_atualizacao)


def render_documentacao() -> None:
    st.title("Documentação das análises")
    documento_word = DOCUMENTACAO_REGRAS_COMBOS
    if documento_word.exists():
        st.download_button(
            "Baixar documentação de regras de combos (Word)",
            data=documento_word.read_bytes(),
            file_name=documento_word.name,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            type="primary",
            help="Baixa a versão atual da matriz de regras, responsáveis e restrições.",
        )
    else:
        st.warning(
            "O documento Word de regras de combos não está disponível neste servidor."
        )
    documento_pop = POP_LIBERACAO_COMBOS
    if documento_pop.exists():
        st.download_button(
            "Baixar POP Liberação de Combos — SGQ (Word)",
            data=documento_pop.read_bytes(),
            file_name=documento_pop.name,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            help="Baixa o procedimento operacional completo e atualizado do SGQ.",
        )
    else:
        st.warning("O POP de Liberação de Combos não está disponível neste servidor.")
    st.caption(
        "Os documentos contêm a matriz consolidada e o procedimento operacional do SGQ."
    )
    st.markdown("""
### 1. Queda de positivação

Identifica clientes que já compraram uma indústria, mas não positivaram nos últimos dias definidos no filtro. A análise é feita por **cliente + indústria**, sem entrar em SKU.

O universo de clientes é cruzado com cada indústria selecionada. Portanto, também entram clientes que nunca compraram a indústria no histórico carregado. Eles são apresentados com última compra e dias sem compra vazios, unidades históricas e dias com compra iguais a zero. Uma compra exatamente na data-limite (`hoje - dias`) é considerada recente e retira o cliente do resultado daquela indústria.

Estas regras de ausência de compra são destinadas somente aos combos Dormente positivação e Dormente volume. Elas não devem ser usadas para analisar os demais tipos de combo.

Na padronização dos títulos, as filiais 3, 4, 5 e 7 representam PR e as filiais 6 e 8 representam SC. O estado deve ser o último marcador do título; marcadores como M e VIN/ESP ficam antes dele. Combos com filiais dos dois estados devem ser revisados antes da alteração.

Regra universal de liberação: se o combo tiver ao menos um produto de vinho, espumante, água ou xarope, nenhum cliente sem Inscrição Estadual válida poderá ser incluído. A regra vale para todas as classificações e todos os estados. IE nula, vazia ou `ISENTO` é bloqueada. Nas inserções originadas das análises de queda de positivação e de volume, a tela permite desconsiderar somente os pares combo/cliente inválidos e prosseguir com os clientes válidos; a prévia identifica os excluídos e a transação recalcula a elegibilidade antes de gravar. Nos demais fluxos, a presença de cliente inválido continua bloqueando a operação inteira. Exclusões permanecem permitidas.

Em combos de Manutenção cujo nome operacional contenha POSITIVACAO, o final deve seguir `... POSITIVACAO M ESTADO`. Isso não os classifica como Dormente; a classificação Dormente positivação exige o marcador `D POSITIVACAO`, que pode aparecer em qualquer posição do título. Da mesma forma, `D VOLUME` pode aparecer em qualquer posição; em ambos os casos, o estado permanece obrigatório no final.

O campo **Tipo de análise** identifica a origem: **Compra indústria** para a carteira atual com vendedor, **Base televendas** para clientes verdes sem vendedor e **Indústria+televendas** quando o CLIFOR pertence aos dois conjuntos. A Base televendas não substitui o histórico: seus clientes recebem a mesma regra de positivação aplicada às vendas da query principal.

**Legenda dos campos:**

- **Unidades históricas:** total de unidades compradas pelo cliente daquela indústria antes do período considerado recente.
- **Dias com compra:** quantidade de datas distintas em que o cliente realizou compras daquela indústria no histórico.
- **Dias sem compra:** quantidade de dias transcorridos desde a última compra registrada daquela indústria.
- **Estado:** UF cadastrada para o cliente no DW, como SC ou PR.
- **Tipo de estabelecimento:** código e nome da classificação comercial cadastrada para o cliente.
- **Quantidade de vendedores na carteira:** total de vendedores distintos vinculados ao cliente.
- **Situação da carteira:** informa se o cliente possui ou não vendedor alocado.

### 2. Queda de volume anual

Compara o volume comprado por cliente e indústria em períodos anuais equivalentes, do dia 01/01 até a data atual e contra o mesmo intervalo do ano anterior. Classifica crescimento, estabilidade, queda, cliente novo e ausência de compra no período atual.

A Base televendas recebe exatamente os mesmos períodos, cálculo de volume (`quantidade / quantidade_compra`) e classificações da Compra indústria. Se o mesmo CLIFOR estiver nas duas bases, o campo **Tipo de análise** apresenta **Indústria+televendas**.

O campo **Estado** apresenta a UF cadastrada para o cliente no DW.

Nas análises que possuem essa informação, o filtro de Estado permite selecionar uma ou várias UFs. Sem seleção, todas são consideradas.

O filtro de **Tipo de estabelecimento** permite selecionar uma ou várias opções no formato “código — nome”.

Nas análises de queda de positivação e de volume, o filtro de carteira inicia em **Com vendedor alocado** e é aplicado **somente aos registros Compra indústria**. Os registros **Base televendas** e **Indústria+televendas** permanecem no resultado independentemente da opção escolhida, pois a carteira de vendedor não restringe a coorte do Televendas.

Na prática:

- **Com vendedor alocado:** filtra a Compra indústria para clientes com vendedor e mantém todos os registros da Base televendas e Indústria+televendas.
- **Sem vendedor alocado:** filtra a Compra indústria para clientes sem vendedor e mantém todos os registros da Base televendas e Indústria+televendas.
- **Todos:** não restringe nenhuma origem.

### Base televendas — semáforo verde

- Considera clientes ativos do tipo cliente (`CLIFOR.TIPO = 1`).
- Exclui clientes ligados ao vendedor BEES 2262.
- Verde significa última compra (`CLIFOR.DATAMOVIMENTO`) entre 30 e 120 dias, inclusive.
- **Verde e sem vendedor** significa ausência de vínculo em `FUNCIONARIOCLIFOR`.
- **Verde e sem rota** significa ausência de vínculo em `ROTACLIFOR`.
- Os três indicadores são carregados do Firebird e exibidos em uma linha própria; os indicadores preexistentes permanecem identificados como **Compra indústria**.

### Inserção de clientes e cotas em combos

Nas tabelas que possuem `cliente_codigo`, o botão **Inserir clientes e cotas em combos existentes** usa exatamente os clientes únicos do último resultado exibido, depois de todos os filtros da tela.

**Regra:** clientes podem ser cadastrados em todos os combos dormentes, tanto **Dormente positivação** quanto **Dormente volume**. Ambos aparecem na seleção e também podem ser informados pelo código.

- A lista apresenta somente combos vigentes na data atual, no formato **código — nome**.
- É possível selecionar vários combos e também digitar vários códigos separados por vírgula, espaço, ponto e vírgula ou quebra de linha.
- Códigos digitados precisam existir e estar vigentes; caso contrário, a preparação é bloqueada.
- Nas análises de **queda de positivação** e de **queda de volume**, a opção **Inserir os clientes válidos** mantém fora da gravação somente os clientes sem IE válida para combos com vinho, espumante, água ou xarope. A prévia apresenta esses clientes separadamente, e a transação revalida todos os pares antes do insert.
- A quantidade de cotas por cliente inicia em `1` e pode ser editada com um inteiro positivo.
- Os códigos de `COTA` são herdados dos registros já existentes do combo em `ITEMCOTACOMBOCLIENTE`. Um combo sem cota configurada é bloqueado.
- Antes da gravação, o sistema consulta `COMBOCLIFOR` e `ITEMCOTACOMBOCLIENTE`, desconsidera vínculos existentes e mostra quantos clientes, combos, vínculos e cotas novos serão afetados.
- A gravação só ocorre após clicar em **Confirmar inserção** na pergunta de confirmação.
- Os vínculos de cliente usam `REPLICAR = 'N'`. Clientes e cotas são gravados na mesma transação; se houver erro, é feito rollback de tudo.
- Se os filtros mudarem após a preparação, a confirmação anterior é invalidada e precisa ser preparada novamente.

### Validação de regras de títulos de combos ativos e criação de combo

Na criação, o código do combo não é digitado: ele será gerado automaticamente pelo ERP. O usuário informa os demais dados do cadastro e revisa a prévia antes da gravação.

O menu **Validação de regras de títulos de combos ativos** consulta todos os combos vigentes na data atual e apresenta, ao lado do título da tela, indicadores do total de combos, títulos OK e títulos pendentes de correção. Também apresenta código, nome, datas e conformidade do título. É uma tela somente de conferência: a classificação continua disponível como filtro, mas classificação e cadastro são mantidos diretamente no ERP. O botão **Atualizar agora** ignora o cache. A pesquisa considera código, nome e situação da validação.

O menu **Conferência de combos** permite selecionar um ou mais combos vigentes e consultar duas visões: clientes com seus códigos de cota, filial e quantidade; e produtos com grupo, faixas de quantidade e valor de venda.

As classificações usadas internamente na validação são **Rede**, **Manutenção**, **Tabela**, **MIX**, **Dormente positivação**, **Dormente volume** e **Não classificado**. A tela não permite editar nem salvar classificações; alterações devem ser realizadas diretamente no ERP.

O formulário único pode ser aberto vazio ou a partir dos resultados filtrados de Positivação e Volume. Ele permite revisar/remover clientes, adicionar códigos manualmente, selecionar várias filiais ativas e editar produtos/faixas com grupo, quantidades, produto e valor. As filiais são planejadas em `COMBOFILIAL`. A validação confere datas, produtos e clientes no TOP, valores, duplicidades e conflitos de faixa; o código do combo é gerado pelo ERP.

A prévia informa vigência, classificação, grupos, produtos, clientes e tabelas planejadas (`COMBO`, `GRUPOCOMBO`, `ITEMGRUPOCOMBO` e `COMBOCLIFOR`). A criação final permanece desabilitada porque o schema não define como reservar `GRUPOCOMBO.CODIGO`, nem permite inferir com segurança `QTDE/BONIFICADO`, `GRUPOCOMBODESCONTO` e flags funcionais do cabeçalho. Nenhum combo parcial é criado.

O acesso ao formulário usa `ANALISE_VENDAS_USUARIOS_CRIAR_COMBO`; sem essa variável, são autorizados os perfis Administrador, Admin, TI e Gerente comercial.

Falhas durante a preparação são registradas em `dados_locais/combo_criacao_erros.jsonl`, com mensagem sanitizada, etapa, usuário e data/hora. Esse arquivo e os arquivos de classificação devem fazer parte do backup operacional.

### Inserção dinâmica de combos

O menu **Inserção dinâmica de combos** seleciona clientes ativos diretamente no Firebird e permite incluir ou excluir seus vínculos em `COMBOCLIFOR`. Todos os campos aceitam múltiplas seleções; campo sem seleção significa **Todos**.

Filtros disponíveis: Região, Estado, Cidade, Segmento, Tipo de estabelecimento, Equipe, Supervisor, Vendedor, Classificação, Combo, Filial, Bairro, presença de CNPJ, situação da IE, presença de Venda e vendas por Fornecedor, Marca, Classe de produto e Produto dentro de Data início e Data fim.

- Estado é obtido pela cidade cadastrada no cliente.
- Segmento é obtido pelo tipo de estabelecimento.
- Equipe e Supervisor são obtidos pelos vendedores vinculados em `FUNCIONARIOCLIFOR`.
- Venda considera pedidos faturados, não cancelados e emitidos dentro do período informado.
- IE válida em **Sim** exige valor preenchido e diferente de `ISENTO`; **Não** seleciona IE nula, vazia ou `ISENTO`. O valor é exibido na prévia para conferência.
- Se Fornecedor, Marca, Classe de produto ou Produto for selecionado, o cliente precisa possuir venda faturada e não cancelada correspondente no período, mesmo quando Venda estiver em **Todos**. A classe vem de `PRODUTO.CLASSE` e o seletor mostra código e nome do cadastro `CLASSE`.
- **Incluir** grava somente vínculos ausentes com `REPLICAR = 'N'`.
- **Incluir** também grava todas as cotas ausentes em `ITEMCOTACOMBOCLIENTE`. Informe uma quantidade inteira positiva (padrão `1`); os códigos de cota são herdados das filiais ativas do combo.
- **Inserir somente cotas** ignora todos os filtros de clientes e consulta exclusivamente os clientes que já pertencem a cada combo em `COMBOCLIFOR`. Essa operação nunca cria, altera ou exclui vínculos em `COMBOCLIFOR`.
- Em **Inserir somente cotas**, selecione o combo, informe a quantidade, prepare a operação e confira a lista de clientes e o total de cotas. A lista de clientes é obrigatoriamente relida dentro da transação antes da gravação.
- Se o cliente já estiver em `COMBOCLIFOR`, mas ainda não possuir a cota, somente a cota faltante será criada. Cotas existentes não são duplicadas nem sobrescritas.
- Para executar corretamente: selecione os clientes pelos filtros, selecione ao menos um combo, informe a quantidade, clique em **Preparar operação**, confira os totais de vínculos e cotas e somente então confirme.
- Combos sem cota configurada, ou com filial ativa sem cota vigente, são bloqueados antes da confirmação.
- **Incluir** permite combos classificados como Dormente positivação ou Dormente volume; **Excluir** continua permitido para remover vínculos existentes.
- **Excluir** remove somente vínculos que já existem para os clientes e combos selecionados.
- A tela apresenta os clientes encontrados e as quantidades afetadas antes da confirmação.
- Inclusões e exclusões são transacionais; qualquer erro provoca rollback de toda a operação.

### 3. Mix por equipe

Compara a quantidade de SKUs distintos e o faturamento por equipe e indústria nos mesmos períodos equivalentes. Assim, a análise identifica tanto a perda de variedade quanto situações em que a equipe continua positivando os mesmos SKUs, mas vende um valor menor. As datas são calculadas pela data atual: por exemplo, em 01/08/2026 compara 01/01/2025–01/08/2025 com 01/01/2026–01/08/2026.

**Legenda dos campos:**

- **Mix anterior/atual:** quantidade de SKUs distintos vendidos em cada período.
- **Queda mix:** diferença entre o mix atual e o anterior; valor negativo representa perda de SKUs.
- **Faturamento anterior/atual:** soma do valor total vendido em cada período.
- **Queda faturamento:** faturamento atual menos o anterior; valor negativo representa redução nas vendas.
- **Situação:** indica queda de mix, faturamento, ambos ou ausência de queda.

### 4. Pernod × Mtrix — fase 2 (em validação de dados iniciais por Gustavo → ver necessidade de desenvolvimento)

Recebe o arquivo CSV ou Excel revisado pelo Gilmar, permite indicar as colunas de cliente, produto e volume e cruza esses dados com as vendas Pernod do DW. O resultado mostra valores conciliados e divergentes por cliente e produto.

Na tela **Análise Pernod Reembolso**, os pedidos tipo 48 são considerados porque a indústria visualiza esse movimento via Mtrix. A tela confronta o reembolso informado pela Pernod com o valor recalculado incluindo tipo 48, mostra a diferença total e o valor extra a cobrar. Também compara, linha a linha por cliente e produto, as vendas do Dinho com a aba `Base_Reembolso`. A exportação completa preserva todas as análises; a simplificada mantém as duas primeiras abas da completa exatamente iguais e substitui a última por uma aba somente com resultado da comparação, cliente, CNPJ, data, filial, produto, unidades consolidadas e faturamento total.

### 9. Pagamentos + usados e bloqueios de condições de pagamento por tipo estabelecimento X equipe

A consulta usa os clientes com compras no período selecionado e apresenta a condição e a forma de pagamento mais usadas por quantidade de pedidos distintos. O período inicia com os últimos seis meses e pode ser alterado. Empates são resolvidos pelo uso mais recente e, depois, pelo menor código.

Tipos de estabelecimento por equipe:

- **Multicanal:** 21, 22, 23, 24, 25 (Farmácia), 26 (Zé Delivery), 31 e 32 (Panificadora), 33, 34, 39, 49 (Cash Carry), 71, 72, 73 (Empório), 93 (Consumidor final), 96 (Delicatessen), 97 (Academia) e 201 (Gula).
- **Key Off:** 35 e 38.
- **Key On/On Trade:** 41, 42, 43, 44, 45, 46, 51, 52, 53, 61, 62, 63, 65, 81, 82, 83, 84, 85, 86, 91 e 92.

O Ranking de SKUs considera Conveniência (21, 22, 23 e 24), Mercado de Bebidas (39 e 71), Distribuidora (72) e Mercados (33, 34, 35 e 38). Os demais tipos listados acima são extras e ainda não participam desse ranking.

O primeiro fluxo atualiza `CLIFOR.CONDICAOPAGAMENTO` e `CLIFOR.FORMAPAGAMENTO` com os padrões mais usados, após prévia e confirmação. O segundo fluxo insere bloqueios ausentes em `CLIFORCONDICAOPAGAMENTO`, conforme estas regras:

1. Condições cujo nome contém `PRZ` não são bloqueadas para clientes CPF, Multicanal ou Key On/On Trade.
2. Condições cujo nome contém `PRZ` são bloqueadas para tipos Key Off.
3. Condições cujo nome não contém `PRZ` são bloqueadas para clientes CPF, Multicanal e Key On/On Trade, exceto a condição 100 protegida pela regra 10.
4. Bloqueios já existentes nunca são removidos.
5. A tabela de preço 480 (Atacado) e seus vínculos não são alterados.
6. Clientes vinculados aos vendedores 1929 ou 187 — Atacado não recebem nenhuma ação.
7. Condições sem `PRZ` não são bloqueadas nos tipos 40, 49, 36, 34, 47, 35, 38, 33 e 39. Os tipos Key Off 35 e 38 continuam bloqueando condições com `PRZ`.
8. Condições inativas são exibidas para conferência e nunca são inseridas.
9. Para Multicanal e Key On/On Trade, condições `PRZ` — inclusive prazos até 28 dias — e condições à vista permanecem liberadas. A preparação não recria esses bloqueios. Bloqueios preexistentes só deixam de restringir o cliente quando forem removidos operacionalmente.
10. A condição `100` (`A VISTA`) é protegida globalmente e nunca é inserida como bloqueio para nenhum cliente. Bloqueios preexistentes são preservados por este fluxo.

As duas operações possuem prévia, confirmação explícita, revalidação e transação única com rollback integral em caso de erro.

Após a preparação das duas etapas, o painel gera um **Resumo documental dinâmico das Etapas 1 e 2**. O texto apresenta o período, pedidos, clientes, alterações de padrão, proteções, fornecedores, bloqueios por regra, condições inativas e registros existentes usando os dados das prévias atuais. O resumo pode ser baixado em TXT para envio por e-mail e seus números são recalculados sempre que o período ou os cadastros mudarem.

O snapshot de restauração de referência da virada para **01/09/2026 00:00**, cuja captura técnica terminou em **31/08/2026 23:56:07**, está na pasta `restore_dados_etapas_1_2_20260831/`, com instruções em `restore_dados_etapas_1_2_20260831/README.md`. Os dois SQLs podem ser baixados diretamente abaixo do botão de geração da análise. Eles cobrem exclusivamente as prévias daquela captura e não substituem o backup nativo do Firebird.

### Liberação temporária para faturamento

O perfil **Faturamento** acessa somente a tela operacional de liberação temporária. A tela recebe a lista de clientes, mostra a prévia dos bloqueios existentes que serão retirados e exige confirmação. Cada operação fica persistida em `temporarios/` com usuário, horário e status, permitindo identificar no dia seguinte quais clientes continuam sem bloqueio.

Após o faturamento, a preparação da reaplicação mostra por cliente quais bloqueios serão recriados, quais já estão presentes e quais não voltam por não atenderem mais às regras atuais da Etapa 2. A reaplicação é transacional, revalida as regras no momento da gravação e registra o usuário e o horário da conclusão.

### Indústrias consideradas

- Pernod: fornecedores 80166 e 80066
- Campari: fornecedor 80047
- VCT: fornecedor 4135
""")


@st.cache_data(ttl=300, show_spinner=False)
def carregar_catalogos_dinamicos() -> dict[str, pd.DataFrame]:
    return listar_catalogos_dinamicos()


def seletor_catalogo(container, label: str, catalogo: pd.DataFrame, chave: str) -> list:
    if catalogo.empty:
        container.multiselect(label, [], key=chave, disabled=True)
        return []
    nomes = {
        int(item.codigo): str(item.nome or "SEM NOME")
        for item in catalogo.itertuples(index=False)
    }
    return container.multiselect(
        label, list(nomes), key=chave,
        format_func=lambda codigo: f"{codigo} — {nomes[codigo]}",
        placeholder="Todos",
    )


def render_insercao_dinamica() -> None:
    st.title("Inserção dinâmica de combos")
    st.caption(
        "Selecione um ou vários códigos em cada campo. Campo vazio significa Todos. "
        "A operação só é gravada após a prévia e a confirmação."
    )
    try:
        catalogos = carregar_catalogos_dinamicos()
        combos_vigentes = classificar_combos(
            carregar_combos_vigentes(), carregar_classificacoes()
        )
    except Exception as exc:
        st.error(f"Não foi possível carregar os filtros do Firebird: {exc}")
        return
    combos_catalogo = combos_vigentes.rename(columns={"combo": "codigo"})[["codigo", "nome"]]
    esquerda, direita = st.columns(2)
    regioes = seletor_catalogo(esquerda, "Região", catalogos["regioes"], "din_regioes")
    estados = seletor_catalogo(direita, "Estado", catalogos["estados"], "din_estados")
    cidades = seletor_catalogo(esquerda, "Cidade", catalogos["cidades"], "din_cidades")
    segmentos = seletor_catalogo(direita, "Segmento", catalogos["segmentos"], "din_segmentos")
    tipos = seletor_catalogo(esquerda, "Tipo estabelecimento", catalogos["tipos_estabelecimento"], "din_tipos")
    equipes = seletor_catalogo(direita, "Equipe", catalogos["equipes"], "din_equipes")
    supervisores = seletor_catalogo(esquerda, "Supervisor", catalogos["supervisores"], "din_supervisores")
    vendedores = seletor_catalogo(direita, "Vendedor", catalogos["vendedores"], "din_vendedores")
    classificacoes = seletor_catalogo(esquerda, "Classificação", catalogos["classificacoes"], "din_classificacoes")
    combos = seletor_catalogo(direita, "Combo", combos_catalogo, "din_combos")
    cnpj = esquerda.radio("Somente CNPJ", ["Todos", "Sim", "Não"], horizontal=True, key="din_cnpj")
    filiais = seletor_catalogo(direita, "Filial", catalogos["filiais"], "din_filiais")
    venda = esquerda.radio("Venda", ["Todos", "Sim", "Não"], horizontal=True, key="din_venda")
    ie = esquerda.radio(
        "IE válida", ["Todos", "Sim", "Não"], horizontal=True, key="din_ie",
        help=(
            "Sim: IE preenchida e diferente de ISENTO. "
            "Não: IE nula, vazia ou ISENTO."
        ),
    )
    data_inicio_col, data_fim_col = direita.columns(2)
    data_inicio = data_inicio_col.date_input(
        "Data início", date.today(), key="din_data_inicio", format="DD/MM/YYYY"
    )
    data_fim = data_fim_col.date_input(
        "Data fim", date.today(), key="din_data_fim", format="DD/MM/YYYY"
    )
    fornecedores = seletor_catalogo(direita, "Vendas — Fornecedor", catalogos["fornecedores"], "din_fornecedores")
    marcas = seletor_catalogo(esquerda, "Vendas — Marca", catalogos["marcas"], "din_marcas")
    classes_produto = seletor_catalogo(
        direita, "Vendas — Classe de produto",
        catalogos["classes_produto"], "din_classes_produto",
    )
    bairros = direita.multiselect(
        "Bairro", catalogos["bairros"]["nome"].astype(str).tolist(),
        key="din_bairros", placeholder="Todos",
    )
    produtos = seletor_catalogo(esquerda, "Vendas — Produto", catalogos["produtos"], "din_produtos")
    opcoes_acao = [
        "Inserir combo sem cotas",
        "Inserir combo com cotas",
        "Inserir somente cotas",
        "Excluir",
    ]
    if st.session_state.get("din_acao") not in {None, *opcoes_acao}:
        st.session_state.din_acao = opcoes_acao[0]
    rotulo_acao = st.radio(
        "Operação nos registros de COMBOCLIFOR",
        opcoes_acao,
        horizontal=True, key="din_acao",
    )
    acao = {
        "Inserir combo sem cotas": "Incluir sem cotas",
        "Inserir combo com cotas": "Incluir",
    }.get(rotulo_acao, rotulo_acao)
    acao_com_cotas = acao in {"Incluir", "Inserir somente cotas"}
    quantidade_cota = 1
    if acao_com_cotas:
        quantidade_cota = int(st.number_input(
            "Quantidade de cotas por cliente",
            min_value=1, value=1, step=1, key="din_quantidade_cota",
            help=(
                "Valor gravado em ITEMCOTACOMBOCLIENTE.QUANTIDADE. Os códigos "
                "de cota são herdados das filiais ativas do combo."
            ),
        ))
    st.caption(
        "Inserir combo sem cotas cria somente os vínculos ausentes. Inserir combo "
        "com cotas cria os vínculos e libera cada cliente na cota de todas as "
        "filiais ativas do combo. Inserir somente cotas ignora os filtros de clientes, "
        "usa exclusivamente quem já está em COMBOCLIFOR e nunca cria novos vínculos. "
        "Excluir remove apenas vínculos existentes "
        "entre os clientes encontrados e os combos selecionados. A inclusão é "
        "permitida em Dormente positivação e Dormente volume; a exclusão também "
        "permanece disponível."
    )
    st.markdown("**Exemplos e fluxos de cada operação**")
    with st.expander("Inserir combo sem cotas"):
        st.markdown(
            """
**Exemplo:** vincular ao combo selecionado os clientes encontrados pelos filtros, sem liberar cotas para eles. A operação cria somente os registros ausentes em `COMBOCLIFOR`.

1. Selecione os filtros que identificam os clientes.
2. Selecione o combo desejado.
3. Escolha **Inserir combo sem cotas**.
4. Clique em **Preparar operação** e confira os clientes e vínculos da prévia.
5. Se estiver tudo correto, clique em **Confirmar inserir combo sem cotas**.
"""
        )
    with st.expander("Inserir combo com cotas"):
        st.markdown(
            """
**Exemplo:** vincular ao combo selecionado os clientes encontrados pelos filtros e também liberá-los nas cotas vigentes de todas as filiais ativas do combo.

1. Selecione os filtros que identificam os clientes.
2. Selecione o combo e escolha **Inserir combo com cotas**.
3. Informe a quantidade de cotas por cliente, normalmente **1**.
4. Clique em **Preparar operação** e confira os clientes, vínculos, cotas e situações da prévia.
5. Se estiver tudo correto, clique em **Confirmar inserir combo com cotas**.
"""
        )
    with st.expander("Inserir somente cotas", expanded=True):
        st.markdown(
            """
**Exemplo — combo 240035686:** cadastrar as cotas 204, 207, 210 e 213, com quantidade 1, para os clientes que já pertencem ao combo. Os códigos das cotas são identificados automaticamente pelas filiais ativas; não é necessário informá-los nem selecionar clientes.

1. Selecione o combo **240035686**.
2. Escolha **Inserir somente cotas**.
3. Informe a quantidade de cotas por cliente, neste exemplo **1**.
4. Clique em **Preparar operação** e confira as cotas e a situação de cada uma na prévia.
5. Se estiver tudo correto, clique em **Confirmar inserir somente cotas**.
"""
        )
    with st.expander("Excluir"):
        st.markdown(
            """
**Exemplo:** remover do combo selecionado somente os clientes encontrados pelos filtros que já possuem vínculo. Esta ação executa a exclusão em `COMBOCLIFOR`; ela não executa exclusão direta em `ITEMCOTACOMBOCLIENTE`.

1. Selecione os filtros que identificam os clientes.
2. Selecione o combo desejado.
3. Escolha **Excluir**.
4. Clique em **Preparar operação** e confira cuidadosamente os vínculos da prévia.
5. Se estiver tudo correto, clique em **Confirmar excluir**.
"""
        )
    if data_fim < data_inicio:
        st.error("A data fim não pode ser menor que a data início.")
        return
    filtros = {
        "regioes": regioes, "estados": estados, "cidades": cidades,
        "segmentos": segmentos, "tipos_estabelecimento": tipos,
        "equipes": equipes, "supervisores": supervisores,
        "vendedores": vendedores, "classificacoes": classificacoes,
        "filiais": filiais, "bairros": bairros, "cnpj": cnpj,
        "ie": ie, "venda": venda,
        "data_inicio": data_inicio, "data_fim": data_fim,
        "fornecedores": fornecedores, "marcas": marcas,
        "classes_produto": classes_produto, "produtos": produtos,
    }
    assinatura = repr((filtros, combos, acao, quantidade_cota))
    if st.button("Preparar operação", type="primary", use_container_width=True):
        if not combos:
            st.error("Selecione ao menos um combo vigente.")
        else:
            try:
                with st.spinner("Consultando clientes e vínculos atuais..."):
                    if acao == "Inserir somente cotas":
                        clientes_df = consultar_clientes_cotas_combos(combos)[
                            ["combo", "cliente_codigo", "cliente_nome"]
                        ].drop_duplicates().reset_index(drop=True)
                        clientes = []
                    else:
                        clientes_df = consultar_clientes_dinamicos(filtros)
                        clientes = clientes_df["cliente_codigo"].dropna().astype(int).tolist()
                    plano = planejar_alteracao_combos(
                        clientes, combos, acao, quantidade_cota
                    )
                    if acao in {"Incluir", "Incluir sem cotas", "Inserir somente cotas"} and plano.get("bloqueios_ie"):
                        bloqueios = plano["bloqueios_ie"]
                        raise ValueError(
                            "Regra universal de IE: combos com vinho, espumante, água "
                            "ou xarope não podem ser liberados para clientes sem IE. "
                            "Clientes bloqueados: "
                            + ", ".join(map(str, sorted({c for _, c in bloqueios})))
                        )
                    if acao_com_cotas and plano.get("combos_sem_cotas"):
                        raise ValueError(
                            "Combos sem filiais/cotas ativas configuradas: "
                            + ", ".join(map(str, plano["combos_sem_cotas"]))
                        )
                    if acao_com_cotas and plano.get("filiais_sem_cota"):
                        detalhes = ", ".join(
                            f"combo {item['combo']} / filial {item['filial_codigo']}"
                            for item in plano["filiais_sem_cota"]
                        )
                        raise ValueError("Filiais ativas sem cota vigente: " + detalhes)
                st.session_state.din_plano = plano
                st.session_state.din_clientes = clientes_df
                st.session_state.din_assinatura = assinatura
            except Exception as exc:
                st.session_state.pop("din_plano", None)
                st.error(f"Não foi possível preparar a operação: {exc}")
                mensagem_erro = str(exc)
                prefixo_sem_cotas = "Combos sem filiais/cotas ativas configuradas:"
                if mensagem_erro.startswith(prefixo_sem_cotas):
                    codigos_texto = mensagem_erro.removeprefix(
                        prefixo_sem_cotas
                    ).strip()
                    combos_sem_cotas = [
                        int(item.strip())
                        for item in codigos_texto.split(",")
                        if item.strip().isdigit()
                    ]
                    modelo_sql = gerar_modelo_sql_configuracao_cotas(
                        combos_sem_cotas or combos
                    )
                    st.warning(
                        "Modelo apenas para apoio técnico. Substitua `<FILIAL>`, "
                        "revise os combos e confirme a existência de uma cota vigente "
                        "antes de executar no banco."
                    )
                    with st.expander(
                        "Mostrar modelo SQL para configurar filiais/cotas",
                        expanded=True,
                    ):
                        st.code(modelo_sql, language="sql")
                        st.download_button(
                            "Baixar modelo SQL",
                            data=modelo_sql.encode("utf-8"),
                            file_name="modelo_configuracao_filiais_cotas_combos.sql",
                            mime="text/plain",
                            key="din_baixar_modelo_cotas",
                            use_container_width=True,
                        )
    plano = st.session_state.get("din_plano")
    if plano and st.session_state.get("din_assinatura") != assinatura:
        st.session_state.pop("din_plano", None)
        plano = None
        st.info("Os filtros mudaram. Prepare novamente a operação.")
    if not plano:
        return
    clientes_df = st.session_state.get("din_clientes", pd.DataFrame())
    afetados = plano["vinculos_afetados"]
    cotas_afetadas = plano.get("cotas_afetadas", [])
    clientes_afetados = len(
        {cliente for _, cliente in afetados}
        | {cliente for _, _, cliente in cotas_afetadas}
    )
    combos_afetados = len(
        {combo for combo, _ in afetados}
        | {combo for combo, _, _ in cotas_afetadas}
    )
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Clientes encontrados", len(plano["clientes"]))
    r2.metric(
        "Clientes com cotas a inserir"
        if acao == "Inserir somente cotas" else f"Clientes a {acao.lower()}",
        clientes_afetados,
    )
    r3.metric("Combos afetados", combos_afetados)
    r4.metric("Cotas a inserir" if acao_com_cotas else "Vínculos afetados",
              len(cotas_afetadas) if acao_com_cotas else len(afetados))
    if acao_com_cotas and not plano["filiais_cotas"].empty:
        st.markdown("**Filiais ativas e cotas dos combos**")
        filiais_cotas_exibicao = plano["filiais_cotas"].copy()
        contagem_novas = pd.DataFrame(
            cotas_afetadas, columns=["combo", "cota", "cliente"]
        )
        cotas_ja_existentes = plano.get("cotas_ja_existentes", [])
        contagem_existentes = pd.DataFrame(
            cotas_ja_existentes, columns=["combo", "cota", "cliente"]
        )
        if not contagem_novas.empty:
            contagem_novas = (
                contagem_novas.groupby(["combo", "cota"]).size()
                .rename("registros_a_inserir").reset_index()
            )
            filiais_cotas_exibicao = filiais_cotas_exibicao.merge(
                contagem_novas, on=["combo", "cota"], how="left"
            )
        else:
            filiais_cotas_exibicao["registros_a_inserir"] = 0
        if not contagem_existentes.empty:
            contagem_existentes = (
                contagem_existentes.groupby(["combo", "cota"]).size()
                .rename("registros_ja_existentes").reset_index()
            )
            filiais_cotas_exibicao = filiais_cotas_exibicao.merge(
                contagem_existentes, on=["combo", "cota"], how="left"
            )
        else:
            filiais_cotas_exibicao["registros_ja_existentes"] = 0
        filiais_cotas_exibicao[[
            "registros_a_inserir", "registros_ja_existentes"
        ]] = filiais_cotas_exibicao[[
            "registros_a_inserir", "registros_ja_existentes"
        ]].fillna(0).astype(int)
        filiais_cotas_exibicao["situação"] = filiais_cotas_exibicao.apply(
            lambda linha: (
                "Inserção parcial"
                if linha.registros_a_inserir and linha.registros_ja_existentes
                else "Será inserida"
                if linha.registros_a_inserir
                else "Já existente"
            ),
            axis=1,
        )
        st.dataframe(
            filiais_cotas_exibicao,
            hide_index=True,
            use_container_width=True,
            column_config={
                "combo": "Combo",
                "filial_codigo": "Filial",
                "filial_nome": "Nome da filial",
                "cota": "Cota",
                "cota_nome": "Nome da cota",
                "registros_a_inserir": "Registros a inserir",
                "registros_ja_existentes": "Registros já existentes",
                "situação": "Situação",
            },
        )
    st.dataframe(clientes_df, use_container_width=True, hide_index=True, height=320)
    if not afetados and not cotas_afetadas:
        st.info("Nenhum vínculo precisa ser alterado com os critérios informados.")
        return
    if acao == "Inserir somente cotas":
        st.warning(
            f"Deseja inserir {len(cotas_afetadas)} registros de cota para "
            f"{clientes_afetados} clientes que já pertencem aos "
            f"{len(plano['combos'])} combos selecionados? Nenhum vínculo em "
            "COMBOCLIFOR será criado ou alterado."
        )
    else:
        verbo = "inserir" if acao in {"Incluir", "Incluir sem cotas"} else "excluir"
        st.warning(
            f"Deseja {verbo} {len(afetados)} vínculos de {clientes_afetados} clientes "
            f"nos {len(plano['combos'])} combos selecionados? "
            + (f"Também serão inseridos {len(cotas_afetadas)} registros de cota." if acao == "Incluir" else "")
        )
    confirmar, cancelar = st.columns(2)
    if confirmar.button(
        f"Confirmar {rotulo_acao.lower()}", type="primary",
        key="din_confirmar", use_container_width=True,
    ):
        try:
            with st.spinner(f"Executando {acao.lower()}..."):
                resumo = aplicar_alteracao_combos(
                    plano["clientes"], plano["combos"], acao,
                    plano.get("quantidade_cota", quantidade_cota),
                )
            st.session_state.pop("din_plano", None)
            st.success(
                f"Concluído: {resumo['alterados']} vínculos alterados; "
                f"{resumo['sem_alteracao']} não precisavam de alteração."
                + (
                    f" {resumo.get('cotas_inseridas', 0)} cotas inseridas com "
                    f"quantidade {resumo.get('quantidade_cota', quantidade_cota)}."
                    if acao_com_cotas else ""
                )
            )
        except Exception as exc:
            st.error(f"A transação foi revertida devido ao erro: {exc}")
    if cancelar.button("Cancelar", key="din_cancelar", use_container_width=True):
        st.session_state.pop("din_plano", None)
        st.rerun()


def render_liberacao_temporaria_faturamento() -> None:
    if str(st.session_state.usuario.get("perfil", "")).strip().lower() != "faturamento":
        st.error("Acesso restrito ao perfil Faturamento.")
        return
    st.title("Liberação temporária para faturamento")
    st.warning(
        "Use esta área somente para pedidos que precisam ser faturados. Os bloqueios "
        "devem ser reaplicados assim que o faturamento terminar."
    )
    aba_nova, aba_pendentes = st.tabs([
        "Nova liberação", "Pendências e reaplicação",
    ])
    with aba_nova:
        texto_clientes = st.text_area(
            "Códigos dos clientes",
            placeholder="Um código por linha ou separados por vírgula/espaço",
            height=180,
            key="fat_clientes_liberacao",
        )
        if st.button(
            "Preparar retirada dos bloqueios", type="primary",
            use_container_width=True, key="fat_preparar_liberacao",
        ):
            try:
                clientes = normalizar_clientes_bloqueios(texto_clientes)
                with st.spinner("Conferindo os bloqueios atuais..."):
                    plano = preparar_liberacao(clientes)
                st.session_state.fat_plano_liberacao = plano
                st.session_state.fat_confirmar_liberacao = False
            except Exception as exc:
                st.session_state.pop("fat_plano_liberacao", None)
                st.error(str(exc))
        plano = st.session_state.get("fat_plano_liberacao")
        if plano:
            pares = plano["pares"]
            resumo = pd.DataFrame(pares, columns=["cliente_codigo", "condicao_codigo"])
            por_cliente = (
                resumo.groupby("cliente_codigo").size().rename("bloqueios_a_retirar")
                .reset_index() if not resumo.empty else pd.DataFrame(
                    columns=["cliente_codigo", "bloqueios_a_retirar"]
                )
            )
            c1, c2, c3 = st.columns(3)
            c1.metric("Clientes informados", len(plano["clientes_informados"]))
            c2.metric("Clientes que serão liberados", len(plano["clientes_removiveis"]))
            c3.metric("Bloqueios que serão retirados", len(pares))
            if plano["clientes_sem_registro"]:
                st.info(
                    "Sem bloqueios do fluxo para retirar: "
                    + ", ".join(map(str, plano["clientes_sem_registro"]))
                )
            st.dataframe(por_cliente, hide_index=True, use_container_width=True)
            st.checkbox(
                "Confirmo a retirada temporária e farei a reaplicação após o faturamento.",
                key="fat_confirmar_liberacao",
            )
            if st.button(
                "Retirar bloqueios temporariamente",
                disabled=not st.session_state.get("fat_confirmar_liberacao", False),
                type="primary", use_container_width=True,
                key="fat_executar_liberacao",
            ):
                try:
                    resultado = executar_liberacao(
                        plano, st.session_state.usuario["username"]
                    )
                    st.session_state.pop("fat_plano_liberacao", None)
                    st.session_state.fat_clientes_liberacao = ""
                    st.success(
                        f"Liberação concluída: {resultado['total_clientes']} cliente(s) "
                        f"e {resultado['total_bloqueios']} bloqueio(s) retirados. "
                        "A operação está pendente de reaplicação."
                    )
                    st.rerun()
                except Exception as exc:
                    st.error("Nenhuma alteração foi mantida devido ao erro: " + str(exc))

    with aba_pendentes:
        operacoes = listar_operacoes()
        pendentes = [
            item for item in operacoes
            if item.get("status") == "PENDENTE_REAPLICACAO"
        ]
        p1, p2 = st.columns(2)
        p1.metric("Operações pendentes", len(pendentes))
        p2.metric(
            "Clientes em operações pendentes",
            len({
                cliente for item in pendentes
                for cliente, _ in item.get("pares_removidos", [])
            }),
        )
        if not pendentes:
            st.success("Não há liberações temporárias aguardando reaplicação.")
        else:
            selecionada_id = st.selectbox(
                "Operação pendente",
                [item["id"] for item in pendentes],
                format_func=lambda codigo: next(
                    (
                        f"{item.get('criado_em', '')[:19]} — "
                        f"{item.get('total_clientes', 0)} clientes — "
                        f"{item.get('total_bloqueios', 0)} bloqueios"
                    )
                    for item in pendentes if item["id"] == codigo
                ),
                key="fat_operacao_pendente",
            )
            operacao = next(item for item in pendentes if item["id"] == selecionada_id)
            with st.spinner("Verificando quem continua sem bloqueio..."):
                auditoria = auditar_operacao(operacao)
            st.markdown("**Clientes que continuam total ou parcialmente liberados**")
            st.dataframe(
                auditoria[auditoria["ainda_sem_bloqueio"].gt(0)],
                hide_index=True, use_container_width=True,
            )
            if st.button(
                "Preparar reaplicação", type="primary", use_container_width=True,
                key="fat_preparar_reaplicacao",
            ):
                try:
                    with st.spinner("Recalculando as regras atuais da Etapa 2..."):
                        st.session_state.fat_plano_reaplicacao = preparar_reaplicacao(
                            operacao
                        )
                    st.session_state.fat_confirmar_reaplicacao = False
                except Exception as exc:
                    st.error(str(exc))
            plano_reaplicacao = st.session_state.get("fat_plano_reaplicacao")
            if (
                plano_reaplicacao
                and plano_reaplicacao.get("operacao_id") == selecionada_id
            ):
                r1, r2, r3 = st.columns(3)
                r1.metric("Serão bloqueados novamente", len(plano_reaplicacao["inserir"]))
                r2.metric("Já estão bloqueados", len(plano_reaplicacao["ja_presentes"]))
                r3.metric(
                    "Não voltam pelas regras atuais",
                    len(plano_reaplicacao["nao_reaplicar"]),
                )
                por_cliente = pd.DataFrame(
                    plano_reaplicacao["inserir"],
                    columns=["cliente_codigo", "condicao_codigo"],
                )
                if not por_cliente.empty:
                    por_cliente = (
                        por_cliente.groupby("cliente_codigo").size()
                        .rename("bloqueios_a_reaplicar").reset_index()
                    )
                st.dataframe(por_cliente, hide_index=True, use_container_width=True)
                st.checkbox(
                    "Confirmo que o faturamento terminou e desejo reaplicar os bloqueios.",
                    key="fat_confirmar_reaplicacao",
                )
                if st.button(
                    "Reaplicar bloqueios agora",
                    disabled=not st.session_state.get(
                        "fat_confirmar_reaplicacao", False
                    ),
                    type="primary", use_container_width=True,
                    key="fat_executar_reaplicacao",
                ):
                    try:
                        resultado = executar_reaplicacao(
                            plano_reaplicacao,
                            st.session_state.usuario["username"],
                        )
                        st.session_state.pop("fat_plano_reaplicacao", None)
                        st.success(
                            f"Operação finalizada: "
                            f"{resultado['bloqueios_reaplicados']} bloqueio(s) "
                            "reaplicados conforme as regras atuais."
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(
                            "A reaplicação foi revertida devido ao erro: " + str(exc)
                        )
        with st.expander("Histórico de operações"):
            if operacoes:
                st.dataframe(pd.DataFrame(operacoes)[[
                    "id", "status", "criado_em", "criado_por",
                    "total_clientes", "total_bloqueios",
                ]], hide_index=True, use_container_width=True)
            else:
                st.info("Nenhuma operação registrada por este acesso.")


if not login():
    st.stop()

if str(st.session_state.usuario.get("perfil", "")).strip().lower() == "faturamento":
    with st.sidebar:
        st.write(f"Olá, **{st.session_state.usuario['nome']}**")
        st.caption("Acesso exclusivo: liberação temporária para faturamento")
        if st.button("Sair", key="fat_sair"):
            st.session_state.clear()
            st.rerun()
    render_liberacao_temporaria_faturamento()
    st.stop()

with st.sidebar:
    st.write(f"Olá, **{st.session_state.usuario['nome']}**")
    if st.button("Sair"):
        st.session_state.clear(); st.rerun()
    if st.session_state.get("tela_principal") in {
        "9. Pagamentos mais usados",
        "9. Pagamentos mais usados e suas tabelas de preços",
    }:
        st.session_state.tela_principal = (
            "9. Pagamentos + usados e bloqueios de condições de pagamento por "
            "tipo estabelecimento X equipe"
        )
    if "tela_principal" not in st.session_state:
        st.session_state.tela_principal = "1. Queda de positivação"
    tela = st.session_state.tela_principal

    def botao_menu(container, rotulo: str, destino: str, chave: str) -> None:
        if container.button(
            rotulo,
            key=chave,
            type="primary" if tela == destino else "secondary",
            use_container_width=True,
        ):
            st.session_state.tela_principal = destino
            st.rerun()

    grupo_criacao = st.expander(
        "Análises para criação de combos",
        expanded=True,
    )
    botao_menu(grupo_criacao, "Queda de positivação", "1. Queda de positivação", "menu_positivacao")
    botao_menu(grupo_criacao, "Queda de volume anual", "2. Queda de volume anual", "menu_volume")
    botao_menu(grupo_criacao, "Mix por equipe", "3. Mix por equipe", "menu_mix")
    botao_menu(grupo_criacao, "Pernod × Mtrix", "4. Pernod × Mtrix", "menu_mtrix")

    grupo_acoes = st.expander(
        "Análises para ações relacionadas a combos",
        expanded=True,
    )
    botao_menu(grupo_acoes, "Ranking de SKUs", "8. Ranking de SKUs", "menu_ranking_skus")
    botao_menu(
        grupo_acoes,
        "Pagamentos + usados e bloqueios de condições de pagamento por tipo "
        "estabelecimento X equipe",
        "9. Pagamentos + usados e bloqueios de condições de pagamento por tipo "
        "estabelecimento X equipe",
        "menu_pagamentos",
    )

    grupo_edicao = st.expander(
        "Edição de combos",
        expanded=True,
    )
    botao_menu(
        grupo_edicao,
        "Validação de regras de títulos de combos ativos",
        "5. Combos ativos",
        "menu_combos_ativos",
    )
    botao_menu(
        grupo_edicao,
        "Inserção dinâmica de combos",
        "6. Inserção dinâmica de combos",
        "menu_insercao_dinamica",
    )
    botao_menu(
        grupo_edicao,
        "Conferência de combos",
        "7. Conferência de combos",
        "menu_conferencia_combos",
    )

    grupo_extras = st.expander(
        "Análises extras",
        expanded=True,
    )
    for analise in ANALISES_EXTRAS:
        botao_menu(
            grupo_extras,
            analise.titulo,
            analise.destino,
            f"menu_extra_{analise.chave}",
        )

    st.divider()
    botao_menu(st, "Documentação", "Documentação", "menu_documentacao")
    st.divider()
    forcar = st.button("Atualizar dados agora", help="Ignora o cache de hoje e consulta novamente o BigQuery.")

if tela == "Documentação":
    render_documentacao()
    st.stop()

if tela == "5. Combos ativos":
    render_combos_ativos()
    st.stop()

if tela == "6. Inserção dinâmica de combos":
    render_insercao_dinamica()
    st.stop()

if tela == "7. Conferência de combos":
    render_conferencia_combos()
    st.stop()

if tela == "8. Ranking de SKUs":
    render_ranking_skus()
    st.stop()

analise_extra = obter_analise_extra(tela)
if analise_extra is not None:
    analise_extra.renderizar()
    st.stop()

if tela == (
    "9. Pagamentos + usados e bloqueios de condições de pagamento por tipo "
    "estabelecimento X equipe"
):
    render_pagamentos_mais_usados()
    st.stop()

try:
    if (
        forcar
        or "base_diaria" not in st.session_state
        or st.session_state.get("versao_base_diaria") != CACHE_VERSION
    ):
        with st.spinner("Carregando base diária..."):
            base, meta = carregar_base(forcar=forcar)
        st.session_state.base_diaria = base
        st.session_state.meta_base_diaria = meta
        st.session_state.versao_base_diaria = CACHE_VERSION
    else:
        base = st.session_state.base_diaria
        meta = st.session_state.meta_base_diaria
except Exception as exc:
    st.error(f"Não foi possível carregar a base: {exc}")
    st.info("Configure uma credencial do BigQuery em credentials/credential.json ou GOOGLE_APPLICATION_CREDENTIALS.")
    st.stop()

st.title(TITULO_PAINEL)
st.caption(f"Fonte: {meta['origem']} · atualização: {meta['atualizado_em']:%d/%m/%Y %H:%M} · {len(base):,} registros agregados")

titulos_analises = {
    "1. Queda de positivação": "Clientes dormentes — Queda de positivação",
    "2. Queda de volume anual": "Clientes dormentes — Queda de volume anual",
    "3. Mix por equipe": "Comparativo de mix e faturamento por equipe",
    "4. Pernod × Mtrix": (
        "Pernod × Mtrix — fase 2 (em validação de dados iniciais por Gustavo → "
        "ver necessidade de desenvolvimento)"
    ),
}
st.header(titulos_analises[tela])

tem_filtro_estado = tela in {
    "1. Queda de positivação", "2. Queda de volume anual", "4. Pernod × Mtrix"
}
colunas_filtros = st.columns(4 if tem_filtro_estado else 2)
c1, c2 = colunas_filtros[:2]
industrias = multiselect_com_acoes(
    c1, "Indústria", list(INDUSTRIAS), "filtro_industrias", list(INDUSTRIAS)
)
cadastro_equipes = (
    base[["equipe_codigo", "equipe_nome"]]
    .dropna(subset=["equipe_codigo"])
    .drop_duplicates("equipe_codigo")
    .sort_values("equipe_codigo")
)
nomes_equipes = {
    int(linha.equipe_codigo): str(linha.equipe_nome)
    for linha in cadastro_equipes.itertuples(index=False)
}
equipes_disponiveis = list(nomes_equipes)
equipes = multiselect_com_acoes(
    c2,
    "Equipe",
    equipes_disponiveis,
    "filtro_equipes",
    format_func=lambda codigo: f"{codigo} — {nomes_equipes.get(codigo, 'SEM NOME')}",
)
estados: list[str] = []
tipos_estabelecimento: list[int] = []
if tem_filtro_estado:
    estados_disponiveis = sorted(
        estado for estado in base.cliente_estado.dropna().astype(str).unique().tolist()
        if estado != "NÃO IDENTIFICADO"
    )
    estados = multiselect_com_acoes(
        colunas_filtros[2],
        "Estado",
        estados_disponiveis,
        "filtro_estados",
    )
    cadastro_tipos = (
        base[["estabelecimento_tipo_codigo", "estabelecimento_tipo_nome"]]
        .dropna(subset=["estabelecimento_tipo_codigo"])
        .drop_duplicates("estabelecimento_tipo_codigo")
        .sort_values("estabelecimento_tipo_codigo")
    )
    nomes_tipos = {
        int(linha.estabelecimento_tipo_codigo): str(linha.estabelecimento_tipo_nome)
        for linha in cadastro_tipos.itertuples(index=False)
    }
    tipos_estabelecimento = multiselect_com_acoes(
        colunas_filtros[3],
        "Tipo estabelecimento",
        list(nomes_tipos),
        "filtro_tipos_estabelecimento",
        format_func=lambda codigo: f"{codigo} — {nomes_tipos.get(codigo, 'NÃO IDENTIFICADO')}",
    )
dados = filtrar(
    base, industrias, equipes, estados, tipos_estabelecimento, "Todos"
)
dados_universo_clientes = filtrar(
    base, [], equipes, estados, tipos_estabelecimento, "Todos"
)
padrao = periodos_equivalentes(date.today())

if tela == "1. Queda de positivação":
    dias_col, carteira_col = st.columns([2.2, 1])
    dias = dias_col.slider("Sem compra da indústria nos últimos dias", 15, 120, 30)
    filtro_carteira = carteira_col.selectbox(
        "Carteira de vendedor — somente Compra indústria",
        ["Com vendedor alocado", "Sem vendedor alocado", "Todos"],
        key="carteira_positivacao",
    )
    informar_escopo_filtro_carteira()
    resultado_todos = clientes_dormentes(
        dados_universo_clientes,
        date.today(),
        dias,
        industrias or list(INDUSTRIAS),
    )
    com_vendedor, sem_vendedor, total_clientes = resumo_carteira(resultado_todos)
    render_indicadores_televendas(meta)
    st.divider()
    st.markdown("**Indicadores — Compra indústria**")
    com_col, sem_col, todos_col = st.columns(3)
    com_col.metric("Com vendedor", com_vendedor)
    sem_col.metric("Sem vendedor", sem_vendedor)
    todos_col.metric("Todos", total_clientes)
    resultado = aplicar_filtro_carteira(resultado_todos, filtro_carteira)
    st.divider()
    a, b = st.columns(2)
    a.metric("Indústrias impactadas", resultado.industria.nunique())
    b.metric("Média de dias sem compra", f"{resultado.dias_sem_compra.mean():.0f}" if len(resultado) else "0")
    render_resumo_origens(resultado)
    formatar_tabela(resultado, "positivacao")

elif tela == "2. Queda de volume anual":
    datas = filtro_datas("volume", padrao)
    resultado_todos = comparar_volume(dados, datas)
    com_vendedor, sem_vendedor, total_clientes = resumo_carteira(resultado_todos)
    opcoes_classificacao = sorted(resultado_todos.classificacao.dropna().unique().tolist())
    padrao_classificacao = [
        item for item in ["QUEDA", "SEM COMPRA NO PERÍODO ATUAL"]
        if item in opcoes_classificacao
    ]
    class_col, carteira_col = st.columns([1, 1])
    classificacoes = multiselect_com_acoes(
        class_col,
        "Classificação",
        opcoes_classificacao,
        "filtro_classificacoes",
        padrao_classificacao,
    )
    filtro_carteira = carteira_col.selectbox(
        "Carteira de vendedor — somente Compra indústria",
        ["Com vendedor alocado", "Sem vendedor alocado", "Todos"],
        key="carteira_volume",
    )
    informar_escopo_filtro_carteira()
    render_indicadores_televendas(meta)
    st.divider()
    st.markdown("**Indicadores — Compra indústria**")
    com_col, sem_col, todos_col = st.columns(3)
    com_col.metric("Com vendedor", com_vendedor)
    sem_col.metric("Sem vendedor", sem_vendedor)
    todos_col.metric("Todos", total_clientes)
    resultado = aplicar_filtro_carteira(resultado_todos, filtro_carteira)
    exibicao = resultado[resultado.classificacao.isin(classificacoes)] if classificacoes else resultado
    st.divider()
    a, b, c = st.columns(3)
    a.metric("Clientes analisados", resultado.cliente_codigo.nunique())
    b.metric("Clientes em queda", int(resultado.classificacao.isin(["QUEDA", "SEM COMPRA NO PERÍODO ATUAL"]).sum()))
    c.metric("Volume perdido", f"{abs(resultado.loc[resultado.diferenca < 0, 'diferenca'].sum()):,.2f}")
    render_resumo_origens(exibicao)
    formatar_tabela(exibicao, "volume")

elif tela == "3. Mix por equipe":
    datas = filtro_datas("mix", padrao)
    resultado = analisar_mix(dados, datas)
    somente_queda = st.toggle("Mostrar somente equipes com queda de mix ou faturamento", True)
    if somente_queda:
        resultado = resultado[(resultado.queda_mix < 0) | (resultado.queda_faturamento < 0)]
    a, b, c = st.columns(3)
    a.metric("Equipes com queda de mix", resultado.loc[resultado.queda_mix < 0, "equipe_codigo"].nunique())
    b.metric("Equipes com queda de faturamento", resultado.loc[resultado.queda_faturamento < 0, "equipe_codigo"].nunique())
    faturamento_perdido = abs(resultado.loc[resultado.queda_faturamento < 0, "queda_faturamento"].sum())
    c.metric("Faturamento perdido", f"R$ {faturamento_perdido:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    formatar_tabela(resultado, "mix")

else:
    arquivo = st.file_uploader("Arquivo Mtrix revisado", type=["csv", "xlsx", "xls"])
    if arquivo:
        mtrix = pd.read_csv(arquivo, sep=None, engine="python") if arquivo.name.lower().endswith(".csv") else pd.read_excel(arquivo)
        st.write("Prévia Mtrix", mtrix.head())
        colunas = list(mtrix.columns)
        c1, c2, c3 = st.columns(3)
        col_cliente = c1.selectbox("Coluna cliente", colunas)
        col_produto = c2.selectbox("Coluna produto", colunas)
        col_volume = c3.selectbox("Coluna volume", colunas)
        oficial = dados[dados.industria.eq("Pernod")].groupby(["cliente_codigo", "cliente_estado", "estabelecimento_tipo_codigo", "estabelecimento_tipo_nome", "produto_codigo"], as_index=False, dropna=False).volume.sum()
        externo = mtrix[[col_cliente, col_produto, col_volume]].rename(columns={col_cliente: "cliente_codigo", col_produto: "produto_codigo", col_volume: "volume_mtrix"})
        for col in ("cliente_codigo", "produto_codigo"):
            externo[col] = pd.to_numeric(externo[col], errors="coerce").astype("Int64")
        externo["volume_mtrix"] = pd.to_numeric(externo.volume_mtrix, errors="coerce").fillna(0)
        externo = externo.groupby(["cliente_codigo", "produto_codigo"], as_index=False).volume_mtrix.sum()
        cruzado = oficial.merge(externo, on=["cliente_codigo", "produto_codigo"], how="outer")
        cruzado["cliente_estado"] = cruzado.cliente_estado.fillna("NÃO IDENTIFICADO")
        cruzado["estabelecimento_tipo_codigo"] = cruzado.estabelecimento_tipo_codigo.fillna(0).astype("Int64")
        cruzado["estabelecimento_tipo_nome"] = cruzado.estabelecimento_tipo_nome.fillna("NÃO IDENTIFICADO")
        cruzado[["volume", "volume_mtrix"]] = cruzado[["volume", "volume_mtrix"]].fillna(0)
        if estados:
            cruzado = cruzado[cruzado.cliente_estado.isin(estados)]
        if tipos_estabelecimento:
            cruzado = cruzado[
                cruzado.estabelecimento_tipo_codigo.isin(tipos_estabelecimento)
            ]
        cruzado["diferenca"] = cruzado.volume - cruzado.volume_mtrix
        cruzado["status"] = cruzado.diferenca.abs().le(0.01).map({True: "CONCILIADO", False: "DIVERGENTE"})
        formatar_tabela(
            cruzado.sort_values("diferenca", key=abs, ascending=False), "mtrix"
        )



##para compilar -> python -m streamlit run main.py --server.port 8520


# REFERENCIA OPERACIONAL - INSERIR COTAS EM COMBO EXISTENTE
# Operacao realizada em 09/11/2026:
# combo 240035686, cliente 172422, cotas 204, 207, 210 e 213, quantidade 1.
# A rotina transacional usada foi:
# inserir_clientes_em_combos(
#     clientes=[172422], combos=[240035686], quantidade_cota=1
# )
#
# SQL equivalente e idempotente para cada cota/cliente:
# INSERT INTO ITEMCOTACOMBOCLIENTE (QUANTIDADE, COTA, COMBO, CLIENTE)
# SELECT 1, <COTA>, <COMBO>, <CLIENTE>
# FROM RDB$DATABASE
# WHERE NOT EXISTS (
#     SELECT 1 FROM ITEMCOTACOMBOCLIENTE
#     WHERE COTA = <COTA> AND COMBO = <COMBO> AND CLIENTE = <CLIENTE>
# );
#
# Como pedir nas proximas vezes:
# "Insira no ERP as cotas <COTAS> no combo <COMBO>, para o cliente <CLIENTE>,
# com quantidade <QUANTIDADE>. Confira combo, cliente, filiais/cotas vigentes e
# registros existentes; use transacao idempotente e valide o resultado final."
