# Quick setup for media stack (ASR / FFmpeg / Whisper).
# Prefer the all-in-one local deploy (install + launch):
#   .\一键安装启动.ps1
#   .\scripts\install_and_run.ps1
#
# This script only prepares media deps:
#   - Python deps: faster-whisper / pytesseract / Pillow (+ base requirements)
#   - System: FFmpeg (required for video/audio probe & extract)
#   - System: Tesseract (optional OCR)
#   - Prefetch Whisper model weights into data/models/faster-whisper
#
# Usage (from repo root):
#   .\scripts\setup_media.ps1
#   .\scripts\setup_media.ps1 -SkipModelDownload
#   .\scripts\setup_media.ps1 -ModelSize base

param(
    [string]$ModelSize = "tiny",
    [switch]$SkipModelDownload,
    [switch]$SkipOcrHint
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Write-Step([string]$msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg) { Write-Host "  OK  $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "  !!  $msg" -ForegroundColor Yellow }

Write-Step "Insight Engine media setup (repo: $Root)"

# --- Python venv ---
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Step "Creating .venv (Python 3.12 preferred)"
    $created = $false
    try {
        & py -3.12 -m venv .venv
        if ($LASTEXITCODE -eq 0) { $created = $true }
    } catch { }
    if (-not $created) {
        & python -m venv .venv
    }
}
if (-not (Test-Path $VenvPython)) {
    Write-Error "Failed to create .venv. Install Python 3.12+ and retry."
}
Write-Ok ".venv ready: $VenvPython"

Write-Step "Install base + media Python packages"
& $VenvPython -m pip install -U pip
& $VenvPython -m pip install -r (Join-Path $Root "requirements.txt")
& $VenvPython -m pip install -r (Join-Path $Root "requirements-media.txt")
Write-Ok "pip packages installed (see requirements.txt / requirements-media.txt)"

# --- FFmpeg ---
Write-Step "Check FFmpeg (ffprobe/ffmpeg on PATH)"
$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
$ffprobe = Get-Command ffprobe -ErrorAction SilentlyContinue
if ($ffmpeg -and $ffprobe) {
    Write-Ok "ffmpeg: $($ffmpeg.Source)"
    Write-Ok "ffprobe: $($ffprobe.Source)"
} else {
    Write-Warn "FFmpeg not found on PATH. Video/audio upload needs it."
    Write-Host "  Install options (pick one):" -ForegroundColor Yellow
    Write-Host "    winget install Gyan.FFmpeg"
    Write-Host "    choco install ffmpeg -y"
    Write-Host "  Then reopen the terminal and re-run this script."
}

# --- Tesseract (optional OCR) ---
if (-not $SkipOcrHint) {
    Write-Step "Check Tesseract OCR (optional)"
    $tess = Get-Command tesseract -ErrorAction SilentlyContinue
    if ($tess) {
        Write-Ok "tesseract: $($tess.Source)"
    } else {
        Write-Warn "Tesseract not found (OCR optional; ASR does not need it)."
        Write-Host "    winget install UB-Mannheim.TesseractOCR"
        Write-Host "  Install Chinese+English language packs if prompted."
    }
}

# --- Prefetch Whisper model ---
$modelDir = Join-Path $Root "data\models\faster-whisper"
New-Item -ItemType Directory -Force -Path $modelDir | Out-Null

if (-not $SkipModelDownload) {
    Write-Step "Prefetch faster-whisper model '$ModelSize' -> $modelDir"
    Write-Host "  First download may take several minutes (network)." -ForegroundColor DarkGray
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
        Write-Warn "Model prefetch failed. Package may still be installed; first ASR run will retry download."
    } else {
        Write-Ok "Model cached under data/models/faster-whisper"
    }
} else {
    Write-Warn "Skipped model download (-SkipModelDownload). First ASR will download on demand."
}

# --- Env hint file (local, gitignored if user copies to .env) ---
Write-Step "Suggested environment flags"
Write-Host @"
  Add to your local .env (do not commit secrets):

    INSIGHT_ASR_ENABLED=1
    INSIGHT_ASR_MODEL=$ModelSize
    # INSIGHT_OCR_ENABLED=1

  Without ASR: upload a same-name .srt/.vtt with the media file.
  Disable ASR explicitly: INSIGHT_ASR_ENABLED=0
"@

Write-Step "Verify ASR import"
& $VenvPython -c "import faster_whisper; print('faster_whisper', faster_whisper.__version__)"
Write-Ok "Done. Restart public app: .\scripts\run_public.ps1"
