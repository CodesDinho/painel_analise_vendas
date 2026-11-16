# Padrão para análises extras

Esta pasta contém funcionalidades independentes que são acopladas ao painel principal.
Cada análise possui interface, consultas, cálculos, exportações e testes próprios, mas reutiliza
autenticação, conexões e configuração do projeto.

## Estrutura recomendada

```text
analises_extras/
├── registro.py
└── nome_da_analise/
    ├── __init__.py
    ├── pagina.py
    ├── consultas.py
    ├── calculos.py
    ├── exportacoes.py
    ├── README.md
    └── testes/
        └── test_nome_da_analise.py
```

Arquivos sem necessidade real podem ser omitidos. Evite concentrar novas análises no `main.py`.

## Passo a passo para o desenvolvedor

1. Copie a pasta `analises_extras/modelo/` para `analises_extras/nome_da_analise/`.
2. Renomeie `render_analise_modelo()` para uma função exclusiva, por exemplo
   `render_nome_da_analise()`.
3. Implemente a tela em `pagina.py`. Quando o módulo crescer, separe consultas, cálculos e
   exportações nos arquivos recomendados acima.
4. Reutilize as conexões centrais de `conexoes.py`; não crie credenciais, arquivos de configuração
   ou clientes de banco paralelos.
5. Reutilize a autenticação e as permissões do painel. O usuário atual está disponível em
   `st.session_state.get("usuario")`.
6. Prefixe todas as chaves do Streamlit com a chave da análise, por exemplo
   `nome_da_analise_filtro` e `nome_da_analise_resultado`.
7. Exporte a função de entrada no `__init__.py` do pacote.
8. Registre a análise explicitamente em `analises_extras/registro.py`, conforme o exemplo abaixo.
9. Crie testes para regras, cálculos, normalizações e arquivos exportados.
10. Execute as validações indicadas neste documento e abra a análise pelo menu
    **Análises extras**.

O desenvolvedor não deve alterar o bloco de menu no `main.py`: o menu é montado automaticamente a
partir de `ANALISES_EXTRAS`.

## Contrato obrigatório

O pacote deve exportar uma função de renderização sem argumentos:

```python
def render_nome_da_analise() -> None:
    ...
```

O módulo deve ser registrado explicitamente em `analises_extras/registro.py`:

```python
from .nome_da_analise import render_nome_da_analise

AnaliseExtra(
    chave="nome_da_analise",
    titulo="Nome exibido no menu",
    destino="11. Nome da análise",
    renderizar=render_nome_da_analise,
)
```

Somente análises registradas aparecem no menu. Não há descoberta ou execução automática de pastas.

## Recursos compartilhados

- BigQuery: `from conexoes import cliente_bigquery`
- Firebird: `from conexoes import cliente_firebird`
- Usuário atual: `st.session_state.get("usuario")`
- Autorização: reutilize as funções existentes em `autenticacao.py`
- Cache: use `st.cache_data` em consultas somente leitura

Não crie outro login, não copie credenciais e não mantenha `config.ini`, `.env`, tokens ou senhas
dentro da pasta da análise.

## Regras de isolamento

1. A importação do módulo não pode consultar banco, gravar arquivo nem renderizar Streamlit.
2. Consultas ficam em funções e devem declarar claramente se são somente leitura.
3. Escritas exigem prévia, confirmação explícita, autorização e transação.
4. Chaves de `session_state` devem começar com a chave da análise.
5. Arquivos temporários e operacionais não devem ser versionados.
6. Exportações devem ser produzidas em memória com `BytesIO` quando possível.
7. O `main.py` deve conhecer apenas o registro, nunca detalhes internos da análise.

## Validação antes da entrega

```powershell
python -m compileall -q .
python testes_calculos.py
python testes_combos.py
```

Acrescente testes específicos para cálculos, normalizações, consultas montadas e estrutura dos
arquivos exportados. Valide também a abertura da tela pelo menu **Análises extras**.

## Exemplo disponível

`analises_extras/modelo/pagina.py` é um esqueleto não registrado. A implementação real de
referência está em `analises_extras/pernod_reembolso/`.

## O que entregar

- a nova pasta dentro de `analises_extras/`;
- o novo item em `analises_extras/registro.py`;
- testes específicos da análise;
- README próprio quando houver regras de negócio, fontes ou operação que precisem ser explicadas;
- confirmação dos comandos de validação executados e das pendências encontradas.

