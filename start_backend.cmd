@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT=%~dp0"
set "PORT=5000"
set "PID_FILE=%ROOT%.backend.pid"

cd /d "%ROOT%"

rem --- Check if already running ---
for /f "tokens=5" %%P in ('netstat -ano ^| findstr :%PORT% ^| findstr LISTENING') do (
	echo Backend already running on port %PORT% - PID %%P
	>"%PID_FILE%" echo %%P
	exit /b 0
)

rem --- Find python ---
where python >nul 2>nul
if !errorlevel! EQU 0 (
	set "PY=python"
	goto :launch
)
where py >nul 2>nul
if !errorlevel! EQU 0 (
	set "PY=py -3"
	goto :launch
)
echo Python not found in PATH.
exit /b 1

:launch
echo Starting backend with: !PY! backend\app.py
start "" /B !PY! backend\app.py
echo Waiting for port %PORT%...

set /a tries=0
:wait_loop
set /a tries+=1
for /f "tokens=5" %%P in ('netstat -ano ^| findstr :%PORT% ^| findstr LISTENING') do (
	>"%PID_FILE%" echo %%P
	echo Backend started on http://127.0.0.1:%PORT% - PID %%P
	exit /b 0
)
if !tries! GEQ 30 (
	echo Backend did not start on port %PORT% within 30s.
	exit /b 1
)
timeout /t 1 /nobreak >nul
goto wait_loop