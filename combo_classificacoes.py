from __future__ import annotations

import json
import os
import re
import threading
import unicodedata
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "dados_locais"
ARQUIVO_CLASSIFICACOES = DATA_DIR / "combo_classificacoes.json"
ARQUIVO_AUDITORIA = DATA_DIR / "combo_classificacoes_auditoria.jsonl"
CLASSIFICACOES = [
    "Rede", "Manutenção", "Tabela", "MIX", "Dormente positivação", "Dormente volume",
    "Não classificado",
]
_LOCK = threading.RLock()


def _sem_acentos(valor: str) -> str:
    return "".join(
        caractere for caractere in unicodedata.normalize("NFKD", valor or "")
        if not unicodedata.combining(caractere)
    ).upper()


def sugerir_classificacao(nome: str) -> str:
    normalizado = " ".join(_sem_acentos(nome).split())
    if "D POSITIVACAO" in normalizado or "D POSITICAVAO" in normalizado:
        return "Dormente positivação"
    if "D VOLUME" in normalizado:
        return "Dormente volume"
    if re.search(r"(?:^|\s)M(?:\s|$)", normalizado):
        return "Manutenção"
    if "MIX" in normalizado:
        return "MIX"
    if re.search(r"(?:^|\s)T$", normalizado):
        return "Tabela"
    if "REDE" in normalizado:
        return "Rede"
    return "Não classificado"


def carregar_classificacoes(caminho: Path = ARQUIVO_CLASSIFICACOES) -> dict:
    if not caminho.exists():
        return {}
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"Arquivo de classificações inválido: {exc}") from exc
    if not isinstance(dados, dict):
        return {}
    for registro in dados.values():
        if registro.get("classificacao") == "Classificação":
            registro["classificacao"] = "Manutenção"
        if registro.get("classificacao") not in CLASSIFICACOES:
            registro["classificacao"] = "Não classificado"
    return dados


def _gravar_json_atomico(caminho: Path, dados: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    with temporario.open("w", encoding="utf-8", newline="\n") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2, sort_keys=True)
        arquivo.flush()
        os.fsync(arquivo.fileno())
    temporario.replace(caminho)


def salvar_classificacao(
    codigo_combo: int,
    classificacao: str,
    usuario: str,
    caminho: Path = ARQUIVO_CLASSIFICACOES,
    auditoria: Path = ARQUIVO_AUDITORIA,
    agora: datetime | None = None,
) -> dict:
    if classificacao not in CLASSIFICACOES:
        raise ValueError("Classificação inválida.")
    agora = agora or datetime.now().astimezone()
    with _LOCK:
        dados = carregar_classificacoes(caminho)
        chave = str(int(codigo_combo))
        anterior = dados.get(chave, {}).get("classificacao")
        registro = {
            "classificacao": classificacao,
            "atualizado_em": agora.isoformat(),
            "atualizado_por": usuario,
        }
        dados[chave] = registro
        _gravar_json_atomico(caminho, dados)
        auditoria.parent.mkdir(parents=True, exist_ok=True)
        evento = {
            "codigo_combo": int(codigo_combo),
            "valor_anterior": anterior,
            "valor_novo": classificacao,
            "usuario": usuario,
            "data_hora": agora.isoformat(),
        }
        with auditoria.open("a", encoding="utf-8", newline="\n") as arquivo:
            arquivo.write(json.dumps(evento, ensure_ascii=False) + "\n")
            arquivo.flush()
            os.fsync(arquivo.fileno())
    return registro


def classificar_combos(combos, classificacoes: dict | None = None):
    resultado = combos.copy()
    classificacoes = classificacoes if classificacoes is not None else carregar_classificacoes()
    valores, origens = [], []
    for linha in resultado.itertuples(index=False):
        salvo = classificacoes.get(str(int(linha.combo)))
        if salvo:
            valores.append(salvo.get("classificacao", "Não classificado"))
            origens.append("Editada")
        else:
            valores.append(sugerir_classificacao(str(linha.nome or "")))
            origens.append("Sugestão automática")
    resultado["classificacao"] = valores
    resultado["origem_classificacao"] = origens
    return resultado
