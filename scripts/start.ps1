param(
    [int]$Port = 8080
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

if (-not (Test-Path ".env")) {
    throw ".env does not exist. Run scripts\init-env.ps1 first."
}

New-Item -ItemType Directory -Force -Path "logs" | Out-Null

$api = Start-Process -WindowStyle Hidden -FilePath powershell.exe -ArgumentList @(
    "-NoProfile",
    "-Command",
    "cd `"$Root`"; python -B -m uvicorn orchestrator.main:app --host 0.0.0.0 --port $Port *> logs\api.out.log"
) -PassThru

$worker = Start-Process -WindowStyle Hidden -FilePath powershell.exe -ArgumentList @(
    "-NoProfile",
    "-Command",
    "cd `"$Root`"; python -B -m orchestrator.worker *> logs\worker.out.log"
) -PassThru

Set-Content -Path "logs\api.pid" -Value $api.Id -Encoding ASCII
Set-Content -Path "logs\worker.pid" -Value $worker.Id -Encoding ASCII

Start-Sleep -Seconds 2
Write-Host "API wrapper PID: $($api.Id)"
Write-Host "Worker wrapper PID: $($worker.Id)"
Write-Host "Health: http://127.0.0.1:$Port/healthz"
Write-Host "Webhook URL: http://<orchestrator-host-ip>:$Port/gitlab/webhook"
