param(
    [string]$OutputDir = "dist\windows"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Get-PythonLauncher {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return "py"
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return "python"
    }
    $pyFromWhere = where.exe py 2>$null
    if ($pyFromWhere) {
        return ($pyFromWhere | Select-Object -First 1).Trim()
    }
    $pythonFromWhere = where.exe python 2>$null
    if ($pythonFromWhere) {
        return ($pythonFromWhere | Select-Object -First 1).Trim()
    }
    $knownPaths = @(
        (Join-Path $env:WINDIR "py.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
        "C:\Windows\py.exe"
    )
    foreach ($path in $knownPaths) {
        if ($path -and (Test-Path $path)) {
            return $path
        }
    }
    throw "Kein Python-Launcher gefunden. Installiere Python 3.12+ mit py.exe oder python.exe."
}

$Launcher = Get-PythonLauncher
$LauncherLeaf = [System.IO.Path]::GetFileName($Launcher).ToLowerInvariant()
$IsPyLauncher = ($Launcher -eq "py" -or $LauncherLeaf -eq "py.exe")
$BuildVenv = Join-Path $ProjectRoot ".venv-build"
$BuildPython = Join-Path $BuildVenv "Scripts\python.exe"
$ResolvedOutputDir = $OutputDir
if (-not [System.IO.Path]::IsPathRooted($ResolvedOutputDir)) {
    $ResolvedOutputDir = Join-Path $ProjectRoot $ResolvedOutputDir
}

function Wait-ForPath {
    param(
        [string]$Path,
        [int]$TimeoutSeconds = 10,
        [int]$PollMilliseconds = 250
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path $Path) {
            return $true
        }
        Start-Sleep -Milliseconds $PollMilliseconds
    }
    return (Test-Path $Path)
}

if (-not (Test-Path $BuildPython)) {
    if (Test-Path $BuildVenv) {
        Remove-Item $BuildVenv -Recurse -Force
    }

    if ($IsPyLauncher) {
        try {
            & "$Launcher" -3.12 -m venv $BuildVenv
        }
        catch {
            & "$Launcher" -3 -m venv $BuildVenv
        }
    }
    else {
        & "$Launcher" -m venv $BuildVenv
    }
}

if (-not (Wait-ForPath -Path $BuildPython -TimeoutSeconds 10)) {
    throw "Build-Venv konnte nicht erstellt werden. Erwartet: $BuildPython"
}

function Invoke-BuildPython {
    param([string[]]$Arguments)
    & "$BuildPython" @Arguments
    $exitCode = $LASTEXITCODE
    if (-not $?) {
        throw "Python-Kommando fehlgeschlagen: $BuildPython $($Arguments -join ' ')"
    }
    if ($null -ne $exitCode -and $exitCode -ne 0) {
        throw "Python-Kommando fehlgeschlagen: $BuildPython $($Arguments -join ' ') (ExitCode: $exitCode)"
    }
}

Invoke-BuildPython @("-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools")
Invoke-BuildPython @("-m", "pip", "install", "pyinstaller")
Invoke-BuildPython @("-m", "pip", "install", "-e", "$ProjectRoot")
Invoke-BuildPython @("-m", "pip", "install", "pywebview", "pystray", "pillow")

$BuildDir = Join-Path $ProjectRoot "build\pyinstaller"
if (Test-Path $BuildDir) {
    Remove-Item $BuildDir -Recurse -Force
}
if (Test-Path $ResolvedOutputDir) {
    Remove-Item $ResolvedOutputDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
New-Item -ItemType Directory -Force -Path $ResolvedOutputDir | Out-Null

Invoke-BuildPython @(
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--noconsole",
    "--name",
    "Alertivo",
    "--distpath",
    $ResolvedOutputDir,
    "--workpath",
    $BuildDir,
    "--paths",
    (Join-Path $ProjectRoot "src"),
    "--add-data",
    ((Join-Path $ProjectRoot "src\gpu_alerts\control_center_template.html") + ";gpu_alerts"),
    (Join-Path $ProjectRoot "scripts\alertivo_exe_entry.py")
)

Start-Sleep -Milliseconds 750

$BundleDir = Join-Path $ResolvedOutputDir "bundle"
New-Item -ItemType Directory -Force -Path $BundleDir | Out-Null

$exeCandidates = @(
    (Join-Path $ResolvedOutputDir "Alertivo.exe"),
    (Join-Path $ProjectRoot "dist\windows\Alertivo.exe"),
    (Join-Path $ProjectRoot "dist/windows/Alertivo.exe")
)
$ExePath = $exeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $ExePath) {
    foreach ($candidate in $exeCandidates) {
        if (Wait-ForPath -Path $candidate -TimeoutSeconds 5) {
            $ExePath = $candidate
            break
        }
    }
}
if (-not $ExePath -and (Test-Path $ResolvedOutputDir)) {
    $found = Get-ChildItem -Path $ResolvedOutputDir -Filter "Alertivo.exe" -File -Recurse -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($found) {
        $ExePath = $found.FullName
    }
}
if (-not $ExePath) {
    throw "PyInstaller hat keine EXE erzeugt. Erwartete Kandidaten: $($exeCandidates -join ', ')"
}

Copy-Item $ExePath (Join-Path $BundleDir "Alertivo.exe") -Force
Copy-Item (Join-Path $ProjectRoot "system.json") (Join-Path $BundleDir "system.json") -Force
if (Test-Path (Join-Path $ProjectRoot "assets")) {
    Copy-Item (Join-Path $ProjectRoot "assets") (Join-Path $BundleDir "assets") -Recurse -Force
}
if (Test-Path (Join-Path $ProjectRoot "wav")) {
    Copy-Item (Join-Path $ProjectRoot "wav") (Join-Path $BundleDir "wav") -Recurse -Force
}

$hiddenStarter = @'
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ExePath = Join-Path $ScriptDir "Alertivo.exe"
$ConfigPath = Join-Path $ScriptDir "system.json"
$SetupPath = Join-Path $ScriptDir "first-run-setup.ps1"

if (-not (Test-Path $ExePath)) {
    throw "EXE nicht gefunden: $ExePath"
}

if (Test-Path $SetupPath) {
    & $SetupPath -SystemPath $ConfigPath
}

Start-Process -WindowStyle Hidden -FilePath $ExePath -ArgumentList @(
    "--config", $ConfigPath
)
'@
Set-Content -Path (Join-Path $BundleDir "start-alertivo-hidden.ps1") -Value $hiddenStarter -Encoding UTF8

$runBat = @"
@echo off
setlocal
set "POWERSHELL_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if exist "%POWERSHELL_EXE%" (
  "%POWERSHELL_EXE%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-alertivo-hidden.ps1"
) else (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-alertivo-hidden.ps1"
)
exit /b 0
"@
Set-Content -Path (Join-Path $BundleDir "run-alertivo.bat") -Value $runBat -Encoding ASCII

$stopBat = @"
@echo off
taskkill /IM Alertivo.exe /F >nul 2>&1
exit /b 0
"@
Set-Content -Path (Join-Path $BundleDir "stop-alertivo.bat") -Value $stopBat -Encoding ASCII

Copy-Item (Join-Path $ProjectRoot "scripts\first_run_setup.ps1") (Join-Path $BundleDir "first-run-setup.ps1") -Force

Write-Host ""
Write-Host "Build erfolgreich."
Write-Host "EXE: $BundleDir\Alertivo.exe"
Write-Host "Start: $BundleDir\run-alertivo.bat"
