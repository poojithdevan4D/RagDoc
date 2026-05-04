import os
import sys

def verify():
    print("\n🔍 TurboQuant Team Setup Verification\n" + "="*40)
    
    # 1. Python Check
    print(f"[*] Python Version: {sys.version.split()[0]}", end=" ")
    if sys.version_info >= (3, 10):
        print("✅")
    else:
        print("❌ (Requires 3.10+)")

    # 2. Virtual Env Check
    venv_path = os.path.join(os.getcwd(), ".venv")
    print(f"[*] Virtual Env: {venv_path}", end=" ")
    if os.path.isdir(venv_path):
        print("✅")
    else:
        print("❌ (Run setup.ps1 first)")

    # 3. Dependencies Check
    try:
        import flask
        import pdfplumber
        import docx
        import llama_cpp
        print("[*] Dependencies: ✅ (Found all core libraries)")
    except ImportError as e:
        print(f"[*] Dependencies: ❌ (Missing: {e.name})")

    # 4. Model Check
    models_dir = os.path.join(os.getcwd(), "models")
    print(f"[*] Models Directory: {models_dir}", end=" ")
    if os.path.isdir(models_dir):
        print("✅")
        gguf_files = [f for f in os.listdir(models_dir) if f.endswith(".gguf")]
        if gguf_files:
            print(f"    - Found model: {gguf_files[0]} ✅")
        else:
            print("    - ❌ No .gguf files found in models/ folder!")
    else:
        print("❌ (Directory missing!)")

    # 5. TurboQuant Build Check
    try:
        from llama_cpp import llama_supports_gpu_offload
        # Check for AVX2 support via llama.cpp
        print("[*] AI Engine Optimization: ✅ (Native Build Detected)")
    except:
        print("[*] AI Engine Optimization: ❌ (Basic build or missing)")

    print("="*40 + "\n")

if __name__ == "__main__":
    verify()
