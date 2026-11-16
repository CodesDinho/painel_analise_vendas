# Análise Pernod Reembolso

Módulo independente registrado no grupo **Análises extras**.

- Entrada da tela: `pagina.py::render_analise_pernod_reembolso`
- Fontes: planilha Pernod, BigQuery e cadastro Firebird
- Estado de sessão: prefixo `pernod_reembolso_`
- Exportações: versões completa e simplificada em memória

O arquivo `pagina.py` ainda reúne interface, consultas, cálculos e exportações por compatibilidade
com a implementação original. Em evoluções maiores, essas responsabilidades podem ser separadas
nos arquivos previstos no padrão geral sem alterar o registro nem o `main.py`.

