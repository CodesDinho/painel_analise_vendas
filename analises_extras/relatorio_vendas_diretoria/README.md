# Relatório de vendas — Diretoria

Relatório somente leitura, agregado no BigQuery, com os campos de filial, mês, ano, tipo de
estabelecimento, equipe, fornecedor, produto, quantidade, venda líquida e margem bruta.

O usuário escolhe e autoriza períodos de 1, 3, 6 ou 12 meses, sempre encerrados no dia 20 mais
recente disponível por padrão. Logo abaixo da autorização, pode informar livremente as datas inicial
e final, inclusive um ano civil fechado, desde que o intervalo não ultrapasse o volume autorizado nem
o limite absoluto de 12 meses. A tela informa tempos reais de referência para consulta e montagem do
Excel; períodos de 6 e 12 meses exigem confirmação adicional. Pedidos tipo 48 são provisoriamente
excluídos, preservando a regra já utilizada pelas análises gerais do painel.

## Pendências de homologação

- **Venda Líquida:** provisoriamente `SUM(vendas.valor_total)`.
- **Margem Bruta:** provisoriamente `SUM(valor_total - valor_custo * quantidade)`.
- **Bonificações:** confirmar se reduzem margem, são excluídas ou separadas.
- **Devoluções:** confirmar a origem e o estorno de venda, custo e quantidade.
- **Impostos:** confirmar quais tributos devem ser deduzidos.
- **Pedidos tipo 48:** confirmar se devem ser excluídos, incorporados ou separados.

Os dois campos são destacados em laranja na tela e no Excel até a confirmação da Controladoria.
