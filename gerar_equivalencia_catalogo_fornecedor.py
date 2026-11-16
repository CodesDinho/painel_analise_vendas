from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

from conexoes import cliente_firebird


ARQUIVO_ENTRADA = Path(
    r"C:\Users\roberson.souza\.codex\attachments\73886cb9-47f9-45d3-95d1-a92231e30438\pasted-text.txt"
)
ARQUIVO_SAIDA = Path("equivalencia_produtos_fornecedor_20260818.xlsx")
PALAVRAS_GENERICAS = {
    "AGUA", "BEBIDA", "COM", "SEM", "GARRAFA", "LATA", "PET", "VIDRO",
    "PRODUTO", "VARIOS", "SABOR", "SABORES", "TRADICIONAL", "CAIXA",
}


def normalizar(valor: object) -> str:
    texto = "".join(
        c for c in unicodedata.normalize("NFKD", str(valor or ""))
        if not unicodedata.combining(c)
    ).upper()
    texto = texto.replace("&", " E ").replace("º", " ")
    return " ".join(re.findall(r"[A-Z0-9]+", texto))


def extrair_volume_ml(valor: object) -> int | None:
    texto = normalizar(valor).replace(" ", "")
    encontrados = re.findall(r"(\d+(?:[.,]\d+)?)\s*(ML|L)\b", str(valor).upper())
    if not encontrados:
        encontrados = re.findall(r"(\d+(?:[.,]\d+)?)(ML|L)", texto)
    if not encontrados:
        return None
    numero, unidade = encontrados[0]
    quantidade = float(numero.replace(",", "."))
    return round(quantidade * 1000 if unidade == "L" else quantidade)


def extrair_multiplicador(valor: object) -> int | None:
    texto = normalizar(valor)
    encontrados = re.findall(r"(?:X|C\s*\d*|CX)\s*(\d{1,3})\b", texto)
    if encontrados:
        return int(encontrados[-1])
    original = str(valor).upper()
    encontrado = re.search(r"X\s*(\d{1,3})\b", original)
    return int(encontrado.group(1)) if encontrado else None


def extrair_material(valor: object) -> str | None:
    tokens = set(normalizar(valor).split())
    if "LATA" in tokens:
        return "LATA"
    if "PET" in tokens:
        return "PET"
    if "VIDRO" in tokens or "GRF" in tokens or "GARRAFA" in tokens:
        return "VIDRO"
    return None


def tokens_nome(valor: object) -> set[str]:
    return {
        token for token in normalizar(valor).split()
        if len(token) > 2 and not token.isdigit() and token not in PALAVRAS_GENERICAS
    }


def pontuar(nome_externo: str, embalagem: str, nome_interno: str) -> tuple[float, float, float, float]:
    ext = normalizar(nome_externo)
    interno = normalizar(nome_interno)
    a, b = tokens_nome(ext), tokens_nome(interno)
    if a and b:
        cobertura = len(a & b) / len(a)
        precisao = len(a & b) / len(b)
        token_score = 100 * (0.75 * cobertura + 0.25 * precisao)
    else:
        token_score = 0.0
    sequencia = 100 * SequenceMatcher(None, ext, interno).ratio()
    nome_score = max(token_score, 0.65 * token_score + 0.35 * sequencia)
    volume_ext = extrair_volume_ml(embalagem)
    volume_int = extrair_volume_ml(nome_interno)
    volume_score = 50.0 if volume_ext is None or volume_int is None else (100.0 if volume_ext == volume_int else 0.0)
    pack_ext = extrair_multiplicador(embalagem)
    pack_int = extrair_multiplicador(nome_interno)
    material_ext = extrair_material(f"{nome_externo} {embalagem}")
    material_int = extrair_material(nome_interno)
    componentes_embalagem = []
    if pack_ext is not None and pack_int is not None:
        componentes_embalagem.append(100.0 if pack_ext == pack_int else 20.0)
    if material_ext is not None and material_int is not None:
        componentes_embalagem.append(100.0 if material_ext == material_int else 0.0)
    pack_score = sum(componentes_embalagem) / len(componentes_embalagem) if componentes_embalagem else 50.0
    total = 0.75 * nome_score + 0.20 * volume_score + 0.05 * pack_score
    return round(total, 1), round(nome_score, 1), volume_score, pack_score


def carregar_produtos() -> pd.DataFrame:
    con = cliente_firebird("WIN1252")
    cursor = con.cursor()
    try:
        cursor.execute("""
            SELECT p.CODIGO, p.NOME, p.CLIFOR, f.NOME
            FROM PRODUTO p
            LEFT JOIN CLIFOR f ON f.CODIGO = p.CLIFOR
            ORDER BY p.CODIGO
        """)
        return pd.DataFrame(cursor.fetchall(), columns=[
            "nosso_codigo", "nosso_produto", "nosso_fornecedor_codigo",
            "nosso_fornecedor_nome",
        ])
    finally:
        cursor.close()
        con.close()


def executar() -> Path:
    externos = pd.read_csv(ARQUIVO_ENTRADA, sep="\t", dtype=str).fillna("")
    externos.insert(0, "linha_fornecedor", range(1, len(externos) + 1))
    internos = carregar_produtos()
    indice: dict[str, set[int]] = defaultdict(set)
    for indice_linha, nome in internos["nosso_produto"].items():
        for token in tokens_nome(nome):
            indice[token].add(indice_linha)

    candidatos_saida: list[dict] = []
    consolidados: list[dict] = []
    for externo in externos.itertuples(index=False):
        tokens = tokens_nome(externo.Produto)
        candidatos = set().union(*(indice[token] for token in tokens)) if tokens else set()
        if not candidatos:
            candidatos = set(internos.index)
        avaliados = []
        for idx in candidatos:
            interno = internos.loc[idx]
            scores = pontuar(externo.Produto, externo.Embalagem, interno["nosso_produto"])
            avaliados.append((scores[0], scores, interno))
        avaliados.sort(key=lambda item: (-item[0], int(item[2]["nosso_codigo"])))
        top = avaliados[:5]
        melhor = top[0] if top else None
        for posicao, (_, scores, interno) in enumerate(top, 1):
            percentual, nome_score, volume_score, pack_score = scores
            candidatos_saida.append({
                "linha_fornecedor": externo.linha_fornecedor,
                "categoria_fornecedor": externo.Categoria,
                "produto_fornecedor": externo.Produto,
                "embalagem_fornecedor": externo.Embalagem,
                "posicao_candidato": posicao,
                **interno.to_dict(),
                "equivalencia_percentual": percentual,
                "similaridade_nome_percentual": nome_score,
                "equivalencia_volume_percentual": volume_score,
                "equivalencia_multiplicador_percentual": pack_score,
            })
        if melhor:
            percentual, scores, interno = melhor
            volume_ext = extrair_volume_ml(externo.Embalagem)
            volume_int = extrair_volume_ml(interno["nosso_produto"])
            volume_confere = volume_ext is None or volume_int is None or volume_ext == volume_int
            material_ext = extrair_material(f"{externo.Produto} {externo.Embalagem}")
            material_int = extrair_material(interno["nosso_produto"])
            material_confere = (
                material_ext is None or material_int is None or material_ext == material_int
            )
            classificacao = (
                "MATCH TOTAL"
                if percentual >= 90 and scores[1] >= 85 and volume_confere and material_confere
                else "MATCH PARCIAL" if percentual >= 65
                else "SEM MATCH CONFIAVEL"
            )
            consolidados.append({
                "linha_fornecedor": externo.linha_fornecedor,
                "categoria_fornecedor": externo.Categoria,
                "produto_fornecedor": externo.Produto,
                "embalagem_fornecedor": externo.Embalagem,
                **interno.to_dict(),
                "equivalencia_percentual": percentual,
                "similaridade_nome_percentual": scores[1],
                "equivalencia_volume_percentual": scores[2],
                "equivalencia_multiplicador_percentual": scores[3],
                "resultado_match": classificacao,
                "requer_revisao": "NÃO" if classificacao == "MATCH TOTAL" else "SIM",
            })

    resumo = pd.DataFrame(consolidados)
    candidatos_df = pd.DataFrame(candidatos_saida)
    criterios = pd.DataFrame([
        ["Fonte externa", "Produto e Embalagem foram preservados em campos separados."],
        ["Nome comparado", "Nome externo normalizado contra o nome completo do produto interno."],
        ["Peso nome", "75%"], ["Peso volume", "20%"],
        ["Peso multiplicador", "5%"],
        ["Match total", ">= 90% e volume sem divergência identificada"],
        ["Match parcial", ">= 65%"],
        ["Sem match confiável", "< 65%"],
        ["Atenção", "Descrições externas com vários sabores podem corresponder a vários SKUs; confira a aba Candidatos."],
    ], columns=["criterio", "regra"])
    with pd.ExcelWriter(ARQUIVO_SAIDA, engine="openpyxl") as writer:
        resumo.to_excel(writer, sheet_name="Melhor equivalencia", index=False)
        candidatos_df.to_excel(writer, sheet_name="Candidatos", index=False)
        externos.to_excel(writer, sheet_name="Lista original", index=False)
        criterios.to_excel(writer, sheet_name="Critérios", index=False)
        for planilha in writer.sheets.values():
            planilha.freeze_panes = "A2"
            planilha.auto_filter.ref = planilha.dimensions
            for coluna in planilha.columns:
                largura = max((len(str(c.value or "")) for c in coluna), default=10)
                planilha.column_dimensions[coluna[0].column_letter].width = min(largura + 2, 55)
    return ARQUIVO_SAIDA


if __name__ == "__main__":
    caminho = executar()
    print(caminho.resolve())
