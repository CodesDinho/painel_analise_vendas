from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from conexoes import cliente_firebird
from dados import (
    _classificar_regra_bloqueio,
    _codigos_protegidos_pagamentos,
    _condicoes_por_regra,
    _dados_bloqueios_pagamentos,
)
from project_paths import SNAPSHOT_RESTORE_ETAPAS


BASE_DIR = Path(__file__).resolve().parent
PASTA_OPERACOES = BASE_DIR / "temporarios"
MANIFESTO = SNAPSHOT_RESTORE_ETAPAS / "manifesto_etapa_2_20260831.zip"


def normalizar_clientes(texto: str) -> list[int]:
    partes = texto.replace(",", " ").replace(";", " ").split()
    invalidos = [item for item in partes if not item.isdigit()]
    if invalidos:
        raise ValueError("Códigos inválidos: " + ", ".join(invalidos[:20]))
    clientes = sorted({int(item) for item in partes})
    if not clientes:
        raise ValueError("Informe ao menos um código de cliente.")
    return clientes


def _detalhes_manifesto(clientes: set[int]) -> dict[tuple[int, int], dict[str, str]]:
    detalhes: dict[tuple[int, int], dict[str, str]] = {}
    with zipfile.ZipFile(MANIFESTO) as compactado:
        with compactado.open("bloqueios_a_inserir.csv") as binario:
            texto = io.TextIOWrapper(binario, encoding="utf-8-sig", newline="")
            for linha in csv.DictReader(texto, delimiter=";"):
                cliente = int(linha["cliente_codigo"])
                if cliente in clientes:
                    detalhes[(cliente, int(linha["condicao_codigo"]))] = linha
    return detalhes


def _consultar_existentes(cursor, pares: set[tuple[int, int]]) -> set[tuple[int, int]]:
    if not pares:
        return set()
    existentes: set[tuple[int, int]] = set()
    clientes = sorted({cliente for cliente, _ in pares})
    condicoes = sorted({condicao for _, condicao in pares})
    for inicio in range(0, len(clientes), 250):
        lote = clientes[inicio:inicio + 250]
        cursor.execute(
            "SELECT CLIFOR, CONDICAOPAGAMENTO FROM CLIFORCONDICAOPAGAMENTO "
            "WHERE CLIFOR IN (" + ",".join("?" for _ in lote) + ") AND "
            "CONDICAOPAGAMENTO IN (" + ",".join("?" for _ in condicoes) + ")",
            lote + condicoes,
        )
        existentes.update((int(a), int(b)) for a, b in cursor.fetchall())
    return existentes & pares


def preparar_liberacao(clientes: Iterable[int]) -> dict:
    clientes = sorted(set(int(item) for item in clientes))
    detalhes = _detalhes_manifesto(set(clientes))
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        pares = sorted(_consultar_existentes(cursor, set(detalhes)))
    finally:
        cursor.close()
        con.close()
    encontrados = sorted({cliente for cliente, _ in detalhes})
    removiveis = sorted({cliente for cliente, _ in pares})
    return {
        "clientes_informados": clientes,
        "clientes_manifesto": encontrados,
        "clientes_removiveis": removiveis,
        "clientes_sem_registro": sorted(set(clientes) - set(encontrados)),
        "pares": pares,
        "detalhes": detalhes,
    }


def _salvar_csv(caminho: Path, pares: list[tuple[int, int]], detalhes: dict) -> None:
    campos = [
        "cliente_codigo", "cliente_nome", "tipo_estabelecimento",
        "regra_aplicada", "descricao_regra", "condicao_codigo",
        "condicao_nome", "status_condicao", "acao",
    ]
    with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=campos, delimiter=";")
        escritor.writeheader()
        for par in pares:
            linha = dict(detalhes[par])
            linha["acao"] = "Removido temporariamente"
            escritor.writerow({campo: linha.get(campo, "") for campo in campos})


def executar_liberacao(plano: dict, usuario: str) -> dict:
    pares_planejados = set(tuple(item) for item in plano["pares"])
    if not pares_planejados:
        raise ValueError("Não há bloqueios elegíveis atualmente existentes para remover.")
    agora = datetime.now().astimezone()
    pasta = PASTA_OPERACOES / f"faturamento_liberacao_{agora:%Y%m%d_%H%M%S}"
    pasta.mkdir(parents=True, exist_ok=False)
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        existentes = _consultar_existentes(cursor, pares_planejados)
        pares = sorted(existentes)
        if not pares:
            raise ValueError("Os bloqueios da prévia já não existem. Prepare novamente.")
        cursor.executemany(
            "DELETE FROM CLIFORCONDICAOPAGAMENTO WHERE "
            "CLIFOR = ? AND CONDICAOPAGAMENTO = ?",
            pares,
        )
        con.commit()
        restantes = _consultar_existentes(cursor, set(pares))
        if restantes:
            raise RuntimeError(f"Ainda existem {len(restantes)} bloqueios após a remoção.")
        _salvar_csv(pasta / "bloqueios_removidos.csv", pares, plano["detalhes"])
        operacao = {
            "versao": 1,
            "status": "PENDENTE_REAPLICACAO",
            "criado_em": agora.isoformat(),
            "criado_por": usuario,
            "clientes_informados": plano["clientes_informados"],
            "pares_removidos": [list(par) for par in pares],
            "total_clientes": len({cliente for cliente, _ in pares}),
            "total_bloqueios": len(pares),
        }
        (pasta / "operacao.json").write_text(
            json.dumps(operacao, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {**operacao, "pasta": str(pasta), "id": pasta.name}
    except Exception:
        con.rollback()
        raise
    finally:
        cursor.close()
        con.close()


def listar_operacoes() -> list[dict]:
    PASTA_OPERACOES.mkdir(exist_ok=True)
    operacoes = []
    for caminho in sorted(PASTA_OPERACOES.glob("*/operacao.json")):
        try:
            item = json.loads(caminho.read_text(encoding="utf-8"))
            if not item.get("pares_removidos") and item.get("pares_arquivo"):
                with (caminho.parent / item["pares_arquivo"]).open(
                    encoding="utf-8-sig", newline=""
                ) as arquivo:
                    item["pares_removidos"] = [
                        [int(linha["cliente_codigo"]), int(linha["condicao_codigo"])]
                        for linha in csv.DictReader(arquivo, delimiter=";")
                    ]
            item["pasta"] = str(caminho.parent)
            item["id"] = caminho.parent.name
            operacoes.append(item)
        except (OSError, ValueError):
            continue
    return sorted(operacoes, key=lambda item: item.get("criado_em", ""), reverse=True)


def auditar_operacao(operacao: dict) -> pd.DataFrame:
    pares = {tuple(item) for item in operacao.get("pares_removidos", [])}
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        existentes = _consultar_existentes(cursor, pares)
    finally:
        cursor.close()
        con.close()
    linhas = []
    for cliente in sorted({cliente for cliente, _ in pares}):
        pares_cliente = {par for par in pares if par[0] == cliente}
        presentes = len(pares_cliente & existentes)
        ausentes = len(pares_cliente) - presentes
        linhas.append({
            "cliente_codigo": cliente,
            "bloqueios_removidos": len(pares_cliente),
            "ainda_sem_bloqueio": ausentes,
            "ja_presentes": presentes,
            "situacao": "Pendente" if ausentes else "Reaplicado",
        })
    return pd.DataFrame(linhas)


def preparar_reaplicacao(operacao: dict) -> dict:
    removidos = {tuple(item) for item in operacao.get("pares_removidos", [])}
    clientes = sorted({cliente for cliente, _ in removidos})
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        protegidos = _codigos_protegidos_pagamentos(con, clientes)
        cadastros, com_prz, sem_prz, a_vista = _dados_bloqueios_pagamentos(con, clientes)
        elegiveis: set[tuple[int, int]] = set()
        motivos: dict[tuple[int, int], str] = {}
        for par in removidos:
            cliente, condicao = par
            if cliente in protegidos:
                motivos[par] = "Cliente protegido pelos vendedores 1929/187"
                continue
            cadastro = cadastros.get(cliente)
            if cadastro is None:
                motivos[par] = "Cliente não localizado como CLIFOR TIPO = 1"
                continue
            regra = _classificar_regra_bloqueio(cadastro[2], cadastro[3])
            if regra is None:
                motivos[par] = "Cliente fora das regras atuais"
                continue
            permitidas = set(_condicoes_por_regra(regra, com_prz, sem_prz, a_vista))
            if condicao not in permitidas:
                motivos[par] = "Condição fora das regras atuais"
                continue
            elegiveis.add(par)
        existentes = _consultar_existentes(cursor, removidos)
        inserir = sorted(elegiveis - existentes)
        ja_presentes = sorted(elegiveis & existentes)
        nao_reaplicar = sorted(removidos - elegiveis)
        return {
            "operacao_id": operacao["id"], "pasta": operacao["pasta"],
            "inserir": inserir, "ja_presentes": ja_presentes,
            "nao_reaplicar": nao_reaplicar, "motivos": motivos,
            "clientes": clientes,
            "pares_removidos": [list(par) for par in sorted(removidos)],
        }
    finally:
        cursor.close()
        con.close()


def executar_reaplicacao(plano: dict, usuario: str) -> dict:
    pasta = Path(plano["pasta"])
    caminho_operacao = pasta / "operacao.json"
    operacao = json.loads(caminho_operacao.read_text(encoding="utf-8"))
    if operacao.get("status") != "PENDENTE_REAPLICACAO":
        raise ValueError("Esta operação já foi finalizada.")
    if not operacao.get("pares_removidos"):
        operacao["pares_removidos"] = plano["pares_removidos"]
    # Recalcula dentro da operação para não confiar em uma prévia antiga.
    atual = preparar_reaplicacao({**operacao, "id": pasta.name, "pasta": str(pasta)})
    inserir = atual["inserir"]
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        if inserir:
            cursor.executemany(
                "INSERT INTO CLIFORCONDICAOPAGAMENTO "
                "(CLIFOR, CONDICAOPAGAMENTO, REPLICAR) VALUES (?, ?, ?)",
                [(cliente, condicao, "N") for cliente, condicao in inserir],
            )
        con.commit()
        validados = _consultar_existentes(cursor, set(inserir))
        if validados != set(inserir):
            raise RuntimeError("A validação da reaplicação não conferiu todos os registros.")
        agora = datetime.now().astimezone()
        operacao.update({
            "status": "REAPLICADA",
            "reaplicado_em": agora.isoformat(),
            "reaplicado_por": usuario,
            "bloqueios_reaplicados": len(inserir),
            "bloqueios_ja_presentes": len(atual["ja_presentes"]),
            "bloqueios_nao_reaplicados_regras_atuais": len(atual["nao_reaplicar"]),
        })
        caminho_operacao.write_text(
            json.dumps(operacao, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return operacao
    except Exception:
        con.rollback()
        raise
    finally:
        cursor.close()
        con.close()
