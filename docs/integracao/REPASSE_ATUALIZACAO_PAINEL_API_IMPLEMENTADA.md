# Repasse atualizado ao Painel de Análise de Vendas — API implementada

## Situação atual

O `Painel_analise_vendas` já possui a tela **Análises extras → Auditoria de combos** e o cliente de
integração preparado. No `slack_combos`, os três endpoints esperados agora estão implementados:

```text
GET /api/combo-audit
GET /api/combo-audit/{codigo_combo}
GET /api/combo-rules/version
```

O schema retornado é `1.0` e a autenticação usa:

```text
Authorization: Bearer <token interno>
```

## Configuração do Painel

Quando os serviços estiverem na mesma rede Docker privada, configurar:

```text
ANALISE_VENDAS_COMBO_AUDIT_API_URL=http://slack-combos:8080
ANALISE_VENDAS_COMBO_AUDIT_API_TOKEN=<mesmo segredo configurado no slack_combos>
ANALISE_VENDAS_COMBO_AUDIT_API_TIMEOUT=45
```

Não publicar a porta `8080` no host. O endereço acima deve funcionar somente dentro da rede Docker
compartilhada.

No Compose do Painel, conectar somente o serviço que faz a consulta:

```yaml
services:
  painel-analise-vendas:
    networks:
      - default
      - combo_audit_internal

networks:
  combo_audit_internal:
    external: true
    name: combo-audit-internal
```

Adaptar `painel-analise-vendas` ao nome real do serviço. Não criar `ports` para a API.

## Ajuste obrigatório no cliente já implementado

O método atual `consultar_auditoria(config, codigos=None)` faz apenas uma chamada para
`/api/combo-audit`. A API limita a resposta geral a no máximo 25 combos por página para proteger o
Firebird.

O cliente deve:

1. solicitar `GET /api/combo-audit?page=1&page_size=25`;
2. ler `pagination.total_combos` e `pagination.returned_combos`;
3. solicitar as páginas seguintes até processar todos os combos;
4. combinar e remover duplicidades dos `findings`;
5. preservar o `generated_at` mais recente;
6. interromper com mensagem clara se uma página falhar, usando cache somente quando identificado como
   desatualizado.

Não aumentar nem remover o limite na API para adaptar o servidor ao cliente. A paginação é um controle
de segurança e carga.

## Tratamento de erros

Além de `401`, o cliente deve tratar:

- `400`: parâmetros inválidos;
- `405`: método proibido;
- `429`: excesso de auditorias; aguardar antes de tentar novamente;
- `503`: serviço/Firebird indisponível; oferecer cache identificado;
- `504`: auditoria excedeu o timeout; não repetir imediatamente.

Não registrar o Bearer token, cabeçalhos de autenticação ou resposta bruta com dados desnecessários.

## Correções e `/combos-editar`

A API de auditoria é exclusivamente de leitura. Não será criado endpoint de escrita equivalente ao
`/combos-editar`, porque isso permitiria contornar identidade do solicitante, aprovação humana,
registro da decisão e revalidação transacional.

Os relatórios agora retornam:

```json
{
  "correction_workflow": {
    "channel": "slack",
    "command": "/combos-editar",
    "api_write_supported": false,
    "requires_human_approval": true
  }
}
```

O endpoint de versão também retorna as capacidades da integração. O Painel pode:

- exibir a ação recomendada;
- montar um texto para copiar e colar no `/combos-editar`;
- orientar o usuário a abrir o Slack;
- mostrar que a correção exige aprovação.

O Painel não deve chamar a API do Slack fingindo ser o usuário, enviar comandos automaticamente ou
gravar diretamente no Firebird.

## Testes adicionais solicitados ao Painel

1. Auditoria geral com mais de 25 combos e múltiplas páginas.
2. Combinação sem duplicidade entre páginas.
3. Resposta `429` com espera controlada.
4. Resposta `503/504` usando cache sinalizado.
5. Token ausente ou inválido sem exposição da credencial.
6. Exibição de `correction_workflow` sem botão de gravação direta.
7. Incompatibilidade de `schema_version` bloqueando o uso do resultado.

## Critério de aceite conjunto

A integração estará homologada quando o Painel percorrer todas as páginas, exibir os mesmos achados do
`/combos-auditar`, mostrar versão e horário, exportar as evidências e direcionar correções apenas ao
`/combos-editar`, sem rota de escrita e sem exposição da API fora da rede privada.
