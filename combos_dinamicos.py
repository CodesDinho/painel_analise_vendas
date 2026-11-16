from __future__ import annotations

from datetime import date

import pandas as pd

from conexoes import cliente_firebird


CATALOGOS_SQL = {
    "regioes": "SELECT CODIGO, NOME FROM REGIAO ORDER BY CODIGO",
    "estados": "SELECT CODIGO, UF, NOME FROM ESTADO ORDER BY CODIGO",
    "cidades": "SELECT CODIGO, NOME FROM CIDADE ORDER BY CODIGO",
    "segmentos": "SELECT CODIGO, NOME FROM SEGMENTO ORDER BY CODIGO",
    "tipos_estabelecimento": "SELECT CODIGO, NOME FROM TIPOESTABELECIMENTO WHERE COALESCE(ATIVO, 'S') = 'S' ORDER BY CODIGO",
    "equipes": "SELECT CODIGO, NOME FROM EQUIPE ORDER BY CODIGO",
    "supervisores": "SELECT DISTINCT s.CODIGO, s.NOME FROM FUNCIONARIO f JOIN FUNCIONARIO s ON s.CODIGO = f.SUPERVISOR WHERE COALESCE(f.ATIVO, 'S') = 'S' ORDER BY s.CODIGO",
    "vendedores": "SELECT CODIGO, NOME FROM FUNCIONARIO WHERE COALESCE(ATIVO, 'S') = 'S' ORDER BY CODIGO",
    "classificacoes": "SELECT CODIGO, NOME FROM CLASSIFICACAOCLIFOR ORDER BY CODIGO",
    "filiais": "SELECT CODIGO, NOME FROM FILIAL WHERE COALESCE(ATIVO, 'S') = 'S' ORDER BY CODIGO",
    "fornecedores": "SELECT DISTINCT f.CODIGO, f.NOME FROM PRODUTO p JOIN CLIFOR f ON f.CODIGO = p.CLIFOR ORDER BY f.CODIGO",
    "marcas": "SELECT CODIGO, NOME FROM MARCA WHERE COALESCE(ATIVO, 'S') = 'S' ORDER BY CODIGO",
    "classes_produto": "SELECT CODIGO, NOME FROM CLASSE WHERE COALESCE(ATIVO, 'S') = 'S' ORDER BY CODIGO",
    "produtos": "SELECT CODIGO, NOME FROM PRODUTO ORDER BY CODIGO",
}


def listar_catalogos() -> dict[str, pd.DataFrame]:
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    catalogos: dict[str, pd.DataFrame] = {}
    try:
        for nome, sql in CATALOGOS_SQL.items():
            cursor.execute(sql)
            dados = cursor.fetchall()
            if nome == "estados":
                catalogos[nome] = pd.DataFrame(
                    [
                        (codigo, f"{str(uf or '').strip()} - {str(estado or '').strip()}")
                        for codigo, uf, estado in dados
                    ],
                    columns=["codigo", "nome"],
                )
            else:
                catalogos[nome] = pd.DataFrame(
                    dados, columns=["codigo", "nome"]
                )
        cursor.execute(
            "SELECT DISTINCT TRIM(BAIRRO) FROM CLIFOR "
            "WHERE TIPO = 1 AND TRIM(COALESCE(BAIRRO, '')) <> '' ORDER BY 1"
        )
        catalogos["bairros"] = pd.DataFrame(
            [item[0] for item in cursor.fetchall()], columns=["nome"]
        )
    finally:
        cursor.close()
        con.close()
    return catalogos


def _adicionar_in(campo: str, valores: list, condicoes: list[str], parametros: list) -> None:
    if valores:
        condicoes.append(f"{campo} IN ({','.join('?' for _ in valores)})")
        parametros.extend(valores)


def _adicionar_filtro_ie(valor: str, condicoes: list[str]) -> None:
    """Aplica a mesma definição de IE válida usada na liberação dos combos."""
    ie_normalizada = "UPPER(TRIM(COALESCE(c.IE, '')))"
    if valor == "Sim":
        condicoes.append(f"{ie_normalizada} NOT IN ('', 'ISENTO')")
    elif valor == "Não":
        condicoes.append(f"{ie_normalizada} IN ('', 'ISENTO')")


def consultar_clientes(filtros: dict) -> pd.DataFrame:
    condicoes = ["c.TIPO = 1", "COALESCE(c.ATIVO, 'N') = 'S'"]
    parametros: list = []
    _adicionar_in("c.REGIAO", filtros["regioes"], condicoes, parametros)
    _adicionar_in("cid.ESTADO", filtros["estados"], condicoes, parametros)
    _adicionar_in("c.CIDADE", filtros["cidades"], condicoes, parametros)
    _adicionar_in("te.SEGMENTO", filtros["segmentos"], condicoes, parametros)
    _adicionar_in("c.TIPOESTABELECIMENTO", filtros["tipos_estabelecimento"], condicoes, parametros)
    _adicionar_in("c.CLASSIFICACAOCLIFOR", filtros["classificacoes"], condicoes, parametros)
    _adicionar_in("c.FILIAL", filtros["filiais"], condicoes, parametros)
    _adicionar_in("UPPER(TRIM(c.BAIRRO))", [str(x).upper() for x in filtros["bairros"]], condicoes, parametros)

    carteira_condicoes: list[str] = []
    _adicionar_in("fv.EQUIPE", filtros["equipes"], carteira_condicoes, parametros)
    _adicionar_in("fv.SUPERVISOR", filtros["supervisores"], carteira_condicoes, parametros)
    _adicionar_in("fc.FUNCIONARIO", filtros["vendedores"], carteira_condicoes, parametros)
    if carteira_condicoes:
        condicoes.append(
            "EXISTS (SELECT 1 FROM FUNCIONARIOCLIFOR fc "
            "JOIN FUNCIONARIO fv ON fv.CODIGO = fc.FUNCIONARIO "
            "WHERE fc.CLIFOR = c.CODIGO AND " + " AND ".join(carteira_condicoes) + ")"
        )

    if filtros["cnpj"] == "Sim":
        condicoes.append("TRIM(COALESCE(c.CNPJ, '')) <> ''")
    elif filtros["cnpj"] == "Não":
        condicoes.append("TRIM(COALESCE(c.CNPJ, '')) = ''")
    _adicionar_filtro_ie(filtros.get("ie", "Todos"), condicoes)

    venda_condicoes = [
        "p.CLIFOR = c.CODIGO", "COALESCE(p.FATURADO, 'N') = 'S'",
        "COALESCE(p.CANCELADO, 'N') = 'N'", "p.EMISSAO BETWEEN ? AND ?",
    ]
    parametros_venda: list = [filtros["data_inicio"], filtros["data_fim"]]
    precisa_item = bool(
        filtros["fornecedores"] or filtros["marcas"]
        or filtros.get("classes_produto", []) or filtros["produtos"]
    )
    _adicionar_in("pr.CLIFOR", filtros["fornecedores"], venda_condicoes, parametros_venda)
    _adicionar_in("pr.MARCA", filtros["marcas"], venda_condicoes, parametros_venda)
    _adicionar_in(
        "pr.CLASSE", filtros.get("classes_produto", []),
        venda_condicoes, parametros_venda,
    )
    _adicionar_in("ip.PRODUTO", filtros["produtos"], venda_condicoes, parametros_venda)
    joins_venda = (
        " JOIN ITEMPEDIDO ip ON ip.IDPEDIDO = p.ID "
        "JOIN PRODUTO pr ON pr.CODIGO = ip.PRODUTO " if precisa_item else ""
    )
    venda_sql = (
        "EXISTS (SELECT 1 FROM PEDIDO p" + joins_venda
        + " WHERE " + " AND ".join(venda_condicoes) + ")"
    )
    if filtros["venda"] == "Não":
        condicoes.append("NOT " + venda_sql)
        parametros.extend(parametros_venda)
    elif filtros["venda"] == "Sim" or precisa_item:
        condicoes.append(venda_sql)
        parametros.extend(parametros_venda)

    sql = """
SELECT DISTINCT
    c.CODIGO AS cliente_codigo,
    c.NOME AS cliente_nome,
    c.CNPJ AS cnpj,
    c.IE AS inscricao_estadual,
    c.BAIRRO AS bairro,
    c.CIDADE AS cidade_codigo,
    cid.NOME AS cidade_nome,
    cid.ESTADO AS estado_codigo,
    est.UF AS estado,
    c.REGIAO AS regiao_codigo,
    r.NOME AS regiao_nome,
    c.TIPOESTABELECIMENTO AS estabelecimento_tipo_codigo,
    te.NOME AS estabelecimento_tipo_nome,
    te.SEGMENTO AS segmento_codigo,
    s.NOME AS segmento_nome,
    c.CLASSIFICACAOCLIFOR AS classificacao_codigo,
    cc.NOME AS classificacao_nome,
    c.FILIAL AS filial_codigo,
    fl.NOME AS filial_nome
FROM CLIFOR c
LEFT JOIN CIDADE cid ON cid.CODIGO = c.CIDADE
LEFT JOIN ESTADO est ON est.CODIGO = cid.ESTADO
LEFT JOIN REGIAO r ON r.CODIGO = c.REGIAO
LEFT JOIN TIPOESTABELECIMENTO te ON te.CODIGO = c.TIPOESTABELECIMENTO
LEFT JOIN SEGMENTO s ON s.CODIGO = te.SEGMENTO
LEFT JOIN CLASSIFICACAOCLIFOR cc ON cc.CODIGO = c.CLASSIFICACAOCLIFOR
LEFT JOIN FILIAL fl ON fl.CODIGO = c.FILIAL
WHERE """ + " AND ".join(condicoes) + " ORDER BY c.CODIGO"
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        cursor.execute(sql, parametros)
        dados = cursor.fetchall()
        colunas = [desc[0].strip().lower() for desc in cursor.description]
    finally:
        cursor.close()
        con.close()
    return pd.DataFrame(dados, columns=colunas)
