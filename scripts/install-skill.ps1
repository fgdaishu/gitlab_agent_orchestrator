param(
    [string]$Destination
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Source = Join-Path $Root "skills\gitlab-agent-orchestrator"

if (-not (Test-Path $Source)) {
    throw "Skill source not found: $Source"
}

if (-not $Destination) {
    $codexHome = $env:CODEX_HOME
    if (-not $codexHome) {
        $codexHome = Join-Path $HOME ".codex"
    }
    $Destination = Join-Path $codexHome "skills"
}

New-Item -ItemType Directory -Force -Path $Destination | Out-Null
$Target = Join-Path $Destination "gitlab-agent-orchestrator"
if (Test-Path $Target) {
    Remove-Item -LiteralPath $Target -Recurse -Force
}
Copy-Item -LiteralPath $Source -Destination $Target -Recurse
Write-Host "Installed skill to $Target"
