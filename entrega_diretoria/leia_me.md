# Entrega à Diretoria — auditoria e edição de combos

Pacote consolidado para apresentação, validação e repasse operacional.

## Ordem recomendada de leitura

1. [`resposta_validacao_casos_diretoria.md`](resposta_validacao_casos_diretoria.md): resumo executivo,
   conclusões e confirmações comerciais ainda necessárias.
2. [`log_tecnico_validacao_casos_diretoria.md`](log_tecnico_validacao_casos_diretoria.md): evidências
   completas da auditoria que originou a resposta.
3. [`guia_diretoria_auditoria_edicao_combos.md`](guia_diretoria_auditoria_edicao_combos.md): uso pelo
   Slack, integração via API, segurança, exemplos e testes.
4. [`contrato_api_auditoria_combos.md`](contrato_api_auditoria_combos.md): contrato técnico da API
   interna e seus limites.

## Decisão de arquitetura

- Auditoria HTTP: API interna, autenticada e somente leitura.
- Auditoria para usuários: `/combos-auditar` no Slack.
- Edição: exclusivamente `/combos-editar` no Slack, respeitando validações e aprovações.
- Não existe API HTTP de escrita no ERP.

## Segurança

Este pacote não contém tokens, senhas ou credenciais. Não anexar `.env`, `combo_config.ini`,
credenciais do Firebird ou tokens do Portainer/GitHub ao repasse.

O log técnico representa uma fotografia da auditoria realizada. Como os cadastros do ERP podem
mudar, executar nova auditoria antes de decidir ou aplicar uma correção.
