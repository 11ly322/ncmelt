param(
    [string]$Destination = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not $Destination) {
    $Destination = Join-Path $Root "assets\ffmpeg.exe"
}
if (Test-Path $Destination) {
    Write-Host "FFmpeg already exists: $Destination"
    exit 0
}
$existing = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($existing) {
    New-Item -ItemType Directory -Force -Path (Split-Path $Destination) | Out-Null
    Copy-Item $existing.Source $Destination -Force
    Write-Host "Copied FFmpeg from PATH: $($existing.Source)"
    exit 0
}

$url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
$temp = Join-Path $env:TEMP "ffmpeg-ncmelt.zip"
$extract = Join-Path $env:TEMP "ffmpeg-ncmelt"
Write-Host "Downloading FFmpeg from $url ..."
Invoke-WebRequest -Uri $url -OutFile $temp -UseBasicParsing
if (Test-Path $extract) { Remove-Item $extract -Recurse -Force }
Expand-Archive -Path $temp -DestinationPath $extract -Force
$exe = Get-ChildItem $extract -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
if (-not $exe) { throw "ffmpeg.exe was not found in the downloaded archive." }
New-Item -ItemType Directory -Force -Path (Split-Path $Destination) | Out-Null
Copy-Item $exe.FullName $Destination -Force
Remove-Item $temp -Force -ErrorAction SilentlyContinue
Remove-Item $extract -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "Installed FFmpeg: $Destination"
