from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ARQUIVO_USUARIOS_FATURAMENTO = Path(
    os.getenv("ANALISE_VENDAS_USUARIOS_FATURAMENTO_PATH", BASE_DIR / "usuarios_faturamento.json")
)


def _arquivo_usuarios() -> Path | None:
    informado = os.getenv("ANALISE_VENDAS_USUARIOS_PATH", "").strip()
    if informado:
        caminho = Path(informado)
        return caminho if caminho.exists() else None
    proprio = BASE_DIR / "usuarios.json"
    compartilhados = [
        BASE_DIR.parent / "Painel_vendas" / "config" / "usuarios.json",
        BASE_DIR.parent / "config" / "usuarios.json",
    ]
    return proprio if proprio.exists() else next((p for p in compartilhados if p.exists()), None)


def autenticar(username: str, senha: str) -> dict | None:
    caminho = _arquivo_usuarios()
    caminhos = [item for item in (caminho, ARQUIVO_USUARIOS_FATURAMENTO) if item and item.exists()]
    if not caminhos:
        return None
    usuarios = []
    for arquivo in caminhos:
        usuarios.extend(
            json.loads(arquivo.read_text(encoding="utf-8")).get("usuarios", [])
        )
    usuario = next((u for u in usuarios if u.get("username", "").lower() == username.strip().lower() and u.get("ativo")), None)
    if not usuario:
        return None
    calculado = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(usuario["salt"]), int(usuario.get("iteracoes", 600_000)))
    if not hmac.compare_digest(calculado, bytes.fromhex(usuario["senha_hash"])):
        return None
    return {"username": usuario["username"], "nome": usuario.get("nome", usuario["username"]), "perfil": usuario.get("perfil", "Usuario")}


def pode_criar_combo(usuario: dict | None) -> bool:
    if not usuario:
        return False
    configurados = {
        item.strip().lower()
        for item in os.getenv("ANALISE_VENDAS_USUARIOS_CRIAR_COMBO", "").split(",")
        if item.strip()
    }
    username = str(usuario.get("username", "")).strip().lower()
    if configurados:
        return username in configurados
    perfis = {"administrador", "admin", "ti", "gerente comercial"}
    return str(usuario.get("perfil", "")).strip().lower() in perfis
