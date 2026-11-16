from __future__ import annotations

import argparse
import csv
import io
import zipfile
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from dados import (
    consultar_pagamentos_mais_usados,
    gerar_documentacao_bloqueios_zip,
    planejar_atualizacao_pagamentos,
    subtrair_meses,
)


BASE_DIR = Path(__file__).resolve().parent


def literal_sql(valor: object) -> str:
    if pd.isna(valor):
        return "NULL"
    return str(int(valor))


def gerar_restore_etapa_1(plano: pd.DataFrame, destino: Path) -> int:
    alteracoes = plano[plano["atualizacao_necessaria"]].copy()
    with destino.open("w", encoding="utf-8", newline="\n") as arquivo:
        arquivo.write("SET SQL DIALECT 3;\nSET AUTODDL OFF;\n\n")
        arquivo.write(
            "-- Restaura os padrões capturados antes da Etapa 1.\n"
            "-- Execute somente como rollback da operação documentada neste diretório.\n\n"
        )
        for item in alteracoes.itertuples(index=False):
            arquivo.write(
                "UPDATE CLIFOR SET CONDICAOPAGAMENTO = "
                f"{literal_sql(item.condicao_atual_codigo)}, FORMAPAGAMENTO = "
                f"{literal_sql(item.forma_atual_codigo)} WHERE CODIGO = "
                f"{int(item.cliente_codigo)} AND TIPO = 1;\n"
            )
        arquivo.write("\nCOMMIT;\n")
    return len(alteracoes)


def gerar_restore_etapa_2(documentacao_zip: bytes, destino: Path) -> int:
    total = 0
    with zipfile.ZipFile(io.BytesIO(documentacao_zip)) as compactado:
        with compactado.open("bloqueios_a_inserir.csv") as binario:
            texto = io.TextIOWrapper(binario, encoding="utf-8-sig", newline="")
            leitor = csv.DictReader(texto, delimiter=";")
            with destino.open("w", encoding="utf-8", newline="\n") as arquivo:
                arquivo.write("SET SQL DIALECT 3;\nSET AUTODDL OFF;\n\n")
                arquivo.write(
                    "-- Remove somente os bloqueios que estavam ausentes no snapshot.\n"
                    "-- Execute somente como rollback da Etapa 2 documentada neste diretório.\n\n"
                )
                cliente_atual: int | None = None
                condicoes: list[int] = []

                def gravar_cliente() -> None:
                    if cliente_atual is None or not condicoes:
                        return
                    arquivo.write(
                        "DELETE FROM CLIFORCONDICAOPAGAMENTO WHERE CLIFOR = "
                        f"{cliente_atual} AND CONDICAOPAGAMENTO IN ("
                        + ",".join(map(str, condicoes)) + ");\n"
                    )

                for linha in leitor:
                    cliente = int(linha["cliente_codigo"])
                    condicao = int(linha["condicao_codigo"])
                    if cliente_atual is not None and cliente != cliente_atual:
                        gravar_cliente()
                        condicoes = []
                    cliente_atual = cliente
                    condicoes.append(condicao)
                    total += 1
                gravar_cliente()
                arquivo.write("\nCOMMIT;\n")
    return total


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gera scripts somente de leitura para restaurar as Etapas 1 e 2."
    )
    parser.add_argument("--data-final", type=date.fromisoformat, default=date.today())
    parser.add_argument("--data-inicial", type=date.fromisoformat)
    parser.add_argument("--destino", type=Path)
    args = parser.parse_args()

    data_fim = args.data_final
    data_inicio = args.data_inicial or subtrair_meses(data_fim, 6)
    destino = args.destino or (
        BASE_DIR / f"restore_dados_etapas_1_2_{date.today():%Y%m%d}"
    )
    destino.mkdir(parents=True, exist_ok=True)

    resultado = consultar_pagamentos_mais_usados(data_inicio, data_fim)
    plano_etapa_1 = planejar_atualizacao_pagamentos(resultado)
    nome_data = f"{date.today():%Y%m%d}"
    total_etapa_1 = gerar_restore_etapa_1(
        plano_etapa_1, destino / f"restore_etapa_1_{nome_data}.sql"
    )
    plano_etapa_1.to_csv(
        destino / f"snapshot_etapa_1_{nome_data}.csv",
        sep=";", index=False, encoding="utf-8-sig",
    )

    documentacao_zip, total_documentado = gerar_documentacao_bloqueios_zip(resultado)
    (destino / f"manifesto_etapa_2_{nome_data}.zip").write_bytes(documentacao_zip)
    total_etapa_2 = gerar_restore_etapa_2(
        documentacao_zip, destino / f"restore_etapa_2_{nome_data}.sql"
    )
    if total_etapa_2 != total_documentado:
        raise RuntimeError("Totais divergentes na geração do restore da Etapa 2.")

    gerado_em = datetime.now().astimezone()
    total_etapa_1_formatado = f"{total_etapa_1:,}".replace(",", ".")
    total_etapa_2_formatado = f"{total_etapa_2:,}".replace(",", ".")
    readme = f"""# Snapshot de restauração das Etapas 1 e 2

- Capturado em: {gerado_em:%d/%m/%Y %H:%M:%S %z}
- Período analisado: {data_inicio:%d/%m/%Y} a {data_fim:%d/%m/%Y}
- Clientes com restauração prevista na Etapa 1: {total_etapa_1_formatado}
- Pares cliente × condição previstos na restauração da Etapa 2: {total_etapa_2_formatado}

## Arquivos

- `restore_etapa_1_{nome_data}.sql`: devolve condição e forma padrão aos valores capturados antes da execução.
- `snapshot_etapa_1_{nome_data}.csv`: manifesto de conferência dos valores atuais e novos da Etapa 1.
- `restore_etapa_2_{nome_data}.sql`: remove somente os bloqueios ausentes no momento deste snapshot e elegíveis para a Etapa 2.
- `manifesto_etapa_2_{nome_data}.zip`: CSV detalhado dos pares documentados e descrição das regras.

## Uso seguro

1. Valide primeiro em ambiente de homologação e mantenha backup nativo do Firebird.
2. Estes scripts não são backup geral do banco; restauram apenas o escopo das prévias registradas.
3. Para desfazer uma execução completa, rode primeiro o restore da Etapa 2 e depois o restore da Etapa 1.
4. Use-os somente para reverter a execução baseada neste mesmo snapshot. Alterações legítimas feitas posteriormente podem ser sobrescritas ou removidas.
5. Revise os manifestos e execute com usuário autorizado, janela de manutenção e acompanhamento do DBA.
"""
    (destino / "README.md").write_text(readme, encoding="utf-8")
    print(f"Destino: {destino.resolve()}")
    print(f"Etapa 1: {total_etapa_1} clientes")
    print(f"Etapa 2: {total_etapa_2} pares cliente x condição")


if __name__ == "__main__":
    main()
