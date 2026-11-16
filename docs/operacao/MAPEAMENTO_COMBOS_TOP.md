# Mapeamento de combos no TOP

Levantamento realizado por consultas somente leitura aos metadados e a combos vigentes do Firebird em 07/08/2026. Nenhum registro foi criado, alterado ou excluído durante o levantamento.

## Estrutura confirmada

### `COMBO`

Cabeçalho. Chave primária manual `CODIGO`; não existe generator para ela. Campos `CODIGO`, `NOME`, `DATAINICIO` e `DATAFIM` são obrigatórios. Os campos funcionais observados incluem `INSERIRAUTOMATICO`, `TIPO` (`D` desconto ou `B` brinde), `GERARFLEX`, `LIBERARQTDEMULTIPLA`, `BLOQUEARALTERARQUANTIDADE`, `COMISSAO`, `COMISSAOFIXA`, `MARCA`, `QTDEMAXIMA`, `OBS` e `CUSTOMREPLICARION` (default `N`). Há trigger de integração ION, atualmente inativa no banco consultado.

### `GRUPOCOMBO`

Grupos do combo. Chave primária `CODIGO`, obrigatória, sem generator e sem trigger de preenchimento. Também são obrigatórios `COMBO`, `NOME` e `QTDE`; `BONIFICADO` é opcional. Amostras válidas mostram grupos de desconto e de brinde com regras diferentes.

### `ITEMGRUPOCOMBO`

Produtos/faixas. Campos obrigatórios: `GRUPOCOMBO`, `PRODUTO`, `QTDEINICIO`, `QTDEFIM` e `VALORVENDA`. O `ID` é preenchido por `TRI_ITEMGRUPOCOMBO_BI` usando `GEN_ITEMGRUPOCOMBO_ID`. `REPLICAR` possui default e trigger para `N`. Existem FKs para grupo e produto e unicidade por grupo/produto.

### `GRUPOCOMBODESCONTO`

Faixas de desconto associadas ao grupo, com `QTDE`, `DESCONTO`, `DESCONTOMINIMO` e `DESCONTOMAXIMO`. O `ID` usa `GEN_GRUPOCOMBODESCONTO_ID`. Muitos combos vigentes do tipo `D` possuem registros aqui, mas há combos válidos sem eles; a condição funcional para obrigatoriedade não pôde ser determinada apenas pelo schema.

### `COMBOCLIFOR`

Vínculos de clientes. Campos obrigatórios `COMBO` e `CLIFOR`; o `ID` usa `GEN_COMBOCLIFOR_ID`. `REPLICAR` é forçado para `N` por trigger. Há FKs para `COMBO` e `CLIFOR` e unicidade do par combo/cliente.

### Outras relações encontradas

`COMBOESTADO`, `COMBOFILIAL`, `COMBOFUNCIONARIO`, `COMBOTIPOPEDIDO`, `COMBOPEDIDO`, `COMBOPEDIDOGRUPOPRODUTO` e `ITEMCOTACOMBOCLIENTE`. Na inserção de clientes em combos existentes, `ITEMCOTACOMBOCLIENTE` recebe `QUANTIDADE`, `COTA`, `COMBO` e `CLIENTE`; o `ID` é identidade gerada pelo Firebird. Os códigos de cota vigentes são herdados dos registros já configurados no combo e a quantidade, normalmente 1, é informada pelo usuário.

É permitido cadastrar clientes em todos os combos dormentes, tanto Dormente positivação quanto Dormente volume. A liberação vale para a inserção a partir das análises e para a inclusão dinâmica; a exclusão de vínculos existentes também continua permitida.

## Regra universal de IE para produtos restritos

Qualquer combo que contenha ao menos um produto identificado como vinho, espumante, água ou xarope só pode ser liberado para clientes com Inscrição Estadual preenchida em `CLIFOR.IE`. A regra independe da classificação do combo e do estado do cliente/filial. Valores nulos, vazios ou `ISENTO` não atendem à regra.

A identificação consulta `ITEMGRUPOCOMBO` e os campos cadastrais de `PRODUTO`, `TIPOPRODUTO`, `GRUPO`, `CATEGORIAPRODUTO` e `TIPOLINHA`. A validação ocorre no planejamento e é obrigatoriamente repetida dentro da transação antes de inserir em `COMBOCLIFOR` ou `ITEMCOTACOMBOCLIENTE`. Na inserção originada da análise de queda de volume, a opção de processar somente os válidos remove da preparação os pares combo/cliente sem IE e grava os demais; nos outros fluxos, qualquer par bloqueado impede toda a inclusão. A exclusão de vínculos existentes permanece permitida.

## Padrões observados

- Combos ativos existentes usam `TIPO = D` ou `TIPO = B`.
- Combos recentes do tipo desconto normalmente usam `GERARFLEX = S`, `INSERIRAUTOMATICO = N`, flags de quantidade `N` e `CUSTOMREPLICARION = N`, mas há exceções históricas.
- Em diversos combos de desconto, `GRUPOCOMBO.QTDE` corresponde à quantidade de uma faixa em `GRUPOCOMBODESCONTO`; em outros grupos livres, a quantidade é zero e pode não existir faixa de desconto.
- Combos de brinde normalmente possuem pelo menos um grupo de compra e um grupo `BONIFICADO = S`.
- `ITEMGRUPOCOMBO.QTDEINICIO/QTDEFIM` pode ser zero em combos existentes, mas o formulário deste painel exige valores positivos conforme a regra solicitada.

## Bloqueios para criação automática

O botão final permanece desabilitado até confirmação formal das seguintes regras:

1. como o TOP reserva `GRUPOCOMBO.CODIGO` sem generator, inclusive sob concorrência;
2. como derivar `GRUPOCOMBO.QTDE` e `BONIFICADO` das linhas do formulário;
3. quando criar `GRUPOCOMBODESCONTO` e como preencher desconto mínimo/máximo;
4. qual modalidade (`TIPO`) e quais flags funcionais usar para cada combo criado por este painel.

Sem essas respostas, inserir apenas `COMBO`, `GRUPOCOMBO`, `ITEMGRUPOCOMBO` e `COMBOCLIFOR` poderia produzir um cadastro tecnicamente válido no schema, mas funcionalmente incorreto no TOP.
