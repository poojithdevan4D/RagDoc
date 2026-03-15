# Audit Checklist Generator

A fully **offline**, AI-powered tool that converts government regulatory PDFs (AFQMS, IMTAR, AQA Directives, HAL policy documents, etc.) into structured DGAQA-format audit checklists in Word (`.docx`).

All processing happens locally — no data leaves your machine.

---

## What It Does

Upload a regulatory PDF → the system:
1. Extracts all auditable clauses from the document
2. Uses a local LLM (Qwen3-14B) to generate YES/NO audit checkpoint questions for each clause
3. Outputs two Word documents:
   - **Master Checklist** — every checkpoint extracted
   - **Audit Sheet** — a depth-controlled random sample (Light / Standard / Deep / Full)

The audit sheet columns match the standard DGAQA 8-column format:
`SL No. | Clause # | Sub Point | Description | Org. Procedure # | Adequacy | Compliant | Remarks`

---

## System Requirements

| Component | Minimum |
|---|---|
| Python | 3.10 or higher |
| RAM | 12 GB (for Qwen3-14B-Q4_K_M) |
| Disk | 12 GB free (9 GB model + workspace) |
| OS | Linux, macOS, Windows 10/11 |
| CPU | Any modern x86-64 (no GPU required) |

> **Note:** The first run after downloading the model takes ~30-60 seconds to load. Subsequent clause processing takes ~30-90 seconds per clause depending on CPU.

---

## Quick Start

### Linux / macOS

```bash
# 1. Clone the repository
git clone https://your-org-git/audit-checklist-generator.git
cd audit-checklist-generator

# 2. Run setup (creates virtualenv, installs dependencies, downloads model)
bash setup.sh

# 3. Activate virtualenv and start
source .venv/bin/activate
python3 server.py

# 4. Open browser
# http://localhost:5000
```

### Windows (PowerShell)

```powershell
# 1. Clone the repository
git clone https://your-org-git/audit-checklist-generator.git
cd audit-checklist-generator

# 2. Allow script execution (one-time, current user only)
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# 3. Run setup
.\setup.ps1

# 4. Activate virtualenv and start
.\.venv\Scripts\Activate.ps1
python server.py

# 5. Open browser
# http://localhost:5000
```

---

## Manual Setup (Without Setup Script)

If you prefer to set up manually or already have a conda/virtualenv environment:

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

> **llama-cpp-python** is the most platform-sensitive dependency. If the above fails:
>
> ```bash
> # Linux — with OpenBLAS acceleration
> CMAKE_ARGS="-DLLAMA_BLAS=ON -DLLAMA_BLAS_VENDOR=OpenBLAS" pip install llama-cpp-python
>
> # macOS — with Metal (Apple Silicon) acceleration
> CMAKE_ARGS="-DLLAMA_METAL=on" pip install llama-cpp-python
>
> # Windows — ensure Visual C++ Build Tools are installed first
> pip install llama-cpp-python --no-cache-dir
> ```

### 2. Download the model

Download **Qwen3-14B-Q4_K_M.gguf** (~9 GB) from HuggingFace:

```
https://huggingface.co/feihu.hf/Qwen3-14B-GGUF/resolve/main/Qwen3-14B-Q4_K_M.gguf
```

Save it to the `models/` folder inside the project:

```
audit-checklist-generator/
└── models/
    └── Qwen3-14B-Q4_K_M.gguf   ← here
```

Using `wget`:
```bash
wget "https://huggingface.co/feihu.hf/Qwen3-14B-GGUF/resolve/main/Qwen3-14B-Q4_K_M.gguf" \
     -O models/Qwen3-14B-Q4_K_M.gguf
```

Using `curl`:
```bash
curl -L "https://huggingface.co/feihu.hf/Qwen3-14B-GGUF/resolve/main/Qwen3-14B-Q4_K_M.gguf" \
     -o models/Qwen3-14B-Q4_K_M.gguf
```

### 3. Download UI fonts (for offline use)

```bash
mkdir -p static
curl -sL "https://fonts.gstatic.com/s/ibmplexsans/v19/zYXgKVElMYYaJe8bpLHnCwDKjQ.woff2" \
     -o static/ibmplexsans.woff2
curl -sL "https://fonts.gstatic.com/s/ibmplexmono/v19/-F6pfjptAgt5VM-kVkqdyU8n3kwq.woff2" \
     -o static/ibmplexmono.woff2
```

### 4. Start the server

```bash
python3 server.py        # Linux / macOS
python  server.py        # Windows
```

Open [http://localhost:5000](http://localhost:5000)

---

## Using a Different Model

The server auto-detects any `.gguf` file in the `models/` folder. To use a different model, either:

**Option A** — Place it in `models/` (auto-detected alphabetically if multiple exist):
```
models/
└── your-model.gguf
```

**Option B** — Set the `MODEL_PATH` environment variable:
```bash
# Linux / macOS
export MODEL_PATH=/path/to/your/model.gguf
python3 server.py

# Windows PowerShell
$env:MODEL_PATH = "C:\path\to\your\model.gguf"
python server.py
```

Other tested models (all Qwen3 variants work; Mistral-7B also works):

| Model | Size | RAM needed | Quality |
|---|---|---|---|
| Qwen3-14B-Q4_K_M *(recommended)* | 9 GB | 12 GB | ★★★★☆ |
| Qwen3-14B-Q5_K_M | 10.5 GB | 13 GB | ★★★★★ |
| Qwen3-14B-Q8_0 | 15.7 GB | 18 GB | ★★★★★ |
| Mistral-7B-Instruct-Q4_K_M | 4.1 GB | 6 GB | ★★★☆☆ |

> If switching to Mistral-7B, the prompt format must be changed in `checklist_generator.py` from ChatML (`<|im_start|>`) back to `[INST]...[/INST]`.

---

## Conda Environment (Alternative to venv)

If your organisation uses Anaconda/Miniconda:

```bash
conda create -n audit_ai python=3.11 -y
conda activate audit_ai
pip install -r requirements.txt
python3 server.py
```

---

## Supported Document Types

The system handles three document structures automatically:

| Document Style | Examples | Clause Format |
|---|---|---|
| AFQMS / IMTAR style | AFQMS, IMTAR Part 21 | `2.1`, `21.B1.4`, `11.3.1` |
| AQA Directive style | AQA Directives 01-06/2018 | `1. TITLE`, `(a) sub-item` |
| HAL Policy style | HAL CQAG documents | `10.1`, `11.3.2/4` |

Scanned (image-only) pages are automatically skipped. The tool works best on machine-readable PDFs.

---

## Project Structure

```
audit-checklist-generator/
├── server.py                  # Flask web server (entry point)
├── checklist_generator.py     # Core pipeline: PDF → clauses → checkpoints → docx
├── ui.html                    # Single-file frontend (served by Flask)
├── requirements.txt           # Python dependencies
├── setup.sh                   # Setup script for Linux/macOS
├── setup.ps1                  # Setup script for Windows
├── models/
│   └── README.txt             # Instructions for placing model file
│   └── (your .gguf file)      # Not committed to git
└── static/
    ├── ibmplexsans.woff2      # UI font (offline)
    └── ibmplexmono.woff2      # UI font (offline)
```

---

## Troubleshooting

### `Model not loaded. Check MODEL_PATH`
The server cannot find a `.gguf` file. Verify:
```bash
ls models/        # Should show your .gguf file
```
Or set `MODEL_PATH` explicitly (see above).

### `llama-cpp-python` install fails on Windows
You need Visual C++ Build Tools. Download and install:
> https://visualstudio.microsoft.com/visual-cpp-build-tools/

Then retry `pip install llama-cpp-python --no-cache-dir`.

### `llama-cpp-python` install fails on Linux
Install build dependencies first:
```bash
sudo apt-get install build-essential cmake libopenblas-dev   # Debian/Ubuntu
sudo yum install gcc gcc-c++ cmake openblas-devel            # RHEL/CentOS
```

### `unknown model architecture: 'qwen3'`
Your `llama-cpp-python` version is too old (pre-Qwen3 support). Upgrade:
```bash
pip install llama-cpp-python --upgrade --no-cache-dir
```
You need version **0.3.4 or higher**.

### PDF shows 0 readable pages
The PDF is fully scanned (image-only). The tool requires machine-readable (text-layer) PDFs. Use an OCR tool like Adobe Acrobat or `ocrmypdf` to convert it first:
```bash
pip install ocrmypdf
ocrmypdf input.pdf output_readable.pdf
```

### Slow processing
Processing speed depends entirely on CPU. For a 100-clause document at standard depth:
- 8-core modern CPU: ~20-30 minutes
- 4-core older CPU: ~45-60 minutes

The progress bar in the UI shows per-clause progress in real time.

### Port 5000 already in use
```bash
PORT=8080 python3 server.py   # Linux/macOS
$env:PORT=8080; python server.py   # Windows
```

---

## Configuration

All configuration is via environment variables — no config file needed:

| Variable | Default | Description |
|---|---|---|
| `MODEL_PATH` | Auto-detected from `models/` | Full path to `.gguf` model file |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `5000` | Server port |

Example — run on a specific port accessible on your network:
```bash
HOST=0.0.0.0 PORT=8080 python3 server.py
```

---

## Security Note

This tool is designed for **internal/intranet use only**. It has no authentication. Do not expose it on a public network. If deploying for a team, restrict access via your network firewall or use a reverse proxy with authentication (nginx, Caddy, etc.).

---

## Dependencies

| Package | Purpose | License |
|---|---|---|
| Flask | Web server | BSD |
| pdfplumber | PDF text extraction | MIT |
| python-docx | Word document generation | MIT |
| llama-cpp-python | Local LLM inference | MIT |
| Qwen3-14B (model) | AI checkpoint generation | Apache 2.0 |

---

## Support

For issues or questions, contact the Quality Assurance Department or raise an issue in the repository.
