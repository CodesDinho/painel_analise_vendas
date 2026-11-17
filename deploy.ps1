[CmdletBinding()]
param(
    [string]$Message
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

$pending = @(& git status --porcelain)
if ($LASTEXITCODE -ne 0) {
    throw 'Nao foi possivel consultar o estado do Git.'
}
if (-not $pending.Count) {
    throw 'Nenhuma alteracao salva foi encontrada. O deploy foi cancelado.'
}

if (-not $Message) {
    $Message = (Read-Host 'Descreva a alteracao para o commit').Trim()
}
if (-not $Message) {
    throw 'A mensagem do commit e obrigatoria.'
}

$branch = (& git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or -not $branch) {
    throw 'Nao foi possivel identificar a branch atual.'
}

if ($branch -eq 'main') {
    $automaticBranch = 'change/' + (Get-Date -Format 'yyyyMMdd-HHmmss')
    & git switch -c $automaticBranch
    if ($LASTEXITCODE -ne 0) {
        throw "Nao foi possivel criar a branch $automaticBranch."
    }
    Write-Host "Branch criada automaticamente: $automaticBranch"
}

$deployScript = Join-Path $ProjectRoot 'scripts\commit-deploy.ps1'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $deployScript `
    -Message $Message `
    -ConfirmProduction

exit $LASTEXITCODE
