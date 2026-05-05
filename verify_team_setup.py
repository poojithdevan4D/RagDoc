import os
import sys

def verify():
    # Get the directory where the script is located
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    print("\n--- TurboQuant Team Setup Verification ---\n" + "="*40)
    
    # 1. Python Check
    print(f"[*] Python Version: {sys.version.split()[0]}", end=" ")
    if sys.version_info >= (3, 10):
        print("OK")
    else:
        print("ERROR (Requires 3.10+)")

    # 2. Virtual Env Check
    venv_path = os.path.join(base_dir, ".venv")
    print(f"[*] Virtual Env: .venv", end=" ")
    if os.path.isdir(venv_path):
        print("OK")
    else:
        print("ERROR (Missing .venv in project folder)")

    # 3. Dependencies Check
    try:
        import flask
        import pdfplumber
        import docx
        import llama_cpp
        import numpy
        print("[*] Dependencies: OK (Found all core libraries)")
    except ImportError as e:
        print(f"[*] Dependencies: ERROR (Missing: {e.name})")

    # 4. Model Check
    models_dir = os.path.join(base_dir, "models")
    print(f"[*] Models Directory: models/", end=" ")
    if os.path.isdir(models_dir):
        print("OK")
        gguf_files = [f for f in os.listdir(models_dir) if f.endswith(".gguf")]
        if gguf_files:
            print(f"    - Found model: {gguf_files[0]} OK")
        else:
            print("    - ERROR: No .gguf files found in models/ folder!")
    else:
        print("ERROR (Directory missing!)")

    # 5. AI Engine & Hardware Acceleration
    try:
        import llama_cpp
        gpu_support = llama_cpp.llama_supports_gpu_offload()
        print(f"[*] Hardware Acceleration: ", end="")
        if gpu_support:
            print("GPU (CUDA) Enabled")
        else:
            print("CPU Optimized Mode")
    except Exception as e:
        print(f"[*] AI Engine Status: ERROR (Error checking engine: {e})")

    print("="*40)
    print("If all items are OK, you are ready to run: python server.py")
    print("="*40 + "\n")

if __name__ == "__main__":
    verify()
