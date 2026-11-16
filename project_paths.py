from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / "docs"
REGRAS_DIR = DOCS_DIR / "regras"
DADOS_OPERACIONAIS_DIR = BASE_DIR / "dados_operacionais"
SNAPSHOTS_DIR = DADOS_OPERACIONAIS_DIR / "snapshots"

DOCUMENTACAO_REGRAS_COMBOS = REGRAS_DIR / "DOCUMENTACAO_REGRAS_COMBOS.docx"
POP_LIBERACAO_COMBOS = REGRAS_DIR / "POP_Liberacao_de_Combos_SGQ.docx"
SNAPSHOT_RESTORE_ETAPAS = SNAPSHOTS_DIR / "restore_dados_etapas_1_2_20260831"
