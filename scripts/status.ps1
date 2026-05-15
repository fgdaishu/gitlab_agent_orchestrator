param(
    [int]$Port = 8080
)

$ErrorActionPreference = "Continue"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

Write-Host "== Service =="
foreach ($name in @("api", "worker")) {
    $pidPath = "logs\$name.pid"
    if (Test-Path $pidPath) {
        $pidText = (Get-Content $pidPath -Raw).Trim()
        $proc = Get-Process -Id $pidText -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "[OK] $name wrapper PID $pidText is running"
        } else {
            Write-Host "[STALE] $name wrapper PID $pidText is not running"
        }
    } else {
        Write-Host "[INFO] $name pid file not found"
    }
}

try {
    $health = Invoke-RestMethod "http://127.0.0.1:$Port/healthz" -TimeoutSec 3
    Write-Host "[OK] API health: $($health.ok)"
} catch {
    Write-Host "[INFO] API health check failed"
}

Write-Host "== Docker project sandboxes =="
docker ps --filter "name=gitlab-agent-project-" --format "table {{.Names}}\t{{.Status}}\t{{.Image}}" 2>$null
