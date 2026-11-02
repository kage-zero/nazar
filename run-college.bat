@echo off
rem NAZAR on the COLLEGE GPU: API + web on this laptop, reconstruction in the college VDI.
rem No local GPU worker is started; jobs are marked "College GPU" and wait for the VDI worker.
setlocal
cd /d "%~dp0"
title NAZAR - college GPU

call :prereqs || exit /b 1

echo NAZAR on the COLLEGE GPU. Log in to the SyncHPC portal and open the VDI yourself.
echo.
echo How will the VDI reach this laptop?
echo   [O] Online - opens this laptop's API (port 8000) to the campus network while it runs.
echo                Use it only if the VDI can reach the laptop (todoCollege.md step 6).
echo   [B] Bundle - the API stays private; move zip files through portal Storage.
choice /c OB /n /m "Online or Bundle? [O/B] "
if errorlevel 2 goto bundle

:online
echo.
echo This makes the API reachable by other machines on the campus network until you close it.
choice /c YN /n /m "Continue? [Y/N] "
if errorlevel 2 (echo Cancelled. Nothing was started. & pause & exit /b 0)
rem For this run only; .env is not changed.
set NAZAR_API_HOST=0.0.0.0
echo Starting the API (all interfaces) and web app...
start "NAZAR API + web (campus network)" cmd /k pnpm dev
call :wait_api || exit /b 1
start "" "http://127.0.0.1:5173/?compute=college"
echo.
echo This laptop's addresses (use the Wi-Fi/LAN one):
ipconfig | findstr /c:"IPv4"
echo.
echo If Windows Firewall asks, allow Private networks only, and remove the rule afterwards.
echo.
echo In a VDI terminal (type the worker token there yourself; never paste it in chat):
echo     cd ~/nazar
echo     bash scripts/run-college-worker.sh ^<laptop IP^>
echo.
echo Then in the browser: upload the video and press Reconstruct ("Run on" is College GPU).
echo The panel shows when the college worker is online.
echo.
echo To stop and close the API to the campus: close the "NAZAR API + web" window.
pause
exit /b 0

:bundle
set NAZAR_API_HOST=127.0.0.1
if not exist "var\bundles" mkdir "var\bundles"
echo Starting the API and web app (private)...
start "NAZAR API + web" cmd /k pnpm dev
call :wait_api || exit /b 1
start "" "http://127.0.0.1:5173/?compute=college"
echo.
echo 1. In the browser: upload the video and press Reconstruct ("Run on" is College GPU).
echo    Then come back here.
pause
uv run --package nazar-worker nazar-worker bundle export --out var\bundles\mission.zip --location college
if errorlevel 1 (echo Export failed or no college job is queued. & pause & exit /b 1)
echo.
echo 2. Upload %CD%\var\bundles\mission.zip with the portal's Storage module.
echo    In the VDI:  cd ~/nazar ^&^& uv run nazar-worker bundle run mission.zip --out result.zip
echo 3. Download result.zip through Storage and save it as:
echo    %CD%\var\bundles\result.zip
echo    Then come back here.
:wait_result
pause
if not exist "var\bundles\result.zip" (echo var\bundles\result.zip is not there yet. & goto wait_result)
uv run --package nazar-worker nazar-worker bundle import var\bundles\result.zip
if errorlevel 1 (echo Import failed; see the message above. & pause & exit /b 1)
echo.
echo Imported. The result is in the browser. Close the "NAZAR API + web" window to stop.
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
