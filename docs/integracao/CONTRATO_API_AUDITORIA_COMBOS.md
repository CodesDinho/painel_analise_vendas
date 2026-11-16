# Contrato da API interna de auditoria de combos

Status: implementada no `slack_combos`, desabilitada por padrão até configuração e homologação.  
Schema: `1.0`  
Regras: `5.1`

## Segurança e ativação

A API somente inicia quando `COMBO_AUDIT_API_TOKEN` possui valor. Sem o token, o bot continua
funcionando e registra que a API está desabilitada.

O Compose usa apenas `expose: 8080`; não existe publicação da porta no host. O `slack-combos` ingressa
na rede privada nomeada `combo-audit-internal`. Para consumir a API, o Painel deverá ingressar nessa
mesma rede como externa. Não deve ser criado `ports: 8080:8080` nem acesso público.

Configurações:

```text
COMBO_AUDIT_API_TOKEN=<segredo forte e exclusivo>
COMBO_AUDIT_API_HOST=0.0.0.0
COMBO_AUDIT_API_PORT=8080
COMBO_AUDIT_API_TIMEOUT_SECONDS=45
```

O token deve ser configurado como secret no ambiente de implantação e enviado em:

```text
Authorization: Bearer <token>
```

Nunca registrar, enviar no Slack ou versionar esse token.
O serviço recusa ativação com token menor que 32 caracteres.

## Endpoints

### Versão das regras

```http
GET /api/combo-rules/version
```

Retorna versão do schema, versão das regras e horário da última auditoria realizada pela API.

### Auditoria individual

```http
GET /api/combo-audit/240034782
```

### Auditoria por códigos

```http
GET /api/combo-audit?codes=240034782,240032879
```

Máximo de 25 códigos por requisição.

### Auditoria paginada dos ativos

```http
GET /api/combo-audit?page=1&page_size=20
```

`page_size` aceita no máximo 25 combos. O resultado contém paginação, códigos processados, resumo e
achados estruturados.

## Respostas de erro

- `400`: parâmetros inválidos.
- `401`: credencial ausente ou inválida.
- `405`: método diferente de `GET`.
- `429`: limite de auditorias simultâneas atingido.
- `404`: endpoint inexistente.
- `503`: Firebird ou auditoria indisponível; detalhes internos não são expostos.
- `504`: tempo máximo excedido.

Todas as respostas usam JSON, `Cache-Control: no-store`, `X-Content-Type-Options: nosniff` e não
retornam credenciais ou configuração do Firebird.

## Fluxo de correção informado ao consumidor

Todo relatório contém `correction_workflow`, indicando `/combos-editar` como canal autorizado,
`api_write_supported: false` e aprovação humana obrigatória. O endpoint de versão apresenta as mesmas
capacidades.

O consumidor pode exibir a orientação e preparar texto para o usuário copiar, mas não pode executar
o comando do Slack automaticamente, personificar o solicitante ou gravar no ERP. Esta API não terá
endpoint de correção.

## Limites conhecidos antes da integração do Painel

- O Painel ainda precisa ingressar na rede `combo-audit-internal` como externa.
- A referência comercial de preço ainda depende de tabela aplicável ou valor aprovado pela
  Diretoria/Gerência.
- Resultados de conflito são candidatos técnicos e podem depender de confirmação no T1.
- A API não possui endpoint de correção e não deve receber um.
- O Painel deverá tratar timeout, indisponibilidade e cache identificado como desatualizado.

## Riscos para avaliação da Direção e da IA responsável

1. **Decisão comercial não estruturada:** preço, prioridade, público e substituição de brindes não
   podem ser inferidos quando dependerem de decisão humana.
2. **Falso positivo:** compartilhar produto não significa conflito por si só; devem ser consideradas
   quantidade, vigência, filial e público.
3. **Dado desatualizado:** cache no Painel deve mostrar a data/hora da auditoria.
4. **Sobrecarga do ERP:** paginação e limites não devem ser removidos; auditorias recorrentes precisam
   de intervalo controlado. A API limita trabalhadores e fila concorrente, mas o consumidor também
   deve aplicar espera e retentativa controlada após `429`, `503` ou `504`.
5. **Exposição de dados:** não publicar a porta no host, não registrar tokens e não retornar dados além
   do necessário.
6. **Duplicação de regras:** o Painel e o aplicativo dos vendedores não devem reimplementar as regras.
7. **Automação indevida:** nenhuma IA deve transformar ação recomendada em alteração automática sem o
   fluxo de aprovação do Slack.

## Próxima etapa

Configurar token exclusivo, criar rede privada entre os serviços, homologar estes endpoints com dados
reais e somente então implementar a tela de Auditoria de combos no `Painel_analise_vendas`.
