# Retorno da validação dos casos de combos

Atualizamos nossa IA de Combos com um validador integrado ao ERP. Em resumo, ele consulta os combos
ativos diretamente no Firebird, cruza produtos, grupos, quantidades, caixas de carregamento,
vigências, filiais e públicos, identifica possíveis sobreposições e separa inconsistências
confirmadas de situações que ainda dependem de decisão comercial ou reprodução no T1.

O validador é somente leitura: ele não altera o ERP. Os resultados são classificados como erro,
conflito, alerta ou informativo e sempre apresentam uma ação recomendada. A análise também é mais
ampla do que os casos inicialmente enviados, pois pode encontrar outros combos que disputam os mesmos
produtos e condições.

## Resultado resumido dos casos enviados

1. **Combo 240034782 — preço R$ 26,77 × R$ 25,90:** não foi encontrada uma referência aprovada que
   permita afirmar qual valor está correto; o combo também possui o produto bonificado 2793 como SKU
   único e o grupo 6905 exige 1 unidade para produto com caixa de carregamento 6.
2. **Combos sobrepostos:** foram confirmados candidatos a conflito em `240035662 × 240035672` e
   `240035663 × 240035670`; não foram confirmados diretamente `240031841 × 240031867` nem
   `240035537 × 240035441`, embora tenham sido encontrados outros conflitos relacionados.
3. **Combo 240032879 — Keep Cooler:** não foi encontrada inconsistência de carregamento; o resultado é
   compatível com a informação de que o grupo exige 48 unidades independentemente dos sabores.
4. **Combo 240035106 — Pringles 10×1:** o ERP confirmou cinco opções de brinde — produtos 9963, 9964,
   9965, 9966 e 9967 — portanto não existe brinde único no cadastro.
5. **Combo 240032677 — Baly 2L 3 PCT:** a diferença de preço não foi classificada como erro, pois pode
   existir valor específico aprovado na criação; falta confirmar a referência comercial correta.
6. **Produto 10128 — Velho Barreiro Limão:** não foi possível confirmar o suposto combo “6+6 St Pierre
   Zero Pink Lemon”, pois o relato não contém código do combo nem dados suficientes para reprodução.
7. **Nome enviado à observação:** o texto informado possui 51 caracteres, mas não há evidência de
   truncamento nem confirmação do tamanho final do campo após prefixos e sufixos do aplicativo.

## Confirmações necessárias

1. **Combo 240034782:** para o produto 2793 do combo 240034782, qual é o valor comercial aprovado:
   R$ 26,77, R$ 25,90 ou outro? Esse valor segue alguma tabela de preço? O produto 2793 deve permanecer
   como único brinde e pode ser bonificado em 1 unidade mesmo com caixa de carregamento 6?

2. **Combos sobrepostos:** a frase “o vendedor vê duas opções iguais ou não vê uma delas” é uma
   ocorrência confirmada ou uma possibilidade? Em qual tela e etapa do T1 isso acontece? Para cada par
   confirmado, qual combo deve prevalecer quando ambos atenderem produto, quantidade, filial e público?

3. **Combo 240032879:** podemos considerar confirmado que o grupo exige 48 unidades no total,
   independentemente dos sabores, e manter o cadastro atual sem alteração?

4. **Combo 240035106:** o T1 apresenta ao vendedor todas as opções de brinde 9963, 9964, 9965, 9966 e
   9967? Se apresentar, podemos encerrar este item sem alteração no ERP?

5. **Combo 240032677:** o valor R$ 8,59 foi aprovado especificamente pela Diretoria/Gerência na criação
   do combo ou deve seguir o piso de R$ 8,99? Se foi aprovado, quem é o responsável pela referência e
   o valor deve permanecer mesmo quando a tabela possuir mínimo diferente?

6. **Produto 10128:** qual é o código do combo “6+6 St Pierre Zero Pink Lemon”? Em qual filial, cliente,
   vendedor, data e pedido o produto 10128 com quantidade 6 acionou esse combo e gerou Save negativo?
   Qual combo deveria ter sido aplicado?

7. **Nome da observação:** existe truncamento ou erro real causado pelo nome `PRESIDENTE DZ13 ** ATE
   10% DA VENDA DO CLIENTE M PR`? O nome precisa ser menor? Qual é o código do combo e qual texto
   aparece efetivamente na observação do pedido de bonificação?

## Papel de cada projeto nesta evolução

### Slack Combos

O Slack Combos continuará sendo a fonte oficial das regras, consultas ao Firebird, auditorias,
aprovações e alterações autorizadas no ERP. O `/combos-auditar` é somente leitura, enquanto qualquer
correção continuará passando pelo fluxo de aprovação do `/combos-editar`.

### Painel de Análise de Vendas

O Painel já existe e continuará sendo utilizado para geração de dados de clientes, análises comerciais
e apoio à criação de combos. A API interna, versionada e somente leitura do Slack Combos está
implementada, autenticada, restrita à rede privada e homologada. O Painel possui uma tela de
**Auditoria de combos** consumindo essa API no ambiente de produção.

No Painel será possível pesquisar, filtrar, conferir e exportar as auditorias. As regras não serão
copiadas para o Painel, e nenhuma correção será executada diretamente por ele.

Os resultados da API também informam que a correção deve ocorrer pelo `/combos-editar`, com aprovação
humana. O Painel poderá preparar a orientação ou um texto para copiar, mas não executará alterações em
nome do usuário e não terá API de escrita no ERP.

### Aplicativo dos vendedores

Uma integração futura poderá disponibilizar validações homologadas ao aplicativo dos vendedores, mas
somente após aprovação da Direção e definição do comportamento esperado no T1. O aplicativo não deve
manter uma cópia independente das regras.

O detalhamento técnico para evolução do Painel está registrado em
`INSTRUCAO_INTEGRACAO_PAINEL_ANALISE_VENDAS.md`, e o contrato seguro da API está em
`CONTRATO_API_AUDITORIA_COMBOS.md`. O ajuste solicitado ao cliente já implementado no Painel está em
`REPASSE_ATUALIZACAO_PAINEL_API_IMPLEMENTADA.md`.

## Log técnico

O comando utilizado, já disponível no Slack, foi:

```text
/combos-auditar 240034782, 240031841, 240031867, 240035662, 240035672, 240035663, 240035670, 240035537, 240035441, 240032879, 240035106, 240032677
```

Também é possível auditar todos os combos atualmente ativos com:

```text
/combos-auditar ativos
```

A auditoria é exclusivamente de leitura. Nenhuma correção é executada automaticamente. Depois do
retorno das áreas responsáveis, ajustaremos somente os cadastros cuja inconsistência for confirmada.
Situações intencionais serão mantidas e documentadas como regras comerciais válidas.

## Próximos passos sugeridos

1. Centralizar e evoluir as regras de combos neste ambiente, aproveitando as validações, aprovações e
   controles já implementados.

2. Homologar as regras com a Direção, Gerência e demais responsáveis, especialmente quando o cadastro
   depender de uma decisão comercial.

3. Avaliar, mediante aprovação e direcionamento da Direção, a futura integração com o aplicativo dos
   vendedores. Essa integração deverá ocorrer somente depois da homologação do contrato da API, das
   regras e dos retornos do validador.

4. Registrar como regra oficial as decisões comerciais confirmadas, evitando que situações
   intencionais sejam tratadas novamente como inconsistências.

## Síntese

A análise inicial indica que boa parte das dúvidas apresentadas está relacionada à definição de
escopo, prioridade e estratégia comercial, e não necessariamente a falhas no cadastro do ERP.

Com a definição do comportamento esperado em cada caso, a TI poderá transformar as decisões em
validações objetivas e indicar com segurança quais cadastros devem ser corrigidos, mantidos ou apenas
documentados.

Nosso objetivo é utilizar o mesmo conjunto de regras no Slack, no futuro painel de auditoria e, quando
homologado, no aplicativo dos vendedores, evitando interpretações diferentes entre os sistemas.

---

**Anexo:** [Log técnico completo da validação](log_tecnico_validacao_casos_diretoria.md)

