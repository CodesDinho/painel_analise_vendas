# Regras do Painel Análise de Vendas

## Fonte oficial

- Trabalhar somente neste checkout do projeto `Painel_analise_vendas`.
- Antes de editar, executar `git status` e, quando houver remoto configurado, `git pull --ff-only`.
- Não sobrescrever mudanças locais nem usar o repositório Git superior da árvore `CODES`.

## Fluxo obrigatório

1. criar uma branch curta a partir de `main` atualizada;
2. alterar o código e a documentação relacionados;
3. executar testes e validar o Compose;
4. revisar segredos e o diff antes do commit;
5. publicar a branch e integrar em `main` somente após validação;
6. acompanhar GitHub Actions, publicação no GHCR, atualização da tag imutável e saúde do container.

Nunca versionar `.env`, `secrets.toml`, credenciais, cadastros reais de usuários, bancos, logs,
planilhas operacionais, dados locais, relatórios ou backups. Não copiar código manualmente para o
servidor nem editar o container em execução.

As regras centrais em `_GIT/_catalogo_servicos/AGENTS.md` também se aplicam.
