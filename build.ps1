# Builds dist\DS2_Fix_Installer.exe (launch_ds2.exe is bundled inside it).
# Needs: Python 3 (py launcher) and PyInstaller  ->  py -3 -m pip install pyinstaller
# Usage: powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$work = Join-Path $root 'build'
$dist = Join-Path $root 'dist'
Remove-Item -Recurse -Force -LiteralPath $work -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $work, $dist | Out-Null

function Build-Exe {
    param([string[]]$ExtraArgs)
    & py -3 -m PyInstaller @ExtraArgs
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
}

# 1) launcher
Build-Exe @('--onefile', '--noconsole', '--name', 'launch_ds2',
    '--distpath', "$work\launcher", '--workpath', "$work\w1", '--specpath', $work,
    '--paths', "$root\src", "$root\src\launch_ds2.py")

# 2) installer (bundles the launcher and the default ini)
Build-Exe @('--onefile', '--windowed', '--name', 'DS2_Fix_Installer',
    '--distpath', "$work\installer", '--workpath', "$work\w2", '--specpath', $work,
    '--add-data', "$work\launcher\launch_ds2.exe;.",
    '--add-data', "$root\src\ds2_keys.ini;.",
    "$root\installer\ds2_installer.py")

# Only the installer is shipped; it carries launch_ds2.exe inside.
Get-ChildItem -LiteralPath $dist -Force | Remove-Item -Recurse -Force
Copy-Item -LiteralPath "$work\installer\DS2_Fix_Installer.exe" -Destination $dist -Force
Write-Host "Done: $dist\DS2_Fix_Installer.exe"
