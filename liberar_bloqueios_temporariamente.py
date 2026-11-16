from __future__ import annotations

import argparse
import csv
import io
import zipfile
from datetime import datetime
from pathlib import Path

from conexoes import cliente_firebird


BASE_DIR = Path(__file__).resolve().parent
MANIFESTO = (
    BASE_DIR / "restore_dados_etapas_1_2_20260831"
    / "manifesto_etapa_2_20260831.zip"
)


def ler_clientes(caminho: Path) -> list[int]:
    return sorted({int(valor) for valor in caminho.read_text().split()})


def pares_do_manifesto(clientes: set[int]) -> dict[tuple[int, int], dict[str, str]]:
    pares: dict[tuple[int, int], dict[str, str]] = {}
    with zipfile.ZipFile(MANIFESTO) as compactado:
        with compactado.open("bloqueios_a_inserir.csv") as binario:
            texto = io.TextIOWrapper(binario, encoding="utf-8-sig", newline="")
            for linha in csv.DictReader(texto, delimiter=";"):
                cliente = int(linha["cliente_codigo"])
                if cliente in clientes:
                    pares[(cliente, int(linha["condicao_codigo"]))] = linha
    return pares


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


def salvar_evidencias(
    pasta: Path,
    pares: list[tuple[int, int]],
    detalhes: dict[tuple[int, int], dict[str, str]],
) -> None:
    pasta.mkdir(parents=True, exist_ok=False)
    with (pasta / "bloqueios_removidos.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as arquivo:
        campos = [
            "cliente_codigo", "cliente_nome", "tipo_estabelecimento",
            "regra_aplicada", "descricao_regra", "condicao_codigo",
            "condicao_nome", "status_condicao", "acao",
        ]
        escritor = csv.DictWriter(arquivo, fieldnames=campos, delimiter=";")
        escritor.writeheader()
        for par in pares:
            linha = dict(detalhes[par])
            linha["acao"] = "Removido temporariamente"
            escritor.writerow({campo: linha.get(campo, "") for campo in campos})
    with (pasta / "reaplicar_bloqueios.sql").open(
        "w", encoding="utf-8", newline="\n"
    ) as arquivo:
        arquivo.write("SET SQL DIALECT 3;\nSET AUTODDL OFF;\n\n")
        for cliente, condicao in pares:
            arquivo.write(
                "INSERT INTO CLIFORCONDICAOPAGAMENTO "
                "(CLIFOR, CONDICAOPAGAMENTO, REPLICAR) "
                f"SELECT {cliente}, {condicao}, 'N' FROM RDB$DATABASE WHERE NOT EXISTS "
                "(SELECT 1 FROM CLIFORCONDICAOPAGAMENTO WHERE CLIFOR = "
                f"{cliente} AND CONDICAOPAGAMENTO = {condicao});\n"
            )
        arquivo.write("\nCOMMIT;\n")
    with (pasta / "remocao_executada.sql").open(
        "w", encoding="utf-8", newline="\n"
    ) as arquivo:
        arquivo.write("SET SQL DIALECT 3;\nSET AUTODDL OFF;\n\n")
        for cliente, condicao in pares:
            arquivo.write(
                "DELETE FROM CLIFORCONDICAOPAGAMENTO WHERE "
                f"CLIFOR = {cliente} AND CONDICAOPAGAMENTO = {condicao};\n"
            )
        arquivo.write("\nCOMMIT;\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clientes", type=Path, required=True)
    parser.add_argument("--pasta-base", type=Path, default=BASE_DIR)
    parser.add_argument("--executar", action="store_true")
    args = parser.parse_args()
    clientes = ler_clientes(args.clientes)
    detalhes = pares_do_manifesto(set(clientes))
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        existentes = consultar_existentes(cursor, set(detalhes))
        pares = sorted(existentes)
        agora = datetime.now().astimezone()
        pasta = (
            args.pasta_base.resolve()
            / f"liberacao_temporaria_bloqueios_{agora:%Y%m%d_%H%M%S}"
        )
        salvar_evidencias(pasta, pares, detalhes)
        if args.executar and pares:
            cursor.executemany(
                "DELETE FROM CLIFORCONDICAOPAGAMENTO WHERE "
                "CLIFOR = ? AND CONDICAOPAGAMENTO = ?",
                pares,
            )
            con.commit()
            restantes = consultar_existentes(cursor, set(pares))
            if restantes:
                raise RuntimeError(
                    f"Validação encontrou {len(restantes)} bloqueios ainda presentes."
                )
        else:
            con.rollback()
        clientes_manifesto = {cliente for cliente, _ in detalhes}
        clientes_removidos = {cliente for cliente, _ in pares}
        (pasta / "README.md").write_text(
            "# Liberação temporária de bloqueios\n\n"
            f"- Gerado em: {agora:%d/%m/%Y %H:%M:%S %z}\n"
            f"- Clientes informados (sem duplicidade): {len(clientes)}\n"
            f"- Clientes encontrados no manifesto: {len(clientes_manifesto)}\n"
            f"- Clientes com bloqueios removidos: {len(clientes_removidos)}\n"
            f"- Bloqueios removidos: {len(pares)}\n"
            f"- Execução realizada: {'SIM' if args.executar else 'NÃO'}\n\n"
            "Use `reaplicar_bloqueios.sql` somente após a confirmação do faturamento.\n",
            encoding="utf-8",
        )
        print(f"PASTA={pasta}")
        print(f"CLIENTES_INFORMADOS={len(clientes)}")
        print(f"CLIENTES_MANIFESTO={len(clientes_manifesto)}")
        print(f"CLIENTES_REMOVIDOS={len(clientes_removidos)}")
        print(f"BLOQUEIOS_REMOVIDOS={len(pares)}")
        print(f"EXECUTADO={'SIM' if args.executar else 'NAO'}")
    except Exception:
        con.rollback()
        raise
    finally:
        cursor.close()
        con.close()


if __name__ == "__main__":
    main()
