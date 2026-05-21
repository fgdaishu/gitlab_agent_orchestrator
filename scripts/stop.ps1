param(
    [int]$Port = 8080
)

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

$portPids = @()
$netstat = netstat -ano 2>$null
foreach ($line in $netstat) {
    if ($line -match "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$") {
        $portPids += [int]$Matches[1]
    }
}

foreach ($portPid in ($portPids | Sort-Object -Unique)) {
    taskkill /PID $portPid /T /F | Out-Null
    Write-Host "[OK] Stopped process listening on port $Port PID $portPid"
}
