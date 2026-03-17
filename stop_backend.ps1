param(
    [int]$Port = 5000
)

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$pids = New-Object System.Collections.Generic.List[int]

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    foreach ($item in $listener) {
        [void]$pids.Add([int]$item.OwningProcess)
    }
}

$pidFile = Join-Path $repoRoot ".backend.pid"
if (Test-Path $pidFile) {
    $value = Get-Content $pidFile | Select-Object -First 1
    if ($value -match '^\d+$') {
        [void]$pids.Add([int]$value)
    }
}

$launcherFile = Join-Path $repoRoot ".backend.launcher.pid"
if (Test-Path $launcherFile) {
    $value = Get-Content $launcherFile | Select-Object -First 1
    if ($value -match '^\d+$') {
        [void]$pids.Add([int]$value)
    }
}

$pythonProcesses = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        ($_.Name -match '^python(\.exe)?$' -or $_.Name -match '^py(\.exe)?$') -and
        $_.CommandLine -and
        $_.CommandLine -match 'backend[\\/]+app\.py'
    }

foreach ($proc in $pythonProcesses) {
    [void]$pids.Add([int]$proc.ProcessId)
    if ($proc.ParentProcessId -and $proc.ParentProcessId -gt 0) {
        [void]$pids.Add([int]$proc.ParentProcessId)
    }
}

$uniquePids = $pids | Sort-Object -Unique

if (-not $uniquePids) {
    Write-Output "No backend process found on port $Port."
    Remove-Item $pidFile -ErrorAction SilentlyContinue
    Remove-Item $launcherFile -ErrorAction SilentlyContinue
    exit 0
}

foreach ($procId in $uniquePids) {
    try {
        Stop-Process -Id $procId -Force -ErrorAction Stop
        Write-Output "Stopped PID $procId"
    } catch {
        try {
            taskkill /PID $procId /T /F | Out-Null
            Write-Output "Killed PID tree $procId"
        } catch {}
    }
}

Remove-Item $pidFile -ErrorAction SilentlyContinue
Remove-Item $launcherFile -ErrorAction SilentlyContinue

for ($i = 0; $i -lt 10; $i++) {
    Start-Sleep -Milliseconds 300
    $check = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $check) { break }
}

$check = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($check) {
    $remaining = ($check | Select-Object -ExpandProperty OwningProcess | Sort-Object -Unique) -join ", "
    Write-Output "Backend still listening on port $Port (PID $remaining)."
    exit 1
}

Write-Output "Backend stopped."