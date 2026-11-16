# Instrução para evolução do Painel de Análise de Vendas — auditoria de combos

## Contexto

O `Painel_analise_vendas` já é utilizado para geração de dados de clientes, análises comerciais e
apoio à criação de combos. O projeto `slack_combos`, por sua vez, já possui o fluxo operacional de
consulta, validação, aprovação e alteração de combos no ERP.

O `slack_combos` foi complementado com o comando `/combos-auditar`, que consulta o Firebird em modo
somente leitura e produz resultados estruturados com severidade, regra, mensagem, evidências e ação
recomendada.

O objetivo da próxima etapa é homologar a API interna já implementada no `slack_combos` e, depois,
disponibilizar esses resultados no Painel sem copiar regras entre os projetos e sem permitir
alterações diretas no ERP fora do fluxo aprovado no Slack.

## Responsabilidade de cada projeto

### `slack_combos`

- Ser a fonte oficial das regras de validação de combos.
- Consultar o Firebird e executar a auditoria.
- Classificar resultados em erro, conflito, alerta ou informativo.
- Informar evidências e ações recomendadas.
- Receber solicitações e controlar aprovações.
- Executar alterações autorizadas de forma transacional.
- Registrar solicitante, aprovador, decisão e resultado.
- Disponibilizar a API interna, versionada e somente leitura já implementada, após configuração segura
  e homologação.
- Continuar sendo o único caminho para correções e alterações automáticas no ERP.

### `Painel_analise_vendas`

- Continuar responsável pelas análises de vendas e clientes já existentes.
- Continuar apoiando a identificação de clientes, oportunidades e dados necessários à criação de
  combos.
- Receber os resultados estruturados do `slack_combos` por API interna.
- Criar a tela **Auditoria de combos**.
- Permitir filtros por combo, produto, filial, tipo, regra, severidade e vigência.
- Exibir evidências, referências comerciais e ações recomendadas.
- Permitir exportação para Excel.
- Exibir a versão das regras e a data/hora da auditoria.
- Informar claramente quando os dados forem provenientes de cache ou estiverem desatualizados.
- Direcionar qualquer solicitação de correção para o fluxo do Slack.

### Aplicativo dos vendedores

- Não deve receber regras copiadas ou reimplementadas manualmente.
- Poderá consumir futuramente um contrato homologado de consulta/validação.
- A integração dependerá de aprovação da Direção, definição do comportamento esperado no T1 e
  homologação prévia das regras no Slack e no Painel.

## O que não deve ser feito no Painel

- Não copiar `combo_rules.py`, `combo_repository.py` ou consultas internas do bot.
- Não importar arquivos diretamente do checkout de `slack_combos`.
- Não acessar o Firebird para recriar as mesmas regras em outro código.
- Não executar `INSERT`, `UPDATE` ou `DELETE` de combos.
- Não criar botão de correção direta no ERP.
- Não definir automaticamente preço, prioridade, brinde ou quantidade quando faltar decisão
  comercial.

## Integração proposta

A integração utilizará a API interna do `slack_combos`, somente leitura. O contrato versão `1.0` já
está implementado e testado, mas permanece desabilitado até receber token exclusivo e ser homologado
em rede Docker privada. A tela definitiva do Painel deve começar somente depois dessa homologação.

Endpoints iniciais sugeridos:

```text
GET /api/combo-audit
GET /api/combo-audit/{codigo_combo}
GET /api/combo-rules/version
```

O contrato deverá prever:

- autenticação entre os serviços;
- versão do schema;
- filtros e paginação;
- timeout e erros previsíveis;
- data/hora da auditoria;
- versão das regras;
- indicação de dados em cache;
- ausência de qualquer endpoint de gravação.

O Painel já implementou a tela e o cliente inicial. O repasse incremental com a API real, paginação,
tratamento de erros e fluxo seguro de correção está em
`REPASSE_ATUALIZACAO_PAINEL_API_IMPLEMENTADA.md`.

Exemplo resumido de resultado:

```json
{
  "schema_version": "1.0",
  "combo": 240034782,
  "status": "INFORMATIVO",
  "regra": "REFERENCIA_PRECO_NAO_DETERMINADA",
  "mensagem": "Não foi identificada referência aprovada para validar o preço.",
  "acao_recomendada": "Confirmar tabela ou valor comercial aprovado pela Diretoria/Gerência.",
  "evidencias": {},
  "data_analise": "2026-11-16"
}
```

## Tela sugerida no Painel

Nome da tela: **Auditoria de combos**.

Indicadores:

- combos analisados;
- erros;
- conflitos;
- alertas;
- informativos;
- combos sem pendências.

Tabela principal:

- severidade;
- código e nome do combo;
- regra;
- produtos envolvidos;
- combo conflitante;
- filial e público;
- valores e referências, quando comprovados;
- mensagem;
- ação recomendada;
- data da auditoria.

## Ordem recomendada

1. Homologar com a Direção/Gerência as regras e pendências já identificadas pelo `/combos-auditar`.
2. Configurar token exclusivo e rede Docker privada para a API já implementada.
3. Homologar o contrato real, autenticação, exemplos e erros documentados em
   `CONTRATO_API_AUDITORIA_COMBOS.md`.
4. Testar a API com os casos já auditados.
5. Implementar no Painel a tela de leitura, filtros e exportação.
6. Validar comportamento de indisponibilidade e cache.
7. Homologar a tela com usuários responsáveis.
8. Somente depois avaliar integração com o aplicativo dos vendedores.

## Critério de aceite

A evolução estará pronta quando o Painel exibir os mesmos resultados produzidos pelo
`/combos-auditar`, sem duplicar regras, sem acesso de gravação ao ERP e com direcionamento claro das
correções para o fluxo de aprovação do Slack.
