# Launch public product UI (upload / collect → report).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Error "Missing .venv. Run: py -3.12 -m venv .venv ; .\.venv\Scripts\pip install -r requirements.txt"
}

& $VenvPython scripts\init_db.py
& $VenvPython -m streamlit run src\insight_engine\ui\public_app.py
