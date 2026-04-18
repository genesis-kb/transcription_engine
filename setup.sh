#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Bitcoin Transcription Engine — Linux/Mac Setup Script
# Run from the project root: ./setup.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e

# Parse arguments
DOCKER=0
SKIP_VENV=0
WITH_WHISPER=0

for arg in "$@"; do
    case $arg in
        --docker)
        DOCKER=1
        ;;
        --skip-venv)
        SKIP_VENV=1
        ;;
        --with-whisper)
        WITH_WHISPER=1
        ;;
    esac
done

# Colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

print_step() {
    echo -e "\n${CYAN}──────────────────────────────────────────${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}──────────────────────────────────────────${NC}"
}

print_success() { echo -e "  ${GREEN}✓ $1${NC}"; }
print_warn() { echo -e "  ${YELLOW}⚠ $1${NC}"; }
print_fail() { echo -e "  ${RED}✗ $1${NC}"; }

# ── Header ────────────────────────────────────────────────────────────────────
echo -e "\n  Bitcoin Transcription Engine — Setup"
echo -e "  =====================================\n"

# ── Docker path ───────────────────────────────────────────────────────────────
if [ $DOCKER -eq 1 ]; then
    print_step "Docker Setup"

    if ! command -v docker &> /dev/null; then
        print_fail "Docker is not installed."
        exit 1
    fi
    print_success "Docker found: $(docker --version)"

    if [ ! -f .env ]; then
        cp env.example .env
        print_warn ".env created from env.example — fill in your API keys before continuing!"
        echo -e "      Edit .env now, then run:  docker compose up --build\n"
        exit 0
    fi

    print_step "Building and starting Docker services"
    docker compose up --build -d
    print_success "Services started. Server: http://localhost:8000"
    print_success "Health check: http://localhost:8000/health\n"
    
    echo -e "  Useful commands:"
    echo -e "    docker compose logs -f server      # tail server logs"
    echo -e "    docker compose down                 # stop all services\n"
    exit 0
fi

# ── Local (non-Docker) setup ──────────────────────────────────────────────────

print_step "1. Checking Python"
if ! command -v python3 &> /dev/null; then
    print_fail "python3 not found."
    exit 1
fi

# Check version (>= 3.10)
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' &> /dev/null; then
    print_fail "Python 3.10 or higher is required. Found: Python ${PYTHON_VERSION}"
    exit 1
fi

print_success "Found: Python ${PYTHON_VERSION}"

print_step "2. Checking FFmpeg"
if command -v ffmpeg &> /dev/null; then
    print_success "FFmpeg found: $(ffmpeg -version | head -n1)"
else
    print_warn "FFmpeg not found in PATH. Please install it (e.g. apt install ffmpeg or brew install ffmpeg)"
fi

print_step "3. Setting up virtual environment"
if [ $SKIP_VENV -eq 0 ]; then
    if [ ! -d "venv" ]; then
        python3 -m venv venv
        print_success "Virtual environment created at ./venv"
    else
        print_success "Virtual environment already exists"
    fi
    source venv/bin/activate
    print_success "Virtual environment activated"
else
    print_warn "Skipping venv creation (--skip-venv flag set)"
fi

print_step "4. Installing Python dependencies"
pip install --upgrade pip --quiet
pip install --no-cache-dir -r requirements.txt
print_success "Core dependencies installed"

if [ $WITH_WHISPER -eq 1 ]; then
    echo -e "  ${CYAN}Installing Whisper support...${NC}"
    pip install --no-cache-dir -r requirements-whisper.txt
    print_success "Whisper dependencies installed"
fi

pip install --no-cache-dir -e . --quiet
print_success "Package installed in editable mode"

print_step "5. Configuring environment"
if [ ! -f .env ]; then
    cp env.example .env
    print_success ".env created from env.example"
    print_warn "ACTION REQUIRED: Edit .env and fill in your API keys."
else
    print_success ".env already exists"
fi

print_step "6. Pipeline configuration"
if [ ! -f config.ini ]; then
    cp config.ini.example config.ini
    print_success "config.ini created from config.ini.example"
else
    print_success "config.ini already exists"
fi

echo -e "\n${GREEN}─────────────────────────────────────────────${NC}"
echo -e "${GREEN}  Setup complete!${NC}"
echo -e "${GREEN}─────────────────────────────────────────────${NC}\n"

echo -e "  Next steps:"
echo -e "    1. Edit .env with your API keys (if not done already)"
echo -e "    2. Start the server:"
echo -e "         source venv/bin/activate"
echo -e "         python -m uvicorn server:app --host 0.0.0.0 --port 8000\n"
