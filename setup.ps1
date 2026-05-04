# ─────────────────────────────────────────────────────────────
#  Offline Audit Checklist Generator — Setup (Windows)
#  Usage: .\setup.ps1
#  If blocked run first: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
# ─────────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"
function Info { Write-Host "[setup] $args" -ForegroundColor Cyan }
function Ok   { Write-Host "[  ok ] $args" -ForegroundColor Green }
function Fail { Write-Host "[error] $args" -ForegroundColor Red; exit 1 }

Write-Host ""
Info "Offline Audit Checklist Generator — Setup (Windows)"
Write-Host ""

# ── Python check ─────────────────────────────────────────────
$python = $null
foreach ($cmd in @("python", "python3", "py")) {
    try { if ((& $cmd --version 2>&1) -match "Python 3") { $python = $cmd; break } } catch {}
}
if (-not $python) { Fail "Python 3.10+ not found. Download from https://python.org (tick 'Add to PATH')" }
Info "Python found: $(& $python --version 2>&1)"

# ── Virtual environment ───────────────────────────────────────
if (-not (Test-Path ".venv")) {
    Info "Creating virtual environment..."
    & $python -m venv .venv
    Ok "Created .venv"
} else { Ok "Virtual environment already exists" }

. ".\.venv\Scripts\Activate.ps1"
pip install --upgrade pip --quiet

# ── Dependencies ──────────────────────────────────────────────
Info "Installing dependencies..."
pip install flask pdfplumber python-docx --quiet
Ok "flask, pdfplumber, python-docx installed"

Info "Installing llama-cpp-python with TurboQuant optimizations..."
$env:CMAKE_ARGS = "-DGGML_AVX2=ON -DGGML_FLASH_ATTN=ON -DGGML_NATIVE=ON"
try {
    pip install llama-cpp-python --no-cache-dir --upgrade
    Ok "llama-cpp-python (TurboQuant version) installed"
} catch {
    Fail "Could not build TurboQuant engine. Ensure you have 'Visual Studio C++ Build Tools' installed."
}

# ── Model ─────────────────────────────────────────────────────
if (-not (Test-Path "models")) { New-Item -ItemType Directory -Path "models" | Out-Null }
$modelUrl  = "https://huggingface.co/MaziyarPanahi/Mistral-7B-Instruct-v0.3-GGUF/resolve/main/Mistral-7B-Instruct-v0.3.Q4_K_M.gguf"

if (Test-Path $modelFile) {
    Ok "Model already present: $modelFile"
} else {
    Write-Host ""
    Write-Host "  The model file (~4 GB) is not present."
    $choice = Read-Host "  Download now? [Y/n]"
    if (-not $choice -or $choice -match "^[Yy]") {
        Info "Downloading model..."
        (New-Object System.Net.WebClient).DownloadFile($modelUrl, (Join-Path (Get-Location) $modelFile))
        Ok "Model downloaded"
    } else {
        Write-Host "  Download manually and place at: $modelFile"
    }
}

# ── Fonts ─────────────────────────────────────────────────────
if (-not (Test-Path "static")) { New-Item -ItemType Directory -Path "static" | Out-Null }
if (-not (Test-Path "static\ibmplexsans.woff2")) {
    Info "Downloading UI fonts..."
    $wc = New-Object System.Net.WebClient
    try {
        $wc.DownloadFile("https://fonts.gstatic.com/s/ibmplexsans/v19/zYXgKVElMYYaJe8bpLHnCwDKjQ.woff2",  (Join-Path (Get-Location) "static\ibmplexsans.woff2"))
        $wc.DownloadFile("https://fonts.gstatic.com/s/ibmplexmono/v19/-F6pfjptAgt5VM-kVkqdyU8n3kwq.woff2", (Join-Path (Get-Location) "static\ibmplexmono.woff2"))
        Ok "Fonts downloaded"
    } catch { Write-Host "  Could not download fonts (non-critical)" }
}

Write-Host ""
Write-Host "────────────────────────────────────────" -ForegroundColor Green
Write-Host "  Setup complete!" -ForegroundColor Green
Write-Host "────────────────────────────────────────" -ForegroundColor Green
Write-Host ""
Write-Host "  To start:"
Write-Host "    .\.venv\Scripts\Activate.ps1"
Write-Host "    python server.py"
Write-Host ""
Write-Host "  Then open: http://localhost:5000"
Write-Host ""
