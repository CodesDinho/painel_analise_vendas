# Controle da liberação temporária — 01/09/2026

## Lista acumulada

- Arquivo: `clientes_liberacao_temporaria_20260901.txt`
- Clientes únicos recebidos até o momento: 135
- Novos códigos devem ser acrescentados a esse arquivo antes de qualquer conferência.

## Primeira liberação — 07:33:13

- Clientes liberados: 123
- Bloqueios da ação removidos: 11.541
- Evidências: `liberacao_temporaria_bloqueios_20260901_073313/`
- Reaplicação: `liberacao_temporaria_bloqueios_20260901_073313/reaplicar_bloqueios.sql`
- Códigos sem pares no manifesto: 5416, 186377 e 1328884.

## Liberação adicional — 08:26:53

- Cliente liberado: 1657
- Bloqueios da ação removidos: 139
- Bloqueios anteriores preservados: 19
- Evidências: `liberacao_temporaria_bloqueios_20260901_082653/`
- Reaplicação: `liberacao_temporaria_bloqueios_20260901_082653/reaplicar_bloqueios.sql`

## Código 16967

- Não foi localizado no CLIFOR.
- Não possui registros em `CLIFORCONDICAOPAGAMENTO`.
- Nenhum bloqueio foi removido e nenhuma reaplicação será necessária.

## Segunda liberação adicional — 08:28:36

- Clientes liberados: 38029, 188667 e 54093
- Bloqueios removidos do cliente 38029: 90
- Bloqueios removidos do cliente 188667: 17
- Bloqueios removidos do cliente 54093: 117
- Total removido nesta operação: 224
- Evidências: `liberacao_temporaria_bloqueios_20260901_082836/`
- Reaplicação: `liberacao_temporaria_bloqueios_20260901_082836/reaplicar_bloqueios.sql`

## Terceira liberação adicional — 08:30:46

- Cliente liberado: 169674
- Bloqueios removidos: 111
- Evidências: `liberacao_temporaria_bloqueios_20260901_083046/`
- Reaplicação: `liberacao_temporaria_bloqueios_20260901_083046/reaplicar_bloqueios.sql`

## Quarta liberação adicional — 08:31:31

- Cliente liberado: 53099
- Bloqueios removidos: 112
- Evidências: `liberacao_temporaria_bloqueios_20260901_083131/`
- Reaplicação: `liberacao_temporaria_bloqueios_20260901_083131/reaplicar_bloqueios.sql`

## Código 18386

- Recebido em 01/09/2026 às 08:34.
- Não foi localizado no CLIFOR.
- Não possui registros em `CLIFORCONDICAOPAGAMENTO`.
- Nenhum bloqueio foi removido e nenhuma reaplicação será necessária.

## Quinta liberação adicional — 08:38:42

- Cliente liberado: 183186
- Bloqueios removidos: 14
- Evidências: `liberacao_temporaria_bloqueios_20260901_083842/`
- Reaplicação: `liberacao_temporaria_bloqueios_20260901_083842/reaplicar_bloqueios.sql`

## Reaplicação futura

Foram removidos temporariamente **12.141 bloqueios** no total:

1. 11.541 registros da primeira liberação.
2. 139 registros da liberação adicional do cliente 1657.
3. 224 registros da segunda liberação adicional.
4. 111 registros da terceira liberação adicional.
5. 112 registros da quarta liberação adicional.
6. 14 registros da quinta liberação adicional.

Antes da execução, os dois manifestos devem ser consolidados, deduplicados e comparados novamente com o banco. Os inserts de reaplicação são idempotentes (`WHERE NOT EXISTS`).

**Orientação operacional posterior:** antes da reaplicação, excluir do consolidado quaisquer condições `PRZ` e à vista para clientes Multicanal ou Key On/On Trade. Portanto, o total final elegível para reaplicação deverá ser recalculado e será menor ou igual a 12.141. Os SQLs individuais permanecem como evidência exata do que foi removido, mas não devem ser executados diretamente sem aplicar essa regra atualizada.

## Reaplicação concluída — 09:15:14

- Bloqueios removidos documentados: 12.141
- Bloqueios reaplicados e validados: 11.930
- Bloqueios não reaplicados pelas regras atuais: 211
- Os 211 excluídos eram condições à vista: código 100 (118 registros), código 150 (90 registros) e código 200 (3 registros).
- Clientes afetados pelas exclusões atuais: 120
- Evidências: `reaplicacao_bloqueios_20260901_091514/`
- Situação: **CONCLUÍDA**
