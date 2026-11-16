[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Message,
    [string]$Config = 'deploy.config.psd1',
    [switch]$SkipTests,
    [switch]$SkipCommit,
    [switch]$SkipDeploy,
    [switch]$ConfirmProduction
)

$ErrorActionPreference = 'Stop'

function Write-Stage([string]$Name, [string]$Text) {
    Write-Host "[ETAPA:$Name] $Text"
}

function Format-Duration([TimeSpan]$Duration) {
    return '{0:00}:{1:00}:{2:00}' -f [math]::Floor($Duration.TotalHours), $Duration.Minutes, $Duration.Seconds
}

function Write-WaitProgress([string]$Stage, [datetime]$StartedAt, [datetime]$Deadline, [string]$Detail) {
    $now = Get-Date
    $remaining = $Deadline - $now
    if ($remaining.TotalSeconds -lt 0) { $remaining = [TimeSpan]::Zero }
    Write-Host "[$Stage] Decorrido: $(Format-Duration ($now - $StartedAt)) | Restante: $(Format-Duration $remaining) | $Detail"
}

function Invoke-Native([string]$File, [string[]]$Arguments) {
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Comando falhou ($LASTEXITCODE): $File $($Arguments -join ' ')"
    }
}

function Get-DotEnvValue([string]$Path, [string]$Name) {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $line = Get-Content -LiteralPath $Path |
        Where-Object { $_ -match "^$([regex]::Escape($Name))=" } |
        Select-Object -First 1
    if ($null -eq $line) { return $null }
    return ($line -split '=', 2)[1].Trim().Trim('"').Trim("'")
}

function Resolve-RepositoryFile([string]$RepositoryPath, [string]$ConfiguredPath) {
    if ([IO.Path]::IsPathRooted($ConfiguredPath)) {
        return [IO.Path]::GetFullPath($ConfiguredPath)
    }
    return [IO.Path]::GetFullPath((Join-Path $RepositoryPath $ConfiguredPath))
}

function Assert-SafeStage {
    $staged = @(& git diff --cached --name-only --diff-filter=ACMR)
    $blocked = @($staged | Where-Object {
        $_ -match '(^|/)(\.env($|\.)|secrets\.toml$|credential.*\.json$|usuarios(_faturamento)?\.json$|.*\.(pfx|p12|pem|key)$)'
    })
    if ($blocked.Count) {
        & git restore --staged -- @blocked 2>$null
        throw "Arquivos sensiveis removidos do stage: $($blocked -join ', ')"
    }
}

function Wait-GitHubActions([hashtable]$Settings, [string]$Commit, [string]$RepositoryPath) {
    Write-Stage 'github-actions' 'Aguardando o pipeline'
    $headers = @{ Accept = 'application/vnd.github+json'; 'X-GitHub-Api-Version' = '2022-11-28' }
    $token = [Environment]::GetEnvironmentVariable([string]$Settings.TokenEnvironmentVariable)
    if (-not $token) {
        $tokenPath = Resolve-RepositoryFile $RepositoryPath ([string]$Settings.TokenDotEnvPath)
        $token = Get-DotEnvValue $tokenPath ([string]$Settings.TokenDotEnvName)
    }
    if ($token) { $headers.Authorization = "Bearer $token" }
    $workflow = [Uri]::EscapeDataString([string]$Settings.Workflow)
    $uri = "https://api.github.com/repos/$($Settings.Repository)/actions/workflows/$workflow/runs?head_sha=$Commit&per_page=10"
    $startedAt = Get-Date
    $deadline = $startedAt.AddSeconds([int]$Settings.TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $result = Invoke-RestMethod -Method Get -Uri $uri -Headers $headers
            $run = $result.workflow_runs | Sort-Object created_at -Descending | Select-Object -First 1
            $status = if ($run) { [string]$run.status } else { 'aguardando criacao' }
            Write-WaitProgress 'github-actions' $startedAt $deadline "Status: $status"
            if ($run.status -eq 'completed') {
                if ($run.conclusion -ne 'success') {
                    throw "Pipeline falhou ($($run.conclusion)): $($run.html_url)"
                }
                Write-Host "Pipeline concluido: $($run.html_url)"
                return
            }
        } catch {
            if ($_.Exception.Message -like 'Pipeline falhou*') { throw }
            Write-Verbose $_.Exception.Message
        }
        Start-Sleep -Seconds 10
    }
    throw "Tempo esgotado aguardando o pipeline do commit $Commit."
}

function Wait-Portainer([hashtable]$Settings, [string]$Commit, [string]$RepositoryPath) {
    Write-Stage 'portainer' "Aguardando $($Settings.ContainerName) no servidor 153"
    $apiKey = [Environment]::GetEnvironmentVariable([string]$Settings.ApiKeyEnvironmentVariable)
    if (-not $apiKey) {
        $keyPath = Resolve-RepositoryFile $RepositoryPath ([string]$Settings.ApiKeyDotEnvPath)
        $apiKey = Get-DotEnvValue $keyPath ([string]$Settings.ApiKeyDotEnvName)
    }
    if (-not $apiKey) { throw 'PORTAINER_ACCESS_TOKEN nao encontrado.' }
    $base = ([string]$Settings.Url).TrimEnd('/')
    $expected = ([string]$Settings.ImageTemplate).Replace('{commit}', $Commit)
    $startedAt = Get-Date
    $deadline = $startedAt.AddSeconds([int]$Settings.TimeoutSeconds)
    do {
        try {
            $uri = "$base/api/endpoints/$($Settings.EndpointId)/docker/containers/json?all=true"
            $containers = Invoke-RestMethod -Method Get -Uri $uri -Headers @{ 'X-API-Key' = $apiKey }
            $container = $containers |
                Where-Object { $_.Names -contains "/$($Settings.ContainerName)" } |
                Select-Object -First 1
            $current = if ($container) { "$($container.Image) | $($container.Status)" } else { 'nao encontrado' }
            Write-WaitProgress 'portainer' $startedAt $deadline "Atual: $current"
            if ($container -and $container.Image -eq $expected -and
                $container.State -eq 'running' -and $container.Status -match '\(healthy\)') {
                Write-Host "Container saudavel: $expected"
                return
            }
        } catch {
            Write-Verbose $_.Exception.Message
        }
        Start-Sleep -Seconds 10
    } while ((Get-Date) -lt $deadline)
    throw "Portainer nao confirmou a imagem saudavel $expected."
}

$configPath = (Resolve-Path -LiteralPath $Config).Path
$settings = Import-PowerShellDataFile -LiteralPath $configPath
$repositoryPath = [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $configPath) $settings.RepositoryPath))
$scriptStartedAt = Get-Date

if (-not $ConfirmProduction -and -not $SkipDeploy) {
    throw 'Producao exige -ConfirmProduction.'
}

Push-Location $repositoryPath
try {
    Invoke-Native git @('rev-parse', '--is-inside-work-tree')
    $branch = (& git branch --show-current).Trim()
    if (-not $branch -or $branch -eq $settings.ProductionBranch) {
        throw 'Execute a partir de uma branch curta, nunca diretamente na main.'
    }

    if (-not $SkipTests) {
        Write-Stage 'testes' 'Executando validacoes obrigatorias'
        foreach ($testCommand in $settings.TestCommands) {
            & ([scriptblock]::Create($testCommand))
            if ($LASTEXITCODE -ne 0 -or -not $?) { throw "Teste falhou: $testCommand" }
        }
    }

    if (-not $SkipCommit) {
        Write-Stage 'commit' 'Preparando alteracoes versionaveis'
        Invoke-Native git @('add', '--all')
        Assert-SafeStage
        $staged = @(& git diff --cached --name-only)
        if ($staged.Count) { Invoke-Native git @('commit', '-m', $Message) }
        Write-Stage 'push' "Enviando $branch"
        Invoke-Native git @('push', '--set-upstream', $settings.Remote, $branch)
    }

    $commit = (& git rev-parse HEAD).Trim()
    Write-Host "COMMIT=$commit"

    if (-not $SkipDeploy) {
        Write-Stage 'integracao' "Integrando em $($settings.ProductionBranch)"
        Invoke-Native git @('fetch', $settings.Remote, $settings.ProductionBranch)
        Invoke-Native git @('merge-base', '--is-ancestor', "$($settings.Remote)/$($settings.ProductionBranch)", $commit)
        Invoke-Native git @('switch', $settings.ProductionBranch)
        Invoke-Native git @('pull', '--ff-only', $settings.Remote, $settings.ProductionBranch)
        Invoke-Native git @('merge', '--ff-only', $commit)
        Invoke-Native git @('push', $settings.Remote, $settings.ProductionBranch)
        Wait-GitHubActions $settings.GitHubActions $commit $repositoryPath
        Wait-Portainer $settings.Portainer $commit $repositoryPath
    }

    Write-Stage 'concluido' "Commit $commit finalizado em $(Format-Duration ((Get-Date) - $scriptStartedAt))"
} catch {
    Write-Stage 'falha' $_.Exception.Message
    exit 1
} finally {
    Pop-Location
}
