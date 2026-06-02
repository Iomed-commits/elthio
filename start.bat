@echo off
cd /d C:\myfristai

if exist "%~dp0.venv\Scripts\python.exe" (
  set "PY=%~dp0.venv\Scripts\python.exe"
) else (
  echo WARNING: .venv not found — using system python. Run: py -m venv .venv
  set "PY=python"
)

echo Starting Elthio with: %PY%
echo Open http://127.0.0.1:8765 after you see "Elthio Server running"

REM Kill every listener on 8765 (stale copies often use system python, not .venv)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }" >nul 2>&1
timeout /t 2 /nobreak >nul

REM Start server in its own window, wait until HTTP responds, then open browser
start "Elthio Server" "%PY%" "%~dp0Server.PY"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$n=0; while($n -lt 45){ try { $r=Invoke-WebRequest -Uri 'http://127.0.0.1:8765/' -UseBasicParsing -TimeoutSec 2; if($r.StatusCode -eq 200){ Write-Host 'Server ready on port 8765.'; exit 0 } } catch {}; Start-Sleep -Seconds 1; $n++ }; Write-Host 'ERROR: Elthio did not start on port 8765 within 45s.'; exit 1"
if errorlevel 1 (
  echo.
  echo Server failed to respond. Check the Elthio Server window for errors.
  pause
  exit /b 1
)
start "" http://127.0.0.1:8765/
echo Browser opened. Keep the Elthio Server window open while you use the app.
pause
