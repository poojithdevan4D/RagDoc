# Offline Checklist Generator

A fully **offline**, AI-powered tool that converts government regulatory PDFs into structured DGAQA-format audit checklists in Word (`.docx`).

No data leaves your machine. No internet connection required after setup.

---

## What It Does

Upload a regulatory PDF → the system:

1. Extracts all auditable obligation clauses from the document
2. Uses a local LLM to generate YES/NO audit checkpoint questions per clause
3. Outputs two Word documents:
   - **Master Checklist** — every checkpoint extracted from every clause
   - **Audit Sheet** — a depth-controlled sample (Light / Standard / Deep / Full)

Output follows the standard DGAQA 8-column table format:
`SL No. | Clause # | Sub Point | Description | Org. Procedure # | Adequacy | Compliant | Remarks`

### Supported Document Types

| Style | Examples |
|---|---|
| AFQMS / IMTAR | AFQMS, IMTAR Part 21 |
| AQA Directives | AQA Directives 01–06/2018 |
| HAL Policy Documents | HAL CQAG series |

---

## Requirements

| | Minimum |
|---|---|
| Python | 3.10+ |
| RAM | 8 GB (16 GB recommended) |
| Disk | 6 GB free |
| OS | Linux, macOS, Windows 10/11 |
| CPU | Any modern x86-64 — no GPU needed |

---

## Quick Start

### Linux / macOS

```bash
git clone https://github.com/Arut123/Offline-checklist-generator.git
cd Offline-checklist-generator
bash setup.sh
source .venv/bin/activate
python3 server.py
```

### Windows (PowerShell)

```powershell
git clone https://github.com/Arut123/Offline-checklist-generator.git
cd Offline-checklist-generator

# Allow scripts (one-time)
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

.\setup.ps1
.\.venv\Scripts\Activate.ps1
python server.py
```

Then open **http://localhost:5000**

---

## Manual Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

If `llama-cpp-python` fails:

```bash
# Linux
CMAKE_ARGS="-DLLAMA_BLAS=ON -DLLAMA_BLAS_VENDOR=OpenBLAS" pip install llama-cpp-python

# macOS (Apple Silicon)
CMAKE_ARGS="-DLLAMA_METAL=on" pip install llama-cpp-python

# Windows — install Visual C++ Build Tools first, then:
pip install llama-cpp-python --no-cache-dir
```

### 2. Download the model

Download `mistral-7b-instruct-v0.2.Q4_K_M.gguf` (~4 GB):

```
https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF
```

Place it in the `models/` folder:

```
Offline-checklist-generator/
└── models/
    └── mistral-7b-instruct-v0.2.Q4_K_M.gguf
```

### 3. Download UI fonts (optional — for fully offline use)

```bash
mkdir -p static
curl -sL "https://fonts.gstatic.com/s/ibmplexsans/v19/zYXgKVElMYYaJe8bpLHnCwDKjQ.woff2" -o static/ibmplexsans.woff2
curl -sL "https://fonts.gstatic.com/s/ibmplexmono/v19/-F6pfjptAgt5VM-kVkqdyU8n3kwq.woff2" -o static/ibmplexmono.woff2
```

### 4. Run

```bash
python3 server.py
```

---

## Using a Different Model

Any GGUF instruction-tuned model works. Place it in `models/` and the server auto-detects it on startup. Or point to it explicitly:

```bash
# Linux / macOS
export MODEL_PATH=/path/to/your/model.gguf
python3 server.py

# Windows
set MODEL_PATH=C:\path\to\your\model.gguf
python server.py
```

---

## Project Structure

```
Offline-checklist-generator/
├── server.py                  # Flask web server — run this
├── checklist_generator.py     # Core pipeline: PDF → clauses → checkpoints → docx
├── ui.html                    # Frontend (served by Flask)
├── requirements.txt           # Python dependencies
├── setup.sh                   # Setup script for Linux / macOS
├── setup.ps1                  # Setup script for Windows
├── models/                    # Place your .gguf model file here
└── static/                    # Place font .woff2 files here (optional)
```

---

## Troubleshooting

**`Model not loaded` error** — No `.gguf` file found in `models/`. Verify the file is there or set `MODEL_PATH`.

**`llama-cpp-python` install fails on Windows** — Install [Visual C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) first.

**PDF shows 0 readable pages** — PDF is scanned/image-only. Run OCR first:
```bash
pip install ocrmypdf
ocrmypdf input.pdf output.pdf
```

**Port 5000 in use:**
```bash
PORT=8080 python3 server.py
```

---

## Security

Designed for internal / intranet use only. No authentication is built in. Do not expose on a public network without a reverse proxy and access controls.
