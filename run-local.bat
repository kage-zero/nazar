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

rem Use the Fast3R runtime from "pnpm gpu:setup" when .env does not name one.
findstr /r /b /c:"NAZAR_FAST3R_PYTHON=." .env >nul 2>nul
if errorlevel 1 if exist "var\gpu\fast3r-env\Scripts\python.exe" if exist "var\gpu\weights\Fast3R_ViT_Large_512" (
  set "NAZAR_FAST3R_PYTHON=%CD%\var\gpu\fast3r-env\Scripts\python.exe"
  set "NAZAR_FAST3R_WEIGHTS=%CD%\var\gpu\weights\Fast3R_ViT_Large_512"
  echo Using the Fast3R runtime in var\gpu.
)

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
