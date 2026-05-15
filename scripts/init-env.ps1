param(
    [string]$GitLabUrl,
    [string]$GitLabToken,
    [string]$WebhookSecret,
    [ValidateSet("opencode", "codex", "gemini")]
    [string]$DefaultAgent = "opencode",
    [ValidateSet("local", "docker_project")]
    [string]$Backend = "docker_project",
    [string]$GitAuthorName = "agent-bot",
    [string]$GitAuthorEmail = "agent-bot@example.local",
    [string]$OpenAIApiKey,
    [string]$AnthropicApiKey,
    [string]$GeminiApiKey,
    [string]$GoogleApiKey,
    [string]$SandboxPassEnv = "OPENAI_API_KEY,ANTHROPIC_API_KEY,GEMINI_API_KEY,GOOGLE_API_KEY,GOOGLE_GENAI_USE_VERTEXAI,GOOGLE_GENAI_USE_GCA",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$EnvPath = Join-Path $Root ".env"
$ExamplePath = Join-Path $Root ".env.example"

if ((Test-Path $EnvPath) -and -not $Force) {
    Write-Host ".env already exists. Use -Force to rewrite it."
    exit 0
}

if (-not (Test-Path $ExamplePath)) {
    throw ".env.example was not found at $ExamplePath"
}

if (-not $GitLabUrl) {
    $GitLabUrl = Read-Host "GitLab URL, for example http://192.168.1.251/gitlab"
}
if (-not $GitLabToken) {
    $GitLabToken = Read-Host "GitLab access token"
}
if (-not $WebhookSecret) {
    $WebhookSecret = Read-Host "GitLab webhook secret"
}
if (-not $OpenAIApiKey) {
    $OpenAIApiKey = Read-Host "Optional OPENAI_API_KEY for Codex or OpenAI-compatible agents, blank to skip"
}
if (-not $AnthropicApiKey) {
    $AnthropicApiKey = Read-Host "Optional ANTHROPIC_API_KEY, blank to skip"
}
if (-not $GeminiApiKey) {
    $GeminiApiKey = Read-Host "Optional GEMINI_API_KEY, blank to skip"
}
if (-not $GoogleApiKey) {
    $GoogleApiKey = Read-Host "Optional GOOGLE_API_KEY, blank to skip"
}

$content = Get-Content -LiteralPath $ExamplePath -Raw -Encoding UTF8
$replacements = @{
    "GITLAB_URL=.*" = "GITLAB_URL=$($GitLabUrl.TrimEnd('/'))"
    "GITLAB_TOKEN=.*" = "GITLAB_TOKEN=$GitLabToken"
    "GITLAB_WEBHOOK_SECRET=.*" = "GITLAB_WEBHOOK_SECRET=$WebhookSecret"
    "DEFAULT_AGENT=.*" = "DEFAULT_AGENT=$DefaultAgent"
    "AGENT_EXECUTION_BACKEND=.*" = "AGENT_EXECUTION_BACKEND=$Backend"
    "GIT_AUTHOR_NAME=.*" = "GIT_AUTHOR_NAME=$GitAuthorName"
    "GIT_AUTHOR_EMAIL=.*" = "GIT_AUTHOR_EMAIL=$GitAuthorEmail"
    "SANDBOX_PASS_ENV=.*" = "SANDBOX_PASS_ENV=$SandboxPassEnv"
}

foreach ($pattern in $replacements.Keys) {
    $content = [regex]::Replace($content, "(?m)^$pattern$", $replacements[$pattern])
}

$agentKeys = @(
    "OPENAI_API_KEY=$OpenAIApiKey",
    "ANTHROPIC_API_KEY=$AnthropicApiKey",
    "GEMINI_API_KEY=$GeminiApiKey",
    "GOOGLE_API_KEY=$GoogleApiKey"
) -join [Environment]::NewLine

$content = $content.TrimEnd() + [Environment]::NewLine + [Environment]::NewLine + "# Optional agent API keys. Leave blank when OAuth or a free/default model is used." + [Environment]::NewLine + $agentKeys + [Environment]::NewLine

Set-Content -LiteralPath $EnvPath -Value $content -Encoding UTF8
Write-Host "Wrote .env. Do not commit this file."
