from __future__ import annotations

import sys

from conexoes import cliente_firebird


cliente = int(sys.argv[1])
con = cliente_firebird("WIN1252")
cursor = con.cursor()
try:
    cursor.execute(
        "SELECT CODIGO, NOME, TIPO, CNPJ, TIPOESTABELECIMENTO "
        "FROM CLIFOR WHERE CODIGO = ?",
        [cliente],
    )
    print("CLIFOR", cursor.fetchall())
    cursor.execute(
        "SELECT FUNCIONARIO FROM FUNCIONARIOCLIFOR WHERE CLIFOR = ?",
        [cliente],
    )
    print("VENDEDORES", [item[0] for item in cursor.fetchall()])
    cursor.execute(
        "SELECT COUNT(*) FROM CLIFORCONDICAOPAGAMENTO WHERE CLIFOR = ?",
        [cliente],
    )
    print("BLOQUEIOS_TOTAL", cursor.fetchone()[0])
    cursor.execute(
        "SELECT ccp.CONDICAOPAGAMENTO, cp.NOME, cp.ATIVO "
        "FROM CLIFORCONDICAOPAGAMENTO ccp "
        "LEFT JOIN CONDICAOPAGAMENTO cp ON cp.CODIGO = ccp.CONDICAOPAGAMENTO "
        "WHERE ccp.CLIFOR = ? ORDER BY ccp.CONDICAOPAGAMENTO ROWS 20",
        [cliente],
    )
    print("AMOSTRA", cursor.fetchall())
finally:
    cursor.close()
    con.close()
