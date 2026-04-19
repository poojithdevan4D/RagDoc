# Audit Checklist Generator (BitNet Edition)

Generates structured audit checklists from government/regulatory PDF documents using a **local, offline BitNet LLM** — no cloud API needed.

Upload a PDF → the tool extracts obligation clauses → calls BitNet to turn each clause into YES/NO audit questions → outputs two `.docx` files:
- **Master Checklist** — all checkpoints
- **Audit Sheet** — filtered subset at your chosen depth (Light / Standard / Deep / Full)

---

## Requirements

| Dependency | Version |
|---|---|
| Python | 3.9+ |
| [bitnet.cpp](https://github.com/microsoft/bitnet.cpp) | latest |
| BitNet model | `BitNet-b1.58-2B-4T` (GGUF i2_s) |
| pdfplumber | `pip install pdfplumber` |
| python-docx | `pip install python-docx` |
| flask | `pip install flask` |

---

## Installation

### 1. Build BitNet

Follow the official instructions at https://github.com/microsoft/bitnet.cpp to build the project. After a successful build you will have a binary at a path like:

```
/path/to/bitnet.cpp/build/bin/llama-cli
```

### 2. Download the model

Download the `BitNet-b1.58-2B-4T` GGUF model (i2_s quantisation). The model file will be at a path like:

```
/path/to/models/BitNet-b1.58-2B-4T/ggml-model-i2_s.gguf
```

### 3. Install Python dependencies

```bash
pip install flask pdfplumber python-docx
```

### 4. Clone this repo

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO
```

---

## Configuration

**No paths are hardcoded.** You configure the binary and model via environment variables:

```bash
export BITNET_CLI=/path/to/bitnet.cpp/build/bin/llama-cli
export BITNET_MODEL=/path/to/models/BitNet-b1.58-2B-4T/ggml-model-i2_s.gguf
```

You can add these to your shell profile (`~/.bashrc`, `~/.zshrc`) so they persist across sessions:

```bash
echo 'export BITNET_CLI=/path/to/bitnet.cpp/build/bin/llama-cli' >> ~/.bashrc
echo 'export BITNET_MODEL=/path/to/models/BitNet-b1.58-2B-4T/ggml-model-i2_s.gguf' >> ~/.bashrc
source ~/.bashrc
```

Or create a `.env` file in the project directory and source it before running:

```bash
# .env
export BITNET_CLI=/path/to/bitnet.cpp/build/bin/llama-cli
export BITNET_MODEL=/path/to/models/BitNet-b1.58-2B-4T/ggml-model-i2_s.gguf
```

```bash
source .env && python3 server.py
```

---

## Running the Web UI

```bash
python3 server.py
```

Then open **http://localhost:5000** in your browser.

Optional port/host overrides:

```bash
HOST=127.0.0.1 PORT=8080 python3 server.py
```

---

## Running from the Command Line (no UI)

```bash
python3 checklist_generator.py your_document.pdf [max_clauses]
```

Example:

```bash
python3 checklist_generator.py regulations.pdf 20
```

This writes two files to the current directory:
- `Audit_Checklist.docx` — master checklist
- `Audit_Checklist_filtered.docx` — standard-depth audit sheet

---

## File Overview

| File | Purpose |
|---|---|
| `server.py` | Flask backend — handles PDF upload, streams progress, returns `.docx` files |
| `checklist_generator.py` | Core logic — PDF reading, clause extraction, BitNet inference, Word output |
| `ui.html` | Single-file frontend — served by Flask at `/` |

### Optional: Custom fonts

The UI references two optional web fonts via `/static/`:
- `ibmplexmono.woff2`
- `ibmplexsans.woff2`

If these are not present, the browser falls back to system monospace/sans-serif fonts and everything works fine. To use the exact fonts, download IBM Plex Mono and IBM Plex Sans from [Google Fonts](https://fonts.google.com) and place the `.woff2` files in a `static/` folder next to `ui.html`.

---

## Audit Depth Presets

| Preset | Min per clause (N) | % of checkpoints (M) |
|---|---|---|
| Light | 1 | 25% |
| Standard | 2 | 50% |
| Deep | 3 | 75% |
| Full | all | 100% |

You can also set N and M manually with the **Custom** option in the UI.

---

## Troubleshooting

**"BitNet binary not found"**
→ Check your `BITNET_CLI` path is correct and the binary is executable (`chmod +x`).

**"Model file not found"**
→ Check your `BITNET_MODEL` path. Make sure the `.gguf` file was downloaded completely.

**"No clauses found"**
→ The PDF may be scanned (image-only). The tool requires machine-readable text. Try a text-layer PDF.

**Generation is slow**
→ BitNet runs on CPU by default. Generation time scales with the number of clauses. Start with a low `Max Clauses` value (e.g. 5–10) to test.

**Port already in use**
→ Run with `PORT=8080 python3 server.py` or kill the existing process on port 5000.
