# One-shot local deploy (admin-friendly):
#   venv + pip (base + media/ASR) + FFmpeg + Whisper model + DB + launch public UI
#
# From repo root (after git clone):
#   powershell -ExecutionPolicy Bypass -File .\scripts\install_and_run.ps1
#
# Options:
#   .\scripts\install_and_run.ps1 -ModelSize tiny
#   .\scripts\install_and_run.ps1 -NoLaunch          # install only
#   .\scripts\install_and_run.ps1 -SkipModelDownload  # download Whisper on first ASR

param(
    [ValidateSet("tiny", "base", "small", "medium", "large-v3")]
    [string]$ModelSize = "tiny",
    [switch]$NoLaunch,
    [switch]$SkipModelDownload,
    [switch]$SkipOcr
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Write-Step([string]$msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg) { Write-Host "  OK  $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "  !!  $msg" -ForegroundColor Yellow }

function Refresh-Path {
    $machine = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = @($machine, $user) -join ";"
}

function Ensure-WingetPackage {
    param(
        [Parameter(Mandatory = $true)][string]$Id,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$IsInstalled
    )
    if (& $IsInstalled) {
        Write-Ok "$Name already installed"
        return
    }
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Warn "winget not found; install $Name manually, then re-run."
        return
    }
    Write-Step "Install $Name via winget ($Id)"
    & winget install --id $Id -e --accept-source-agreements --accept-package-agreements
    Refresh-Path
    if (& $IsInstalled) {
        Write-Ok "$Name ready"
    } else {
        Write-Warn "$Name still missing. Open a new terminal (or reboot) and re-run this script."
    }
}

Write-Host ""
Write-Host "Insight Engine — one-shot local install & run" -ForegroundColor White
Write-Host "Repo: $Root" -ForegroundColor DarkGray

# --- Python venv ---
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Step "Create .venv (Python 3.12 preferred)"
    $created = $false
    try {
        & py -3.12 -m venv .venv
        if ($LASTEXITCODE -eq 0 -and (Test-Path $VenvPython)) { $created = $true }
    } catch { }
    if (-not $created) {
        & python -m venv .venv
    }
}
if (-not (Test-Path $VenvPython)) {
    Write-Error "Failed to create .venv. Install Python 3.12+ from https://www.python.org/downloads/ then re-run."
}
Write-Ok ".venv: $VenvPython"

# --- pip packages (base + ASR/OCR) ---
Write-Step "Install Python packages (requirements.txt + requirements-media.txt)"
& $VenvPython -m pip install -U pip
& $VenvPython -m pip install -r (Join-Path $Root "requirements.txt")
& $VenvPython -m pip install -r (Join-Path $Root "requirements-media.txt")
Write-Ok "pip packages installed"

# --- System: FFmpeg (required for media) ---
Write-Step "Ensure FFmpeg (required for audio/video)"
Ensure-WingetPackage -Id "Gyan.FFmpeg" -Name "FFmpeg" -IsInstalled {
    Refresh-Path
    return [bool]((Get-Command ffmpeg -ErrorAction SilentlyContinue) -and (Get-Command ffprobe -ErrorAction SilentlyContinue))
}
if (-not ((Get-Command ffmpeg -ErrorAction SilentlyContinue) -and (Get-Command ffprobe -ErrorAction SilentlyContinue))) {
    Write-Error "FFmpeg is required. Install with: winget install Gyan.FFmpeg   then re-run this script."
}

# --- System: Tesseract (OCR; recommended with media stack) ---
if (-not $SkipOcr) {
    Write-Step "Ensure Tesseract OCR"
    Ensure-WingetPackage -Id "UB-Mannheim.TesseractOCR" -Name "Tesseract" -IsInstalled {
        Refresh-Path
        return [bool](Get-Command tesseract -ErrorAction SilentlyContinue)
    }
}

# --- Prefetch Whisper weights (ASR required) ---
$modelDir = Join-Path $Root "data\models\faster-whisper"
New-Item -ItemType Directory -Force -Path $modelDir | Out-Null
if (-not $SkipModelDownload) {
    Write-Step "Download Whisper model '$ModelSize' -> $modelDir"
    Write-Host "  First download may take several minutes." -ForegroundColor DarkGray
    $env:INSIGHT_ASR_MODEL = $ModelSize
    & $VenvPython -c @"
from pathlib import Path
import os
root = Path(r'$Root') / 'data' / 'models' / 'faster-whisper'
root.mkdir(parents=True, exist_ok=True)
size = os.environ.get('INSIGHT_ASR_MODEL', 'tiny')
print('loading WhisperModel', size, 'download_root=', root)
from faster_whisper import WhisperModel
WhisperModel(size, device='cpu', compute_type='int8', download_root=str(root))
print('model ready')
"@
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Model prefetch failed; first ASR run will retry download."
    } else {
        Write-Ok "Whisper model cached"
    }
} else {
    Write-Warn "Skipped model download; first ASR will download on demand."
}

# --- Local .env (ASR on by default) ---
$EnvFile = Join-Path $Root ".env"
$Example = Join-Path $Root ".env.example"
if (-not (Test-Path $EnvFile) -and (Test-Path $Example)) {
    Write-Step "Create .env from .env.example"
    Copy-Item $Example $EnvFile
}
if (Test-Path $EnvFile) {
    $raw = Get-Content $EnvFile -Raw -ErrorAction SilentlyContinue
    if ($null -eq $raw) { $raw = "" }
    $lines = @()
    if ($raw.Trim().Length -gt 0) {
        $lines = @(Get-Content $EnvFile)
    }
    $map = @{
        "INSIGHT_ASR_ENABLED" = "1"
        "INSIGHT_ASR_MODEL"   = $ModelSize
    }
    foreach ($key in $map.Keys) {
        $val = $map[$key]
        $hit = $false
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if ($lines[$i] -match "^\s*#?\s*$key\s*=") {
                $lines[$i] = "$key=$val"
                $hit = $true
                break
            }
        }
        if (-not $hit) { $lines += "$key=$val" }
    }
    Set-Content -Path $EnvFile -Value ($lines -join "`r`n") -Encoding UTF8
    Write-Ok ".env ASR flags: INSIGHT_ASR_ENABLED=1 INSIGHT_ASR_MODEL=$ModelSize"
} else {
    Write-Warn "No .env / .env.example; set INSIGHT_ASR_ENABLED=1 in the environment before launch."
}

# --- DB ---
Write-Step "Initialize database"
& $VenvPython (Join-Path $Root "scripts\init_db.py")
Write-Ok "database ready"

# --- Verify media ---
Write-Step "Verify media dependencies"
& $VenvPython (Join-Path $Root "scripts\check_media_deps.py")

if ($NoLaunch) {
    Write-Ok "Install finished (-NoLaunch). Start later with: .\scripts\run_public.ps1"
    exit 0
}

Write-Step "Launch public app (Ctrl+C to stop)"
Write-Host "  Browser: http://localhost:8501" -ForegroundColor Green
& $VenvPython -m streamlit run (Join-Path $Root "src\insight_engine\ui\public_app.py")
