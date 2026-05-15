$ErrorActionPreference = "Continue"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

foreach ($name in @("api", "worker")) {
    $pidPath = "logs\$name.pid"
    if (-not (Test-Path $pidPath)) {
        Write-Host "[INFO] $pidPath not found"
        continue
    }
    $pidText = (Get-Content $pidPath -Raw).Trim()
    if ($pidText -match "^\d+$") {
        taskkill /PID $pidText /T /F | Out-Null
        Write-Host "[OK] Stopped $name wrapper PID $pidText"
    }
    Remove-Item $pidPath -Force -ErrorAction SilentlyContinue
}
