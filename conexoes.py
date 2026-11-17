from __future__ import annotations

import configparser
import base64
import ctypes
import os
from pathlib import Path
from ctypes import wintypes


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ID = os.getenv("ANALISE_VENDAS_GCP_PROJECT", "dinho-dw")


def localizar_credencial() -> Path | None:
    candidatos = [
        os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
        BASE_DIR / "credentials" / "credential.json",
        BASE_DIR.parent / "Painel_vendas" / "credentials" / "credential.json",
        BASE_DIR.parent / "Painel_vendas" / "config" / "credentials" / "credential.json",
        BASE_DIR.parent / "credentials" / "credential.json",
        BASE_DIR.parent.parent / "rel_controladoria" / "credentials" / "credential.json",
    ]
    # No container BASE_DIR e /app e possui poucos ancestrais. O fallback legado
    # abaixo existe apenas no checkout Windows e nao pode indexar parents[2]
    # incondicionalmente.
    if len(BASE_DIR.parents) > 2:
        candidatos.append(
            BASE_DIR.parents[2]
            / "_OLDS"
            / "rel_controladoria"
            / "credentials"
            / "credential.json"
        )
    return next((Path(p) for p in candidatos if p and Path(p).exists()), None)


def cliente_bigquery():
    from google.cloud import bigquery

    credencial = localizar_credencial()
    if credencial:
        from google.oauth2 import service_account

        credentials = service_account.Credentials.from_service_account_file(
            str(credencial), scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        return bigquery.Client(project=PROJECT_ID, credentials=credentials)
    return bigquery.Client(project=PROJECT_ID)


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _descriptografar_dpapi(texto: str) -> str:
    dados = base64.b64decode(texto.encode("ascii"))
    buffer = ctypes.create_string_buffer(dados)
    entrada = _DATA_BLOB(len(dados), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    saida = _DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(entrada), None, None, None, None, 0, ctypes.byref(saida)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(saida.pbData, saida.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(saida.pbData)


def _ler_config_firebird() -> configparser.ConfigParser:
    informado = os.getenv("ANALISE_VENDAS_CONFIG_FIREBIRD", "").strip()
    candidatos = ([Path(informado)] if informado else []) + [
        BASE_DIR / "config.ini.enc", BASE_DIR / "config.ini",
        BASE_DIR.parent / "Painel_vendas" / "config" / "config.ini.enc",
        BASE_DIR.parent / "Painel_vendas" / "config" / "config.ini",
        BASE_DIR.parent / "config" / "config.ini.enc", BASE_DIR.parent / "config" / "config.ini",
    ]
    caminho = next((p for p in candidatos if p.exists()), None)
    if not caminho:
        raise FileNotFoundError("Configure config.ini(.enc) ou ANALISE_VENDAS_CONFIG_FIREBIRD.")
    config = configparser.ConfigParser()
    if caminho.suffix.lower() == ".enc":
        config.read_string(_descriptografar_dpapi(caminho.read_text(encoding="ascii").strip()))
    elif not config.read(caminho, encoding="utf-8"):
        raise FileNotFoundError(f"Não foi possível ler {caminho}.")
    return config


def cliente_firebird(charset: str | None = None):
    import fdb

    host = os.getenv("ANALISE_VENDAS_FIREBIRD_HOST", "").strip()
    database = os.getenv("ANALISE_VENDAS_FIREBIRD_DATABASE", "").strip()
    user = os.getenv("ANALISE_VENDAS_FIREBIRD_USER", "").strip()
    password = os.getenv("ANALISE_VENDAS_FIREBIRD_PASSWORD", "")
    if all((host, database, user, password)):
        return fdb.connect(
            dsn=f"{host}:{database}", user=user, password=password,
            charset=charset or os.getenv("ANALISE_VENDAS_FIREBIRD_CHARSET", "UTF8"),
        )

    config = _ler_config_firebird()
    ambiente = config.get("ambiente", "ativo", fallback="producao").strip().lower()
    secao = f"firebird_{ambiente}" if f"firebird_{ambiente}" in config else "firebird"
    fb = config[secao]
    return fdb.connect(
        dsn=f"{fb['host']}:{fb['database']}",
        user=fb["user"], password=fb["password"],
        charset=charset or fb.get("charset", "UTF8")
    )
