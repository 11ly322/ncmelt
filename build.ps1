param(
    [string]$PythonExe = "python",
    [string]$Iscc = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$env:PYTHONUTF8 = "1"

$Version = "0.1.2alpha"
$AppName = "ncmelt"
$DistRoot = Join-Path $Root "dist"
$AppDir = Join-Path $DistRoot $AppName
$ReleaseDir = Join-Path $Root "release"
$BuildRoot = Join-Path $Root "build"
$Ffmpeg = Join-Path $Root "assets\ffmpeg.exe"
$ZipPath = Join-Path $ReleaseDir "ncmelt-$Version-portable-win64.zip"
$SetupPath = Join-Path $ReleaseDir "ncmelt-Setup-$Version.exe"

Write-Host "==> Checking build prerequisites" -ForegroundColor Cyan
if (-not (Test-Path $Ffmpeg)) {
    throw "assets\ffmpeg.exe is missing. Run scripts\fetch_ffmpeg.ps1 first."
}
& $PythonExe -c "import PyInstaller, customtkinter, tkinterdnd2, mutagen, Crypto, PIL; print('dependencies ok')"
if ($LASTEXITCODE -ne 0) { throw "Python dependencies are incomplete." }

if (-not $Iscc) {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )
    $Iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $Iscc -or -not (Test-Path $Iscc)) {
    throw "Inno Setup 6 was not found. Install it with: winget install JRSoftware.InnoSetup"
}

Write-Host "==> Cleaning previous output" -ForegroundColor Cyan
foreach ($path in @($DistRoot, $BuildRoot, $ReleaseDir)) {
    if (Test-Path $path) { Remove-Item $path -Recurse -Force }
}
New-Item -ItemType Directory -Force -Path $DistRoot | Out-Null

$common = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--distpath", $DistRoot
)

Write-Host "==> Building ncmelt-gui.exe" -ForegroundColor Cyan
$guiArgs = @(
    "--onedir",
    "--windowed",
    "--name", "ncmelt-gui",
    "--icon", (Join-Path $Root "assets\app.ico"),
    "--version-file", (Join-Path $Root "version_info.txt"),
    "--manifest", (Join-Path $Root "ncmelt.manifest"),
    "--add-data", ((Join-Path $Root "assets\app.ico") + ";assets"),
    "--add-data", ((Join-Path $Root "assets\app-64.png") + ";assets"),
    "--add-data", ((Join-Path $Root "assets\app-128.png") + ";assets"),
    "--add-data", ((Join-Path $Root "assets\app-256.png") + ";assets"),
    "--collect-all", "customtkinter",
    "--collect-all", "tkinterdnd2",
    "--hidden-import", "PIL._tkinter_finder",
    "--exclude-module", "numpy",
    "--exclude-module", "pandas",
    "--exclude-module", "scipy",
    "--workpath", (Join-Path $BuildRoot "gui"),
    "--specpath", (Join-Path $BuildRoot "gui"),
    (Join-Path $Root "app.py")
)
& $PythonExe @common @guiArgs
if ($LASTEXITCODE -ne 0) { throw "GUI build failed." }

Write-Host "==> Building ncmelt.exe (CLI)" -ForegroundColor Cyan
$cliArgs = @(
    "--onefile",
    "--console",
    "--name", "ncmelt",
    "--icon", (Join-Path $Root "assets\app.ico"),
    "--version-file", (Join-Path $Root "version_info.txt"),
    "--manifest", (Join-Path $Root "ncmelt.manifest"),
    "--exclude-module", "customtkinter",
    "--exclude-module", "tkinterdnd2",
    "--exclude-module", "numpy",
    "--exclude-module", "pandas",
    "--exclude-module", "scipy",
    "--workpath", (Join-Path $BuildRoot "cli"),
    "--specpath", (Join-Path $BuildRoot "cli"),
    (Join-Path $Root "cli_main.py")
)
& $PythonExe @common @cliArgs
if ($LASTEXITCODE -ne 0) { throw "CLI build failed." }

Write-Host "==> Assembling portable application" -ForegroundColor Cyan
if (Test-Path $AppDir) { Remove-Item $AppDir -Recurse -Force }
Move-Item (Join-Path $DistRoot "ncmelt-gui") $AppDir
Copy-Item (Join-Path $DistRoot "ncmelt.exe") (Join-Path $AppDir "ncmelt.exe") -Force
Remove-Item (Join-Path $DistRoot "ncmelt.exe") -Force
Copy-Item $Ffmpeg (Join-Path $AppDir "ffmpeg.exe") -Force

Copy-Item "README.md" $AppDir -Force
Copy-Item "使用说明.txt" $AppDir -Force
Copy-Item "LICENSE" $AppDir -Force
Copy-Item "THIRD_PARTY_NOTICES.txt" $AppDir -Force
Copy-Item "docs" $AppDir -Recurse -Force
New-Item -ItemType Directory -Force -Path (Join-Path $AppDir "licenses") | Out-Null
Copy-Item "LICENSE" (Join-Path $AppDir "licenses\GPL-3.0.txt") -Force

Write-Host "==> Adding GPL source bundle" -ForegroundColor Cyan
$sourceDir = Join-Path $AppDir "source"
New-Item -ItemType Directory -Force -Path $sourceDir | Out-Null
foreach ($name in @(
    "app.py", "cli_main.py", "pyproject.toml", "requirements.txt",
    "requirements-dev.txt", "build.ps1", "installer.iss", "ncmelt.manifest",
    "version_info.txt", "README.md", "使用说明.txt", "LICENSE",
    "THIRD_PARTY_NOTICES.txt"
)) {
    Copy-Item $name $sourceDir -Force
}
foreach ($name in @("ncmelt", "scripts", "tests", "docs", "installer")) {
    Copy-Item $name $sourceDir -Recurse -Force
}
$sourceAssets = Join-Path $sourceDir "assets"
New-Item -ItemType Directory -Force -Path $sourceAssets | Out-Null
foreach ($icon in @("app.ico", "app.png", "app-64.png", "app-128.png", "app-256.png")) {
    Copy-Item (Join-Path $Root "assets\$icon") $sourceAssets -Force
}
Get-ChildItem $sourceDir -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem $sourceDir -Recurse -File -Filter "*.pyc" | Remove-Item -Force
Get-ChildItem $sourceDir -Recurse -Directory -Filter "generated" | Remove-Item -Recurse -Force

Write-Host "==> Creating portable zip" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path $AppDir -DestinationPath $ZipPath -CompressionLevel Optimal

Write-Host "==> Building installer" -ForegroundColor Cyan
& $Iscc (Join-Path $Root "installer.iss") /Qp
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed." }
if (-not (Test-Path $SetupPath)) {
    throw "Installer was not produced at $SetupPath"
}

$hashLines = @()
foreach ($file in @($SetupPath, $ZipPath)) {
    $hash = (Get-FileHash $file -Algorithm SHA256).Hash.ToLower()
    $hashLines += "$hash  $([System.IO.Path]::GetFileName($file))"
}
$hashFile = Join-Path $ReleaseDir "SHA256SUMS.txt"
Set-Content -Path $hashFile -Value ($hashLines -join "`n") -Encoding ASCII

$appSize = (Get-ChildItem $AppDir -Recurse -File | Measure-Object Length -Sum).Sum
$zipSize = (Get-Item $ZipPath).Length
$setupSize = (Get-Item $SetupPath).Length
Write-Host ""
Write-Host "Build complete." -ForegroundColor Green
Write-Host ("App folder: {0} ({1:N1} MB)" -f $AppDir, ($appSize / 1MB))
Write-Host ("Portable:   {0} ({1:N1} MB)" -f $ZipPath, ($zipSize / 1MB))
Write-Host ("Installer:  {0} ({1:N1} MB)" -f $SetupPath, ($setupSize / 1MB))
Write-Host ("SHA256:     {0}" -f $hashFile)
