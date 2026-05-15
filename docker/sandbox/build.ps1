param(
    [string]$Tag = "gitlab-agent-sandbox:latest",
    [string]$OpenCodePackage = "opencode-ai",
    [string]$CodexPackage = "@openai/codex",
    [string]$GeminiPackage = "@google/gemini-cli"
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")

docker build `
    --tag $Tag `
    --file (Join-Path $PSScriptRoot "Dockerfile") `
    --build-arg "OPENCODE_NPM_PACKAGE=$OpenCodePackage" `
    --build-arg "CODEX_NPM_PACKAGE=$CodexPackage" `
    --build-arg "GEMINI_NPM_PACKAGE=$GeminiPackage" `
    $repoRoot
