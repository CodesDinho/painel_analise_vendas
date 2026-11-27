# Relatório de vendas — Diretoria

Relatório somente leitura, agregado no BigQuery, com os campos de filial, mês, ano, tipo de
estabelecimento, equipe, fornecedor, produto, quantidade, venda líquida e margem bruta.

O período padrão vai do primeiro dia do mês até o dia 20 mais recente disponível. Consultas e
exportações detalhadas aceitam no máximo três meses. Pedidos tipo 48 são excluídos, preservando a
regra já utilizada pelas análises gerais do painel.

## Pendências de homologação

- **Venda Líquida:** provisoriamente `SUM(vendas.valor_total)`.
- **Margem Bruta:** provisoriamente `SUM(valor_total - valor_custo * quantidade)`.

Os dois campos são destacados em laranja na tela e no Excel até a confirmação da Controladoria.
