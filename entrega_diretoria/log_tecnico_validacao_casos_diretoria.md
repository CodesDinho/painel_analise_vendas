# Log técnico da validação dos casos apresentados à Diretoria

Comando executado:

```text
/combos-auditar 240034782, 240031841, 240031867, 240035662, 240035672, 240035663, 240035670, 240035537, 240035441, 240032879, 240035106, 240032677
```

## Retorno completo

```text
Auditoria: 49 apontamento(s) | 0 erro(s), 27 conflito(s), 10 alerta(s), 12 informativo(s)
:warning: ALERTA | combo 240034782 | produto 2793 | BRINDE_UNICO_SEM_ALTERNATIVA
Grupo bonificado possui um unico SKU; nao ha substituto cadastrado.
Acao: Verificar estoque por filial e decidir entre manter, cadastrar alternativa ou suspender o combo.
:warning: ALERTA | combo 240034782 | QUANTIDADE_FORA_MULTIPLO_CARREGAMENTO
Grupo 6905 exige 1 unidade(s), quantidade que nao e multipla da caixa 6, em 1 produto(s).
Produtos: 2793
Acao: Verificar no TOP se o produto permite fracionamento; se nao permitir, corrigir grupo ou carregamento com aprovacao.
:information_source: INFORMATIVO | combo 240034782 | REFERENCIA_PRECO_NAO_DETERMINADA
Nao foi identificada referencia aprovada para validar o preco de 1 produto(s). A referencia pode ser uma tabela aplicavel ou um valor comercial definido pela Diretoria/Gerencia; isso nao e uma inconsistencia confirmada.
Produtos: 2793
Acao: Confirmar se o combo deve seguir uma tabela ou um valor especifico aprovado pela Diretoria/Gerencia antes de alterar o ERP.
:information_source: INFORMATIVO | combo 240031841 | REFERENCIA_PRECO_NAO_DETERMINADA
Nao foi identificada referencia aprovada para validar o preco de 9 produto(s). A referencia pode ser uma tabela aplicavel ou um valor comercial definido pela Diretoria/Gerencia; isso nao e uma inconsistencia confirmada.
Produtos: 2449, 3025, 3444, 3575, 3668, 3725, 4139, 4140, 4296
Acao: Confirmar se o combo deve seguir uma tabela ou um valor especifico aprovado pela Diretoria/Gerencia antes de alterar o ERP.
:twisted_rightwards_arrows: CONFLITO | combo 240031867 | conflito com 240031842 | COMBOS_ATIVOS_SOBREPOSTOS
Combos 240031867 e 240031842 podem disputar 9 produto(s), quantidade, filial e publico.
Produtos: 2449, 3025, 3444, 3575, 3668, 3725, 4139, 4140, 4296
Acao: A Direcao deve definir qual combo prevalece ou separar vigencia, quantidade, filial ou publico.
:information_source: INFORMATIVO | combo 240031867 | REFERENCIA_PRECO_NAO_DETERMINADA
Nao foi identificada referencia aprovada para validar o preco de 10 produto(s). A referencia pode ser uma tabela aplicavel ou um valor comercial definido pela Diretoria/Gerencia; isso nao e uma inconsistencia confirmada.
Produtos: 2449, 3025, 3444, 3575, 3668, 3725, 4139, 4140, 4296, 9955
Acao: Confirmar se o combo deve seguir uma tabela ou um valor especifico aprovado pela Diretoria/Gerencia antes de alterar o ERP.
:twisted_rightwards_arrows: CONFLITO | combo 240035662 | conflito com 240033751 | COMBOS_ATIVOS_SOBREPOSTOS
Combos 240035662 e 240033751 podem disputar 10 produto(s), quantidade, filial e publico.
Produtos: 1901, 1902, 1903, 1904, 1905, 1916, 1918, 2994, 9529, 9701
Acao: A Direcao deve definir qual combo prevalece ou separar vigencia, quantidade, filial ou publico.
:twisted_rightwards_arrows: CONFLITO | combo 240035662 | conflito com 240035432 | COMBOS_ATIVOS_SOBREPOSTOS
Combos 240035662 e 240035432 podem disputar 10 produto(s), quantidade, filial e publico.
Produtos: 1901, 1902, 1903, 1904, 1905, 1916, 1918, 2994, 5007, 9529
Acao: A Direcao deve definir qual combo prevalece ou separar vigencia, quantidade, filial ou publico.
:twisted_rightwards_arrows: CONFLITO | combo 240035662 | conflito com 240035619 | COMBOS_ATIVOS_SOBREPOSTOS
Combos 240035662 e 240035619 podem disputar 10 produto(s), quantidade, filial e publico.
Produtos: 1901, 1902, 1903, 1904, 1905, 1916, 1918, 2994, 9529, 9701
Acao: A Direcao deve definir qual combo prevalece ou separar vigencia, quantidade, filial ou publico.
:twisted_rightwards_arrows: CONFLITO | combo 240035662 | conflito com 240035620 | COMBOS_ATIVOS_SOBREPOSTOS
Combos 240035662 e 240035620 podem disputar 11 produto(s), quantidade, filial e publico.
Produtos: 1901, 1902, 1903, 1904, 1905, 1916, 1918, 2994, 5007, 9529 (+1)
[12h55]Acao: A Direcao deve definir qual combo prevalece ou separar vigencia, quantidade, filial ou publico.
:twisted_rightwards_arrows: CONFLITO | combo 240035662 | conflito com 240035667 | COMBOS_ATIVOS_SOBREPOSTOS
Combos 240035662 e 240035667 podem disputar 11 produto(s), quantidade, filial e publico.
Produtos: 1901, 1902, 1903, 1904, 1905, 1916, 1918, 2994, 5007, 9529 (+1)
Acao: A Direcao deve definir qual combo prevalece ou separar vigencia, quantidade, filial ou publico.
:twisted_rightwards_arrows: CONFLITO | combo 240035662 | conflito com 240035672 | COMBOS_ATIVOS_SOBREPOSTOS
Combos 240035662 e 240035672 podem disputar 11 produto(s), quantidade, filial e publico.
Produtos: 1901, 1902, 1903, 1904, 1905, 1916, 1918, 2994, 5007, 9529 (+1)
Acao: A Direcao deve definir qual combo prevalece ou separar vigencia, quantidade, filial ou publico.
:warning: ALERTA | combo 240035662 | QUANTIDADE_FORA_MULTIPLO_CARREGAMENTO
Grupo 8373 exige 1 unidade(s), quantidade que nao e multipla da caixa 12, em 11 produto(s).
Produtos: 1901, 1902, 1903, 1904, 1905, 1916, 1918, 2994, 5007, 9529 (+1)
Acao: Verificar no TOP se o produto permite fracionamento; se nao permitir, corrigir grupo ou carregamento com aprovacao.
:information_source: INFORMATIVO | combo 240035662 | REFERENCIA_PRECO_NAO_DETERMINADA
Nao foi identificada referencia aprovada para validar o preco de 11 produto(s). A referencia pode ser uma tabela aplicavel ou um valor comercial definido pela Diretoria/Gerencia; isso nao e uma inconsistencia confirmada.
Produtos: 1901, 1902, 1903, 1904, 1905, 1916, 1918, 2994, 5007, 9529 (+1)
Acao: Confirmar se o combo deve seguir uma tabela ou um valor especifico aprovado pela Diretoria/Gerencia antes de alterar o ERP.
:twisted_rightwards_arrows: CONFLITO | combo 240035672 | conflito com 240033751 | COMBOS_ATIVOS_SOBREPOSTOS
Combos 240035672 e 240033751 podem disputar 10 produto(s), quantidade, filial e publico.
Produtos: 1901, 1902, 1903, 1904, 1905, 1916, 1918, 2994, 9529, 9701
Acao: A Direcao deve definir qual combo prevalece ou separar vigencia, quantidade, filial ou publico.
:twisted_rightwards_arrows: CONFLITO | combo 240035672 | conflito com 240035432 | COMBOS_ATIVOS_SOBREPOSTOS
Combos 240035672 e 240035432 podem disputar 10 produto(s), quantidade, filial e publico.
Produtos: 1901, 1902, 1903, 1904, 1905, 1916, 1918, 2994, 5007, 9529
Acao: A Direcao deve definir qual combo prevalece ou separar vigencia, quantidade, filial ou publico.
:twisted_rightwards_arrows: CONFLITO | combo 240035672 | conflito com 240035619 | COMBOS_ATIVOS_SOBREPOSTOS
Combos 240035672 e 240035619 podem disputar 10 produto(s), quantidade, filial e publico.
Produtos: 1901, 1902, 1903, 1904, 1905, 1916, 1918, 2994, 9529, 9701
Acao: A Direcao deve definir qual combo prevalece ou separar vigencia, quantidade, filial ou publico.
:twisted_rightwards_arrows: CONFLITO | combo 240035672 | conflito com 240035620 | COMBOS_ATIVOS_SOBREPOSTOS
Combos 240035672 e 240035620 podem disputar 11 produto(s), quantidade, filial e publico.
Produtos: 1901, 1902, 1903, 1904, 1905, 1916, 1918, 2994, 5007, 9529 (+1)
Acao: A Direcao deve definir qual combo prevalece ou separar vigencia, quantidade, filial ou publico.
:twisted_rightwards_arrows: CONFLITO | combo 240035672 | conflito com 240035667 | COMBOS_ATIVOS_SOBREPOSTOS
Combos 240035672 e 240035667 podem disputar 11 produto(s), quantidade, filial e publico.
Produtos: 1901, 1902, 1903, 1904, 1905, 1916, 1918, 2994, 5007, 9529 (+1)
Acao: A Direcao deve definir qual combo prevalece ou separar vigencia, quantidade, filial ou publico.
:warning: ALERTA | combo 240035672 | QUANTIDADE_FORA_MULTIPLO_CARREGAMENTO
Grupo 8387 exige 1 unidade(s), quantidade que nao e multipla da caixa 12, em 11 produto(s).
Produtos: 1901, 1902, 1903, 1904, 1905, 1916, 1918, 2994, 5007, 9529 (+1)
[12h55]Acao: Verificar no TOP se o produto permite fracionamento; se nao permitir, corrigir grupo ou carregamento com aprovacao.
:information_source: INFORMATIVO | combo 240035672 | REFERENCIA_PRECO_NAO_DETERMINADA
Nao foi identificada referencia aprovada para validar o preco de 11 produto(s). A referencia pode ser uma tabela aplicavel ou um valor comercial definido pela Diretoria/Gerencia; isso nao e uma inconsistencia confirmada.
Produtos: 1901, 1902, 1903, 1904, 1905, 1916, 1918, 2994, 5007, 9529 (+1)
Acao: Confirmar se o combo deve seguir uma tabela ou um valor especifico aprovado pela Diretoria/Gerencia antes de alterar o ERP.
:twisted_rightwards_arrows: CONFLITO | combo 240035663 | conflito com 240035278 | COMBOS_ATIVOS_SOBREPOSTOS
Combos 240035663 e 240035278 podem disputar 8 produto(s), quantidade, filial e publico.
Produtos: 1910, 1911, 1913, 1914, 1915, 3039, 3275, 3512
Acao: A Direcao deve definir qual combo prevalece ou separar vigencia, quantidade, filial ou publico.
:twisted_rightwards_arrows: CONFLITO | combo 240035663 | conflito com 240035432 | COMBOS_ATIVOS_SOBREPOSTOS
Combos 240035663 e 240035432 podem disputar 7 produto(s), quantidade, filial e publico.
Produtos: 1910, 1911, 1913, 1914, 1915, 3039, 3275
Acao: A Direcao deve definir qual combo prevalece ou separar vigencia, quantidade, filial ou publico.
:twisted_rightwards_arrows: CONFLITO | combo 240035663 | conflito com 240035619 | COMBOS_ATIVOS_SOBREPOSTOS
Combos 240035663 e 240035619 podem disputar 9 produto(s), quantidade, filial e publico.
Produtos: 1910, 1911, 1913, 1914, 1915, 3039, 3275, 3512, 10370
Acao: A Direcao deve definir qual combo prevalece ou separar vigencia, quantidade, filial ou publico.
:twisted_rightwards_arrows: CONFLITO | combo 240035663 | conflito com 240035620 | COMBOS_ATIVOS_SOBREPOSTOS
Combos 240035663 e 240035620 podem disputar 9 produto(s), quantidade, filial e publico.
Produtos: 1910, 1911, 1913, 1914, 1915, 3039, 3275, 3512, 10370
Acao: A Direcao deve definir qual combo prevalece ou separar vigencia, quantidade, filial ou publico.
:twisted_rightwards_arrows: CONFLITO | combo 240035663 | conflito com 240035667 | COMBOS_ATIVOS_SOBREPOSTOS
Combos 240035663 e 240035667 podem disputar 9 produto(s), quantidade, filial e publico.
Produtos: 1910, 1911, 1913, 1914, 1915, 3039, 3275, 3512, 10370
Acao: A Direcao deve definir qual combo prevalece ou separar vigencia, quantidade, filial ou publico.
:twisted_rightwards_arrows: CONFLITO | combo 240035663 | conflito com 240035670 | COMBOS_ATIVOS_SOBREPOSTOS
Combos 240035663 e 240035670 podem disputar 9 produto(s), quantidade, filial e publico.
Produtos: 1910, 1911, 1913, 1914, 1915, 3039, 3275, 3512, 10370
Acao: A Direcao deve definir qual combo prevalece ou separar vigencia, quantidade, filial ou publico.
:warning: ALERTA | combo 240035663 | QUANTIDADE_FORA_MULTIPLO_CARREGAMENTO
Grupo 8375 exige 1 unidade(s), quantidade que nao e multipla da caixa 6, em 1 produto(s).
Produtos: 10370
Acao: Verificar no TOP se o produto permite fracionamento; se nao permitir, corrigir grupo ou carregamento com aprovacao.
:warning: ALERTA | combo 240035663 | QUANTIDADE_FORA_MULTIPLO_CARREGAMENTO
Grupo 8375 exige 1 unidade(s), quantidade que nao e multipla da caixa 12, em 8 produto(s).
Produtos: 1910, 1911, 1913, 1914, 1915, 3039, 3275, 3512
Acao: Verificar no TOP se o produto permite fracionamento; se nao permitir, corrigir grupo ou carregamento com aprovacao.
:information_source: INFORMATIVO | combo 240035663 | REFERENCIA_PRECO_NAO_DETERMINADA
Nao foi identificada referencia aprovada para validar o preco de 9 produto(s). A referencia pode ser uma tabela aplicavel ou um valor comercial definido pela Diretoria/Gerencia; isso nao e uma inconsistencia confirmada.
Produtos: 1910, 1911, 1913, 1914, 1915, 3039, 3275, 3512, 10370
[12h55]Acao: Confirmar se o combo deve seguir uma tabela ou um valor especifico aprovado pela Diretoria/Gerencia antes de alterar o ERP.
:twisted_rightwards_arrows: CONFLITO | combo 240035670 | conflito com 240035278 | COMBOS_ATIVOS_SOBREPOSTOS
Combos 240035670 e 240035278 podem disputar 10 produto(s), quantidade, filial e publico.
Produtos: 1910, 1911, 1913, 1914, 1915, 3039, 3275, 3512, 9617, 9671
Acao: A Direcao deve definir qual combo prevalece ou separar vigencia, quantidade, filial ou publico.
:twisted_rightwards_arrows: CONFLITO | combo 240035670 | conflito com 240035432 | COMBOS_ATIVOS_SOBREPOSTOS
Combos 240035670 e 240035432 podem disputar 7 produto(s), quantidade, filial e publico.
Produtos: 1910, 1911, 1913, 1914, 1915, 3039, 3275
Acao: A Direcao deve definir qual combo prevalece ou separar vigencia, quantidade, filial ou publico.
:twisted_rightwards_arrows: CONFLITO | combo 240035670 | conflito com 240035619 | COMBOS_ATIVOS_SOBREPOSTOS
Combos 240035670 e 240035619 podem disputar 9 produto(s), quantidade, filial e publico.
Produtos: 1910, 1911, 1913, 1914, 1915, 3039, 3275, 3512, 10370
Acao: A Direcao deve definir qual combo prevalece ou separar vigencia, quantidade, filial ou publico.
:twisted_rightwards_arrows: CONFLITO | combo 240035670 | conflito com 240035620 | COMBOS_ATIVOS_SOBREPOSTOS
Combos 240035670 e 240035620 podem disputar 9 produto(s), quantidade, filial e publico.
Produtos: 1910, 1911, 1913, 1914, 1915, 3039, 3275, 3512, 10370
Acao: A Direcao deve definir qual combo prevalece ou separar vigencia, quantidade, filial ou publico.
:twisted_rightwards_arrows: CONFLITO | combo 240035670 | conflito com 240035664 | COMBOS_ATIVOS_SOBREPOSTOS
Combos 240035670 e 240035664 podem disputar 4 produto(s), quantidade, filial e publico.
Produtos: 9599, 9600, 9601, 9602
Acao: A Direcao deve definir qual combo prevalece ou separar vigencia, quantidade, filial ou publico.
:twisted_rightwards_arrows: CONFLITO | combo 240035670 | conflito com 240035667 | COMBOS_ATIVOS_SOBREPOSTOS
Combos 240035670 e 240035667 podem disputar 19 produto(s), quantidade, filial e publico.
Produtos: 1910, 1911, 1913, 1914, 1915, 3039, 3275, 3424, 3511, 3512 (+9)
Acao: A Direcao deve definir qual combo prevalece ou separar vigencia, quantidade, filial ou publico.
:warning: ALERTA | combo 240035670 | QUANTIDADE_FORA_MULTIPLO_CARREGAMENTO
Grupo 8382 exige 12 unidade(s), quantidade que nao e multipla da caixa 24, em 1 produto(s).
Produtos: 3511
Acao: Verificar no TOP se o produto permite fracionamento; se nao permitir, corrigir grupo ou carregamento com aprovacao.
:warning: ALERTA | combo 240035670 | QUANTIDADE_FORA_MULTIPLO_CARREGAMENTO
Grupo 8383 exige 1 unidade(s), quantidade que nao e multipla da caixa 6, em 5 produto(s).
Produtos: 9599, 9600, 9601, 9602, 10370
Acao: Verificar no TOP se o produto permite fracionamento; se nao permitir, corrigir grupo ou carregamento com aprovacao.
:warning: ALERTA | combo 240035670 | QUANTIDADE_FORA_MULTIPLO_CARREGAMENTO
Grupo 8383 exige 1 unidade(s), quantidade que nao e multipla da caixa 12, em 13 produto(s).
Produtos: 1910, 1911, 1913, 1914, 1915, 3039, 3275, 3424, 3512, 3754 (+3)
Acao: Verificar no TOP se o produto permite fracionamento; se nao permitir, corrigir grupo ou carregamento com aprovacao.
:warning: ALERTA | combo 240035670 | QUANTIDADE_FORA_MULTIPLO_CARREGAMENTO
Grupo 8383 exige 1 unidade(s), quantidade que nao e multipla da caixa 24, em 1 produto(s).
Produtos: 3511
Acao: Verificar no TOP se o produto permite fracionamento; se nao permitir, corrigir grupo ou carregamento com aprovacao.
:information_source: INFORMATIVO | combo 240035670 | REFERENCIA_PRECO_NAO_DETERMINADA
Nao foi identificada referencia aprovada para validar o preco de 19 produto(s). A referencia pode ser uma tabela aplicavel ou um valor comercial definido pela Diretoria/Gerencia; isso nao e uma inconsistencia confirmada.[12h55]Produtos: 1910, 1911, 1913, 1914, 1915, 3039, 3275, 3424, 3511, 3512 (+9)
Acao: Confirmar se o combo deve seguir uma tabela ou um valor especifico aprovado pela Diretoria/Gerencia antes de alterar o ERP.
:twisted_rightwards_arrows: CONFLITO | combo 240035537 | conflito com 240035432 | COMBOS_ATIVOS_SOBREPOSTOS
Combos 240035537 e 240035432 podem disputar 1 produto(s), quantidade, filial e publico.
Produtos: 5171
Acao: A Direcao deve definir qual combo prevalece ou separar vigencia, quantidade, filial ou publico.
:information_source: INFORMATIVO | combo 240035537 | REFERENCIA_PRECO_NAO_DETERMINADA
Nao foi identificada referencia aprovada para validar o preco de 16 produto(s). A referencia pode ser uma tabela aplicavel ou um valor comercial definido pela Diretoria/Gerencia; isso nao e uma inconsistencia confirmada.
Produtos: 5169, 5171, 5172, 5176, 10603, 10604, 10605, 10637, 10643, 10647 (+6)
Acao: Confirmar se o combo deve seguir uma tabela ou um valor especifico aprovado pela Diretoria/Gerencia antes de alterar o ERP.
:twisted_rightwards_arrows: CONFLITO | combo 240035441 | conflito com 240035432 | COMBOS_ATIVOS_SOBREPOSTOS
Combos 240035441 e 240035432 podem disputar 1 produto(s), quantidade, filial e publico.
Produtos: 5171
Acao: A Direcao deve definir qual combo prevalece ou separar vigencia, quantidade, filial ou publico.
:information_source: INFORMATIVO | combo 240035441 | REFERENCIA_PRECO_NAO_DETERMINADA
Nao foi identificada referencia aprovada para validar o preco de 16 produto(s). A referencia pode ser uma tabela aplicavel ou um valor comercial definido pela Diretoria/Gerencia; isso nao e uma inconsistencia confirmada.
Produtos: 5169, 5171, 5172, 5176, 10603, 10604, 10605, 10637, 10643, 10647 (+6)
Acao: Confirmar se o combo deve seguir uma tabela ou um valor especifico aprovado pela Diretoria/Gerencia antes de alterar o ERP.
:information_source: INFORMATIVO | combo 240032879 | REFERENCIA_PRECO_NAO_DETERMINADA
Nao foi identificada referencia aprovada para validar o preco de 6 produto(s). A referencia pode ser uma tabela aplicavel ou um valor comercial definido pela Diretoria/Gerencia; isso nao e uma inconsistencia confirmada.
Produtos: 591, 592, 593, 596, 4326, 4485
Acao: Confirmar se o combo deve seguir uma tabela ou um valor especifico aprovado pela Diretoria/Gerencia antes de alterar o ERP.
:information_source: INFORMATIVO | combo 240035106 | REFERENCIA_PRECO_NAO_DETERMINADA
Nao foi identificada referencia aprovada para validar o preco de 5 produto(s). A referencia pode ser uma tabela aplicavel ou um valor comercial definido pela Diretoria/Gerencia; isso nao e uma inconsistencia confirmada.
Produtos: 9963, 9964, 9965, 9966, 9967
Acao: Confirmar se o combo deve seguir uma tabela ou um valor especifico aprovado pela Diretoria/Gerencia antes de alterar o ERP.
:twisted_rightwards_arrows: CONFLITO | combo 240032677 | conflito com 240035432 | COMBOS_ATIVOS_SOBREPOSTOS
Combos 240032677 e 240035432 podem disputar 2 produto(s), quantidade, filial e publico.
Produtos: 5178, 10634
Acao: A Direcao deve definir qual combo prevalece ou separar vigencia, quantidade, filial ou publico.
:information_source: INFORMATIVO | combo 240032677 | REFERENCIA_PRECO_NAO_DETERMINADA
Nao foi identificada referencia aprovada para validar o preco de 11 produto(s). A referencia pode ser uma tabela aplicavel ou um valor comercial definido pela Diretoria/Gerencia; isso nao e uma inconsistencia confirmada.
Produtos: 5173, 5174, 5178, 5180, 10600, 10601, 10602, 10634, 10636, 10921 (+1)
Acao: Confirmar se o combo deve seguir uma tabela ou um valor especifico aprovado pela Diretoria/Gerencia antes de alterar o ERP.
```

