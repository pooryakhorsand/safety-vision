<#
.SYNOPSIS
  Builds the two self-contained Python runtimes of the desktop app under desktop\runtime\.

    runtime\web\     Django, waitress, whitenoise and the launcher's packages (pywebview, pystray, Pillow)
    runtime\engine\  PyTorch, Ultralytics, BoxMOT, OpenCV, ONNX Runtime

.EXAMPLE
  .\desktop\build\build_runtimes.ps1                 # GPU engine, CUDA 12.1 build of PyTorch
  .\desktop\build\build_runtimes.ps1 -Cuda cu124      # another CUDA build
  .\desktop\build\build_runtimes.ps1 -Cpu             # CPU-only engine
  .\desktop\build\build_runtimes.ps1 -Only engine     # rebuild one runtime

  Each runtime is a copy of a standalone CPython (managed by uv), so it runs on a computer without Python.
  desktop\runtime\versions.txt lists every installed package and its version.
#>
param(
    [string]$Cuda = "cu121",
    [switch]$Cpu,
    [string]$PythonVersion = "3.11",
    [ValidateSet("all", "web", "engine")][string]$Only = "all"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..\..").Path
$RuntimeDir = Join-Path $Root "desktop\runtime"
New-Item -ItemType Directory -Force $RuntimeDir | Out-Null

function Assert-Ok($what) {
    if ($LASTEXITCODE -ne 0) { throw "$what failed (exit code $LASTEXITCODE)" }
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    python -m pip install --quiet uv
    Assert-Ok "installing uv"
}

# One standalone CPython that both runtimes are copied from.
uv python install $PythonVersion
Assert-Ok "uv python install"
$BasePython = (uv python find $PythonVersion --no-project).Trim()
Assert-Ok "uv python find"
$BaseDir = Split-Path $BasePython -Parent

function New-Runtime($name) {
    $target = Join-Path $RuntimeDir $name
    if (Test-Path $target) { Remove-Item -Recurse -Force $target }
    Copy-Item -Recurse $BaseDir $target
    # uv marks its Pythons as "externally managed"; this copy is ours to fill.
    Get-ChildItem $target -Recurse -Filter "EXTERNALLY-MANAGED" | Remove-Item -Force
    $python = Join-Path $target "python.exe"
    & $python -m ensurepip --upgrade
    Assert-Ok "ensurepip ($name)"
    return $python
}

function Write-Versions($name, $python) {
    $freeze = & $python -m pip freeze
    Add-Content -Path (Join-Path $RuntimeDir "versions.txt") -Value (@("", "[$name]") + $freeze)
}

if ($Only -eq "all") { Set-Content -Path (Join-Path $RuntimeDir "versions.txt") -Value "Python $PythonVersion" }

if ($Only -in "all", "web") {
    Write-Host "== web runtime"
    $python = New-Runtime "web"
    & $python -m pip install --no-warn-script-location -r (Join-Path $Root "requirements.txt") -r (Join-Path $Root "desktop\requirements.txt")
    Assert-Ok "installing the web packages"
    Write-Versions "web" $python
}

if ($Only -in "all", "engine") {
    Write-Host "== engine runtime ($(if ($Cpu) { 'CPU' } else { $Cuda }))"
    $python = New-Runtime "engine"
    $index = if ($Cpu) { "https://download.pytorch.org/whl/cpu" } else { "https://download.pytorch.org/whl/$Cuda" }
    & $python -m pip install --no-warn-script-location torch torchvision --index-url $index
    Assert-Ok "installing PyTorch"

    $requirements = Join-Path $Root "engine\requirements.txt"
    if ($Cpu) {
        # No GPU build of ONNX Runtime on a CPU-only installer.
        $requirements = Join-Path $RuntimeDir "engine-requirements-cpu.txt"
        (Get-Content (Join-Path $Root "engine\requirements.txt")) -replace "^onnxruntime-gpu", "onnxruntime" | Set-Content $requirements
    }
    & $python -m pip install --no-warn-script-location -r $requirements
    Assert-Ok "installing the engine packages"
    Write-Versions "engine" $python
}

Write-Host "Runtimes are in $RuntimeDir"
