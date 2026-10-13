# Windows helper: create venv if missing, install deps, init DB, launch Streamlit.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Uv312 = Join-Path $env:APPDATA "uv\python\cpython-3.12.14-windows-x86_64-none\python.exe"
$PythonExe = $null
foreach ($candidate in @(
        $Uv312,
        (Get-Command py -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
        "D:\softwares\python\python.exe",
        "python"
    )) {
    if (-not $candidate) { continue }
    if ($candidate -eq (Get-Command py -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)) {
        # Prefer explicit 3.12 via py launcher when registered
        try {
            & py -3.12 -c "import sys" 2>$null
            if ($LASTEXITCODE -eq 0) { $PythonExe = "py-3.12"; break }
        } catch { }
        continue
    }
    if (Test-Path $candidate) {
        $PythonExe = $candidate
        break
    }
}
if (-not $PythonExe) {
    Write-Error "Python 3.12+ not found. Install Python 3.12/3.13 and retry."
}

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating virtualenv with: $PythonExe"
    if ($PythonExe -eq "py-3.12") {
        & py -3.12 -m venv .venv
    } else {
        & $PythonExe -m venv .venv
    }
}

& $VenvPython -m pip install -U pip
& $VenvPython -m pip install -r requirements.txt
& $VenvPython scripts\init_db.py
Write-Host "Tip: public product UI -> scripts\run_public.ps1"
& $VenvPython -m streamlit run src\insight_engine\ui\app.py
