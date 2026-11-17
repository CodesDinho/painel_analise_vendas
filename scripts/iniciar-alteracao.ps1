[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*$')]
    [string]$Branch
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Invoke-Git([string[]]$Arguments) {
    & git @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Git falhou: git $($Arguments -join ' ')"
    }
}

Push-Location $ProjectRoot
try {
    Invoke-Git @('rev-parse', '--is-inside-work-tree')
    $pending = @(& git status --porcelain)
    if ($pending.Count) {
        throw 'Existem alteracoes locais. Conclua, guarde ou descarte essas alteracoes antes de iniciar outra branch.'
    }

    Invoke-Git @('switch', 'main')
    Invoke-Git @('pull', '--ff-only', 'origin', 'main')

    & git show-ref --verify --quiet "refs/heads/$Branch"
    if ($LASTEXITCODE -eq 0) {
        throw "A branch local '$Branch' ja existe. Escolha outro nome ou abra a branch existente."
    }

    Invoke-Git @('switch', '-c', $Branch)
    Write-Host "Branch pronta: $Branch"
    Write-Host 'Depois de editar e salvar, execute:'
    Write-Host 'powershell -ExecutionPolicy Bypass -File .\scripts\commit-deploy.ps1 -Message "Descricao da alteracao" -ConfirmProduction'
} finally {
    Pop-Location
}
