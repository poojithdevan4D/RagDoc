#!/usr/bin/env python3
"""
Audit Checklist Generator — Backend Server
==========================================
Usage:
    pip install flask pdfplumber python-docx llama-cpp-python
    python3 server.py
    Open: http://localhost:5000
"""

import os, sys, json, base64, tempfile, traceback, math
from flask import Flask, request, Response, send_from_directory

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
def _find_model():
    if "MODEL_PATH" in os.environ:
        return os.environ["MODEL_PATH"]
    models_dir = os.path.join(BASE_DIR, "models")
    if os.path.isdir(models_dir):
        for f in sorted(os.listdir(models_dir)):
            if f.endswith(".gguf"):
                return os.path.join(models_dir, f)
    return os.path.join(BASE_DIR, "models", "mistral-7b-instruct-v0.2.Q4_K_M.gguf")

MODEL_PATH = _find_model()

sys.path.insert(0, BASE_DIR)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024

print(f"Loading model: {MODEL_PATH}")
try:
    from llama_cpp import Llama
    LLM = Llama(
        model_path=MODEL_PATH,
        n_ctx=4096,
        n_threads=os.cpu_count() or 4,
        verbose=False,
    )
    print("Model ready.")
except Exception as e:
    print(f"WARNING: Could not load model — {e}")
    LLM = None

from checklist_generator import (
    read_pdf, detect_structure, compile_patterns,
    extract_clauses, build_master, filter_checkpoints,
    create_docx, DEPTH_PRESETS,
)


@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "ui.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(os.path.join(BASE_DIR, "static"), filename)


@app.route("/default_prompt")
def default_prompt():
    """Return the default checkpoint prompt so the UI can pre-fill the textarea."""
    from checklist_generator import DEFAULT_CHECKPOINT_PROMPT
    return DEFAULT_CHECKPOINT_PROMPT, 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/generate", methods=["POST"])
def generate():
    if LLM is None:
        return Response(
            json.dumps({"type": "error", "text": "Model not loaded. Check MODEL_PATH."}) + "\n",
            status=500, mimetype="application/x-ndjson"
        )

    pdf_file   = request.files.get("pdf")
    max_items  = int(request.form.get("max_items", 10))
    doc_title  = request.form.get("doc_title", "").strip()
    depth           = request.form.get("depth", "standard").lower()
    custom_n        = request.form.get("custom_n", "")
    custom_m        = request.form.get("custom_m", "")
    prompt_template = request.form.get("prompt_template", "").strip() or None
    auditor_focus   = request.form.get("auditor_focus", "").strip()

    if not pdf_file:
        return Response(
            json.dumps({"type": "error", "text": "No PDF uploaded."}) + "\n",
            status=400, mimetype="application/x-ndjson"
        )

    # Resolve N and M% from depth setting
    if depth == "custom" and custom_n and custom_m:
        try:
            n_val   = int(custom_n)
            m_val   = float(custom_m)
        except ValueError:
            n_val, m_val = 2, 50.0
    else:
        preset  = DEPTH_PRESETS.get(depth, DEPTH_PRESETS["standard"])
        n_val   = preset["n"]
        m_val   = preset["m"]

    # Read file bytes before entering generator
    pdf_bytes    = pdf_file.read()
    pdf_filename = pdf_file.filename

    def stream():
        def emit(obj):
            yield json.dumps(obj) + "\n"

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        master_path   = tmp_path.replace(".pdf", "_master.docx")
        filtered_path = tmp_path.replace(".pdf", "_filtered.docx")

        try:
            # 1. Read PDF
            yield from emit({"type": "progress", "pct": 5, "label": "Reading PDF..."})
            pages = read_pdf(tmp_path)
            readable = sum(1 for p in pages if p)
            skipped  = len(pages) - readable
            msg = f"Read {len(pages)} pages — {readable} readable"
            if skipped:
                msg += f", {skipped} scanned/empty skipped"
            yield from emit({"type": "log", "text": msg, "level": "ok" if readable > 0 else "warn"})

            # 2. Detect structure
            yield from emit({"type": "progress", "pct": 15, "label": "Detecting document structure..."})
            structure = detect_structure(LLM, pages)
            clause_re, sect_re = compile_patterns(structure)
            if structure:
                yield from emit({"type": "log", "text": f"Structure: {structure.get('clause_example','?')} / {structure.get('section_example','?')}", "level": "ok"})
            else:
                yield from emit({"type": "log", "text": "Using fallback patterns", "level": "warn"})

            # 3. Extract clauses
            yield from emit({"type": "progress", "pct": 28, "label": "Extracting clauses..."})
            clauses = extract_clauses(pages, clause_re, sect_re)
            yield from emit({"type": "log", "text": f"{len(clauses)} obligation clauses found", "level": "ok"})

            if not clauses:
                yield from emit({"type": "error", "text": "No clauses found. Check PDF has machine-readable text."})
                return

            subset = clauses[:max_items] if max_items else clauses
            total  = len(subset)

            # 4. Extract checkpoints (all of them = master)
            yield from emit({"type": "progress", "pct": 32, "label": f"Extracting checkpoints from {total} clauses..."})

            master = []
            for i, clause in enumerate(subset, 1):
                pct = 32 + int((i / total) * 55)
                yield from emit({
                    "type": "progress", "pct": pct,
                    "label": f"Clause {i}/{total}: {clause['ref'][:45]}"
                })

                from checklist_generator import extract_checkpoints
                checkpoints = extract_checkpoints(LLM, clause,
                                                  prompt_template=prompt_template,
                                                  focus=auditor_focus)
                n = len(checkpoints)

                if checkpoints:
                    for j, q in enumerate(checkpoints, 1):
                        master.append({
                            "clause_base": clause["ref"],
                            "subpoint":    f"{j}/{n}",
                            "ref":         f"{clause['ref']} ({j}/{n})",
                            "question":    q,
                        })
                    yield from emit({"type": "log", "text": f"[{i}/{total}] {clause['ref']} — {n} checkpoints", "level": "ok"})
                else:
                    yield from emit({"type": "log", "text": f"[{i}/{total}] {clause['ref']} — skipped", "level": "warn"})

            if not master:
                yield from emit({"type": "error", "text": "No checkpoints extracted. Check model integrity."})
                return

            # 5. Write master checklist
            yield from emit({"type": "progress", "pct": 89, "label": "Writing master checklist..."})
            title = doc_title or os.path.splitext(pdf_filename)[0].replace("_", " ")
            create_docx(master, master_path, doc_title=title,
                        sheet_label="MASTER AUDIT CHECKLIST")

            with open(master_path, "rb") as f:
                master_b64 = base64.b64encode(f.read()).decode()

            # 6. Build filtered audit sheet
            yield from emit({"type": "progress", "pct": 94, "label": f"Building audit sheet (N={n_val}, M={m_val}%)..."})
            filtered = filter_checkpoints(master, n=n_val, m_pct=m_val)

            depth_label = depth.upper() if depth != "custom" else f"CUSTOM (N={n_val}, M={m_val}%)"
            create_docx(filtered, filtered_path, doc_title=title,
                        sheet_label=f"AUDIT SHEET — {depth_label}")

            with open(filtered_path, "rb") as f:
                filtered_b64 = base64.b64encode(f.read()).decode()

            yield from emit({"type": "progress", "pct": 100, "label": "Complete"})
            yield from emit({
                "type":            "done",
                "total_clauses":   len(clauses),
                "master_items":    len(master),
                "filtered_items":  len(filtered),
                "depth_label":     depth_label,
                "n_val":           n_val,
                "m_val":           m_val,
                "master_file":     master_b64,
                "filtered_file":   filtered_b64,
            })

        except Exception as e:
            tb = traceback.format_exc()
            yield from emit({"type": "error", "text": str(e)})
            yield from emit({"type": "log",   "text": tb[:400], "level": "err"})

        finally:
            for p in [tmp_path, master_path, filtered_path]:
                try:
                    if os.path.exists(p): os.unlink(p)
                except Exception:
                    pass

    return Response(stream(), mimetype="application/x-ndjson")


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    print(f"\n{'─'*50}")
    print(f"  Audit Checklist Generator")
    print(f"  http://{host}:{port}")
    print(f"  Model: {MODEL_PATH}")
    print(f"{'─'*50}\n")
    app.run(host=host, port=port, debug=False, threaded=False)