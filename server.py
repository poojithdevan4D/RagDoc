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

import os, sys, re, json, time, math, io, base64, tempfile, traceback
from flask import Flask, request, Response, send_from_directory

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))

# ── Path configuration ───────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def _find_model():
    # 1. Check environment variable first
    env_model = os.environ.get("BITNET_MODEL")
    if env_model and os.path.exists(env_model):
        return env_model
        
    # 2. Check models/ folder
    models_dir = os.path.join(BASE_DIR, "models")
    if not os.path.isdir(models_dir):
        try: os.makedirs(models_dir)
        except: pass
        return None
        
    for f in sorted(os.listdir(models_dir)):
        if f.endswith(".gguf"):
            return os.path.join(models_dir, f)
    return None

MODEL_PATH = _find_model()

# ── AI Model Initialization (TurboQuant Optimized) ───────────────────────────
print(f"Loading model: {MODEL_PATH or '(No model found in models/ folder)'}")

LLM = None
current_mode = "Unknown"
current_ctx  = 0

if MODEL_PATH:
    try:
        from llama_cpp import Llama
        import llama_cpp
        
        # ── Universal Optimization Logic (Auto-Detect Hardware) ──────────
        # Try for "Truly Quantized" mode, fallback to "Safe Mode" if incompatible
        n_ctx_target = 8192
        import llama_cpp
        
        try:
            print(f"[*] Attempting TurboQuant Optimization (8-bit KV + 8k Context)...")
            LLM = Llama(
                model_path=MODEL_PATH,
                n_ctx=8192,
                n_batch=512,
                n_gpu_layers=-1, # GPU UNLOCKED: Offload all layers to RTX 3050
                flash_attn=True,
                type_k=llama_cpp.GGML_TYPE_Q8_0,
                type_v=llama_cpp.GGML_TYPE_Q8_0,
                verbose=False
            )
            current_mode = "Truly Quantized (GPU Accelerated)"
            current_ctx  = 8192
            print(f"TURBOQUANT GPU MODE ACTIVE: Using RTX 3050 with 8-bit KV Cache")
        except Exception as e:
            print(f"GPU Initialization failed, falling back to CPU: {e}")
            try:
                LLM = Llama(
                    model_path=MODEL_PATH,
                    n_ctx=4096,
                    n_gpu_layers=0,
                    verbose=False
                )
                current_mode = "Universal Safe Mode (CPU)"
                current_ctx  = 4096
                print("Using Universal Safe Mode (CPU Fallback)")
            except Exception as e2:
                print(f"CRITICAL ERROR: Could not load model in any mode: {e2}")
        
        print(f"  Context: {current_ctx} tokens")
        print(f"--------------------------------------------------")
    except Exception as e:
        print(f"ERROR: Could not load model: {e}")
else:
    print("WARNING: No .gguf model found in models/ directory.")

sys.path.insert(0, BASE_DIR)
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

from checklist_generator import (
    read_pdf, detect_structure, compile_patterns,
    extract_clauses, build_master, build_master_turbo, 
    filter_checkpoints, create_docx, DEPTH_PRESETS,
)


@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "ui.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    static_path = os.path.join(BASE_DIR, "static")
    if not os.path.isdir(static_path):
        return "Not Found", 404
    return send_from_directory(static_path, filename)


@app.route("/default_prompt")
def default_prompt():
    from checklist_generator import DEFAULT_CHECKPOINT_PROMPT
    return DEFAULT_CHECKPOINT_PROMPT, 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/generate", methods=["POST"])
def generate():
    if LLM is None:
        return Response(
            json.dumps({
                "type": "error",
                "text": "Model not loaded. Check your models/ folder."
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
    turbo_mode      = request.form.get("turbo_mode", "false").lower() == "true"

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
            start_time = time.time()
            yield from emit({"type": "log", "text": "Starting TurboQuant Performance Run...", "level": "info"})
            
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
            structure = detect_structure(LLM, pages)
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
            
            if turbo_mode:
                master = build_master_turbo(LLM, subset, focus=auditor_focus, batch_size=5)
            else:
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
                yield from emit({"type": "error", "text": "No checkpoints extracted. Check model output."})
                return

            # 5. Write master checklist
            yield from emit({"type": "progress", "pct": 89, "label": "Writing master checklist..."})
            title = doc_title or os.path.splitext(pdf_filename)[0].replace("_", " ")
            
            duration = time.time() - start_time
            clauses_count = len(subset)
            speed = (clauses_count / duration) * 60 if duration > 0 else 0
            
            yield from emit({"type": "log", "text": f"Performance Summary:", "level": "ok"})
            yield from emit({"type": "log", "text": f" - Total Time: {duration:.1f}s", "level": "ok"})
            yield from emit({"type": "log", "text": f" - Speed: {speed:.1f} clauses/min", "level": "ok"})
            yield from emit({"type": "log", "text": f" - Context Window: {current_ctx} tokens", "level": "info"})
            yield from emit({"type": "log", "text": f" - Mode: {current_mode}", "level": "info"})

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
    print(f"\n{'-'*50}")
    print(f"  Audit Checklist Generator (Local AI)")
    print(f"  http://localhost:{port}")
    print(f"  Model  : {MODEL_PATH or '(not configured)'}")
    print(f"{'-'*50}\n")
    app.run(host=host, port=port, debug=False, threaded=False)
