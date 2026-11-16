# Pendências de estrutura

## Git próprio

O projeto possui repositório Git independente, branch inicial `main`, regras locais em `AGENTS.md`
e pipeline em `.github/workflows/build.yml`. O `.gitignore` exclui dados operacionais, caches,
credenciais, planilhas, bancos, logs e backups.

O remoto `origin` está configurado como
`https://github.com/CodesDinho/painel_analise_vendas.git`. Ainda é necessário revisar o primeiro
stage e somente então criar e publicar o primeiro commit. Nenhum commit foi criado automaticamente
durante a preparação.

## Container

O projeto passou a possuir `Dockerfile`, `.dockerignore`, `compose.yml` e scripts PowerShell de
implantação. A imagem inclui o cliente nativo do Firebird, executa com usuário não administrativo e
mantém credenciais fora da imagem. O Compose publica somente o Streamlit na porta 8520 e conecta o
serviço à rede externa `combo-audit-internal`.

O pipeline segue o padrão GitOps do `ti_dinho_slack`: testa, publica imagens `latest` e
`sha-<commit>` no GHCR e atualiza no Compose a referência imutável após integração em `main`.

Ainda é necessário validar o primeiro build no GitHub Actions, criar a stack no Portainer 153,
preparar a raiz `/home/administrator/Desktop/codes/Painel_analise_vendas`, configurar credenciais e
usuários em runtime e homologar o acesso real ao BigQuery, Firebird e API `slack_combos`.

