param(
    [ValidateSet("pypi", "git", "local")]
    [string]$Source = $(if ($env:HELLOAGI_INSTALL_SOURCE) { $env:HELLOAGI_INSTALL_SOURCE } else { "pypi" }),
    [string]$Ref = $(if ($env:HELLOAGI_GIT_REF) { $env:HELLOAGI_GIT_REF } else { "main" }),
    [string]$Package = $(if ($env:HELLOAGI_PACKAGE_SPEC) { $env:HELLOAGI_PACKAGE_SPEC } else { "helloagi[rich,telegram]" }),
    [switch]$SkipOnboard,
    [switch]$UpgradePip
)

$ErrorActionPreference = "Stop"

$RepoUrl = if ($env:HELLOAGI_REPO_URL) { $env:HELLOAGI_REPO_URL } else { "https://github.com/mmsk2007/helloagi.git" }
$Root = Split-Path -Parent $PSScriptRoot

function Write-Info {
    param([string]$Message)
    Write-Host "[HelloAGI] $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "[HelloAGI] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[HelloAGI] $Message" -ForegroundColor Yellow
}

function Fail-Install {
    param([string]$Message)
    Write-Host "[HelloAGI] $Message" -ForegroundColor Red
    exit 1
}

function Get-PythonCommand {
    foreach ($candidate in @("py", "python", "python3")) {
        if (Get-Command $candidate -ErrorAction SilentlyContinue) {
            return $candidate
        }
    }
    Fail-Install "Python 3.9+ is required but was not found on PATH."
}

function Invoke-Python {
    param(
        [string]$PythonCmd,
        [string[]]$Arguments
    )

    if ($PythonCmd -eq "py") {
        & py -3 @Arguments
    } else {
        & $PythonCmd @Arguments
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed: $PythonCmd $($Arguments -join ' ')"
    }
}

function Get-PythonVersion {
    param([string]$PythonCmd)

    if ($PythonCmd -eq "py") {
        return (& py -3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    }
    return (& $PythonCmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
}

function Ensure-Pip {
    param([string]$PythonCmd)

    try {
        Invoke-Python $PythonCmd @("-m", "pip", "--version")
        Write-Ok "pip available"
        return
    } catch {
        Write-Info "Bootstrapping pip with ensurepip..."
        Invoke-Python $PythonCmd @("-m", "ensurepip", "--upgrade")
        Write-Ok "pip bootstrapped"
    }
}

function Build-InstallTarget {
    switch ($Source) {
        "pypi" { return $Package }
        "git" { return "helloagi[rich,telegram] @ git+$RepoUrl@$Ref" }
        "local" { return "$Root[rich,telegram]" }
        default { Fail-Install "Unsupported source '$Source'." }
    }
}

Write-Host ""
Write-Host "  HelloAGI Installer" -ForegroundColor White
Write-Host "  Fast Windows bootstrap with immediate onboarding" -ForegroundColor White
Write-Host ""

$pythonCmd = Get-PythonCommand
$version = Get-PythonVersion $pythonCmd
$parts = $version.Split(".")
if ([int]$parts[0] -lt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -lt 9)) {
    Fail-Install "Python 3.9+ is required (found $version)."
}
Write-Ok "Python $version detected"

Ensure-Pip $pythonCmd

if ($UpgradePip) {
    Write-Info "Upgrading pip..."
    Invoke-Python $pythonCmd @("-m", "pip", "install", "--user", "--upgrade", "pip")
}

$installTarget = Build-InstallTarget
Write-Info "Installing HelloAGI from $Source..."
Invoke-Python $pythonCmd @("-m", "pip", "install", "--user", "--upgrade", $installTarget)
Write-Ok "Package installed"

Write-Info "Initializing runtime config..."
try {
    Invoke-Python $pythonCmd @("-m", "agi_runtime.cli", "init")
} catch {
}
Write-Ok "Config ready"

Write-Info "Running health check..."
try {
    Invoke-Python $pythonCmd @("-m", "agi_runtime.cli", "doctor")
} catch {
    Write-Warn "Doctor check reported issues"
}

if (-not $SkipOnboard) {
    Write-Host ""
    Write-Info "Launching onboarding wizard..."
    Invoke-Python $pythonCmd @("-m", "agi_runtime.cli", "onboard")
    Write-Host ""
}

Write-Host "  HelloAGI is installed." -ForegroundColor Green
Write-Host ""
Write-Host "  First-run command:" -ForegroundColor White
Write-Host "    python -m agi_runtime.cli run" -ForegroundColor Cyan
Write-Host ""
Write-Host "  If your PATH already includes Python's Scripts directory, you can also use:" -ForegroundColor White
Write-Host "    helloagi run" -ForegroundColor Cyan
Write-Host ""
