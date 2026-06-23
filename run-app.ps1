<#
.SYNOPSIS
    Launch the cert-poc development servers (PowerShell).

.DESCRIPTION
    Run this from the repository root. It starts two servers, each in its own
    PowerShell window:
      - FastAPI backend  : python -m uvicorn api.main:app  (default :8000, --reload)
      - Next.js frontend : npm run dev                      (default :3000)

    web/.env.local NEXT_PUBLIC_API_BASE must match the backend port so the
    frontend connects to the real server (otherwise it runs in mock mode).
    Press Ctrl+C in each window to stop that server.

.PARAMETER ApiPort
    FastAPI port (default 8000).

.PARAMETER WebPort
    Next.js port (default 3000).

.PARAMETER Install
    Install dependencies before launching (.venv creation + pip install -r requirements.txt + npm install).

.PARAMETER NoReload
    Disable uvicorn auto-reload (avoids restarts during long LLM runs).

.EXAMPLE
    .\run-app.ps1
    .\run-app.ps1 -Install
    .\run-app.ps1 -ApiPort 8001 -WebPort 3001
#>

[CmdletBinding()]
param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 3000,
    [switch]$Install,
    [switch]$NoReload
)

$ErrorActionPreference = "Stop"

# -- Pin paths to the script location (repo root) --------------------
$Root = $PSScriptRoot
$WebDir = Join-Path $Root "web"

Write-Host "cert-poc dev -- root: $Root" -ForegroundColor Cyan

# -- Pre-flight checks -----------------------------------------------
if (-not (Test-Path (Join-Path $Root "api\main.py"))) {
    throw "Cannot find api\main.py. Run this from the repository root."
}
if (-not (Test-Path (Join-Path $WebDir "package.json"))) {
    throw "Cannot find web\package.json."
}

function Test-Command($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

if (-not (Test-Command "python")) { throw "python not found on PATH." }
if (-not (Test-Command "npm"))    { throw "npm not found on PATH." }

$VenvDir = Join-Path $Root ".venv"
$VenvPy = Join-Path $VenvDir "Scripts\python.exe"

function Ensure-Venv {
    if (Test-Path $VenvPy) { return }
    Write-Host "[setup] python -m venv .venv" -ForegroundColor Yellow
    python -m venv $VenvDir
}

# -- Install dependencies (-Install) ---------------------------------
if ($Install) {
    Ensure-Venv
    Write-Host "[install] pip install -r requirements.txt" -ForegroundColor Yellow
    & $VenvPy -m pip install -r (Join-Path $Root "requirements.txt")
    if (Test-Path (Join-Path $Root "api\requirements.txt")) {
        Write-Host "[install] pip install -r api\requirements.txt" -ForegroundColor Yellow
        & $VenvPy -m pip install -r (Join-Path $Root "api\requirements.txt")
    }
    Write-Host "[install] npm install (web)" -ForegroundColor Yellow
    Push-Location $WebDir
    npm install
    Pop-Location
}

if (Test-Path $VenvPy) {
    $PythonCmd = $VenvPy
} else {
    $PythonCmd = "python"
}

# -- Port-in-use check (warning only) --------------------------------
function Test-PortInUse($port) {
    try {
        return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop)
    } catch {
        return $false
    }
}
foreach ($p in @($ApiPort, $WebPort)) {
    if (Test-PortInUse $p) {
        Write-Host "[warn] Port $p is already in use. Use -ApiPort/-WebPort to change it if it conflicts." -ForegroundColor Red
    }
}

# -- Backend (FastAPI) launch arguments ------------------------------
$reloadArg = if ($NoReload) { "" } else { "--reload" }
$apiCmd = "`"$PythonCmd`" -m uvicorn api.main:app --port $ApiPort $reloadArg"

# -- Frontend (Next.js) launch arguments -----------------------------
$webCmd = "npm run dev -- --port $WebPort"

Write-Host ""
Write-Host "[backend] $apiCmd   (cwd: $Root)"      -ForegroundColor Green
Write-Host "[frontend] $webCmd  (cwd: $WebDir)"    -ForegroundColor Green
Write-Host ""

# -- Launch each server in its own PowerShell window -----------------
# -NoExit: keeps the window open so you can read logs and Ctrl+C to stop.
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location -LiteralPath '$Root'; `$Host.UI.RawUI.WindowTitle='cert-poc API :$ApiPort'; $apiCmd"
)

Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location -LiteralPath '$WebDir'; `$Host.UI.RawUI.WindowTitle='cert-poc WEB :$WebPort'; $webCmd"
)

Write-Host "Both servers launched in new windows." -ForegroundColor Cyan
Write-Host "  - API : http://localhost:$ApiPort  (health: /health, docs: /docs)"
Write-Host "  - WEB : http://localhost:$WebPort  (-> /sessions)"
Write-Host "Press Ctrl+C in each window to stop." -ForegroundColor DarkGray
