@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT=%~dp0"
set "PORT=5000"
set "PID_FILE=%ROOT%.backend.pid"

cd /d "%ROOT%"

set "found=0"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr :%PORT% ^| findstr LISTENING') do (
	set "found=1"
	taskkill /PID %%P /T /F >nul 2>nul
	if !errorlevel! EQU 0 echo Stopped PID %%P
)

if exist "%PID_FILE%" (
	for /f %%P in (%PID_FILE%) do (
		taskkill /PID %%P /T /F >nul 2>nul
	)
	del /q "%PID_FILE%" >nul 2>nul
)

timeout /t 1 /nobreak >nul
for /f "tokens=5" %%P in ('netstat -ano ^| findstr :%PORT% ^| findstr LISTENING') do (
	echo Backend still listening on port %PORT% - PID %%P.
	exit /b 1
)

if "%found%"=="0" (
	echo No backend process found on port %PORT%.
) else (
	echo Backend stopped.
)

exit /b 0