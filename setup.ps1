# ─────────────────────────────────────────────────────────────
#  Audit Checklist Generator — Setup Script (Windows)
#  Run in PowerShell as: .\setup.ps1
#  If blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
# ─────────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"

function Info  { Write-Host "[setup] $args" -ForegroundColor Cyan }
function Ok    { Write-Host "[  ok ] $args" -ForegroundColor Green }
function Fail  { Write-Host "[error] $args" -ForegroundColor Red; exit 1 }

Info "Audit Checklist Generator — Setup (Windows)"
Write-Host ""

# ── Python check ─────────────────────────────────────────────
$python = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python 3") { $python = $cmd; break }
    } catch {}
}
if (-not $python) {
    Fail "Python 3 not found. Download from https://python.org (tick 'Add to PATH')"
}
$version = (& $python --version 2>&1) -replace "Python ",""
Info "Found Python $version"

# ── Virtual environment ───────────────────────────────────────
if (-not (Test-Path ".venv")) {
    Info "Creating virtual environment..."
    & $python -m venv .venv
    Ok "Created .venv"
} else {
    Ok "Virtual environment already exists"
}

$activate = ".\.venv\Scripts\Activate.ps1"
. $activate

# ── Install dependencies ──────────────────────────────────────
Info "Installing Python dependencies..."
pip install --upgrade pip --quiet
pip install flask pdfplumber python-docx --quiet
Ok "Core dependencies installed"

Info "Installing llama-cpp-python..."
try {
    pip install llama-cpp-python --quiet
    Ok "llama-cpp-python installed (prebuilt wheel)"
} catch {
    Info "Prebuilt wheel failed — trying source build (requires Visual C++ Build Tools)..."
    pip install llama-cpp-python --no-cache-dir
    Ok "llama-cpp-python installed from source"
}

# ── Model download ────────────────────────────────────────────
$modelDir  = "models"
$modelFile = "$modelDir\Qwen3-14B-Q4_K_M.gguf"
$modelUrl  = "https://huggingface.co/feihu.hf/Qwen3-14B-GGUF/resolve/main/Qwen3-14B-Q4_K_M.gguf"

if (-not (Test-Path $modelDir)) { New-Item -ItemType Directory -Path $modelDir | Out-Null }

if (Test-Path $modelFile) {
    Ok "Model already downloaded: $modelFile"
} else {
    Write-Host ""
    Write-Host "  The LLM model (~9 GB) needs to be downloaded."
    Write-Host "  URL: $modelUrl"
    $choice = Read-Host "  Download now? [Y/n]"
    if (-not $choice) { $choice = "Y" }
    if ($choice -match "^[Yy]") {
        Info "Downloading model — this may take a while..."
        $wc = New-Object System.Net.WebClient
        $wc.DownloadFile($modelUrl, (Resolve-Path $modelDir).Path + "\Qwen3-14B-Q4_K_M.gguf")
        Ok "Model downloaded"
    } else {
        Write-Host ""
        Write-Host "  Skipped. Download manually later:"
        Write-Host "    $modelUrl"
        Write-Host "  Save to: $modelFile"
    }
}

# ── Static fonts ──────────────────────────────────────────────
$staticDir = "static"
if (-not (Test-Path $staticDir)) { New-Item -ItemType Directory -Path $staticDir | Out-Null }
$sansFile = "$staticDir\ibmplexsans.woff2"
$monoFile = "$staticDir\ibmplexmono.woff2"
if (-not (Test-Path $sansFile) -or -not (Test-Path $monoFile)) {
    Info "Downloading UI fonts..."
    $wc = New-Object System.Net.WebClient
    try {
        $wc.DownloadFile("https://fonts.gstatic.com/s/ibmplexsans/v19/zYXgKVElMYYaJe8bpLHnCwDKjQ.woff2", (Resolve-Path $staticDir).Path + "\ibmplexsans.woff2")
        $wc.DownloadFile("https://fonts.gstatic.com/s/ibmplexmono/v19/-F6pfjptAgt5VM-kVkqdyU8n3kwq.woff2", (Resolve-Path $staticDir).Path + "\ibmplexmono.woff2")
        Ok "Fonts downloaded"
    } catch {
        Write-Host "  Could not download fonts (non-critical, UI will use fallback font)"
    }
}

Write-Host ""
Write-Host "────────────────────────────────────────" -ForegroundColor Green
Write-Host "  Setup complete!" -ForegroundColor Green
Write-Host "────────────────────────────────────────" -ForegroundColor Green
Write-Host ""
Write-Host "  To start the server:"
Write-Host "    .\.venv\Scripts\Activate.ps1"
Write-Host "    python server.py"
Write-Host ""
Write-Host "  Then open: http://localhost:5000"
Write-Host ""
