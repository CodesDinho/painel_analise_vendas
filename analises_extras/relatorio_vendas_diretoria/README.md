# Relatório de vendas — Diretoria

Relatório somente leitura, agregado no BigQuery, com os campos de filial, mês, ano, tipo de
estabelecimento, equipe, fornecedor, produto, quantidade, venda líquida e margem bruta. O nome da
filial é usado nos filtros, mas não ocupa uma coluna na grade nem no Excel.

O usuário escolhe e autoriza períodos de 1, 3, 6 ou 12 meses, sempre encerrados no dia 20 mais
recente disponível por padrão. Logo abaixo da autorização, pode informar livremente as datas inicial
e final, inclusive um ano civil fechado, desde que o intervalo não ultrapasse o volume autorizado nem
o limite absoluto de 12 meses. A tela informa tempos reais de referência para consulta e montagem do
Excel; períodos de 6 e 12 meses exigem confirmação adicional. Pedidos tipo 48 são excluídos por
padrão, mas podem ser incluídos conscientemente por meio de um checkbox; a escolha fica registrada
na tela, no nome do arquivo e no Excel.

## Regras e escopo

- **Venda Líquida:** confirmada como `SUM(vendas.valor_total)`.
- **Margem Bruta (%):** o campo oficial foi localizado em `VIEW_ITEMPEDIDO.MARGEMBRUTA`. Como todas
  as filiais ativas usam custo bruto, o agregado aplica
  `((SUM(valor_total) / SUM(valor_custo * quantidade)) - 1) * 100`. O resultado ainda deve ser
  validado contra uma amostra do relatório TOP.
- **Bonificações:** permanecem na base e reduzem a margem; o tratamento definitivo está a verificar.
- **Devoluções:** não entram; a origem considerada contém somente vendas.
- **Impostos:** não há dedução ou tratamento adicional.
- **Pedidos tipo 48:** excluídos por padrão; a inclusão opcional exibe um alerta por poder afetar a
  leitura da margem.

A margem e as bonificações permanecem destacadas em laranja até a validação final.
