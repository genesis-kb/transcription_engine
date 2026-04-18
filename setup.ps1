# ─────────────────────────────────────────────────────────────────────────────
# Bitcoin Transcription Engine — Windows Setup Script
# Run from the project root: .\setup.ps1
# ─────────────────────────────────────────────────────────────────────────────

param(
    [switch]$SkipVenv,       # Skip virtual environment creation
    [switch]$WithWhisper,    # Also install local Whisper support
    [switch]$Docker          # Set up using Docker instead
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$msg)
    Write-Host ""
    Write-Host "──────────────────────────────────────────" -ForegroundColor Cyan
    Write-Host "  $msg" -ForegroundColor Cyan
    Write-Host "──────────────────────────────────────────" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$msg)
    Write-Host "  ✓ $msg" -ForegroundColor Green
}

function Write-Warn {
    param([string]$msg)
    Write-Host "  ⚠ $msg" -ForegroundColor Yellow
}

function Write-Fail {
    param([string]$msg)
    Write-Host "  ✗ $msg" -ForegroundColor Red
}

# ── Header ────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Bitcoin Transcription Engine — Setup" -ForegroundColor White
Write-Host "  =====================================" -ForegroundColor White
Write-Host ""

# ── Docker path ───────────────────────────────────────────────────────────────
if ($Docker) {
    Write-Step "Docker Setup"

    # Check Docker
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Fail "Docker is not installed. Install from https://docs.docker.com/desktop/windows/"
        exit 1
    }
    Write-Success "Docker found: $(docker --version)"

    # .env
    if (-not (Test-Path ".env")) {
        Copy-Item "env.example" ".env"
        Write-Warn ".env created from env.example — fill in your API keys before continuing!"
        Write-Host "      Edit .env now, then run:  docker compose up --build" -ForegroundColor Yellow
        exit 0
    }

    Write-Step "Building and starting Docker services"
    docker compose up --build -d
    Write-Success "Services started. Server: http://localhost:8000"
    Write-Success "Health check: http://localhost:8000/health"
    Write-Host ""
    Write-Host "  Useful commands:" -ForegroundColor White
    Write-Host "    docker compose logs -f server      # tail server logs"
    Write-Host "    docker compose down                 # stop all services"
    Write-Host ""
    exit 0
}

# ── Local (non-Docker) setup ──────────────────────────────────────────────────

# 1. Check Python
Write-Step "1. Checking Python"
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Fail "Python not found. Install Python 3.10+ from https://www.python.org/downloads/"
    exit 1
}
$pyVersion = python --version 2>&1
Write-Success "Found: $pyVersion"
$pyMajor = (python -c "import sys; print(sys.version_info.major)")
$pyMinor = (python -c "import sys; print(sys.version_info.minor)")
if ([int]$pyMajor -lt 3 -or ([int]$pyMajor -eq 3 -and [int]$pyMinor -lt 10)) {
    Write-Fail "Python 3.10 or higher is required (found $pyVersion)"
    exit 1
}

# 2. Check FFmpeg
Write-Step "2. Checking FFmpeg"
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Write-Success "FFmpeg found: $(ffmpeg -version 2>&1 | Select-Object -First 1)"
} else {
    Write-Warn "FFmpeg not found in PATH."
    Write-Host "      The project uses 'static_ffmpeg' as a fallback, but for best results" -ForegroundColor Yellow
    Write-Host "      install FFmpeg: https://ffmpeg.org/download.html" -ForegroundColor Yellow
    Write-Host "      (or via winget: winget install Gyan.FFmpeg)" -ForegroundColor Yellow
}

# 3. Virtual environment
Write-Step "3. Setting up virtual environment"
if (-not $SkipVenv) {
    if (-not (Test-Path "venv")) {
        python -m venv venv
        Write-Success "Virtual environment created at .\venv"
    } else {
        Write-Success "Virtual environment already exists"
    }
    # Activate
    & ".\venv\Scripts\Activate.ps1"
    Write-Success "Virtual environment activated"
} else {
    Write-Warn "Skipping venv creation (--SkipVenv flag set)"
}

# 4. Install dependencies
Write-Step "4. Installing Python dependencies"
pip install --upgrade pip --quiet
pip install --no-cache-dir -r requirements.txt
Write-Success "Core dependencies installed"

if ($WithWhisper) {
    Write-Host "  Installing Whisper support..." -ForegroundColor Cyan
    pip install --no-cache-dir -r requirements-whisper.txt
    Write-Success "Whisper dependencies installed"
}

# Install the package itself
pip install --no-cache-dir -e . --quiet
Write-Success "Package installed in editable mode"

# 5. Environment configuration
Write-Step "5. Configuring environment"
if (-not (Test-Path ".env")) {
    Copy-Item "env.example" ".env"
    Write-Success ".env created from env.example"
    Write-Warn "ACTION REQUIRED: Edit .env and fill in your API keys:"
    Write-Host ""
    Write-Host "      GOOGLE_API_KEY   → https://aistudio.google.com/" -ForegroundColor Yellow
    Write-Host "      YOUTUBE_API_KEY  → https://console.cloud.google.com/" -ForegroundColor Yellow
    Write-Host "      DATABASE_URL     → your PostgreSQL connection string" -ForegroundColor Yellow
    Write-Host "      DEEPGRAM_API_KEY → https://console.deepgram.com/ (optional)" -ForegroundColor Yellow
    Write-Host ""
} else {
    Write-Success ".env already exists"
}

# 6. config.ini
Write-Step "6. Pipeline configuration"
if (-not (Test-Path "config.ini")) {
    Copy-Item "config.ini.example" "config.ini"
    Write-Success "config.ini created from config.ini.example"
} else {
    Write-Success "config.ini already exists"
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "─────────────────────────────────────────────" -ForegroundColor Green
Write-Host "  Setup complete!" -ForegroundColor Green
Write-Host "─────────────────────────────────────────────" -ForegroundColor Green
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor White
Write-Host "    1. Edit .env with your API keys (if not done already)"
Write-Host "    2. Start the server:"
Write-Host "         python -m uvicorn server:app --host 0.0.0.0 --port 8000" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Or use Docker (no Python install needed on host):"
Write-Host "    .\setup.ps1 -Docker" -ForegroundColor Cyan
Write-Host ""
