# painel_analise_vendas

Plataforma interna de inteligência comercial e apoio operacional desenvolvida em Streamlit. Apesar do
nome histórico, o projeto vai além da análise de vendas: centraliza indicadores, diagnósticos,
conferências e rotinas controladas que apoiam as equipes Comercial, Faturamento, Diretoria e TI.

Entre as principais capacidades estão:

- análises de vendas, positivação, volume, mix e desempenho por cliente, equipe, produto e indústria;
- criação, conferência, auditoria e manutenção de combos comerciais;
- validação de reembolsos e verbas de fornecedores, com rastreabilidade e exportação;
- apoio a bloqueios, liberações temporárias e outras rotinas operacionais controladas;
- integração com BigQuery, Firebird e serviços internos, mantendo segredos e dados operacionais
  fora do código e do Git.

O nome técnico `painel_analise_vendas` foi preservado para manter compatibilidade com caminhos,
automações e implantações existentes.

## Escopo analítico inicial

O projeto nasceu a partir da estrutura do Painel de Televendas, inicialmente com quatro análises:

1. clientes sem positivação por indústria nos últimos 30 dias;
2. queda de volume em períodos anuais equivalentes;
3. queda de mix por equipe em períodos equivalentes;
4. conciliação Pernod × arquivo Mtrix revisado (fase 2).

O menu **Análise Pernod Reembolso** lê a planilha operacional da Pernod,
consulta as vendas do mês no BigQuery e apresenta os cenários de reembolso sem
e com a inclusão integral dos pedidos tipo 48. A tela permite enviar uma nova
planilha, selecionar a competência, recalcular a análise e baixar um texto-base
para o e-mail de validação. A área de perguntas responde localmente às dúvidas
objetivas sobre os totais e pode usar a API da OpenAI para perguntas abertas
quando `OPENAI_API_KEY` estiver configurada. O modelo pode ser definido em
`ANALISE_VENDAS_OPENAI_MODEL`; somente o resumo calculado e a pergunta são
enviados, não o arquivo Excel completo.

O cenário considerado para justificativa inclui os pedidos tipo 48. A tela cruza
os clientes e produtos atendidos pelo Dinho com a aba `Base_Reembolso` do Mtrix,
mostra vendas regulares, tipo 48, totais de cada origem, diferenças e a verba
adicional calculada pela tarifa do produto. Os indicadores confrontam o reembolso
informado pela Pernod com o valor recalculado incluindo tipo 48 e mostram a soma
da diferença e o valor extra a cobrar. O botão de exportação gera um Excel com
resumo, conferência linha a linha por produto e relação cliente × produto para
envio à Pernod.

A exportação possui duas versões. A **completa** preserva todas as abas analíticas.
A **simplificada** mantém as duas primeiras abas da versão completa — `Resumo` e
`Conferência reembolso` — exatamente iguais. A última aba, `Dados simplificados`,
contém somente: resultado da comparação, código e nome do cliente, CNPJ, data,
filial, código e nome do produto, unidades consolidadas e faturamento total.

O painel também possui uma tela operacional de inserção dinâmica de combos, com filtros múltiplos de cadastro e vendas, prévia e confirmação transacional para incluir ou excluir vínculos em `COMBOCLIFOR`.

## Análises extras

Funcionalidades independentes ficam em `analises_extras/` e são acopladas ao menu por meio de
`analises_extras/registro.py`. O `main.py` conhece apenas esse registro; conexões, autenticação e
configuração continuam compartilhadas pelo projeto. Consulte `analises_extras/README.md` para criar
um novo módulo seguindo o padrão e `docs/PENDENCIAS_ESTRUTURA.md` para os itens estruturais ainda
adiados.

O menu **Relatório de vendas — Diretoria** consulta no BigQuery um detalhamento agregado por filial,
mês, tipo de estabelecimento, equipe, fornecedor e produto. O usuário autoriza períodos de 1, 3, 6
ou 12 meses após visualizar os tempos medidos; 6 e 12 meses exigem confirmação adicional. Venda
líquida e margem bruta permanecem destacadas em laranja como pendentes de homologação da fórmula,
tanto na tela quanto no Excel.

### Auditoria de combos

O menu **Auditoria de combos** consome, em modo somente leitura, os resultados estruturados da API
interna do projeto `slack_combos`. As regras não são copiadas para este projeto e nenhuma correção é
executada pelo painel. A tela apresenta indicadores, filtros, evidências, ações recomendadas, versão
das regras e exportação para Excel. Quando a API falha, pode exibir a última resposta válida em cache,
identificada claramente como possivelmente desatualizada.

Configuração da integração:

- `ANALISE_VENDAS_COMBO_AUDIT_API_URL`: URL base da API interna;
- `ANALISE_VENDAS_COMBO_AUDIT_API_TOKEN`: token interno, quando exigido;
- `ANALISE_VENDAS_COMBO_AUDIT_API_TIMEOUT`: timeout em segundos, padrão `45`;
- `ANALISE_VENDAS_COMBO_AUDIT_API_AUTH_HEADER`: cabeçalho, padrão `Authorization`;
- `ANALISE_VENDAS_COMBO_AUDIT_API_AUTH_PREFIX`: prefixo, padrão `Bearer`.

Contrato esperado: `GET /api/combo-audit?page=1&page_size=25`, `GET /api/combo-audit/{codigo_combo}` e
`GET /api/combo-rules/version`, usando schema `1.0`. Correções devem seguir pelo comando
`/combos-editar` no Slack.

Para repassar o uso à Diretoria ou a outra aplicação, consulte o
[`pacote de auditoria e edição de combos`](entrega_diretoria/leia_me.md),
que descreve acesso, segurança, exemplos, testes e o limite intencional entre API de leitura e edição
via Slack.

Em produção, somente o serviço do Painel deve ingressar na rede Docker externa
`combo-audit-internal`, usando `http://slack-combos:8080`. A porta da API não deve ser publicada no
host. A consulta geral percorre todas as páginas antes de apresentar ou salvar o resultado; se uma
página falhar, apenas um cache anterior claramente identificado como desatualizado pode ser exibido.

## Dados e cache

A aplicação faz uma carga ampla agregada do BigQuery no máximo uma vez por dia e salva em `cache/`. Filtros e telas usam essa base local. O botão **Atualizar dados agora** é a única exceção deliberada. As datas padrão são de 1º de janeiro até hoje e o mesmo intervalo do ano anterior; elas nunca ficam fixas em 2025/2026.

Fornecedores configurados: Pernod `80166, 80066`, Campari `80047` e VCT `4135`.

## Configuração

Instale e execute:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run main.py --server.port 8520
```

Também é possível iniciar pelo PowerShell com `scripts/iniciar_local.ps1`.

### Execução em Docker

O Docker executa exclusivamente no servidor Linux 153, gerenciado pelo Portainer/GitOps. O servidor
189 é usado para desenvolvimento, testes, commit e push; ele não deve executar containers deste
projeto.

1. Publique a alteração no GitHub e aguarde o workflow gerar a imagem imutável no GHCR.
2. No 153, mantenha arquivos persistentes em
   `/home/administrator/Desktop/codes/Painel_analise_vendas`.
3. Disponibilize `credential.json` em `credentials/` e os cadastros de usuários em
   `config_runtime/` dentro dessa raiz.
4. Configure no Portainer as variáveis de ambiente, principalmente as credenciais do Firebird.
5. Implante primeiro o `slack_combos`, que cria a rede externa `combo-audit-internal`.

O Compose publica somente o Painel em `8520`. A API de auditoria não possui mapeamento de porta e é
acessada internamente por `http://slack-combos:8080`. Cache, temporários, relatórios e dados locais
são montados fora da camada descartável do container, na raiz persistente do host 153. Operações de
início, parada e atualização devem ser feitas pelo Portainer.

No Linux, o arquivo Firebird protegido por DPAPI do Windows não pode ser usado. O container monta,
somente para leitura, o mesmo `combo_config.ini` operacional mantido fora do Git para o
`slack_combos`, em `/run/secrets/combo_config.ini`. Assim as credenciais não são duplicadas no
Portainer, na imagem ou nos logs.

### Git e entrega da imagem

O projeto usa repositório Git próprio. O fluxo segue o padrão do `ti_dinho_slack`: trabalhar em uma
branch curta, executar os testes, revisar segredos e o diff, integrar em `main` e acompanhar o GitHub
Actions. O workflow `.github/workflows/build.yml` publica no GHCR as tags `latest` e
`sha-<commit>` e atualiza o Compose para a tag imutável. O host de produção deve consumir o Compose
pelo Git/Portainer; não se deve copiar código manualmente nem editar o container em execução.

Para o uso diário, depois de editar e salvar os arquivos, basta executar na raiz:

```powershell
.\deploy.ps1
```

O comando pede a mensagem do commit, cria uma branch automaticamente quando necessário e executa o
fluxo completo de testes, commit, GitHub Actions e Portainer. Ele recusa o deploy quando não encontra
alterações salvas.

Depois de criar uma branch curta e concluir a alteração, o fluxo completo pode ser executado com:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\iniciar-alteracao.ps1 `
  -Branch "tipo/descricao-da-alteracao"
```

O comando acima exige uma árvore limpa, sincroniza `main` por fast-forward e cria a branch. Depois de
editar e salvar os arquivos, execute:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\commit-deploy.ps1 `
  -Message "Descreva a alteracao" `
  -ConfirmProduction
```

O script reutiliza, sem versionar, os tokens operacionais mantidos no ambiente do `ti_dinho_slack`,
aguarda o GitHub Actions e somente conclui quando a imagem do commit estiver saudável no servidor 153.

O repositório oficial é
[`CodesDinho/painel_analise_vendas`](https://github.com/CodesDinho/painel_analise_vendas), e as imagens
são publicadas como `ghcr.io/codesdinho/painel-analise-vendas`.

BigQuery procura a credencial nesta ordem: `GOOGLE_APPLICATION_CREDENTIALS`, `credentials/credential.json`, credencial compartilhada na pasta pai e ADC do Google. O projeto usa `dinho-dw.topsystem_silver.vendas` e `dinho-dw.topsystem_bronze.produto`.

O login reutiliza `../Painel_vendas/config/usuarios.json` enquanto não existir um `usuarios.json` próprio. Isso permite iniciar no servidor atual sem duplicar credenciais; para isolamento total, copie/recrie os usuários no novo arquivo (ele é ignorado pelo Git).

O conector Firebird está disponível em `conexoes.py` e aceita `ANALISE_VENDAS_CONFIG_FIREBIRD`, `config.ini` ou `config.ini.enc` protegido por DPAPI, inclusive a configuração compartilhada do painel original. As análises atuais usam BigQuery porque a consulta fornecida e as dimensões necessárias estão no DW; não há escrita em nenhum banco.

Validação rápida:

```powershell
python -m compileall -q .
python tests/test_calculos.py
python tests/test_combos.py
python tests/test_auditoria_combos.py
```

## Validação de regras de títulos de combos ativos

O menu **Validação de regras de títulos de combos ativos** consulta os combos vigentes diretamente no Firebird e é somente para conferência. Ao lado do título da tela, exibe indicadores do total de combos, títulos OK e títulos pendentes de correção, com destaque quando houver pendências. Permite pesquisar, filtrar pelas classificações existentes — mostrando a quantidade de combos ativos ao lado de cada opção — e verificar a conformidade dos títulos, mas não exibe nem permite editar a classificação na tabela. Alterações cadastrais e classificações devem ser realizadas diretamente no ERP; o painel não apresenta botão de salvamento nessa tela.

No início da tela **Documentação das análises**, o painel disponibiliza dois downloads. `DOCUMENTACAO_REGRAS_COMBOS.docx` centraliza as regras de negócio, validações e padrões de nomenclatura dos combos. `POP_Liberacao_de_Combos_SGQ.docx` contém o processo operacional completo de solicitação, análise, aprovação, execução, resposta no Slack e rastreabilidade.

As regras complementares do Painel de análise de vendas são principalmente regras de nomenclatura e ficam reunidas em uma única seção no documento de regras. O POP referencia a versão vigente desse documento ao executar as validações, sem duplicar os critérios normativos. Aprovações, alçadas e responsáveis pelo processo permanecem no POP.

## Criação de combos

O mesmo formulário é aberto pelo botão **Criar novo combo** ou pelos botões das análises de Positivação e Volume. Nessas análises, são transportados apenas os clientes únicos do resultado filtrado; a lista pode ser revisada e reduzida antes da prévia.

O código do novo combo não é informado pelo usuário: ele é cadastrado automaticamente pelo ERP. O formulário solicita somente os dados funcionais necessários, como nome, vigência, classificação, filiais, produtos/faixas e clientes.

O formulário valida cabeçalho, datas, produtos existentes, clientes, quantidades, valores brasileiros, duplicidades e conflitos de faixa. Também permite selecionar várias filiais ativas, planejadas em `COMBOFILIAL`. A prévia mostra grupos, produtos, clientes, filiais e tabelas planejadas.

A criação final está deliberadamente desabilitada. O levantamento do TOP encontrou regras que não podem ser inferidas com segurança: geração de `GRUPOCOMBO.CODIGO`, semântica de `GRUPOCOMBO.QTDE/BONIFICADO`, uso de `GRUPOCOMBODESCONTO` e flags funcionais do cabeçalho. Consulte [MAPEAMENTO_COMBOS_TOP.md](docs/operacao/MAPEAMENTO_COMBOS_TOP.md).

Falhas de validação/acesso ao TOP durante a preparação ficam em `dados_locais/combo_criacao_erros.jsonl`. O log contém etapa, mensagem sanitizada, usuário e data/hora, sem credenciais.

Somente usuários listados em `ANALISE_VENDAS_USUARIOS_CRIAR_COMBO` podem abrir a criação. Se a variável não estiver configurada, são aceitos os perfis Administrador, Admin, TI e Gerente comercial do cadastro já utilizado pelo login. Nenhuma senha é armazenada no código ou nos logs.

## Regras assumidas

- Positivação é por cliente + indústria, sem entrar em SKU.
- Volume usa `quantidade / produto.quantidade_compra`, conforme a query fornecida.
- As análises de positivação e volume exibem `tipo_analise`: `Compra indústria`, `Base televendas` ou `Indústria+televendas` quando o CLIFOR pertence aos dois conjuntos.
- A Base televendas reutiliza o semáforo verde do Painel_vendas: cliente ativo, `TIPO = 1`, sem vendedor BEES 2262 e `DATAMOVIMENTO` de 30 a 120 dias. Sem vendedor e sem rota são definidos pela ausência de vínculo em `FUNCIONARIOCLIFOR` e `ROTACLIFOR`.
- Estar na Base televendas apenas define a coorte. Os cálculos de queda de positivação e volume continuam usando o mesmo histórico BigQuery e as mesmas regras da Compra indústria.
- Na queda de positivação, o universo de clientes é cruzado com cada indústria selecionada. O cliente é elegível quando não comprou a indústria nos últimos dias definidos, inclusive quando nunca comprou essa indústria no histórico carregado. Estado, tipo de estabelecimento, equipe e carteira continuam respeitados.
- As regras analíticas de ausência de compra são destinadas somente aos combos classificados como Dormente positivação ou Dormente volume; não devem ser usadas para selecionar ou revisar combos de Rede, Manutenção, Tabela, MIX ou outras classificações.
- Padronização de títulos por estado: todo combo deve terminar em `PR`, `SC`, `RS` ou `SP`. Para as filiais atualmente mapeadas, combos liberados apenas nas filiais 3, 4, 5 e/ou 7 recebem `PR`; combos liberados apenas nas filiais 6 e/ou 8 recebem `SC`. Outros marcadores, como `M` e `VIN/ESP`, devem ficar antes do estado. Combos que misturem filiais de estados diferentes exigem revisão antes de renomear.

## Matriz de regras e responsabilidades

| ID | Tipo de Combo | Critério de Liberação | Permitido | Não Permitido / Restrição | Responsável |
|---:|---|---|---|---|---|
| 1 | Rede | Conforme cadastro comercial da rede | Título iniciado por `REDE` e terminado pelo estado | `REDE` fora do início ou estado fora do final | Gustavo |
| 2 | Manutenção | Solicitação pelo SharePoint e aprovação do responsável | `Produto / categorização / M / Estado` | Ausência de `M`, `M` depois do estado ou solicitação fora do fluxo | Fernando / Paulo / Gustavo |
| 3 | Vinhos / Espumantes / Água / Xarope | Regra universal: qualquer combo com ao menos um desses produtos exige IE válida do cliente para liberação, em todos os estados e classificações | Cliente com `CLIFOR.IE` preenchida e válida; nas análises de queda de positivação e de volume, a opção de processar somente válidos exclui os pares inválidos | Cliente com IE nula, vazia ou `ISENTO` nunca pode ser incluído | Responsável a definir |
| 4 | Dormente positivação | Cliente sem compra da indústria no período configurado, inclusive sem compra histórica da indústria | Título contendo `D POSITIVACAO` em qualquer posição, estado no final e cota máxima de 1 por cliente | Aplicar a outros tipos de combo; ausência do marcador; cota maior que 1 | Gustavo |
| 5 | Dormente volume | Regras de volume indicadas no arquivo do SharePoint | Título contendo `D VOLUME` em qualquer posição e estado no final | Aplicar fora das regras do SharePoint, ausência do marcador ou uso em outros tipos | Gustavo |

Carlos Pankratz é responsável exclusivamente pelos combos VCT; ele não é responsável geral por Manutenção nem pela regra universal de IE.

A aba `Validação de regras de títulos de combos ativos` calcula a conformidade do título. A coluna `Título OK` fica vermelha quando o nome não atende ao padrão da classificação, ao estado final ou ao marcador `VIN/ESP` aplicável.

### Regra universal de Inscrição Estadual

Antes de qualquer inclusão em `COMBOCLIFOR` ou `ITEMCOTACOMBOCLIENTE`, o painel verifica os produtos e cadastros de produto do combo. Se houver ao menos um item identificado como vinho, espumante, água ou xarope, cada cliente incluído deve possuir `CLIFOR.IE` preenchida com valor diferente de `ISENTO`. A regra vale para PR, SC e qualquer outro estado, bem como para Rede, Manutenção, Dormente positivação, Dormente volume e demais classificações. Nas inserções originadas das análises de queda de positivação e de volume, o usuário pode optar por excluir somente os pares combo/cliente sem IE válida e prosseguir com os válidos; a prévia lista os excluídos e a transação revalida a regra. Nos demais fluxos, qualquer par inválido bloqueia a inclusão inteira. Exclusões de vínculos existentes continuam permitidas.

Na **Inserção dinâmica de combos**, o filtro `IE válida` possui as opções `Todos`, `Sim` e `Não`. `Sim` seleciona IE preenchida e diferente de `ISENTO`; `Não` seleciona IE nula, vazia ou `ISENTO`. A IE do cliente também é apresentada na prévia. Esse filtro não elimina o bloqueio universal aplicado no momento da inserção quando o combo contém vinho, espumante, água ou xarope. A operação **Incluir** também cria as cotas ausentes em `ITEMCOTACOMBOCLIENTE`: informe uma quantidade positiva (padrão `1`), prepare a operação, confira separadamente os vínculos e as cotas e confirme. Os códigos de cota são herdados das filiais ativas do combo. Se `COMBOCLIFOR` já existir, somente a cota faltante é criada; registros existentes não são duplicados nem sobrescritos. Combos sem cotas vigentes são bloqueados. A opção **Inserir somente cotas** ignora os filtros de clientes, usa apenas os clientes já vinculados ao combo e possui garantia transacional de que nenhum registro será criado ou alterado em `COMBOCLIFOR`.

Quando a preparação informar **Combos sem filiais/cotas ativas configuradas**, a tela exibe e permite baixar um modelo SQL idempotente de `COMBOFILIAL`, acompanhado da consulta de conferência das cotas vigentes. O modelo usa o placeholder `<FILIAL>` e nunca cria ou prorroga registros de `COTA` automaticamente; essa definição deve ser revisada no ERP antes da execução.

Quando `POSITIVACAO` fizer parte do nome operacional de um combo de Manutenção, deve ficar próximo ao final: `Produto / categorização / VIN/ESP (quando já aplicável) / POSITIVACAO / M / Estado`. Esta regra não transforma o combo em Dormente positivação; Dormentes continuam identificados exclusivamente por `D POSITIVACAO`.

Combos de Manutenção devem ser identificados no ERP pelo marcador isolado `M` imediatamente antes do estado, inclusive quando antes apareciam como Não classificados por ausência desse marcador.

A autenticação de dois fatores é requisito obrigatório para operações de combos dormentes, mas sua implementação permanece pendente da definição do segundo fator e do canal corporativo (por exemplo, TOTP, e-mail ou provedor de identidade). Não deve ser simulada apenas com uma segunda senha no mesmo cadastro.
- O filtro de carteira de vendedor atua somente sobre `Compra indústria`. As origens `Base televendas` e `Indústria+televendas` são sempre preservadas, inclusive quando o usuário seleciona com ou sem vendedor.
- O botão `Inserir clientes e cotas em combos existentes` usa os clientes únicos do resultado filtrado em tela. Aceita múltiplos combos vigentes, ignora vínculos já existentes e exige preparação e confirmação explícita. Grava `COMBOCLIFOR` e `ITEMCOTACOMBOCLIENTE` na mesma transação; a quantidade de cotas começa em 1 e pode ser editada.
- É permitido cadastrar clientes em todos os combos dormentes, tanto Dormente positivação quanto Dormente volume, pelos resultados das análises ou pela inclusão dinâmica.
- Os códigos de cota são herdados das cotas já configuradas no combo; combos sem cota são bloqueados.
- O menu `Conferência de combos` mostra clientes/cotas e produtos/valores dos combos selecionados.
- Mix é a quantidade distinta de SKUs por equipe + indústria.
- Mtrix depende do arquivo oficial revisado pelo Gilmar e permite mapear suas três colunas na tela.

Na **Inserção dinâmica de combos**, o filtro múltiplo **Vendas — Classe de produto** lista as classes ativas do cadastro `CLASSE`. Ao selecionar uma ou mais classes, somente clientes com pedido faturado, não cancelado e com item de produto ligado por `PRODUTO.CLASSE` dentro do período informado são considerados. O filtro também é aplicado quando a opção Venda permanece em **Todos** e pode ser combinado com Fornecedor, Marca e Produto.

## Pagamentos + usados e bloqueios de condições de pagamento por tipo estabelecimento X equipe

O menu calcula, por cliente com compras no período, a condição e a forma de pagamento mais usadas por quantidade de pedidos distintos. O período padrão é de seis meses e pode ser alterado. O primeiro fluxo atualiza os padrões `CLIFOR.CONDICAOPAGAMENTO` e `CLIFOR.FORMAPAGAMENTO`; o segundo insere somente bloqueios ausentes em `CLIFORCONDICAOPAGAMENTO`, sem remover bloqueios existentes.

- Multicanal: tipos 21, 22, 23, 24, 25, 26, 31, 32, 33, 34, 39, 49, 71, 72, 73, 93, 96, 97 e 201.
- Key Off: tipos 35 e 38.
- Key On/On Trade: tipos 41, 42, 43, 44, 45, 46, 51, 52, 53, 61, 62, 63, 65, 81, 82, 83, 84, 85, 86, 91 e 92.
- Para CPF, Multicanal e Key On/On Trade, condições com `PRZ` permanecem liberadas e condições sem `PRZ` são bloqueadas, exceto a condição 100 protegida globalmente.
- Para Key Off, condições com `PRZ` são bloqueadas.
- Registros existentes em `CLIFORCONDICAOPAGAMENTO` são sempre preservados.
- Regra 7: condições sem `PRZ` não são bloqueadas nos tipos de estabelecimento 40, 49, 36, 34, 47, 35, 38, 33 e 39. Os tipos Key Off 35 e 38 continuam bloqueando apenas condições com `PRZ`.
- Regra 8: condições de pagamento inativas são exibidas separadamente para conferência e nunca são inseridas como bloqueio; a transação revalida `CONDICAOPAGAMENTO.ATIVO = 'S'`.
- Regra 9: para Multicanal e Key On/On Trade, condições `PRZ` — inclusive prazos até 28 dias — e condições à vista permanecem liberadas e não são recriadas como bloqueio. A preservação de registros existentes não equivale a liberação: um bloqueio preexistente precisa ser removido operacionalmente para deixar de restringir o cliente.
- Regra 10: a condição `100` (`A VISTA`) é protegida globalmente e nunca é inserida como bloqueio para nenhum cliente. A prévia mostra quantos novos bloqueios foram evitados e quantos bloqueios preexistentes serão preservados.
- Regra 5: a tabela de preço 480 (Atacado) e seus vínculos são preservados; o fluxo não insere, altera nem remove registros nela.
- Regra 6: clientes vinculados aos vendedores 1929 ou 187 — Atacado não recebem nenhuma atualização, restrição ou bloqueio. A tela mostra o total e uma aba com código e nome para revisão.

Depois de preparar as duas etapas, a tela apresenta o **Resumo documental dinâmico das Etapas 1 e 2**. Datas, clientes, pedidos, alterações, proteções e bloqueios por regra são calculados a partir das prévias atuais. O resumo pode ser baixado em TXT para documentação ou envio por e-mail; portanto, não se deve reutilizar números de uma execução anterior.

### Snapshot de restauração de 31/08/2026

Os scripts e manifestos de referência da virada para 01/09/2026 00:00, capturados tecnicamente em 31/08/2026 às 23:56:07, estão em `dados_operacionais/snapshots/restore_dados_etapas_1_2_20260831/`. Consulte primeiro o `README.md` dessa pasta. O snapshot cobre 15.790 clientes da Etapa 1 e 693.645 pares cliente × condição da Etapa 2. Os dois SQLs também aparecem como downloads abaixo de **Gerar analise de dados para etapas 1 e 2**. Esses arquivos restauram apenas o escopo das prévias daquela captura e não substituem um backup nativo do Firebird.

### Liberação temporária de 01/09/2026

Em 01/09/2026 às 07:33:13, foram removidos temporariamente 11.541 bloqueios de 123 clientes, limitados aos pares que estavam ausentes no snapshot anterior à Etapa 2. As evidências e o SQL idempotente de reaplicação estão em `liberacao_temporaria_bloqueios_20260901_073313/`. Os códigos 5416, 186377 e 1328884 não pertenciam ao manifesto e não tiveram bloqueios removidos.

A reaplicação consolidada foi concluída em 01/09/2026 às 09:15:14. Dos 12.141 bloqueios temporariamente removidos em todas as operações, 11.930 foram reaplicados e validados. Outros 211 não foram recriados por serem condições à vista excluídas pela regra atual. As evidências estão em `reaplicacao_bloqueios_20260901_091514/`.

### Acesso operacional do Faturamento

O perfil `Faturamento` possui acesso exclusivo à tela **Liberação temporária para faturamento** e não visualiza os demais menus. A tela recebe uma lista de clientes, prepara apenas os bloqueios existentes originados pelo manifesto da Etapa 2 e exige confirmação antes da retirada.

Cada operação fica registrada em `temporarios/`, com usuário, data/hora, clientes, pares removidos e status persistente `PENDENTE_REAPLICACAO` ou `REAPLICADA`. O painel consulta o Firebird ao abrir a pendência e mostra por cliente quantos bloqueios continuam ausentes e quantos já estão presentes. Assim, uma liberação esquecida continua visível nos dias seguintes.

Antes da reaplicação, o sistema recalcula as regras vigentes da Etapa 2. A prévia separa os bloqueios que serão recriados, os que já existem e os que não devem voltar pelas regras atuais. A gravação é transacional, validada após o commit e atualiza o responsável e o horário da finalização.

A credencial específica é mantida em `usuarios_faturamento.json`, ignorado pelo Git, com senha armazenada exclusivamente por hash PBKDF2. O utilitário `criar_usuario_faturamento.py` gera ou redefine a senha inicial da Zeneide.

### Reversão geral da Etapa 2 — 01/09/2026

Por solicitação da direção, todos os 693.645 pares cliente × condição documentados no manifesto original da Etapa 2 foram conferidos. Na execução, 669.016 bloqueios ainda estavam presentes e foram removidos em uma única transação; 24.629 já estavam ausentes, incluindo integralmente os 414 bloqueios da última lista de seis clientes. A validação final encontrou zero bloqueios remanescentes dentro do manifesto. As evidências estão em `temporarios/reversao_etapa_2_20260901_140808_executada/`.

O Ranking de SKUs contempla apenas Conveniência (21, 22, 23, 24), Mercado de Bebidas (39, 71), Distribuidora (72) e Mercados (33, 34, 35, 38). Os demais tipos relacionados acima são exibidos como extras ainda não contemplados.
