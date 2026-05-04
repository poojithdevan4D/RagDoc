#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Offline Audit Checklist Generator — Setup (Linux / macOS)
#  Usage: bash setup.sh
# ─────────────────────────────────────────────────────────────
set -e

CYAN='\033[0;36m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
info() { echo -e "${CYAN}[setup]${NC} $1"; }
ok()   { echo -e "${GREEN}[  ok ]${NC} $1"; }
fail() { echo -e "${RED}[error]${NC} $1"; exit 1; }

echo ""
info "Offline Audit Checklist Generator — Setup"
echo ""

# ── Python check ─────────────────────────────────────────────
PYTHON=$(command -v python3 || command -v python || true)
[ -z "$PYTHON" ] && fail "Python 3.10+ not found. Install from https://python.org"
VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
info "Python $VERSION found"

# ── Virtual environment ───────────────────────────────────────
if [ ! -d ".venv" ]; then
    info "Creating virtual environment..."
    $PYTHON -m venv .venv
    ok "Created .venv"
else
    ok "Virtual environment already exists"
fi

source .venv/bin/activate
pip install --upgrade pip --quiet

# ── Dependencies ──────────────────────────────────────────────
info "Installing dependencies..."
pip install flask pdfplumber python-docx --quiet
ok "flask, pdfplumber, python-docx installed"

info "Installing llama-cpp-python with TurboQuant optimizations..."
export CMAKE_ARGS="-DGGML_AVX2=ON -DGGML_FLASH_ATTN=ON -DGGML_NATIVE=ON"
pip install llama-cpp-python --no-cache-dir --upgrade || fail "Could not build TurboQuant engine. Ensure you have build-essential/gcc installed."
ok "llama-cpp-python (TurboQuant version) installed"
ok "llama-cpp-python installed"

# ── Model ─────────────────────────────────────────────────────
mkdir -p models
MODEL_URL="https://huggingface.co/MaziyarPanahi/Mistral-7B-Instruct-v0.3-GGUF/resolve/main/Mistral-7B-Instruct-v0.3.Q4_K_M.gguf"

if [ -f "$MODEL_FILE" ]; then
    ok "Model already present: $MODEL_FILE"
else
    echo ""
    echo "  The model file (~4 GB) is not present."
    echo "  URL: $MODEL_URL"
    read -r -p "  Download now? [Y/n] " choice
    choice="${choice:-Y}"
    if [[ "$choice" =~ ^[Yy]$ ]]; then
        info "Downloading model..."
        if command -v wget &>/dev/null; then
            wget -q --show-progress "$MODEL_URL" -O "$MODEL_FILE"
        elif command -v curl &>/dev/null; then
            curl -L --progress-bar "$MODEL_URL" -o "$MODEL_FILE"
        else
            fail "Neither wget nor curl found. Download manually:\n  $MODEL_URL\n  Save to: $MODEL_FILE"
        fi
        ok "Model downloaded"
    else
        echo ""
        echo "  Download it manually and place it in: $MODEL_FILE"
        echo "  Or set MODEL_PATH to point to an existing model."
    fi
fi

# ── Fonts (optional, for offline UI) ─────────────────────────
mkdir -p static
if [ ! -f "static/ibmplexsans.woff2" ]; then
    info "Downloading UI fonts for offline use..."
    curl -sL "https://fonts.gstatic.com/s/ibmplexsans/v19/zYXgKVElMYYaJe8bpLHnCwDKjQ.woff2" \
         -o static/ibmplexsans.woff2 2>/dev/null || true
    curl -sL "https://fonts.gstatic.com/s/ibmplexmono/v19/-F6pfjptAgt5VM-kVkqdyU8n3kwq.woff2" \
         -o static/ibmplexmono.woff2 2>/dev/null || true
    ok "Fonts downloaded"
fi

echo ""
echo -e "${GREEN}────────────────────────────────────────${NC}"
echo -e "${GREEN}  Setup complete!${NC}"
echo -e "${GREEN}────────────────────────────────────────${NC}"
echo ""
echo "  To start:"
echo "    source .venv/bin/activate"
echo "    python3 server.py"
echo ""
echo "  Then open: http://localhost:5000"
echo ""
