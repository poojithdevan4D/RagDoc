#!/usr/bin/env python3
"""
Audit Checklist Generator — Backend Server (BitNet edition)
============================================================

Setup:
    See README.md for full installation instructions.

Usage:
    # Set your paths via environment variables first:
    export BITNET_CLI=/path/to/bitnet.cpp/build/bin/llama-cli
    export BITNET_MODEL=/path/to/models/ggml-model-i2_s.gguf

    # Then run:
    python3 server.py

    Open: http://localhost:5000

Optional overrides:
    HOST=0.0.0.0   PORT=5000   (defaults shown)
"""

import os, sys, json, base64, tempfile, traceback, math
from flask import Flask, request, Response, send_from_directory

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))

# ── Path configuration via environment variables ─────────────────────────────
# Do NOT hard-code paths here. Set these in your shell or a .env file.
# See README.md for instructions.
BITNET_CLI  = os.environ.get("BITNET_CLI",  "")
MODEL_PATH  = os.environ.get("BITNET_MODEL", "")

sys.path.insert(0, BASE_DIR)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# ── Startup checks ───────────────────────────────────────────────────────────
print(f"BitNet binary : {BITNET_CLI or '(not set — configure BITNET_CLI)'}")
print(f"Model         : {MODEL_PATH or '(not set — configure BITNET_MODEL)'}")

_ready = True
if not BITNET_CLI:
    print("WARNING: BITNET_CLI environment variable is not set.")
    _ready = False
elif not os.path.exists(BITNET_CLI):
    print(f"WARNING: BitNet binary not found at: {BITNET_CLI}")
    _ready = False

if not MODEL_PATH:
    print("WARNING: BITNET_MODEL environment variable is not set.")
    _ready = False
elif not os.path.exists(MODEL_PATH):
    print(f"WARNING: Model file not found at: {MODEL_PATH}")
    _ready = False

if _ready:
    print("Ready.")
else:
    print("\nSet BITNET_CLI and BITNET_MODEL before generating checklists.")
    print("See README.md for setup instructions.\n")

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
    from checklist_generator import DEFAULT_CHECKPOINT_PROMPT
    return DEFAULT_CHECKPOINT_PROMPT, 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/generate", methods=["POST"])
def generate():
    if not BITNET_CLI or not MODEL_PATH or \
       not os.path.exists(BITNET_CLI) or not os.path.exists(MODEL_PATH):
        return Response(
            json.dumps({
                "type": "error",
                "text": (
                    "BitNet binary or model not found. "
                    "Set BITNET_CLI and BITNET_MODEL environment variables. "
                    "See README.md."
                )
            }) + "\n",
            status=500, mimetype="application/x-ndjson"
        )

    pdf_file        = request.files.get("pdf")
    max_items       = int(request.form.get("max_items", 10))
    doc_title       = request.form.get("doc_title", "").strip()
    depth           = request.form.get("depth", "standard").lower()
    custom_n        = request.form.get("custom_n", "")
    custom_m        = request.form.get("custom_m", "")
    custom_pct      = request.form.get("custom_pct", "").strip()
    prompt_template = request.form.get("prompt_template", "").strip() or None
    auditor_focus   = request.form.get("auditor_focus", "").strip()
    section_filter  = request.form.get("section_filter", "").strip()

    if not pdf_file:
        return Response(
            json.dumps({"type": "error", "text": "No PDF uploaded."}) + "\n",
            status=400, mimetype="application/x-ndjson"
        )

    if depth == "custom" and custom_n and custom_m:
        try:
            n_val = int(custom_n); m_val = float(custom_m)
        except ValueError:
            n_val, m_val = 2, 50.0
    else:
        preset = DEPTH_PRESETS.get(depth, DEPTH_PRESETS["standard"])
        n_val  = preset["n"]; m_val = preset["m"]

    if custom_pct:
        try:
            pct_override = float(custom_pct)
            if 1.0 <= pct_override <= 100.0:
                m_val = round(pct_override)
        except ValueError:
            pass

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
            pages    = read_pdf(tmp_path)
            readable = sum(1 for p in pages if p)
            skipped  = len(pages) - readable
            msg      = f"Read {len(pages)} pages — {readable} readable"
            if skipped: msg += f", {skipped} scanned/empty skipped"
            yield from emit({"type": "log", "text": msg, "level": "ok" if readable > 0 else "warn"})

            # 2. Detect structure
            yield from emit({"type": "progress", "pct": 15, "label": "Detecting document structure..."})
            structure = detect_structure(None, pages)
            clause_re, sect_re = compile_patterns(structure)
            if structure:
                yield from emit({"type": "log", "text": f"Structure: {structure.get('clause_example','?')} / {structure.get('section_example','?')}", "level": "ok"})
            else:
                yield from emit({"type": "log", "text": "Using fallback patterns", "level": "warn"})

            # 3. Extract clauses
            yield from emit({"type": "progress", "pct": 28, "label": "Extracting clauses..."})
            clauses = extract_clauses(pages, clause_re, sect_re, section_filter=section_filter or None)
            filter_msg = f" [filter: {section_filter}]" if section_filter else ""
            yield from emit({"type": "log", "text": f"{len(clauses)} obligation clauses found{filter_msg}",
                             "level": "ok" if clauses else "warn"})

            if not clauses:
                no_clause_hint = " Try broadening or clearing your Section Filter." if section_filter else " Check PDF has machine-readable text."
                yield from emit({"type": "error", "text": f"No clauses found.{no_clause_hint}"})
                return

            subset = clauses[:max_items] if max_items else clauses
            total  = len(subset)

            # 4. Extract checkpoints
            yield from emit({"type": "progress", "pct": 32, "label": f"Extracting checkpoints from {total} clauses..."})
            master = []
            for i, clause in enumerate(subset, 1):
                pct = 32 + int((i / total) * 55)
                yield from emit({"type": "progress", "pct": pct,
                                 "label": f"Clause {i}/{total}: {clause['ref'][:45]}"})

                from checklist_generator import extract_checkpoints
                checkpoints = extract_checkpoints(None, clause,
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
                yield from emit({"type": "error", "text": "No checkpoints extracted. Check model output."})
                return

            # 5. Write master checklist
            yield from emit({"type": "progress", "pct": 89, "label": "Writing master checklist..."})
            title = doc_title or os.path.splitext(pdf_filename)[0].replace("_", " ")
            create_docx(master, master_path, doc_title=title, sheet_label="MASTER AUDIT CHECKLIST")
            yield from emit({"type": "progress", "pct": 91, "label": "Encoding master checklist..."})
            with open(master_path, "rb") as f:
                master_b64 = base64.b64encode(f.read()).decode("ascii")

            # 6. Build filtered audit sheet
            yield from emit({"type": "progress", "pct": 94, "label": f"Building audit sheet (N={n_val}, M={m_val}%)..."})
            filtered    = filter_checkpoints(master, n=n_val, m_pct=m_val)
            depth_label = depth.upper() if depth != "custom" else f"CUSTOM (N={n_val}, M={m_val}%)"
            create_docx(filtered, filtered_path, doc_title=title, sheet_label=f"AUDIT SHEET — {depth_label}")
            yield from emit({"type": "progress", "pct": 97, "label": "Encoding audit sheet..."})
            with open(filtered_path, "rb") as f:
                filtered_b64 = base64.b64encode(f.read()).decode("ascii")

            yield from emit({"type": "progress", "pct": 98, "label": "Sending files..."})
            yield from emit({"type": "master_file",   "data": master_b64})
            yield from emit({"type": "filtered_file", "data": filtered_b64})
            yield from emit({"type": "progress", "pct": 100, "label": "Complete"})
            yield from emit({
                "type": "done", "total_clauses": len(clauses),
                "master_items": len(master), "filtered_items": len(filtered),
                "depth_label": depth_label, "n_val": n_val, "m_val": m_val,
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
    print(f"  Audit Checklist Generator (BitNet)")
    print(f"  http://localhost:{port}")
    print(f"  Binary : {BITNET_CLI or '(not configured)'}")
    print(f"  Model  : {MODEL_PATH or '(not configured)'}")
    print(f"{'─'*50}\n")
    app.run(host=host, port=port, debug=False, threaded=False)
