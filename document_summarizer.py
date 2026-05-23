#!/usr/bin/env python3
"""
Government Document -> Audit Checklist Generator
Uses BitNet (bitnet.cpp / llama-cli) for local offline inference.

Usage (standalone CLI):
    python3 checklist_generator.py your_document.pdf [max_clauses]

Environment variables (override defaults):
    BITNET_CLI    — path to the llama-cli binary
    BITNET_MODEL  — path to the .gguf model file
"""
import os, sys, re, json, math, subprocess, tempfile

PDF_PATH    = "document.pdf"
OUTPUT_DOCX = "Audit_Checklist.docx"
MAX_ITEMS   = 10

# ── Configure these via environment variables ────────────────────────────────
# See README.md for setup instructions.
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

MODEL_PATH = _find_model() or os.environ.get("BITNET_MODEL", "")



# ── BitNet inference ─────────────────────────────────────
def _run_local_llm(llm, prompt, max_tokens=256, temperature=0.1, repeat_penalty=1.15):
    """
    Call the local Llama instance.
    """
    if llm is None:
        # Fallback for CLI usage if no LLM is passed
        return ""

    chat_prompt = prompt
    
    try:
        output = llm(
            chat_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            repeat_penalty=repeat_penalty,
            stop=["\n\n", "DOCUMENT:", "---", "<|eot_id|>"],
            echo=False
        )
        return output['choices'][0]['text'].strip()
    except Exception as e:
        print(f"Inference error: {e}")
        return ""

# ── Step 1: Read PDF ─────────────────────────────────────
def load_model(model_path):
    print(f"\n[4/5] Initializing engine (Auto-Detecting Hardware)...")
    if not model_path or not os.path.exists(model_path):
        sys.exit(f"ERROR: Model file not found at {model_path}")
    
    from llama_cpp import Llama
    import llama_cpp
    
    try:
        llm = Llama(
            model_path=model_path,
            n_ctx=8192,
            type_k=llama_cpp.GGML_TYPE_Q8_0,
            type_v=llama_cpp.GGML_TYPE_Q8_0,
            flash_attn=True,
            n_threads=os.cpu_count() or 4,
            n_gpu_layers=-1,
            verbose=True
        )
        print(f"   Success: TurboQuant Mode Enabled (8-bit KV + 8k Context).")
        return llm
    except Exception as e:
        print(f"   Hardware/Build check failed: {e}")
        print(f"   Switching to Universal Safe Mode (CPU Optimized).")
        physical_threads = max(1, (os.cpu_count() or 4) // 2)
        return Llama(
            model_path=model_path, 
            n_ctx=4096, 
            type_k=llama_cpp.GGML_TYPE_Q8_0,
            type_v=llama_cpp.GGML_TYPE_Q8_0,
            n_batch=512,
            flash_attn=False,
            n_threads=physical_threads,
            n_gpu_layers=0, 
            verbose=True
        )

def read_pdf(path):
    print(f"\n[1/5] Reading: {path}")
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("ERROR: pip install pdfplumber")
    if not os.path.exists(path):
        raise FileNotFoundError(f"ERROR: File not found - {path}")
    pages = []; scanned = 0
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            try:
                t = pg.extract_text()
                text = t.strip() if t else ""
                if len(text) < 30:
                    scanned += 1; pages.append("")
                else:
                    pages.append(text)
            except Exception:
                scanned += 1; pages.append("")
    readable = sum(1 for p in pages if p)
    print(f"   {len(pages)} pages total — {readable} machine-readable, {scanned} scanned/empty (skipped).")
    if readable == 0:
        raise ValueError("ERROR: No readable text. PDF appears fully scanned.")
    return pages


SUMMARY_PROMPT = (
    "DOCUMENT TEXT:\n"
    "--------------------\n"
    "{text}\n"
    "--------------------\n\n"
    "A concise, 3-sentence summary of the document above{focus}:\n"
)

def generate_summary(llm, pages, focus=""):
    focus_str = f"\nFocus: {focus.strip()}" if focus and focus.strip() else ""
    
    chunks = []
    current_chunk = ""
    for p in pages:
        if len(current_chunk) + len(p) > 24000 and current_chunk:
            chunks.append(current_chunk)
            current_chunk = p
        else:
            current_chunk += "\n\n" + p
    if current_chunk:
        chunks.append(current_chunk)
        
    chunk_summaries = []
    for chunk in chunks:
        prompt = SUMMARY_PROMPT.format(text=chunk, focus=focus_str)
        raw = _run_local_llm(llm, prompt, max_tokens=150, temperature=0.3, repeat_penalty=1.15)
        if raw:
            chunk_summaries.append(raw.strip())
            
    if not chunk_summaries:
        return ""
        
    if len(chunk_summaries) == 1:
        return chunk_summaries[0]
        
    final_combined = "\n\n---\n\n".join(chunk_summaries)
    if len(final_combined) > 24000:
        final_combined = final_combined[:24000] + "\n...[TRUNCATED]"
        
    final_prompt = SUMMARY_PROMPT.format(text="Combine these summaries into one final cohesive summary:\n" + final_combined, focus=focus_str)
    final_raw = _run_local_llm(llm, final_prompt, max_tokens=150, temperature=0.3, repeat_penalty=1.15)
    return final_raw.strip()

def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: python document_summarizer.py document.pdf")
    pdf_path = sys.argv[1]
    pages    = read_pdf(pdf_path)
    llm      = load_model(MODEL_PATH)
    print("\n[2/2] Generating summary...")
    summary  = generate_summary(llm, pages)
    print("\n--- FINAL SUMMARY ---\n")
    print(summary)

if __name__ == "__main__":
    main()
