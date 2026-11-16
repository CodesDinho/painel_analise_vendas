from __future__ import annotations

import hashlib
import json
import secrets
import string
from pathlib import Path


ARQUIVO = Path(__file__).resolve().parent / "usuarios_faturamento.json"
USERNAME = "zeneide"
ITERACOES = 600_000


def gerar_senha() -> str:
    alfabeto = string.ascii_letters + string.digits + "@#%+-_"
    while True:
        senha = "".join(secrets.choice(alfabeto) for _ in range(16))
        if (
            any(c.islower() for c in senha)
            and any(c.isupper() for c in senha)
            and any(c.isdigit() for c in senha)
            and any(c in "@#%+-_" for c in senha)
        ):
            return senha


def main() -> None:
    senha = gerar_senha()
    salt = secrets.token_bytes(32)
    senha_hash = hashlib.pbkdf2_hmac(
        "sha256", senha.encode("utf-8"), salt, ITERACOES
    )
    dados = {"usuarios": [{
        "username": USERNAME,
        "nome": "Zeneide — Faturamento",
        "perfil": "Faturamento",
        "ativo": True,
        "salt": salt.hex(),
        "senha_hash": senha_hash.hex(),
        "iteracoes": ITERACOES,
    }]}
    temporario = ARQUIVO.with_suffix(".tmp")
    temporario.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporario.replace(ARQUIVO)
    print(f"USUARIO={USERNAME}")
    print(f"SENHA_INICIAL={senha}")


if __name__ == "__main__":
    main()
