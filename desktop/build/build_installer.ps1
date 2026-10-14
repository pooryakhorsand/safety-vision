<#
.SYNOPSIS
  Compiles the installer from desktop\stage\ with Inno Setup 6.

.EXAMPLE
  .\desktop\build\build_installer.ps1 -Variant gpu      # SafetyVision-<version>-gpu-setup.exe
  .\desktop\build\build_installer.ps1 -Variant cpu

  Needs Inno Setup 6 (ISCC.exe) and, in desktop\installer\redist\, the Microsoft Visual C++ runtime
  (vc_redist.x64.exe) and the Edge WebView2 bootstrapper (MicrosoftEdgeWebview2Setup.exe).
  -DownloadRedist fetches both from Microsoft.
#>
param(
    [ValidateSet("gpu", "cpu")][string]$Variant = "gpu",
    [switch]$DownloadRedist
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..\..").Path
$Redist = Join-Path $Root "desktop\installer\redist"
New-Item -ItemType Directory -Force $Redist | Out-Null

if ($DownloadRedist) {
    Invoke-WebRequest "https://aka.ms/vs/17/release/vc_redist.x64.exe" -OutFile (Join-Path $Redist "vc_redist.x64.exe")
    Invoke-WebRequest "https://go.microsoft.com/fwlink/p/?LinkId=2124703" -OutFile (Join-Path $Redist "MicrosoftEdgeWebview2Setup.exe")
}
foreach ($file in "vc_redist.x64.exe", "MicrosoftEdgeWebview2Setup.exe") {
    if (-not (Test-Path (Join-Path $Redist $file))) { throw "Missing $file in $Redist (use -DownloadRedist)." }
}
if (-not (Test-Path (Join-Path $Root "desktop\stage\app"))) { throw "Run build_app.ps1 first." }

$iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if (-not $iscc) { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
if (-not (Test-Path $iscc)) { throw "Inno Setup 6 was not found." }

# Names come from the profile, so the installer follows the product name.
$profile = python -c "import yaml,sys; p=yaml.safe_load(open(r'$Root\profiles\default\profile.yaml',encoding='utf-8')); print(p['product_name']['en']); print(p['short_name'])"
$AppName, $ShortName = $profile
$Version = (Get-Content (Join-Path $Root "VERSION")).Trim()

& $iscc "/DAppName=$AppName" "/DShortName=$ShortName" "/DAppVersion=$Version" "/DVariant=$Variant" (Join-Path $Root "desktop\installer\setup.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
Write-Host "Installer is in desktop\installer\Output"
