# Convenience entry: right-click → Run with PowerShell (prefer Admin for FFmpeg/winget)
# Or from a terminal in this folder:
#   powershell -ExecutionPolicy Bypass -File .\一键安装启动.ps1
param(
    [ValidateSet("tiny", "base", "small", "medium", "large-v3")]
    [string]$ModelSize = "tiny",
    [switch]$NoLaunch,
    [switch]$SkipModelDownload,
    [switch]$SkipOcr
)

$ErrorActionPreference = "Stop"
& "$PSScriptRoot\scripts\install_and_run.ps1" `
    -ModelSize $ModelSize `
    -NoLaunch:$NoLaunch `
    -SkipModelDownload:$SkipModelDownload `
    -SkipOcr:$SkipOcr
