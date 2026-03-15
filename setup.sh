#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Audit Checklist Generator — Setup Script (Linux / macOS)
# ─────────────────────────────────────────────────────────────
set -e

CYAN='\033[0;36m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${CYAN}[setup]${NC} $1"; }
ok()    { echo -e "${GREEN}[  ok ]${NC} $1"; }
error() { echo -e "${RED}[error]${NC} $1"; exit 1; }

info "Audit Checklist Generator — Setup"
echo ""

# ── Python check ────────────────────────────────────────────
PYTHON=$(command -v python3 || command -v python || true)
[ -z "$PYTHON" ] && error "Python 3.10+ not found. Install from https://python.org"
VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
info "Found Python $VERSION at $PYTHON"

# ── Virtual environment ──────────────────────────────────────
if [ ! -d ".venv" ]; then
    info "Creating virtual environment..."
    $PYTHON -m venv .venv
    ok "Created .venv"
else
    ok "Virtual environment already exists"
fi

source .venv/bin/activate

# ── Install dependencies ─────────────────────────────────────
info "Installing Python dependencies..."
pip install --upgrade pip --quiet
pip install flask pdfplumber python-docx --quiet
ok "Core dependencies installed"

# llama-cpp-python — try prebuilt wheel first, fall back to source
info "Installing llama-cpp-python (this may take a few minutes)..."
pip install llama-cpp-python --quiet || {
    info "Prebuilt wheel failed — building from source..."
    CMAKE_ARGS="-DLLAMA_BLAS=ON -DLLAMA_BLAS_VENDOR=OpenBLAS" \
    pip install llama-cpp-python --no-cache-dir
}
ok "llama-cpp-python installed"

# ── Model download ───────────────────────────────────────────
MODEL_DIR="models"
MODEL_FILE="$MODEL_DIR/Qwen3-14B-Q4_K_M.gguf"
MODEL_URL="https://huggingface.co/feihu.hf/Qwen3-14B-GGUF/resolve/main/Qwen3-14B-Q4_K_M.gguf"

mkdir -p "$MODEL_DIR"

if [ -f "$MODEL_FILE" ]; then
    ok "Model already downloaded: $MODEL_FILE"
else
    echo ""
    echo "  The LLM model (~9 GB) needs to be downloaded."
    echo "  URL: $MODEL_URL"
    read -r -p "  Download now? [Y/n] " choice
    choice="${choice:-Y}"
    if [[ "$choice" =~ ^[Yy]$ ]]; then
        info "Downloading model (this will take a while on slow connections)..."
        if command -v wget &>/dev/null; then
            wget -q --show-progress "$MODEL_URL" -O "$MODEL_FILE"
        elif command -v curl &>/dev/null; then
            curl -L --progress-bar "$MODEL_URL" -o "$MODEL_FILE"
        else
            error "Neither wget nor curl found. Download manually:\n  $MODEL_URL\n  Save to: $MODEL_FILE"
        fi
        ok "Model downloaded"
    else
        echo ""
        echo "  Skipped. Download manually later:"
        echo "    $MODEL_URL"
        echo "  Save to: $MODEL_FILE"
        echo "  Or set the MODEL_PATH environment variable to an existing model."
    fi
fi

# ── Static fonts (offline) ───────────────────────────────────
STATIC_DIR="static"
mkdir -p "$STATIC_DIR"
if [ ! -f "$STATIC_DIR/ibmplexsans.woff2" ] || [ ! -f "$STATIC_DIR/ibmplexmono.woff2" ]; then
    info "Downloading UI fonts for offline use..."
    SANS_URL="https://fonts.gstatic.com/s/ibmplexsans/v19/zYXgKVElMYYaJe8bpLHnCwDKjQ.woff2"
    MONO_URL="https://fonts.gstatic.com/s/ibmplexmono/v19/-F6pfjptAgt5VM-kVkqdyU8n3kwq.woff2"
    if command -v wget &>/dev/null; then
        wget -q "$SANS_URL" -O "$STATIC_DIR/ibmplexsans.woff2" 2>/dev/null || true
        wget -q "$MONO_URL" -O "$STATIC_DIR/ibmplexmono.woff2" 2>/dev/null || true
    elif command -v curl &>/dev/null; then
        curl -sL "$SANS_URL" -o "$STATIC_DIR/ibmplexsans.woff2" 2>/dev/null || true
        curl -sL "$MONO_URL" -o "$STATIC_DIR/ibmplexmono.woff2" 2>/dev/null || true
    fi
    ok "Fonts downloaded"
fi

echo ""
echo -e "${GREEN}────────────────────────────────────────${NC}"
echo -e "${GREEN}  Setup complete!${NC}"
echo -e "${GREEN}────────────────────────────────────────${NC}"
echo ""
echo "  To start the server:"
echo "    source .venv/bin/activate"
echo "    python3 server.py"
echo ""
echo "  Then open: http://localhost:5000"
echo ""
