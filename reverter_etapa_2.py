from __future__ import annotations

import argparse
import csv
import io
import json
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path

from conexoes import cliente_firebird


BASE_DIR = Path(__file__).resolve().parent
MANIFESTO = (
    BASE_DIR / "restore_dados_etapas_1_2_20260831"
    / "manifesto_etapa_2_20260831.zip"
)
PASTA_BASE = BASE_DIR / "temporarios"
ULTIMA_LIBERACAO = (
    PASTA_BASE / "liberacao_temporaria_bloqueios_20260901_133436"
    / "bloqueios_removidos.csv"
)


def carregar_manifesto() -> dict[tuple[int, int], dict[str, str]]:
    linhas: dict[tuple[int, int], dict[str, str]] = {}
    with zipfile.ZipFile(MANIFESTO) as compactado:
        with compactado.open("bloqueios_a_inserir.csv") as binario:
            texto = io.TextIOWrapper(binario, encoding="utf-8-sig", newline="")
            for linha in csv.DictReader(texto, delimiter=";"):
                par = (int(linha["cliente_codigo"]), int(linha["condicao_codigo"]))
                linhas[par] = linha
    return linhas


def carregar_ultima_liberacao() -> set[tuple[int, int]]:
    if not ULTIMA_LIBERACAO.exists():
        return set()
    with ULTIMA_LIBERACAO.open(encoding="utf-8-sig", newline="") as arquivo:
        return {
            (int(linha["cliente_codigo"]), int(linha["condicao_codigo"]))
            for linha in csv.DictReader(arquivo, delimiter=";")
        }


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


def salvar_csv(caminho: Path, pares: list[tuple[int, int]], detalhes: dict, acao: str) -> None:
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
            linha["acao"] = acao
            escritor.writerow({campo: linha.get(campo, "") for campo in campos})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executar", action="store_true")
    args = parser.parse_args()
    detalhes = carregar_manifesto()
    universo = set(detalhes)
    ultima_liberacao = carregar_ultima_liberacao() & universo
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        existentes_antes = consultar_existentes(cursor, universo)
        remover = sorted(existentes_antes)
        ja_ausentes = sorted(universo - existentes_antes)
        if args.executar and remover:
            for inicio in range(0, len(remover), 5000):
                cursor.executemany(
                    "DELETE FROM CLIFORCONDICAOPAGAMENTO WHERE "
                    "CLIFOR = ? AND CONDICAOPAGAMENTO = ?",
                    remover[inicio:inicio + 5000],
                )
                print(
                    f"REMOVIDOS_PROGRESSO={min(inicio + 5000, len(remover))}/"
                    f"{len(remover)}",
                    flush=True,
                )
            con.commit()
            restantes = consultar_existentes(cursor, universo)
            if restantes:
                raise RuntimeError(
                    f"Validação encontrou {len(restantes)} registros ainda presentes."
                )
        else:
            con.rollback()
        agora = datetime.now().astimezone()
        sufixo = "executada" if args.executar else "previa"
        pasta = PASTA_BASE / f"reversao_etapa_2_{agora:%Y%m%d_%H%M%S}_{sufixo}"
        pasta.mkdir(parents=True, exist_ok=False)
        salvar_csv(
            pasta / "bloqueios_removidos_agora.csv", remover, detalhes,
            "Removido na reversão geral" if args.executar else "Remover na reversão geral",
        )
        salvar_csv(
            pasta / "bloqueios_ja_ausentes.csv", ja_ausentes, detalhes,
            "Já estava ausente antes da reversão geral",
        )
        por_regra_removidos = Counter(
            detalhes[par].get("regra_aplicada", "Sem regra") for par in remover
        )
        por_regra_ausentes = Counter(
            detalhes[par].get("regra_aplicada", "Sem regra") for par in ja_ausentes
        )
        resumo = {
            "gerado_em": agora.isoformat(),
            "executado": args.executar,
            "total_manifesto_etapa_2": len(universo),
            "clientes_manifesto": len({cliente for cliente, _ in universo}),
            "bloqueios_presentes_antes": len(remover),
            "bloqueios_ja_ausentes_antes": len(ja_ausentes),
            "bloqueios_removidos_agora": len(remover) if args.executar else 0,
            "bloqueios_restantes_apos": 0 if args.executar else len(remover),
            "ultima_lista_clientes_pares": len(ultima_liberacao),
            "ultima_lista_ja_ausente": len(ultima_liberacao - existentes_antes),
            "por_regra_removidos": dict(por_regra_removidos),
            "por_regra_ja_ausentes": dict(por_regra_ausentes),
        }
        (pasta / "resumo.json").write_text(
            json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (pasta / "README.md").write_text(
            "# Reversão geral da Etapa 2\n\n"
            f"- Executada: {'SIM' if args.executar else 'NÃO — SOMENTE PRÉVIA'}\n"
            f"- Pares documentados no manifesto: {len(universo):,}\n"
            f"- Clientes documentados: {resumo['clientes_manifesto']:,}\n"
            f"- Bloqueios presentes antes: {len(remover):,}\n"
            f"- Bloqueios já ausentes antes: {len(ja_ausentes):,}\n"
            f"- Bloqueios removidos agora: {resumo['bloqueios_removidos_agora']:,}\n"
            f"- Bloqueios restantes após validação: {resumo['bloqueios_restantes_apos']:,}\n"
            f"- Última lista já ausente: {resumo['ultima_lista_ja_ausente']:,} de "
            f"{len(ultima_liberacao):,}\n",
            encoding="utf-8",
        )
        print(f"PASTA={pasta}")
        for chave, valor in resumo.items():
            if not isinstance(valor, dict):
                print(f"{chave.upper()}={valor}")
        print("POR_REGRA_REMOVER=" + json.dumps(dict(por_regra_removidos), ensure_ascii=False))
        print("POR_REGRA_JA_AUSENTES=" + json.dumps(dict(por_regra_ausentes), ensure_ascii=False))
    except Exception:
        con.rollback()
        raise
    finally:
        cursor.close()
        con.close()


if __name__ == "__main__":
    main()
