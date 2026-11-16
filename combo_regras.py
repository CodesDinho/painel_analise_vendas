from __future__ import annotations

import re
import unicodedata


FILIAIS_PR = {3, 4, 5, 7}
FILIAIS_SC = {6, 8}
CLASSIFICACOES_DORMENTES = {"DORMENTE POSITIVACAO", "DORMENTE VOLUME"}
ESTADOS_COM_COMBOS = ("PR", "SC", "RS", "SP")
PADRAO_ESTADO = rf"(?:{'|'.join(ESTADOS_COM_COMBOS)})"


def normalizar(valor: object) -> str:
    texto = "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", str(valor or ""))
        if not unicodedata.combining(caractere)
    ).upper()
    return " ".join(texto.split())


def estado_final(nome: object) -> str | None:
    encontrado = re.search(rf"(?:^|\s)({PADRAO_ESTADO})$", normalizar(nome))
    return encontrado.group(1) if encontrado else None


def exige_vin_esp(evidencias: list[object]) -> bool:
    termos = re.compile(
        r"(?:^|[^A-Z0-9])(VINHO|VINHOS|ESPUMANTE|ESPUMANTES|AGUA|XAROPE|XAROPES)(?:[^A-Z0-9]|$)"
    )
    return any(termos.search(normalizar(item)) for item in evidencias)


def validar_titulo_combo(
    nome: object, classificacao: object, vin_esp: bool = False
) -> tuple[bool, str]:
    titulo = normalizar(nome)
    classe = normalizar(classificacao)
    falhas: list[str] = []
    estado = estado_final(titulo)

    if not estado:
        falhas.append("Estado PR/SC/RS/SP deve estar no final")
    if classe == "REDE" and not titulo.startswith("REDE "):
        falhas.append("REDE deve estar no início")
    if classe == "MANUTENCAO" and not re.search(
        rf"(?:^|\s)M\s+(?:PR\s+SC|{PADRAO_ESTADO})$", titulo
    ):
        falhas.append("Manutenção deve terminar em M + estado")
    if classe == "DORMENTE POSITIVACAO" and "D POSITIVACAO" not in titulo:
        falhas.append("Deve conter D POSITIVACAO")
    if classe == "DORMENTE VOLUME" and "D VOLUME" not in titulo:
        falhas.append("Deve conter D VOLUME")
    if vin_esp and not re.search(
        rf"(?:^|\s)VIN/ESP\s+{PADRAO_ESTADO}$", titulo
    ):
        falhas.append("VIN/ESP deve ficar antes do estado")
    return not falhas, "OK" if not falhas else "; ".join(falhas)
