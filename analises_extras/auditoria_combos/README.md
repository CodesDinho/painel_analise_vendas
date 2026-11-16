# Auditoria de combos

Tela somente leitura que consome a API interna do projeto `slack_combos`.

## Configuração

- `ANALISE_VENDAS_COMBO_AUDIT_API_URL`: URL base da API, sem barra final.
- `ANALISE_VENDAS_COMBO_AUDIT_API_TOKEN`: token interno, quando exigido.
- `ANALISE_VENDAS_COMBO_AUDIT_API_TIMEOUT`: timeout em segundos; padrão `30`.
- `ANALISE_VENDAS_COMBO_AUDIT_API_AUTH_HEADER`: cabeçalho; padrão `Authorization`.
- `ANALISE_VENDAS_COMBO_AUDIT_API_AUTH_PREFIX`: prefixo; padrão `Bearer`.

Endpoints esperados, schema `1.0`:

- `GET /api/combo-audit`
- `GET /api/combo-audit/{codigo_combo}`
- `GET /api/combo-rules/version`

O módulo não consulta o Firebird e não oferece operações de gravação. Quando a API
falha, pode exibir a última resposta válida salva em `cache/auditoria_combos_api.json`,
sempre identificada como possivelmente desatualizada.
