@echo off
rem NAZAR on the LOCAL GPU (this laptop): API + web + a worker, all on 127.0.0.1.
setlocal
cd /d "%~dp0"
title NAZAR - local GPU

call :prereqs || exit /b 1

rem Overrides any NAZAR_API_HOST in .env for this run only: the API stays private.
set NAZAR_API_HOST=127.0.0.1

echo Starting the API and web app...
start "NAZAR API + web" cmd /k pnpm dev
call :wait_api || exit /b 1

rem The worker finds the GPU models installed by "pnpm gpu:setup" in var\gpu by itself.
if exist "var\gpu\main-env" (echo Using the GPU models in var\gpu.) else (echo No GPU models installed: the CPU baseline will run. See "pnpm gpu:setup".)

echo Starting the local GPU worker...
start "NAZAR worker (local GPU)" cmd /k uv run --package nazar-worker nazar-worker run --modes test,standard --step-delay 0.8 --location local

start "" "http://127.0.0.1:5173/?compute=local"
echo.
echo NAZAR is running on the local GPU. "Run on" is set to Local GPU in the browser.
echo To stop: close the "NAZAR API + web" and "NAZAR worker" windows.
echo.
pause
exit /b 0

:prereqs
where pnpm >nul 2>nul || (echo pnpm was not found on PATH. & pause & exit /b 1)
where uv >nul 2>nul || (echo uv was not found on PATH. & pause & exit /b 1)
where curl >nul 2>nul || (echo curl was not found on PATH. & pause & exit /b 1)
if not exist ".env" (echo No .env file yet. Run "pnpm env:init" first. & pause & exit /b 1)
exit /b 0

:wait_api
set /a tries=0
:wait_loop
curl -s -f -o nul http://127.0.0.1:8000/api/health && exit /b 0
set /a tries+=1
if %tries% geq 90 (
  echo The API did not answer on port 8000 within 3 minutes. Check the "NAZAR API + web" window.
  pause
  exit /b 1
)
timeout /t 2 /nobreak >nul
goto wait_loop
