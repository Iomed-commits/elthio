# Elthio pre-deploy gate - regenerate the interaction DB and run the health check.
# Usage:  .\predeploy.ps1          (engine tests only)
#         .\predeploy.ps1 -Full    (also runs endpoint/performance/content tests; server must be up)
param([switch]$Full)

$ErrorActionPreference = "Stop"
$py = ".\.venv\Scripts\python.exe"

Write-Host "== Regenerating interactions_db.json ==" -ForegroundColor Cyan
& $py _build_interactions_db.py
if ($LASTEXITCODE -ne 0) { Write-Host "DB build FAILED" -ForegroundColor Red; exit 1 }

Write-Host "== Running health check ==" -ForegroundColor Cyan
if ($Full) { & $py healthcheck.py --full } else { & $py healthcheck.py }
if ($LASTEXITCODE -ne 0) { Write-Host "HEALTH CHECK FAILED - do not deploy" -ForegroundColor Red; exit 1 }

Write-Host "Pre-deploy checks passed - safe to deploy." -ForegroundColor Green
