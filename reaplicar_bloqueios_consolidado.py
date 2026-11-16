from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path

from conexoes import cliente_firebird
from dados import (
    _classificar_regra_bloqueio,
    _codigos_protegidos_pagamentos,
    _condicoes_por_regra,
    _dados_bloqueios_pagamentos,
)


BASE_DIR = Path(__file__).resolve().parent
OPERACOES_EXECUTADAS = [
    "liberacao_temporaria_bloqueios_20260901_073313",
    "liberacao_temporaria_bloqueios_20260901_082653",
    "liberacao_temporaria_bloqueios_20260901_082836",
    "liberacao_temporaria_bloqueios_20260901_083046",
    "liberacao_temporaria_bloqueios_20260901_083131",
    "liberacao_temporaria_bloqueios_20260901_083842",
]


def carregar_removidos() -> dict[tuple[int, int], dict[str, str]]:
    removidos: dict[tuple[int, int], dict[str, str]] = {}
    for pasta in OPERACOES_EXECUTADAS:
        caminho = BASE_DIR / pasta / "bloqueios_removidos.csv"
        with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
            for linha in csv.DictReader(arquivo, delimiter=";"):
                par = (int(linha["cliente_codigo"]), int(linha["condicao_codigo"]))
                removidos[par] = linha
    return removidos


def consultar_existentes(cursor, pares: set[tuple[int, int]]) -> set[tuple[int, int]]:
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


def salvar_csv(caminho: Path, linhas: list[dict[str, str]]) -> None:
    campos = [
        "cliente_codigo", "cliente_nome", "tipo_estabelecimento",
        "regra_aplicada", "descricao_regra", "condicao_codigo",
        "condicao_nome", "status_condicao", "acao", "motivo",
    ]
    with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=campos, delimiter=";")
        escritor.writeheader()
        for linha in linhas:
            escritor.writerow({campo: linha.get(campo, "") for campo in campos})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executar", action="store_true")
    args = parser.parse_args()
    removidos = carregar_removidos()
    clientes = sorted({cliente for cliente, _ in removidos})
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        protegidos = _codigos_protegidos_pagamentos(con, clientes)
        cadastros, com_prz, sem_prz, a_vista = _dados_bloqueios_pagamentos(
            con, clientes
        )
        permitidos: set[tuple[int, int]] = set()
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
                motivos[par] = "Cliente não se enquadra nas regras atuais"
                continue
            condicoes_regra = set(
                _condicoes_por_regra(regra, com_prz, sem_prz, a_vista)
            )
            if condicao not in condicoes_regra:
                motivos[par] = (
                    "Condição excluída pelas regras atuais (PRZ, à vista, "
                    "inativa ou exceção por tipo)"
                )
                continue
            permitidos.add(par)
        existentes = consultar_existentes(cursor, set(removidos))
        inserir = sorted(permitidos - existentes)
        ja_existentes = permitidos & existentes
        for par in ja_existentes:
            motivos[par] = "Bloqueio já existe; não duplicar"

        agora = datetime.now().astimezone()
        pasta = BASE_DIR / f"reaplicacao_bloqueios_20260901_{agora:%H%M%S}"
        pasta.mkdir(parents=True, exist_ok=False)
        linhas_inserir = []
        linhas_excluidas = []
        for par, original in removidos.items():
            linha = dict(original)
            if par in set(inserir):
                linha["acao"] = "Reaplicar"
                linha["motivo"] = "Elegível pelas regras atuais"
                linhas_inserir.append(linha)
            else:
                linha["acao"] = "Não reaplicar"
                linha["motivo"] = motivos.get(par, "Não elegível")
                linhas_excluidas.append(linha)
        salvar_csv(pasta / "bloqueios_reaplicados.csv", linhas_inserir)
        salvar_csv(pasta / "bloqueios_nao_reaplicados.csv", linhas_excluidas)
        with (pasta / "reaplicacao_executada.sql").open(
            "w", encoding="utf-8", newline="\n"
        ) as arquivo:
            arquivo.write("SET SQL DIALECT 3;\nSET AUTODDL OFF;\n\n")
            for cliente, condicao in inserir:
                arquivo.write(
                    "INSERT INTO CLIFORCONDICAOPAGAMENTO "
                    "(CLIFOR, CONDICAOPAGAMENTO, REPLICAR) VALUES "
                    f"({cliente}, {condicao}, 'N');\n"
                )
            arquivo.write("\nCOMMIT;\n")

        if args.executar and inserir:
            cursor.executemany(
                "INSERT INTO CLIFORCONDICAOPAGAMENTO "
                "(CLIFOR, CONDICAOPAGAMENTO, REPLICAR) VALUES (?, ?, ?)",
                [(cliente, condicao, "N") for cliente, condicao in inserir],
            )
            con.commit()
            validados = consultar_existentes(cursor, set(inserir))
            if validados != set(inserir):
                raise RuntimeError(
                    f"Validação encontrou {len(validados)} de {len(inserir)} registros."
                )
        else:
            con.rollback()
        (pasta / "README.md").write_text(
            "# Reaplicação consolidada de bloqueios\n\n"
            f"- Gerado em: {agora:%d/%m/%Y %H:%M:%S %z}\n"
            f"- Bloqueios removidos documentados: {len(removidos)}\n"
            f"- Bloqueios reaplicados: {len(inserir)}\n"
            f"- Bloqueios não reaplicados pelas regras atuais ou já existentes: "
            f"{len(removidos) - len(inserir)}\n"
            f"- Execução realizada: {'SIM' if args.executar else 'NÃO'}\n",
            encoding="utf-8",
        )
        print(f"PASTA={pasta}")
        print(f"REMOVIDOS_DOCUMENTADOS={len(removidos)}")
        print(f"REAPLICADOS={len(inserir)}")
        print(f"NAO_REAPLICADOS={len(removidos)-len(inserir)}")
        print(f"JA_EXISTENTES={len(ja_existentes)}")
        print(f"PROTEGIDOS={len(protegidos)}")
        print(f"EXECUTADO={'SIM' if args.executar else 'NAO'}")
    except Exception:
        con.rollback()
        raise
    finally:
        cursor.close()
        con.close()


if __name__ == "__main__":
    main()
