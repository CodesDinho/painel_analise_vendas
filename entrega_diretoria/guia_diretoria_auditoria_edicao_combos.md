# Guia para a Diretoria — auditoria e edição de combos

Atualização: 17/11/2026  
Ambiente: produção, servidor 153  
Serviço responsável: `slack-combos`  
Schema da API: `1.0`  
Versão das regras na publicação deste guia: `5.1`

## 1. Resumo executivo

Existem dois canais diferentes e eles não devem ser confundidos:

| Necessidade | Canal autorizado | Escrita no ERP |
|---|---|---|
| Consultar auditoria por outro sistema | API HTTP interna | Não |
| Consultar auditoria como usuário | Slack `/combos-auditar` | Não |
| Solicitar correção ou edição | Slack `/combos-editar` | Pode ocorrer após as validações e aprovações aplicáveis |

Não existe API HTTP para editar combos. Isso é intencional. A API HTTP aceita somente `GET` e informa
`correction_api: false` e `api_write_supported: false`. Uma integração não deve criar uma rota de
escrita paralela, chamar o ERP diretamente nem personificar um usuário do Slack.

## 2. Para quem é cada acesso

### Diretoria e usuários autorizados

- Para consultar: usar o Painel ou `/combos-auditar` no Slack.
- Para corrigir: usar `/combos-editar` no Slack.
- Não precisa receber o token técnico da API para usar esses dois comandos.

### Aplicação consumidora

Uma aplicação pode consumir a API de auditoria se:

1. executar como container no servidor 153;
2. ingressar na rede Docker externa `combo-audit-internal`;
3. receber o token pelo Portainer ou mecanismo equivalente de secrets;
4. não publicar a porta 8080 no host;
5. respeitar paginação, timeout e limites de concorrência.

O token não deve ser enviado por e-mail, Slack, documentação ou Git. Um administrador deve cadastrá-lo
diretamente no ambiente da aplicação consumidora.

## 3. Endereço e autenticação da API

O endereço só funciona dentro da rede Docker compartilhada:

```text
http://slack-combos:8080
```

Todas as chamadas exigem:

```http
Authorization: Bearer <token>
Accept: application/json
```

Variáveis sugeridas na aplicação consumidora:

```text
COMBO_AUDIT_API_URL=http://slack-combos:8080
COMBO_AUDIT_API_TOKEN=<cadastrado diretamente no Portainer>
COMBO_AUDIT_API_TIMEOUT=45
```

Exemplo mínimo de Compose:

```yaml
services:
  aplicacao-consumidora:
    image: imagem-da-aplicacao
    environment:
      COMBO_AUDIT_API_URL: http://slack-combos:8080
      COMBO_AUDIT_API_TOKEN: ${COMBO_AUDIT_API_TOKEN:?token obrigatorio}
      COMBO_AUDIT_API_TIMEOUT: "45"
    networks:
      - default
      - combo_audit_internal

networks:
  combo_audit_internal:
    external: true
    name: combo-audit-internal
```

Não adicionar:

```yaml
ports:
  - "8080:8080"
```

## 4. Endpoints de auditoria

### 4.1 Versão e capacidades

```http
GET /api/combo-rules/version
```

Use este endpoint no healthcheck funcional da integração. Exemplo de resposta:

```json
{
  "schema_version": "1.0",
  "rules_version": "5.1",
  "last_audit_at": null,
  "capabilities": {
    "audit_read_api": true,
    "correction_api": false,
    "correction_command": "/combos-editar",
    "human_approval_required": true
  }
}
```

### 4.2 Auditoria de um combo

```http
GET /api/combo-audit/240034782
```

O código aceita de 1 a 9 dígitos.

### 4.3 Auditoria de códigos informados

```http
GET /api/combo-audit?codes=240034782,240032879
```

- máximo de 25 códigos por requisição;
- códigos repetidos são consolidados;
- não enviar nomes, textos livres ou dados de clientes nesse parâmetro.

### 4.4 Auditoria paginada dos combos ativos

```http
GET /api/combo-audit?page=1&page_size=20
```

- `page` deve ser inteiro positivo;
- `page_size` deve ficar entre 1 e 25;
- continuar enquanto a soma de `returned_combos` for menor que `total_combos`;
- não disparar páginas em paralelo agressivamente.

## 5. Estrutura da resposta de auditoria

Campos principais:

```json
{
  "schema_version": "1.0",
  "generated_at": "data e hora com fuso",
  "scope": "combo_240034782",
  "summary": {
    "erro": 0,
    "conflito": 0,
    "alerta": 0,
    "informativo": 0
  },
  "total_findings": 0,
  "findings": [],
  "correction_workflow": {
    "channel": "slack",
    "command": "/combos-editar",
    "api_write_supported": false,
    "requires_human_approval": true
  }
}
```

Cada item de `findings` pode incluir:

- `status`: `ERRO`, `CONFLITO`, `ALERTA` ou `INFORMATIVO`;
- `combo`;
- `produto`, quando aplicável;
- `regra`;
- `mensagem`;
- `evidencias`;
- `acao_recomendada`.

O consumidor deve aceitar campos adicionais e validar `schema_version` antes de processar o conteúdo.

## 6. Exemplo em Python

```python
import json
import os
from urllib.request import Request, urlopen

base_url = os.environ["COMBO_AUDIT_API_URL"].rstrip("/")
token = os.environ["COMBO_AUDIT_API_TOKEN"]

request = Request(
    f"{base_url}/api/combo-rules/version",
    headers={
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    },
)

with urlopen(request, timeout=15) as response:
    payload = json.load(response)

if payload.get("schema_version") != "1.0":
    raise RuntimeError("Schema incompatível")

print(payload["rules_version"])
```

Nunca imprimir o token, os headers completos ou todas as variáveis do container nos logs.

## 7. Códigos de resposta

| HTTP | Significado | Conduta |
|---|---|---|
| 200 | Consulta concluída | Validar schema e processar |
| 400 | Parâmetro inválido | Corrigir a requisição; não repetir igual |
| 401 | Token ausente ou inválido | Conferir secret no Portainer |
| 404 | Endpoint inexistente | Conferir URL e versão do contrato |
| 405 | Método diferente de GET | Não usar POST, PUT, PATCH ou DELETE |
| 429 | Limite concorrente | Aguardar e tentar novamente uma vez |
| 503 | Firebird ou auditoria indisponível | Aguardar; não tratar cache como dado atual |
| 504 | Tempo excedido | Reduzir o escopo e repetir de forma controlada |

Para `429`, `503` e `504`, usar espera progressiva e poucas retentativas. Não criar loop ilimitado.

## 8. Auditoria pelo Slack

Auditar um combo:

```text
/combos-auditar 240034782
```

Auditar vários combos:

```text
/combos-auditar 240034782, 240032879
```

Auditar todos os ativos:

```text
/combos-auditar ativos
```

O alias `/auditar-combo` existe apenas para transição. O comando recomendado é `/combos-auditar`.
Auditoria é somente leitura e não altera o ERP.

## 9. Edição pelo Slack

O único canal autorizado é:

```text
/combos-editar
```

Também é possível informar a solicitação na mesma linha:

```text
/combos-editar Cliente 196154 Combo 240035279 Vendedor 154
```

### Opções

| Opção | Solicitação | Dados essenciais |
|---|---|---|
| 1 | Liberar cliente no combo | Combo e cliente |
| 2 | Liberar filial no combo | Combo e filial |
| 3 | Remover bloqueio/restrição de vendedor | Combo e vendedor |
| 4 | Alterar produtos e valores | Combo e lista completa de produtos/valores |
| 5 | Alterar vigência, ativar, reativar ou prorrogar | Combo e data máxima |
| 6 | Cadastrar ou atualizar grupo de rede | Combo/nome, filial, data e produtos/valores |

Modelo completo:

```text
Opção escolhida: 1
Combo: 240000000
Filial:
Cliente: 100000
Vendedor:
Data máxima para ativação/reativação:
Produtos/valores:
Observação:
```

Para vários clientes ou combos, separar por vírgula ou ponto e vírgula. Usar sempre os rótulos; não
enviar apenas uma sequência de números.

### Estados possíveis

- `APROVADO`: regra atendida ou operação executada;
- `JA_EXISTE`: vínculo já existia e não foi duplicado;
- `NEGADO`: regra obrigatória impediu a operação;
- `AGUARDANDO_APROVACAO`: nada deve ser considerado concluído antes da decisão;
- `PENDENTE`: faltam dados ou validação externa.

Opções 4 e 5 normalmente exigem aprovação humana. Quando o Slack apresentar o cartão de aprovação,
somente os aprovadores autorizados podem concluir ou rejeitar a solicitação.

## 10. Testes de homologação

### Teste seguro da API

1. Consultar `/api/combo-rules/version` e esperar HTTP 200.
2. Confirmar `schema_version = 1.0`.
3. Confirmar `audit_read_api = true` e `correction_api = false`.
4. Auditar um combo conhecido e conferir `generated_at`, `summary` e `findings`.
5. Testar sem token e esperar HTTP 401.
6. Não começar pela auditoria de todos os ativos.

### Teste seguro pelo Slack

```text
/combos-auditar <combo conhecido>
```

Confirmar que o retorno informa achados e não altera nenhum registro.

### Homologação de edição

Edição pode gravar em produção. Fazer somente com caso previamente autorizado pela área responsável:

1. escolher combo e entidade de teste conhecidos;
2. registrar o estado anterior;
3. enviar `/combos-editar` com todos os rótulos;
4. conferir o resumo antes de qualquer aprovação;
5. se houver aprovação, usar um aprovador autorizado;
6. validar o resultado no ERP e executar nova auditoria;
7. guardar código do combo, solicitante, horário, resultado e aprovador.

Não usar dados fictícios aleatórios em produção e não testar edição chamando diretamente o Firebird.

## 11. Checklist de entrega à Diretoria

- [ ] A Diretoria e os responsáveis receberam este documento.
- [ ] Foi definido se ele usará Slack, aplicação integrada ou ambos.
- [ ] A aplicação consumidora está na rede `combo-audit-internal`.
- [ ] O token foi cadastrado diretamente no Portainer, sem envio por mensagem.
- [ ] O endpoint de versão retornou HTTP 200 e schema `1.0`.
- [ ] Uma auditoria individual foi validada.
- [ ] Ficou registrado que não existe API HTTP de edição.
- [ ] Os usuários autorizados possuem acesso ao comando `/combos-editar` no Slack, se necessário.
- [ ] O primeiro caso de edição foi escolhido e autorizado antes da execução.

## 12. Informações para suporte

Ao reportar falha, enviar somente:

- data e hora;
- aplicação/serviço consumidor;
- endpoint sem token;
- código HTTP;
- código do combo, quando aplicável;
- mensagem de erro sanitizada;
- identificador da requisição ou trecho de log sem headers e secrets.

Nunca enviar token, senha Firebird, conteúdo de `combo_config.ini` ou dump das variáveis de ambiente.

## 13. Fontes de verdade

- Contrato: `docs/integracao/CONTRATO_API_AUDITORIA_COMBOS.md`.
- Regras e implementação: repositório `CodesDinho/ti_dinho_slack`, projeto `slack_combos`.
- Canal de correção: `/combos-editar` no Slack.
- Painel consumidor de referência: `Painel_analise_vendas`.

