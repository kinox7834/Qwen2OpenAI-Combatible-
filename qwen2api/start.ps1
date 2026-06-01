$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = 'utf-8'
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)

$Cyan   = @{ForegroundColor = "Cyan"}
$Green  = @{ForegroundColor = "Green"}
$Yellow = @{ForegroundColor = "Yellow"}
$Red    = @{ForegroundColor = "Red"}

Write-Host @Cyan
@"
  ╔═══════════════════════════════════════════════╗
  ║           Qwen2OpenAI v0.1.0                  ║
  ║     Qwen Studio → OpenAI-Compatible API      ║
  ╚═══════════════════════════════════════════════╝
"@
Write-Host ""

# Check Python
try {
    $pyVersion = python --version
} catch {
    Write-Host "[ERROR] Python not found. Install Python 3.10+ and try again." @Red
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "[OK] $pyVersion" @Green

# Check .env
if (-not (Test-Path -LiteralPath ".env")) {
    Write-Host "[INFO] No .env file found. Setup wizard will start on first run." @Yellow
}

# Install deps
Write-Host "[INFO] Checking dependencies..." @Yellow
python -m pip install -r requirements.txt -q 2>&1 | Out-Null

# Detect port from .env or default to 8000
$port = 8000
if (Test-Path -LiteralPath ".env") {
    $match = Select-String -Path ".env" -Pattern "^PORT=" -SimpleMatch
    if ($match) {
        $port = [int]($match.Line -split "=")[1]
    }
}

# Kill existing process on the port
$process = netstat -ano | Select-String ":$port "
if ($process) {
    $pid = ($process.Line -split '\s+')[-1]
    if ($pid) {
        try { Stop-Process -Id $pid -Force -ErrorAction Stop; Write-Host "[OK] Killed old process (PID $pid) on port $port" @Green } catch {}
    }
}

Write-Host ""
python -m qwen2openai $args
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Qwen2OpenAI exited with code $LASTEXITCODE" @Red
    Read-Host "Press Enter to exit"
}
