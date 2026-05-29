#!/usr/bin/env python3
"""
Offline Document Summarizer — Backend Server (BitNet / TurboQuant edition)
===========================================================================

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
from flask import Flask, request, Response, send_from_directory, send_file, jsonify

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

from document_summarizer import read_pdf, generate_summary


@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "ui.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    static_path = os.path.join(BASE_DIR, "static")
    if not os.path.isdir(static_path):
        return "Not Found", 404
    return send_from_directory(static_path, filename)





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

    pdf_file      = request.files.get("pdf")
    auditor_focus = request.form.get("auditor_focus", "").strip()

    if not pdf_file:
        return Response(
            json.dumps({"type": "error", "text": "No PDF uploaded."}) + "\n",
            status=400, mimetype="application/x-ndjson"
        )

    pdf_bytes    = pdf_file.read()
    pdf_filename = pdf_file.filename

    def stream():
        def emit(obj):
            yield json.dumps(obj) + "\n"

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        try:
            start_time = time.time()
            yield from emit({"type": "log", "text": "Starting TurboQuant Performance Run...", "level": "info"})
            
            # 1. Read PDF
            yield from emit({"type": "progress", "pct": 10, "label": "Reading PDF..."})
            pages    = read_pdf(tmp_path)
            readable = sum(1 for p in pages if p)
            skipped  = len(pages) - readable
            msg      = f"Read {len(pages)} pages — {readable} readable"
            if skipped: msg += f", {skipped} scanned/empty skipped"
            yield from emit({"type": "log", "text": msg, "level": "ok" if readable > 0 else "warn"})

            if readable == 0:
                yield from emit({"type": "error", "text": "No readable text found in PDF."})
                return

            # 2. Generate summary
            yield from emit({"type": "progress", "pct": 40, "label": "Generating summary..."})
            
            summary_text = generate_summary(LLM, pages, focus=auditor_focus)
            
            if not summary_text:
                yield from emit({"type": "error", "text": "No summary generated. Check model output."})
                return
                
            yield from emit({"type": "progress", "pct": 85, "label": "Summary generated..."})
            
            duration = time.time() - start_time
            yield from emit({"type": "log", "text": f"Performance Summary:", "level": "ok"})
            yield from emit({"type": "log", "text": f" - Total Time: {duration:.1f}s", "level": "ok"})
            yield from emit({"type": "log", "text": f" - Context Window: {current_ctx} tokens", "level": "info"})
            yield from emit({"type": "log", "text": f" - Mode: {current_mode}", "level": "info"})
            
            yield from emit({"type": "progress", "pct": 100, "label": "Complete"})
            yield from emit({
                "type": "done",
                "summary": summary_text
            })

        except Exception as e:
            tb = traceback.format_exc()
            yield from emit({"type": "error", "text": str(e)})
            yield from emit({"type": "log",   "text": tb[:400], "level": "err"})
        finally:
            try:
                if os.path.exists(tmp_path): os.unlink(tmp_path)
            except Exception:
                pass

    return Response(stream(), mimetype="application/x-ndjson")


from mail_retriever import locate_thunderbird_inbox, fetch_attachments_from_inbox
from data_extractor import parse_monthly_report
from docx_filler import fill_quarterly_report

@app.route("/pipeline/fetch", methods=["POST"])
def pipeline_fetch():
    try:
        inbox_path = locate_thunderbird_inbox()
        if not inbox_path:
            return jsonify({"status": "error", "message": "Thunderbird offline inbox could not be located automatically."}), 404
        
        extracted = fetch_attachments_from_inbox(inbox_path, os.path.join(BASE_DIR, "incoming_reports"))
        return jsonify({
            "status": "success",
            "inbox_path": inbox_path,
            "extracted_count": len(extracted),
            "files": [os.path.basename(f) for f in extracted]
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/pipeline/upload", methods=["POST"])
def pipeline_upload():
    try:
        uploaded_files = request.files.getlist("reports")
        if not uploaded_files or len(uploaded_files) == 0:
            return jsonify({"status": "error", "message": "No files uploaded"}), 400
            
        output_dir = os.path.join(BASE_DIR, "incoming_reports")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        saved = []
        for file in uploaded_files:
            if file and file.filename:
                target_path = os.path.join(output_dir, file.filename)
                file.save(target_path)
                saved.append(file.filename)
                
        return jsonify({"status": "success", "files": saved})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/pipeline/list", methods=["GET"])
def pipeline_list():
    output_dir = os.path.join(BASE_DIR, "incoming_reports")
    if not os.path.exists(output_dir):
        return jsonify({"files": []})
    files = [f for f in os.listdir(output_dir) if f.lower().endswith(('.pdf', '.docx'))]
    return jsonify({"files": files})

@app.route("/pipeline/clear", methods=["POST"])
def pipeline_clear():
    try:
        output_dir = os.path.join(BASE_DIR, "incoming_reports")
        if os.path.exists(output_dir):
            for f in os.listdir(output_dir):
                fp = os.path.join(output_dir, f)
                if os.path.isfile(fp):
                    os.unlink(fp)
        return jsonify({"status": "success", "message": "Reports cache cleared."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/pipeline/generate", methods=["POST"])
def pipeline_generate():
    if LLM is None:
        return jsonify({"status": "error", "message": "AI model not loaded."}), 500
        
    try:
        output_dir = os.path.join(BASE_DIR, "incoming_reports")
        if not os.path.exists(output_dir):
            return jsonify({"status": "error", "message": "No reports have been fetched or uploaded."}), 400
            
        files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.lower().endswith(('.pdf', '.docx'))]
        if not files:
            return jsonify({"status": "error", "message": "No monthly reports found in incoming folder."}), 400
            
        # Parse all monthly reports
        monthly_datas = []
        for file in sorted(files):
            print(f"Parsing monthly report: {file}")
            data = parse_monthly_report(LLM, file)
            monthly_datas.append(data)
            
        # Generate the quarterly report to a unique temp file to avoid locks
        template_path = os.path.join(BASE_DIR, "Quaterly_progress_report.docx")
        import uuid
        temp_name = f"Generated_Quaterly_Progress_Report_{uuid.uuid4().hex}.docx"
        output_report_path = os.path.join(BASE_DIR, temp_name)
        
        try:
            fill_quarterly_report(template_path, monthly_datas, output_report_path)
            
            # Read into memory
            with open(output_report_path, "rb") as f:
                file_bytes = io.BytesIO(f.read())
                
            # Immediately delete physical file to release locks
            if os.path.exists(output_report_path):
                os.unlink(output_report_path)
                
            return send_file(
                file_bytes,
                as_attachment=True,
                download_name="Generated_Quaterly_Progress_Report.docx",
                mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
        except Exception as write_err:
            if os.path.exists(output_report_path):
                try: os.unlink(output_report_path)
                except: pass
            raise write_err
            
    except Exception as e:
        tb = traceback.format_exc()
        print(tb)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/pipeline/run", methods=["POST"])
def pipeline_run():
    if LLM is None:
        return jsonify({"status": "error", "message": "AI model not loaded."}), 500
        
    try:
        # 1. First fetch latest attachments from Thunderbird
        inbox_path = locate_thunderbird_inbox()
        if inbox_path:
            fetch_attachments_from_inbox(inbox_path, os.path.join(BASE_DIR, "incoming_reports"))
            
        output_dir = os.path.join(BASE_DIR, "incoming_reports")
        if not os.path.exists(output_dir):
            return jsonify({"status": "error", "message": "Staging folder empty."}), 400
            
        files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.lower().endswith(('.pdf', '.docx'))]
        if not files:
            return jsonify({"status": "error", "message": "No monthly reports found in staging folder."}), 400
            
        # 2. Parse all monthly reports
        monthly_datas = []
        for file in sorted(files):
            print(f"Pipeline Auto-Run: Parsing monthly report: {file}")
            data = parse_monthly_report(LLM, file)
            monthly_datas.append(data)
            
        # 3. Generate the quarterly report to a unique temp file to avoid locks
        template_path = os.path.join(BASE_DIR, "Quaterly_progress_report.docx")
        import uuid
        temp_name = f"Generated_Quaterly_Progress_Report_{uuid.uuid4().hex}.docx"
        output_report_path = os.path.join(BASE_DIR, temp_name)
        
        try:
            fill_quarterly_report(template_path, monthly_datas, output_report_path)
            
            # Read into memory
            with open(output_report_path, "rb") as f:
                file_bytes = io.BytesIO(f.read())
                
            # Immediately delete physical file to release locks
            if os.path.exists(output_report_path):
                os.unlink(output_report_path)
                
            return send_file(
                file_bytes,
                as_attachment=True,
                download_name="Generated_Quaterly_Progress_Report.docx",
                mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
        except Exception as write_err:
            if os.path.exists(output_report_path):
                try: os.unlink(output_report_path)
                except: pass
            raise write_err
            
    except Exception as e:
        tb = traceback.format_exc()
        print(tb)
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    print(f"\n{'-'*50}")
    print(f"  Offline Document Summarizer (Local AI)")
    print(f"  http://localhost:{port}")
    print(f"  Model  : {MODEL_PATH or '(not configured)'}")
    print(f"{'-'*50}\n")
    app.run(host=host, port=port, debug=False, threaded=False)
