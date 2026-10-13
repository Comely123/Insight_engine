# Launch admin archive export UI.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Error "Create .venv first (scripts\run_app.ps1 or manual venv)."
}

& $VenvPython scripts\init_db.py
& $VenvPython -m streamlit run src\insight_engine\ui\admin_app.py
