@{
    ProjectName = 'Painel Analise de Vendas'
    RepositoryPath = '.'
    Remote = 'origin'
    ProductionBranch = 'main'
    TestCommands = @('python -m pytest -q')
    GitHubActions = @{
        Repository = 'CodesDinho/painel_analise_vendas'
        Workflow = 'build.yml'
        TimeoutSeconds = 1200
        TokenEnvironmentVariable = 'GITHUB_REPO_WRITE_TOKEN'
        TokenDotEnvPath = '../../TI/3_Slack/ti_dinho_slack/slack_stack/.env.portainer'
        TokenDotEnvName = 'GITHUB_REPO_WRITE_TOKEN'
    }
    Portainer = @{
        Url = 'http://10.1.1.153:9090'
        EndpointId = 3
        ApiKeyEnvironmentVariable = 'PORTAINER_ACCESS_TOKEN'
        ApiKeyDotEnvPath = '../../TI/3_Slack/ti_dinho_slack/slack_stack/.env.portainer'
        ApiKeyDotEnvName = 'PORTAINER_ACCESS_TOKEN'
        ContainerName = 'painel-analise-vendas'
        ImageTemplate = 'ghcr.io/codesdinho/painel-analise-vendas:sha-{commit}'
        TimeoutSeconds = 600
    }
}
