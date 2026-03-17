param(
    [int]$Port = 5000
)

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    $existingProcId = ($existing | Select-Object -First 1 -ExpandProperty OwningProcess)
    Write-Output "Backend already running on port $Port (PID $existingProcId)."
    exit 0
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    $process = Start-Process -FilePath "py" -ArgumentList @("-3", "backend/app.py") -WorkingDirectory $repoRoot -PassThru
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $process = Start-Process -FilePath "python" -ArgumentList @("backend/app.py") -WorkingDirectory $repoRoot -PassThru
} else {
    Write-Error "Python not found. Install Python or add it to PATH."
    exit 1
}

Start-Sleep -Seconds 2

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $listener) {
    Write-Error "Backend did not start on port $Port."
    try { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue } catch {}
    exit 1
}

$serverPid = ($listener | Select-Object -First 1 -ExpandProperty OwningProcess)
Set-Content -Path (Join-Path $repoRoot ".backend.pid") -Value $serverPid
Set-Content -Path (Join-Path $repoRoot ".backend.launcher.pid") -Value $process.Id

Write-Output "Backend started on http://127.0.0.1:$Port (PID $serverPid)."