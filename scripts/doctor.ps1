$ErrorActionPreference = "Continue"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

function Test-Command($Name) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) {
        Write-Host "[OK] $Name -> $($cmd.Source)"
        return $true
    }
    Write-Host "[MISSING] $Name"
    return $false
}

Write-Host "== GitLab Agent Orchestrator doctor =="
Test-Command python | Out-Null
Test-Command git | Out-Null
Test-Command docker | Out-Null

if (Test-Path ".env") {
    Write-Host "[OK] .env exists"
    $required = @("GITLAB_URL", "GITLAB_TOKEN", "GITLAB_WEBHOOK_SECRET", "AGENT_EXECUTION_BACKEND")
    $envText = Get-Content ".env" -Raw -Encoding UTF8
    foreach ($key in $required) {
        if ($envText -match "(?m)^$key=.+") {
            Write-Host "[OK] $key is set"
        } else {
            Write-Host "[MISSING] $key"
        }
    }
} else {
    Write-Host "[MISSING] .env. Run scripts\init-env.ps1 first."
}

try {
    $dockerVersion = docker version --format "{{.Server.Version}}" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Docker server $dockerVersion"
    } else {
        Write-Host "[MISSING] Docker server is not reachable"
    }
} catch {
    Write-Host "[MISSING] Docker server is not reachable"
}

$image = docker images --format "{{.Repository}}:{{.Tag}}" 2>$null | Select-String "^gitlab-agent-sandbox:latest$"
if ($image) {
    Write-Host "[OK] Docker image gitlab-agent-sandbox:latest exists"
} else {
    Write-Host "[MISSING] Docker image gitlab-agent-sandbox:latest. Run docker\sandbox\build.ps1"
}

try {
    $health = Invoke-RestMethod "http://127.0.0.1:8080/healthz" -TimeoutSec 3
    if ($health.ok) {
        Write-Host "[OK] API is healthy on http://127.0.0.1:8080"
    }
} catch {
    Write-Host "[INFO] API is not currently reachable on http://127.0.0.1:8080"
}
