# Elthio smoke tests — run from c:\myfristai with server already up on 8765
$ErrorActionPreference = "Stop"
$Py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }
$Base = "http://127.0.0.1:8765"

Write-Host "=== Elthio smoke tests ===" -ForegroundColor Cyan

try {
    $r = Invoke-WebRequest -Uri "$Base/" -UseBasicParsing -TimeoutSec 5
    Write-Host "[OK] GET / ($($r.StatusCode))"
} catch {
    Write-Host "[FAIL] Server not running on $Base — run start.bat first" -ForegroundColor Red
    exit 1
}

foreach ($path in @("/passport", "/medcheck", "/visit-packet")) {
    try {
        $r = Invoke-WebRequest -Uri "$Base$path" -UseBasicParsing -TimeoutSec 5
        Write-Host "[OK] GET $path ($($r.StatusCode), $($r.Content.Length) bytes)"
    } catch {
        Write-Host "[FAIL] GET $path — $($_.Exception.Message)" -ForegroundColor Red
    }
}

$body = '{"medications":["Warfarin"],"supplements":["Magnesium Glycinate"]}'
try {
    $d = Invoke-RestMethod -Uri "$Base/api/separation-schedule" -Method POST -ContentType "application/json" -Body $body
    $blocks = ($d.blocks | ForEach-Object { $_.id }) -join ", "
    Write-Host "[OK] POST separation-schedule rules=$($d.rules_matched) blocks=$blocks"
} catch {
    Write-Host "[FAIL] separation-schedule — $($_.Exception.Message)" -ForegroundColor Red
}

Push-Location $PSScriptRoot
& $Py -c @"
from med_check_engine import run_med_check
pairs = [
    (['warfarin'], ['vitamin k2'], 1),
    (['metformin'], ['vitamin k2'], 0),
]
for meds, supps, n in pairs:
    r = run_med_check(meds, supps, [])
    got = len(r.get('interactions', []))
    ok = 'OK' if got == n else 'FAIL'
    print(f'[{ok}] med_check {meds[0]}+{supps[0]}: {got} interactions (expected {n})')
"@
$coach = & $Py separation_coach.py 2>&1 | Out-String
if ($coach -match "All tests passed") { Write-Host "[OK] separation_coach.py self-test" } else { Write-Host "[FAIL] separation_coach.py`n$coach" -ForegroundColor Red }
Pop-Location

Write-Host "=== Done ===" -ForegroundColor Cyan
