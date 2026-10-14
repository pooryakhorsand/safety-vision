<#
.SYNOPSIS
  Puts the application together in desktop\stage\ (program files + the two runtimes), ready for the installer.

  Run build_runtimes.ps1 first. Steps: icons from the profile logo, Persian texts, static files, byte-code.

.EXAMPLE
  .\desktop\build\build_app.ps1
#>
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..\..").Path
$Runtime = Join-Path $Root "desktop\runtime"
$Stage = Join-Path $Root "desktop\stage"
$App = Join-Path $Stage "app"
$WebPython = Join-Path $Runtime "web\python.exe"
$EnginePython = Join-Path $Runtime "engine\python.exe"

function Assert-Ok($what) {
    if ($LASTEXITCODE -ne 0) { throw "$what failed (exit code $LASTEXITCODE)" }
}
if (-not (Test-Path $WebPython) -or -not (Test-Path $EnginePython)) { throw "Run build_runtimes.ps1 first." }

# 1. Icons (needs Pillow and PyMuPDF, which the web runtime does not carry: use the build machine's Python)
python -m pip install --quiet Pillow pymupdf PyYAML polib
Assert-Ok "installing the build tools"
python (Join-Path $Root "desktop\build\make_icon.py")
Assert-Ok "making the icons"

# 2. Persian texts
python (Join-Path $Root "scripts\compile_translations.py")
Assert-Ok "compiling translations"

# 3. Copy the program files
if (Test-Path $Stage) { Remove-Item -Recurse -Force $Stage }
New-Item -ItemType Directory -Force $App | Out-Null
Copy-Item (Join-Path $Root "VERSION") $App
foreach ($file in "LICENSE", "CHANGELOG.md") {
    if (Test-Path (Join-Path $Root $file)) { Copy-Item (Join-Path $Root $file) $App }
}
$skipDirs = @("__pycache__", "tests", "weights", "staticfiles", ".pytest_cache", ".ruff_cache")
$skipFiles = @("*.pyc", "db.sqlite3*", ".env", "*.log")
foreach ($folder in "web", "engine", "profiles") {
    robocopy (Join-Path $Root $folder) (Join-Path $App $folder) /E /NFL /NDL /NJH /NJS /NP /XD @skipDirs /XF @skipFiles | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "copying $folder failed" }
}
# Only the launcher, its settings and its assets belong in the installed app (not the build scripts).
$Desktop = Join-Path $App "desktop"
New-Item -ItemType Directory -Force $Desktop | Out-Null
Copy-Item (Join-Path $Root "desktop\__init__.py") $Desktop
foreach ($folder in "launcher", "config", "assets") {
    robocopy (Join-Path $Root "desktop\$folder") (Join-Path $Desktop $folder) /E /NFL /NDL /NJH /NJS /NP /XD __pycache__ | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "copying desktop\$folder failed" }
}
New-Item -ItemType Directory -Force (Join-Path $App "scripts") | Out-Null
Copy-Item (Join-Path $Root "scripts\compile_translations.py") (Join-Path $App "scripts")
$global:LASTEXITCODE = 0

# 4. Static files (the installed folder is read-only for normal users, so this happens now)
$buildSecret = "build-only-" + ("x" * 40)
$dataTemp = Join-Path $env:TEMP "app-build-data"
$env:APP_DATA_DIR = $dataTemp
$env:DJANGO_DEBUG = "False"; $env:DJANGO_SECRET_KEY = $buildSecret; $env:ENGINE_API_TOKEN = $buildSecret
Push-Location (Join-Path $App "web")
& $WebPython manage.py collectstatic --noinput
Assert-Ok "collectstatic"
Pop-Location
Remove-Item -Recurse -Force $dataTemp -ErrorAction SilentlyContinue
Remove-Item Env:APP_DATA_DIR, Env:DJANGO_DEBUG, Env:DJANGO_SECRET_KEY, Env:ENGINE_API_TOKEN

# 5. Byte-code, so the first start is fast although the install folder cannot be written to later
& $WebPython -m compileall -q $App
& $EnginePython -m compileall -q (Join-Path $App "engine")
$global:LASTEXITCODE = 0

# 6. The runtimes
foreach ($name in "web", "engine") {
    robocopy (Join-Path $Runtime $name) (Join-Path $Stage "runtime\$name") /E /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "copying the $name runtime failed" }
}
$global:LASTEXITCODE = 0
Copy-Item (Join-Path $Runtime "versions.txt") $Stage -ErrorAction SilentlyContinue
Write-Host "Application is ready in $Stage"
