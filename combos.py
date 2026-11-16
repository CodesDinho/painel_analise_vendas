from __future__ import annotations

import re
from datetime import date
from io import BytesIO
from typing import Iterable

import pandas as pd

from combo_regras import exige_vin_esp
from conexoes import cliente_firebird


TAMANHO_LOTE = 500


def normalizar_codigos_combos(texto: str) -> list[int]:
    """Aceita códigos separados por espaço, vírgula, ponto e vírgula ou quebra de linha."""
    if not texto.strip():
        return []
    partes = [item for item in re.split(r"[\s,;]+", texto.strip()) if item]
    invalidos = [item for item in partes if not item.isdigit()]
    if invalidos:
        raise ValueError(f"Códigos de combo inválidos: {', '.join(invalidos)}")
    return sorted(set(int(item) for item in partes))


def gerar_modelo_sql_configuracao_cotas(combos: Iterable[int]) -> str:
    """Gera referência idempotente para vincular combos a uma filial com cota."""
    codigos = sorted(set(int(item) for item in combos))
    linhas = [
        "-- MODELO DE APOIO: revise antes de executar no TOP.",
        "-- Substitua <FILIAL> pelo código da filial desejada.",
        "-- Este modelo não cria nem prorroga COTA; isso exige definição comercial.",
        "",
    ]
    for combo in codigos:
        linhas.extend([
            f"-- Combo {combo}",
            "INSERT INTO COMBOFILIAL (ID, COMBO, FILIAL)",
            "SELECT COALESCE((SELECT MAX(ID) FROM COMBOFILIAL), 0) + 1,",
            f"       {combo}, CAST(<FILIAL> AS INTEGER)",
            "FROM RDB$DATABASE",
            "WHERE NOT EXISTS (",
            "    SELECT 1 FROM COMBOFILIAL",
            f"    WHERE COMBO = {combo} AND FILIAL = CAST(<FILIAL> AS INTEGER)",
            ");",
            "",
        ])
    lista = ", ".join(map(str, codigos)) or "NULL"
    linhas.extend([
        "-- Conferência: todos os combos precisam retornar ao menos uma cota vigente.",
        "SELECT cf.COMBO, cf.FILIAL, c.CODIGO AS COTA, c.NOME,",
        "       c.DATAINICIO, c.DATAFIM",
        "FROM COMBOFILIAL cf",
        "JOIN COTA c ON c.FILIAL = cf.FILIAL",
        f"WHERE cf.COMBO IN ({lista})",
        "  AND (c.DATAINICIO IS NULL OR c.DATAINICIO <= CURRENT_DATE)",
        "  AND (c.DATAFIM IS NULL OR c.DATAFIM >= CURRENT_DATE)",
        "ORDER BY cf.COMBO, cf.FILIAL, c.CODIGO;",
        "",
        "-- Se a conferência não retornar cota para alguma filial, cadastre ou",
        "-- prorrogue a COTA no ERP antes de preparar novamente a operação.",
    ])
    return "\n".join(linhas)


def listar_combos_vigentes(hoje: date | None = None) -> pd.DataFrame:
    hoje = hoje or date.today()
    sql = """
SELECT CODIGO AS combo, NOME AS nome, DATAINICIO AS data_inicio, DATAFIM AS data_fim
FROM COMBO
WHERE (DATAINICIO IS NULL OR DATAINICIO <= ?)
  AND (DATAFIM IS NULL OR DATAFIM >= ?)
ORDER BY CODIGO
"""
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        cursor.execute(sql, [hoje, hoje])
        dados = cursor.fetchall()
    finally:
        cursor.close()
        con.close()
    resultado = pd.DataFrame(
        dados, columns=["combo", "nome", "data_inicio", "data_fim"]
    )
    if not resultado.empty:
        resultado["combo"] = pd.to_numeric(
            resultado["combo"], errors="coerce"
        ).astype("Int64")
    return resultado


def consultar_evidencias_produtos_combos(combos: Iterable[int]) -> dict[int, list[str]]:
    """Retorna textos cadastrais dos produtos para validar padrões do título."""
    codigos = sorted(set(int(item) for item in combos))
    resultado: dict[int, list[str]] = {codigo: [] for codigo in codigos}
    if not codigos:
        return resultado
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        for lote in _em_lotes(codigos):
            cursor.execute(
                f"""SELECT DISTINCT co.CODIGO, p.NOME, tp.NOME, g.NOME,
                           cp.NOME, tl.NOME
                    FROM COMBO co
                    JOIN GRUPOCOMBO gc ON gc.COMBO = co.CODIGO
                    JOIN ITEMGRUPOCOMBO ig ON ig.GRUPOCOMBO = gc.CODIGO
                    JOIN PRODUTO p ON p.CODIGO = ig.PRODUTO
                    LEFT JOIN TIPOPRODUTO tp ON tp.CODIGO = p.TIPOPRODUTO
                    LEFT JOIN GRUPO g ON g.CODIGO = p.GRUPO
                    LEFT JOIN CATEGORIAPRODUTO cp ON cp.CODIGO = p.CATEGORIAPRODUTO
                    LEFT JOIN TIPOLINHA tl ON tl.ID = p.TIPOLINHA
                    WHERE co.CODIGO IN ({','.join('?' for _ in lote)})""",
                lote,
            )
            for linha in cursor.fetchall():
                resultado[int(linha[0])].extend(
                    str(valor) for valor in linha[1:] if valor is not None
                )
    finally:
        cursor.close()
        con.close()
    return resultado


def consultar_produtos_por_codigo(codigos: Iterable[int]) -> dict[int, str]:
    codigos = sorted(set(int(item) for item in codigos if item is not None))
    if not codigos:
        return {}
    resultado: dict[int, str] = {}
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        for lote in _em_lotes(codigos):
            cursor.execute(
                f"SELECT CODIGO, NOME FROM PRODUTO WHERE CODIGO IN "
                f"({','.join('?' for _ in lote)})",
                lote,
            )
            resultado.update({int(codigo): str(nome or "") for codigo, nome in cursor.fetchall()})
    finally:
        cursor.close()
        con.close()
    return resultado


def consultar_clientes_por_codigo(codigos: Iterable[int]) -> pd.DataFrame:
    codigos = sorted(set(int(item) for item in codigos if item is not None))
    if not codigos:
        return pd.DataFrame(columns=["cliente_codigo", "cliente_nome", "ativo"])
    dados = []
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        for lote in _em_lotes(codigos):
            cursor.execute(
                f"SELECT CODIGO, NOME, ATIVO FROM CLIFOR WHERE TIPO = 1 AND CODIGO IN "
                f"({','.join('?' for _ in lote)})",
                lote,
            )
            dados.extend(cursor.fetchall())
    finally:
        cursor.close()
        con.close()
    return pd.DataFrame(dados, columns=["cliente_codigo", "cliente_nome", "ativo"])


def combo_codigo_disponivel(codigo: int) -> bool:
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        cursor.execute("SELECT 1 FROM COMBO WHERE CODIGO = ?", [int(codigo)])
        return cursor.fetchone() is None
    finally:
        cursor.close()
        con.close()


def listar_filiais_ativas() -> pd.DataFrame:
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        cursor.execute(
            "SELECT CODIGO, NOME FROM FILIAL "
            "WHERE COALESCE(ATIVO, 'S') = 'S' ORDER BY CODIGO"
        )
        dados = cursor.fetchall()
    finally:
        cursor.close()
        con.close()
    return pd.DataFrame(dados, columns=["filial_codigo", "filial_nome"])


def listar_filiais_cotas_ativas(hoje: date | None = None) -> pd.DataFrame:
    """Retorna somente filiais ativas que possuem cota vigente para combos."""
    hoje = hoje or date.today()
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        cursor.execute(
            "SELECT f.CODIGO, f.NOME, c.CODIGO, c.NOME FROM FILIAL f "
            "JOIN COTA c ON c.FILIAL = f.CODIGO "
            "WHERE COALESCE(f.ATIVO, 'S') = 'S' "
            "AND (c.DATAINICIO IS NULL OR c.DATAINICIO <= ?) "
            "AND (c.DATAFIM IS NULL OR c.DATAFIM >= ?) "
            "ORDER BY f.CODIGO, c.CODIGO",
            [hoje, hoje],
        )
        dados = cursor.fetchall()
    finally:
        cursor.close()
        con.close()
    return pd.DataFrame(dados, columns=[
        "filial_codigo", "filial_nome", "cota", "cota_nome",
    ])


def _em_lotes(valores: list[int], tamanho: int = TAMANHO_LOTE):
    for inicio in range(0, len(valores), tamanho):
        yield valores[inicio:inicio + tamanho]


def _vinculos_existentes(con, clientes: list[int], combos: list[int]) -> set[tuple[int, int]]:
    existentes: set[tuple[int, int]] = set()
    combos_sql = ",".join("?" for _ in combos)
    cursor = con.cursor()
    try:
        for lote in _em_lotes(clientes):
            clientes_sql = ",".join("?" for _ in lote)
            cursor.execute(
                f"SELECT COMBO, CLIFOR FROM COMBOCLIFOR "
                f"WHERE COMBO IN ({combos_sql}) AND CLIFOR IN ({clientes_sql})",
                combos + lote,
            )
            existentes.update((int(combo), int(clifor)) for combo, clifor in cursor.fetchall())
    finally:
        cursor.close()
    return existentes


def _todos_vinculos_dos_combos(con, combos: list[int]) -> set[tuple[int, int]]:
    """Retorna apenas pares que já existem em COMBOCLIFOR."""
    if not combos:
        return set()
    cursor = con.cursor()
    try:
        cursor.execute(
            f"SELECT COMBO, CLIFOR FROM COMBOCLIFOR WHERE COMBO IN "
            f"({','.join('?' for _ in combos)})",
            combos,
        )
        return {
            (int(combo), int(cliente)) for combo, cliente in cursor.fetchall()
        }
    finally:
        cursor.close()


def _filiais_cotas_dos_combos(con, combos: list[int]) -> pd.DataFrame:
    """Lista cada filial ativa do combo e as cotas vigentes ligadas a ela."""
    if not combos:
        return pd.DataFrame(columns=[
            "combo", "filial_codigo", "filial_nome", "cota", "cota_nome",
        ])
    cursor = con.cursor()
    try:
        hoje = date.today()
        cursor.execute(
            f"SELECT DISTINCT cf.COMBO, cf.FILIAL, f.NOME "
            f"FROM COMBOFILIAL cf "
            f"JOIN FILIAL f ON f.CODIGO = cf.FILIAL "
            f"WHERE cf.COMBO IN ({','.join('?' for _ in combos)}) "
            f"AND COALESCE(f.ATIVO, 'S') = 'S' "
            f"ORDER BY cf.COMBO, cf.FILIAL",
            combos,
        )
        filiais = pd.DataFrame(cursor.fetchall(), columns=[
            "combo", "filial_codigo", "filial_nome",
        ])
        cursor.execute(
            f"SELECT DISTINCT cf.COMBO, c.FILIAL, c.CODIGO, c.NOME "
            f"FROM COMBOFILIAL cf "
            f"JOIN COTA c ON c.FILIAL = cf.FILIAL "
            f"WHERE cf.COMBO IN ({','.join('?' for _ in combos)}) "
            f"AND (c.DATAINICIO IS NULL OR c.DATAINICIO <= ?) "
            f"AND (c.DATAFIM IS NULL OR c.DATAFIM >= ?) "
            f"ORDER BY cf.COMBO, c.FILIAL, c.CODIGO",
            combos + [hoje, hoje],
        )
        cotas = pd.DataFrame(cursor.fetchall(), columns=[
            "combo", "filial_codigo", "cota", "cota_nome",
        ])
        return filiais.merge(cotas, on=["combo", "filial_codigo"], how="left")
    finally:
        cursor.close()


def consultar_filiais_cotas_combos(combos: Iterable[int]) -> pd.DataFrame:
    """Consulta pública das filiais ativas e cotas vigentes dos combos informados."""
    combos_unicos = sorted(set(int(item) for item in combos))
    if not combos_unicos:
        return pd.DataFrame(columns=[
            "combo", "filial_codigo", "filial_nome", "cota", "cota_nome",
        ])
    con = cliente_firebird("WIN1252")
    try:
        return _filiais_cotas_dos_combos(con, combos_unicos)
    finally:
        con.close()


def consultar_clientes_cotas_combos(combos: Iterable[int]) -> pd.DataFrame:
    """Lista os clientes atuais dos combos e sua liberação por filial/cota."""
    combos_unicos = sorted(set(int(item) for item in combos))
    colunas = [
        "combo", "cliente_codigo", "cliente_nome", "filial_codigo",
        "filial_nome", "cota", "cota_nome", "quantidade_cota",
    ]
    if not combos_unicos:
        return pd.DataFrame(columns=colunas)
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        cursor.execute(
            f"""SELECT cc.COMBO, cc.CLIFOR, cl.NOME
                FROM COMBOCLIFOR cc
                JOIN CLIFOR cl ON cl.CODIGO = cc.CLIFOR
                WHERE cc.COMBO IN ({','.join('?' for _ in combos_unicos)})
                ORDER BY cc.COMBO, cc.CLIFOR""",
            combos_unicos,
        )
        clientes = pd.DataFrame(cursor.fetchall(), columns=[
            "combo", "cliente_codigo", "cliente_nome",
        ])
        filiais_cotas = _filiais_cotas_dos_combos(con, combos_unicos)
        if clientes.empty or filiais_cotas.empty:
            return pd.DataFrame(columns=colunas)
        resultado = clientes.merge(filiais_cotas, on="combo", how="inner")
        quantidades = []
        clientes_codigos = clientes["cliente_codigo"].dropna().astype(int).unique().tolist()
        for lote in _em_lotes(clientes_codigos):
            cursor.execute(
                f"SELECT COMBO, CLIENTE, COTA, QUANTIDADE "
                f"FROM ITEMCOTACOMBOCLIENTE "
                f"WHERE COMBO IN ({','.join('?' for _ in combos_unicos)}) "
                f"AND CLIENTE IN ({','.join('?' for _ in lote)})",
                combos_unicos + lote,
            )
            quantidades.extend(cursor.fetchall())
        quantidades_df = pd.DataFrame(quantidades, columns=[
            "combo", "cliente_codigo", "cota", "quantidade_cota",
        ])
        if quantidades_df.empty:
            resultado["quantidade_cota"] = pd.NA
        else:
            resultado = resultado.merge(
                quantidades_df,
                on=["combo", "cliente_codigo", "cota"],
                how="left",
            )
        return resultado[colunas].sort_values(
            ["combo", "cliente_codigo", "filial_codigo", "cota"]
        ).reset_index(drop=True)
    finally:
        cursor.close()
        con.close()


def _cotas_por_combo(filiais_cotas: pd.DataFrame, combos: list[int]) -> dict[int, list[int]]:
    resultado = {combo: [] for combo in combos}
    for linha in filiais_cotas.dropna(subset=["cota"]).itertuples(index=False):
        resultado[int(linha.combo)].append(int(linha.cota))
    return {combo: sorted(set(cotas)) for combo, cotas in resultado.items()}


def _vinculos_cota_existentes(
    con, clientes: list[int], combos: list[int]
) -> set[tuple[int, int, int]]:
    existentes: set[tuple[int, int, int]] = set()
    if not clientes or not combos:
        return existentes
    combos_sql = ",".join("?" for _ in combos)
    cursor = con.cursor()
    try:
        for lote in _em_lotes(clientes):
            cursor.execute(
                f"SELECT COMBO, COTA, CLIENTE FROM ITEMCOTACOMBOCLIENTE "
                f"WHERE COMBO IN ({combos_sql}) AND CLIENTE IN "
                f"({','.join('?' for _ in lote)})",
                combos + lote,
            )
            existentes.update(
                (int(combo), int(cota), int(cliente))
                for combo, cota, cliente in cursor.fetchall()
            )
    finally:
        cursor.close()
    return existentes


def _combos_restritos_ie(con, combos: list[int]) -> set[int]:
    """Combos com ao menos um produto de vinho, espumante, água ou xarope."""
    if not combos:
        return set()
    restritos: set[int] = set()
    cursor = con.cursor()
    try:
        for lote in _em_lotes(combos):
            cursor.execute(
                f"""SELECT co.CODIGO, p.NOME, tp.NOME, g.NOME, cp.NOME, tl.NOME
                    FROM COMBO co
                    JOIN GRUPOCOMBO gc ON gc.COMBO = co.CODIGO
                    JOIN ITEMGRUPOCOMBO ig ON ig.GRUPOCOMBO = gc.CODIGO
                    JOIN PRODUTO p ON p.CODIGO = ig.PRODUTO
                    LEFT JOIN TIPOPRODUTO tp ON tp.CODIGO = p.TIPOPRODUTO
                    LEFT JOIN GRUPO g ON g.CODIGO = p.GRUPO
                    LEFT JOIN CATEGORIAPRODUTO cp ON cp.CODIGO = p.CATEGORIAPRODUTO
                    LEFT JOIN TIPOLINHA tl ON tl.ID = p.TIPOLINHA
                    WHERE co.CODIGO IN ({','.join('?' for _ in lote)})""",
                lote,
            )
            for linha in cursor.fetchall():
                if exige_vin_esp(list(linha[1:])):
                    restritos.add(int(linha[0]))
    finally:
        cursor.close()
    return restritos


def _clientes_sem_ie(con, clientes: list[int]) -> set[int]:
    """IE nula, vazia ou declarada como ISENTO não atende à regra universal."""
    sem_ie: set[int] = set()
    encontrados: set[int] = set()
    cursor = con.cursor()
    try:
        for lote in _em_lotes(clientes):
            cursor.execute(
                f"SELECT CODIGO, IE FROM CLIFOR WHERE CODIGO IN "
                f"({','.join('?' for _ in lote)})",
                lote,
            )
            for codigo, ie in cursor.fetchall():
                codigo = int(codigo)
                encontrados.add(codigo)
                valor = str(ie or "").strip().upper()
                if not valor or valor == "ISENTO":
                    sem_ie.add(codigo)
    finally:
        cursor.close()
    return sem_ie | (set(clientes) - encontrados)


def _bloqueios_ie(con, clientes: list[int], combos: list[int]) -> list[tuple[int, int]]:
    restritos = _combos_restritos_ie(con, combos)
    sem_ie = _clientes_sem_ie(con, clientes)
    return sorted((combo, cliente) for combo in restritos for cliente in sem_ie)


def _mensagem_bloqueios_ie(bloqueios: list[tuple[int, int]]) -> str:
    combos = sorted({combo for combo, _ in bloqueios})
    clientes = sorted({cliente for _, cliente in bloqueios})
    return (
        "Regra universal de IE: combos com vinho, espumante, água ou xarope "
        "não podem ser liberados para clientes sem Inscrição Estadual válida. "
        f"Combos: {', '.join(map(str, combos))}. "
        f"Clientes sem IE: {', '.join(map(str, clientes))}."
    )


def _validar_quantidade_cota(quantidade) -> int:
    try:
        resultado = int(quantidade)
    except (TypeError, ValueError):
        raise ValueError("A quantidade de cotas deve ser um número inteiro positivo.")
    if resultado <= 0:
        raise ValueError("A quantidade de cotas deve ser um número inteiro positivo.")
    return resultado


def planejar_insercao(
    clientes: Iterable[int], combos: Iterable[int], quantidade_cota: int = 1,
    inserir_somente_elegiveis_ie: bool = False,
) -> dict:
    quantidade_cota = _validar_quantidade_cota(quantidade_cota)
    clientes_unicos = sorted(set(int(item) for item in clientes))
    combos_unicos = sorted(set(int(item) for item in combos))
    if not clientes_unicos or not combos_unicos:
        return {
            "clientes": clientes_unicos, "combos": combos_unicos,
            "vinculos_novos": [], "ja_existentes": [],
            "quantidade_cota": quantidade_cota, "cotas_por_combo": {},
            "vinculos_cota_novos": [], "cotas_ja_existentes": [],
            "combos_sem_cotas": combos_unicos,
            "bloqueios_ie": [],
            "inserir_somente_elegiveis_ie": bool(inserir_somente_elegiveis_ie),
        }
    con = cliente_firebird("WIN1252")
    try:
        bloqueios_ie = _bloqueios_ie(con, clientes_unicos, combos_unicos)
        existentes = _vinculos_existentes(con, clientes_unicos, combos_unicos)
        filiais_cotas = _filiais_cotas_dos_combos(con, combos_unicos)
        cotas_por_combo = _cotas_por_combo(filiais_cotas, combos_unicos)
        cotas_existentes = _vinculos_cota_existentes(con, clientes_unicos, combos_unicos)
    finally:
        con.close()
    bloqueados_ie = set(bloqueios_ie)
    solicitados = {
        (combo, cliente) for combo in combos_unicos for cliente in clientes_unicos
        if not inserir_somente_elegiveis_ie or (combo, cliente) not in bloqueados_ie
    }
    cotas_solicitadas = {
        (combo, cota, cliente)
        for combo, cotas in cotas_por_combo.items()
        for cota in cotas
        for cliente in clientes_unicos
        if not inserir_somente_elegiveis_ie or (combo, cliente) not in bloqueados_ie
    }
    return {
        "clientes": clientes_unicos,
        "combos": combos_unicos,
        "vinculos_novos": sorted(solicitados - existentes),
        "ja_existentes": sorted(solicitados & existentes),
        "quantidade_cota": quantidade_cota,
        "cotas_por_combo": cotas_por_combo,
        "filiais_cotas": filiais_cotas,
        "filiais_sem_cota": filiais_cotas.loc[
            filiais_cotas["cota"].isna(), ["combo", "filial_codigo", "filial_nome"]
        ].to_dict("records"),
        "vinculos_cota_novos": sorted(cotas_solicitadas - cotas_existentes),
        "cotas_ja_existentes": sorted(cotas_solicitadas & cotas_existentes),
        "combos_sem_cotas": sorted(
            combo for combo, cotas in cotas_por_combo.items() if not cotas
        ),
        "bloqueios_ie": bloqueios_ie,
        "inserir_somente_elegiveis_ie": bool(inserir_somente_elegiveis_ie),
    }


def inserir_clientes_em_combos(
    clientes: Iterable[int], combos: Iterable[int], quantidade_cota: int = 1,
    inserir_somente_elegiveis_ie: bool = False,
) -> dict:
    """Revalida e grava clientes e cotas ausentes em uma única transação."""
    quantidade_cota = _validar_quantidade_cota(quantidade_cota)
    clientes_unicos = sorted(set(int(item) for item in clientes))
    combos_unicos = sorted(set(int(item) for item in combos))
    if not clientes_unicos or not combos_unicos:
        raise ValueError("Informe ao menos um cliente e um combo.")
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        bloqueios_ie = _bloqueios_ie(con, clientes_unicos, combos_unicos)
        if bloqueios_ie and not inserir_somente_elegiveis_ie:
            raise ValueError(_mensagem_bloqueios_ie(bloqueios_ie))
        bloqueados_ie = set(bloqueios_ie)
        existentes = _vinculos_existentes(con, clientes_unicos, combos_unicos)
        filiais_cotas = _filiais_cotas_dos_combos(con, combos_unicos)
        filiais_sem_cota = filiais_cotas.loc[filiais_cotas["cota"].isna()]
        if not filiais_sem_cota.empty:
            detalhes = ", ".join(
                f"combo {int(item.combo)} / filial {int(item.filial_codigo)}"
                for item in filiais_sem_cota.itertuples(index=False)
            )
            raise ValueError("Filiais ativas sem cota vigente configurada: " + detalhes)
        cotas_por_combo = _cotas_por_combo(filiais_cotas, combos_unicos)
        combos_sem_cotas = [combo for combo, cotas in cotas_por_combo.items() if not cotas]
        if combos_sem_cotas:
            raise ValueError(
                "Combos sem cotas configuradas no TOP: "
                + ", ".join(map(str, combos_sem_cotas))
            )
        cotas_existentes = _vinculos_cota_existentes(con, clientes_unicos, combos_unicos)
        pares_permitidos = {
            (combo, cliente)
            for combo in combos_unicos
            for cliente in clientes_unicos
            if not inserir_somente_elegiveis_ie
            or (combo, cliente) not in bloqueados_ie
        }
        novos = sorted(pares_permitidos - existentes)
        for combo, cliente in novos:
            cursor.execute(
                "INSERT INTO COMBOCLIFOR (COMBO, CLIFOR, REPLICAR) VALUES (?, ?, ?)",
                [combo, cliente, "N"],
            )
        cotas_permitidas = {
            (combo, cota, cliente)
            for combo, cotas in cotas_por_combo.items()
            for cota in cotas
            for cliente in clientes_unicos
            if not inserir_somente_elegiveis_ie
            or (combo, cliente) not in bloqueados_ie
        }
        novas_cotas = sorted(cotas_permitidas - cotas_existentes)
        for combo, cota, cliente in novas_cotas:
            cursor.execute(
                "INSERT INTO ITEMCOTACOMBOCLIENTE "
                "(QUANTIDADE, COTA, COMBO, CLIENTE) VALUES (?, ?, ?, ?)",
                [quantidade_cota, cota, combo, cliente],
            )
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        cursor.close()
        con.close()
    return {
        "clientes": len(clientes_unicos),
        "combos": len(combos_unicos),
        "inseridos": len(novos),
        "ja_existentes": len(pares_permitidos & existentes),
        "cotas_inseridas": len(novas_cotas),
        "cotas_ja_existentes": len(cotas_permitidas & cotas_existentes),
        "quantidade_cota": quantidade_cota,
        "bloqueios_ie_ignorados": len(bloqueios_ie),
    }


def consultar_detalhes_combos(combos: Iterable[int]) -> dict[str, pd.DataFrame]:
    combos_unicos = sorted(set(int(item) for item in combos))
    vazios = {
        "clientes_cotas": pd.DataFrame(),
        "produtos_valores": pd.DataFrame(),
        "filiais_cotas": pd.DataFrame(),
    }
    if not combos_unicos:
        return vazios
    marcadores = ",".join("?" for _ in combos_unicos)
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        cursor.execute(
            f"""SELECT cc.COMBO, co.NOME, cc.CLIFOR, cl.NOME,
                       ic.COTA, ct.NOME, ct.FILIAL, ic.QUANTIDADE
                FROM COMBOCLIFOR cc
                JOIN COMBO co ON co.CODIGO = cc.COMBO
                JOIN CLIFOR cl ON cl.CODIGO = cc.CLIFOR
                LEFT JOIN ITEMCOTACOMBOCLIENTE ic
                  ON ic.COMBO = cc.COMBO AND ic.CLIENTE = cc.CLIFOR
                LEFT JOIN COTA ct ON ct.CODIGO = ic.COTA
                WHERE cc.COMBO IN ({marcadores})
                ORDER BY cc.COMBO, cc.CLIFOR, ic.COTA""",
            combos_unicos,
        )
        clientes = pd.DataFrame(cursor.fetchall(), columns=[
            "combo", "combo_nome", "cliente_codigo", "cliente_nome",
            "cota", "cota_nome", "filial", "quantidade_cota",
        ])
        cursor.execute(
            f"""SELECT co.CODIGO, co.NOME, gc.CODIGO, gc.NOME, gc.QTDE,
                       gc.BONIFICADO, ig.PRODUTO, p.NOME, ig.QTDEINICIO,
                       ig.QTDEFIM, ig.VALORVENDA
                FROM COMBO co
                JOIN GRUPOCOMBO gc ON gc.COMBO = co.CODIGO
                JOIN ITEMGRUPOCOMBO ig ON ig.GRUPOCOMBO = gc.CODIGO
                JOIN PRODUTO p ON p.CODIGO = ig.PRODUTO
                WHERE co.CODIGO IN ({marcadores})
                ORDER BY co.CODIGO, gc.CODIGO, ig.PRODUTO""",
            combos_unicos,
        )
        produtos = pd.DataFrame(cursor.fetchall(), columns=[
            "combo", "combo_nome", "grupo_codigo", "grupo_nome", "grupo_quantidade",
            "bonificado", "produto_codigo", "produto_nome", "quantidade_inicial",
            "quantidade_final", "valor_venda",
        ])
        filiais_cotas = _filiais_cotas_dos_combos(con, combos_unicos)
    finally:
        cursor.close()
        con.close()
    return {
        "clientes_cotas": clientes,
        "produtos_valores": produtos,
        "filiais_cotas": filiais_cotas,
    }


def exportar_detalhes_combos_excel(detalhes: dict[str, pd.DataFrame]) -> bytes:
    """Gera a conferência de combos em quatro abas independentes."""
    clientes_cotas = detalhes.get("clientes_cotas", pd.DataFrame())
    produtos = detalhes.get("produtos_valores", pd.DataFrame()).copy()
    filiais_cotas = detalhes.get("filiais_cotas", pd.DataFrame())

    colunas_clientes = ["combo", "combo_nome", "cliente_codigo", "cliente_nome"]
    clientes = (
        clientes_cotas.reindex(columns=colunas_clientes)
        .drop_duplicates()
        .sort_values(["combo", "cliente_codigo"], ignore_index=True)
    )
    colunas_cotas = [
        "combo", "combo_nome", "cliente_codigo", "cliente_nome",
        "cota", "cota_nome", "quantidade_cota",
    ]
    cotas = (
        clientes_cotas.reindex(columns=colunas_cotas)
        .dropna(subset=["cota"])
        .drop_duplicates()
        .sort_values(["combo", "cliente_codigo", "cota"], ignore_index=True)
    )
    colunas_filiais = ["combo", "filial_codigo", "filial_nome"]
    filiais = (
        filiais_cotas.reindex(columns=colunas_filiais)
        .drop_duplicates()
        .sort_values(["combo", "filial_codigo"], ignore_index=True)
    )

    nomes_colunas = {
        "combo": "Combo", "combo_nome": "Nome do combo",
        "cliente_codigo": "Cliente", "cliente_nome": "Nome do cliente",
        "cota": "Cota", "cota_nome": "Nome da cota",
        "quantidade_cota": "Quantidade", "filial_codigo": "Filial",
        "filial_nome": "Nome da filial", "grupo_codigo": "Grupo",
        "grupo_nome": "Nome do grupo", "grupo_quantidade": "Quantidade do grupo",
        "bonificado": "Bonificado", "produto_codigo": "Produto",
        "produto_nome": "Nome do produto", "quantidade_inicial": "Quantidade inicial",
        "quantidade_final": "Quantidade final", "valor_venda": "Valor de venda",
    }
    abas = {
        "Clientes": clientes,
        "Produtos": produtos,
        "Cotas": cotas,
        "Filiais": filiais,
    }
    arquivo = BytesIO()
    with pd.ExcelWriter(arquivo, engine="openpyxl") as writer:
        for nome_aba, dados in abas.items():
            dados.rename(columns=nomes_colunas).to_excel(
                writer, sheet_name=nome_aba, index=False
            )
            planilha = writer.sheets[nome_aba]
            planilha.freeze_panes = "A2"
            planilha.auto_filter.ref = planilha.dimensions
            for coluna in planilha.columns:
                largura = max(
                    (len(str(celula.value)) for celula in coluna if celula.value is not None),
                    default=10,
                )
                planilha.column_dimensions[coluna[0].column_letter].width = min(largura + 2, 45)
    return arquivo.getvalue()


def planejar_alteracao_combos(
    clientes: Iterable[int], combos: Iterable[int], acao: str,
    quantidade_cota: int = 1,
) -> dict:
    clientes_unicos = sorted(set(int(item) for item in clientes))
    combos_unicos = sorted(set(int(item) for item in combos))
    if acao not in {"Incluir", "Incluir sem cotas", "Excluir", "Inserir somente cotas"}:
        raise ValueError(
            "Ação inválida. Use Incluir, Excluir ou Inserir somente cotas."
        )
    if acao == "Inserir somente cotas":
        quantidade_cota = _validar_quantidade_cota(quantidade_cota)
        if not combos_unicos:
            return {
                "acao": acao, "clientes": [], "combos": [],
                "vinculos_afetados": [], "sem_alteracao": [],
                "cotas_afetadas": [], "cotas_ja_existentes": [],
                "filiais_cotas": pd.DataFrame(), "quantidade_cota": quantidade_cota,
                "combos_sem_cotas": [], "filiais_sem_cota": [], "bloqueios_ie": [],
            }
        con = cliente_firebird("WIN1252")
        try:
            vinculos = _todos_vinculos_dos_combos(con, combos_unicos)
            clientes_vinculados = sorted({cliente for _, cliente in vinculos})
            filiais_cotas = _filiais_cotas_dos_combos(con, combos_unicos)
            cotas_por_combo = _cotas_por_combo(filiais_cotas, combos_unicos)
            existentes = _vinculos_cota_existentes(
                con, clientes_vinculados, combos_unicos
            )
            restritos_ie = _combos_restritos_ie(con, combos_unicos)
            clientes_sem_ie = _clientes_sem_ie(con, clientes_vinculados)
        finally:
            con.close()
        solicitadas = {
            (combo, cota, cliente)
            for combo, cliente in vinculos
            for cota in cotas_por_combo.get(combo, [])
        }
        bloqueios_ie = sorted(
            (combo, cliente) for combo, cliente in vinculos
            if combo in restritos_ie and cliente in clientes_sem_ie
        )
        return {
            "acao": acao,
            "clientes": clientes_vinculados,
            "combos": combos_unicos,
            "vinculos_afetados": [],
            "sem_alteracao": sorted(vinculos),
            "cotas_afetadas": sorted(solicitadas - existentes),
            "cotas_ja_existentes": sorted(solicitadas & existentes),
            "filiais_cotas": filiais_cotas,
            "quantidade_cota": quantidade_cota,
            "combos_sem_cotas": sorted(
                combo for combo, cotas in cotas_por_combo.items() if not cotas
            ),
            "filiais_sem_cota": filiais_cotas.loc[
                filiais_cotas["cota"].isna(),
                ["combo", "filial_codigo", "filial_nome"],
            ].to_dict("records"),
            "bloqueios_ie": bloqueios_ie,
        }
    if not clientes_unicos or not combos_unicos:
        return {
            "acao": acao, "clientes": clientes_unicos, "combos": combos_unicos,
            "vinculos_afetados": [], "sem_alteracao": [],
            "cotas_afetadas": [], "filiais_cotas": pd.DataFrame(),
        }
    if acao == "Incluir":
        plano = planejar_insercao(clientes_unicos, combos_unicos, quantidade_cota)
        return {
            "acao": acao, "clientes": clientes_unicos, "combos": combos_unicos,
            "vinculos_afetados": plano["vinculos_novos"],
            "sem_alteracao": plano["ja_existentes"],
            "cotas_afetadas": plano["vinculos_cota_novos"],
            "filiais_cotas": plano["filiais_cotas"],
            "combos_sem_cotas": plano["combos_sem_cotas"],
            "filiais_sem_cota": plano["filiais_sem_cota"],
            "bloqueios_ie": plano["bloqueios_ie"],
            "quantidade_cota": plano["quantidade_cota"],
        }
    con = cliente_firebird("WIN1252")
    try:
        existentes = _vinculos_existentes(con, clientes_unicos, combos_unicos)
        bloqueios_ie = (
            _bloqueios_ie(con, clientes_unicos, combos_unicos)
            if acao == "Incluir sem cotas" else []
        )
    finally:
        con.close()
    solicitados = {(combo, cliente) for combo in combos_unicos for cliente in clientes_unicos}
    incluindo = acao in {"Incluir", "Incluir sem cotas"}
    afetados = solicitados - existentes if incluindo else solicitados & existentes
    sem_alteracao = solicitados & existentes if incluindo else solicitados - existentes
    return {
        "acao": acao,
        "clientes": clientes_unicos,
        "combos": combos_unicos,
        "vinculos_afetados": sorted(afetados),
        "sem_alteracao": sorted(sem_alteracao),
        "cotas_afetadas": [], "filiais_cotas": pd.DataFrame(),
        "bloqueios_ie": bloqueios_ie,
    }


def aplicar_alteracao_combos(
    clientes: Iterable[int], combos: Iterable[int], acao: str,
    quantidade_cota: int = 1,
) -> dict:
    """Revalida e inclui ou exclui vínculos em uma única transação."""
    clientes_unicos = sorted(set(int(item) for item in clientes))
    combos_unicos = sorted(set(int(item) for item in combos))
    if acao not in {"Incluir", "Incluir sem cotas", "Excluir", "Inserir somente cotas"}:
        raise ValueError(
            "Ação inválida. Use Incluir, Excluir ou Inserir somente cotas."
        )
    if not combos_unicos or (acao != "Inserir somente cotas" and not clientes_unicos):
        raise ValueError("Informe ao menos um cliente e um combo.")
    if acao == "Incluir":
        resultado = inserir_clientes_em_combos(
            clientes_unicos, combos_unicos, quantidade_cota
        )
        return {
            "acao": acao, "clientes": resultado["clientes"],
            "combos": resultado["combos"], "alterados": resultado["inseridos"],
            "sem_alteracao": resultado["ja_existentes"],
            "cotas_inseridas": resultado["cotas_inseridas"],
            "quantidade_cota": resultado["quantidade_cota"],
        }
    if acao == "Inserir somente cotas":
        quantidade_cota = _validar_quantidade_cota(quantidade_cota)
        con = cliente_firebird("WIN1252")
        cursor = con.cursor()
        try:
            # A lista é obrigatoriamente relida dentro da transação. Esta
            # operação nunca executa INSERT em COMBOCLIFOR.
            vinculos = _todos_vinculos_dos_combos(con, combos_unicos)
            clientes_vinculados = sorted({cliente for _, cliente in vinculos})
            filiais_cotas = _filiais_cotas_dos_combos(con, combos_unicos)
            filiais_sem_cota = filiais_cotas.loc[filiais_cotas["cota"].isna()]
            if not filiais_sem_cota.empty:
                raise ValueError("Há filial ativa sem cota vigente configurada.")
            cotas_por_combo = _cotas_por_combo(filiais_cotas, combos_unicos)
            combos_sem_cotas = [
                combo for combo, cotas in cotas_por_combo.items() if not cotas
            ]
            if combos_sem_cotas:
                raise ValueError(
                    "Combos sem cotas configuradas no TOP: "
                    + ", ".join(map(str, combos_sem_cotas))
                )
            restritos_ie = _combos_restritos_ie(con, combos_unicos)
            clientes_sem_ie = _clientes_sem_ie(con, clientes_vinculados)
            bloqueios_ie = sorted(
                (combo, cliente) for combo, cliente in vinculos
                if combo in restritos_ie and cliente in clientes_sem_ie
            )
            if bloqueios_ie:
                raise ValueError(_mensagem_bloqueios_ie(bloqueios_ie))
            existentes = _vinculos_cota_existentes(
                con, clientes_vinculados, combos_unicos
            )
            novas_cotas = sorted(
                (combo, cota, cliente)
                for combo, cliente in vinculos
                for cota in cotas_por_combo.get(combo, [])
                if (combo, cota, cliente) not in existentes
            )
            for combo, cota, cliente in novas_cotas:
                cursor.execute(
                    "INSERT INTO ITEMCOTACOMBOCLIENTE "
                    "(QUANTIDADE, COTA, COMBO, CLIENTE) VALUES (?, ?, ?, ?)",
                    [quantidade_cota, cota, combo, cliente],
                )
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            cursor.close()
            con.close()
        return {
            "acao": acao,
            "clientes": len(clientes_vinculados),
            "combos": len(combos_unicos),
            "alterados": 0,
            "sem_alteracao": len(vinculos),
            "cotas_inseridas": len(novas_cotas),
            "quantidade_cota": quantidade_cota,
        }
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        if acao == "Incluir sem cotas":
            bloqueios_ie = _bloqueios_ie(con, clientes_unicos, combos_unicos)
            if bloqueios_ie:
                raise ValueError(_mensagem_bloqueios_ie(bloqueios_ie))
        existentes = _vinculos_existentes(con, clientes_unicos, combos_unicos)
        solicitados = {
            (combo, cliente) for combo in combos_unicos for cliente in clientes_unicos
        }
        incluindo = acao == "Incluir sem cotas"
        afetados = sorted(
            solicitados - existentes if incluindo else solicitados & existentes
        )
        sql = (
            "INSERT INTO COMBOCLIFOR (COMBO, CLIFOR, REPLICAR) VALUES (?, ?, 'N')"
            if incluindo
            else "DELETE FROM COMBOCLIFOR WHERE COMBO = ? AND CLIFOR = ?"
        )
        for combo, cliente in afetados:
            cursor.execute(sql, [combo, cliente])
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        cursor.close()
        con.close()
    return {
        "acao": acao,
        "clientes": len(clientes_unicos),
        "combos": len(combos_unicos),
        "alterados": len(afetados),
        "sem_alteracao": len(solicitados) - len(afetados),
    }
