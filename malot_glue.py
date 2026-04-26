# /// script
# dependencies = [
#   "torch",
#   "vllm",
#   "transformers",
#   "datasets",
#   "pyyaml",
#   "tqdm",
#   "easydict",
#   "aiohttp",
#   "fastapi",
#   "uvicorn",
#   "pydantic",
#   "numpy",
#   "pytz",
# ]
# ///

import os
import sys
import subprocess
import shutil
import torch
import time

# FORCE vLLM to use CUDA
os.environ["VLLM_TARGET_DEVICE"] = "cuda"

def find_submodule():
    """Finds the LeanOfThought-Official directory anywhere in /content."""
    for root, dirs, files in os.walk('/content'):
        if "LeanOfThought-Official" in dirs and ".git" not in root:
            return os.path.join(root, "LeanOfThought-Official")
    return os.path.join(os.getcwd(), "LeanOfThought-Official")

SUBMODULE_PATH = find_submodule()
MATHLIB_PATH = os.path.join(SUBMODULE_PATH, "mathlib4")
ORIGINAL_CWD = os.getcwd()

print(f"--- HARDWARE CHECK ---")
cuda_available = torch.cuda.is_available()
print(f"CUDA Available: {cuda_available}")
if cuda_available:
    print(f"GPU Name: {torch.cuda.get_device_name(0)}")
else:
    print("!!! ERROR: NO GPU DETECTED !!!")
    print("Go to Runtime > Change runtime type and select 'T4 GPU'.")

print(f"\n--- PATH CHECK ---")
print(f"Submodule: {SUBMODULE_PATH}")
print(f"Mathlib: {MATHLIB_PATH}")

# Force path addition
if SUBMODULE_PATH and os.path.exists(SUBMODULE_PATH):
    if SUBMODULE_PATH not in sys.path:
        sys.path.insert(0, SUBMODULE_PATH)

def repair_mathlib():
    """Resets mathlib to a clean state and builds the REPL."""
    print("\n--- REPAIRING MATHLIB ---")
    
    elan_bin = os.path.expanduser("~/.elan/bin")
    os.environ["PATH"] = elan_bin + os.pathsep + os.environ["PATH"]
    os.environ["ELAN_HOME"] = os.path.expanduser("~/.elan")
    
    if not shutil.which("lake"):
        print("Installing elan...")
        subprocess.run("curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh -s -- -y", shell=True, check=True)

    try:
        # 1. Reset manifest
        print("Restoring original manifest...")
        subprocess.run(["git", "checkout", "lake-manifest.json"], cwd=MATHLIB_PATH, check=False)
        
        # 2. Setup Toolchain
        toolchain_file = os.path.join(MATHLIB_PATH, "lean-toolchain")
        if os.path.exists(toolchain_file):
            with open(toolchain_file, 'r') as f:
                toolchain = f.read().strip()
            print(f"Forcing toolchain: {toolchain}")
            subprocess.run(["elan", "override", "set", toolchain], cwd=MATHLIB_PATH, check=True)

        # 3. Get binaries (even if partial)
        print("Fetching binaries (cache get)...")
        # Use yes to bypass any prompts and a timeout to prevent hanging
        try:
            subprocess.run("yes | lake exe cache get", shell=True, cwd=MATHLIB_PATH, check=False, timeout=600)
        except subprocess.TimeoutExpired:
            print("Cache fetch timed out, proceeding anyway...")
        
        # 4. Build REPL
        print("Building REPL bridge...")
        subprocess.run("yes | lake build REPL", shell=True, cwd=MATHLIB_PATH, check=False, timeout=300)
        
        # 5. Symlink for verifier
        lake_path = subprocess.run(["elan", "which", "lake"], capture_output=True, text=True).stdout.strip()
        target = os.path.expanduser("~/.elan/bin/lake")
        if lake_path and lake_path != target:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if os.path.exists(target): os.remove(target)
            try:
                os.symlink(lake_path, target)
            except OSError:
                print("Failed to create lake symlink")
            
        return True
    except Exception as e:
        print(f"Mathlib setup warning: {e}")
        return True

def patch_submodule():
    """Applies critical fixes to the research code."""
    print("\n--- PATCHING SUBMODULE ---")
    
    # 1. Fix aggressive stripping bug and newline issue in Prover.py
    prover_py = os.path.join(SUBMODULE_PATH, "Prover.py")
    if os.path.exists(prover_py):
        with open(prover_py, 'r') as f:
            content = f.read()
        
        old_code = "while not input_statement.endswith(\":=\"):"
        if old_code in content:
            new_code = "if \":=\" in input_statement: input_statement = input_statement[:input_statement.rfind(\":=\")];\n        while False:"
            content = content.replace(old_code, new_code)
            
        old_newline_code = "input_statement += \":= by\"\n        return input_statement"
        if old_newline_code in content:
            new_newline_code = "input_statement += \":= by\\n\"\n        return input_statement"
            content = content.replace(old_newline_code, new_newline_code)
            
        with open(prover_py, 'w') as f:
            f.write(content)
        print("Patched Prover.py")

    # 2. Fix model ID check in LoT_Prover.py to support official DeepSeek models
    lot_prover_py = os.path.join(SUBMODULE_PATH, "LoT_Prover.py")
    if os.path.exists(lot_prover_py):
        with open(lot_prover_py, 'r') as f:
            content = f.read()
        
        # Expand check to allow official names
        old_check = "if \"lot-solver\" in self.model_id.lower():"
        new_check = "if \"lot-solver\" in self.model_id.lower() or \"prover-v1.5\" in self.model_id.lower():"
        if old_check in content:
            content = content.replace(old_check, new_check)
            with open(lot_prover_py, 'w') as f:
                f.write(content)
            print("Patched LoT_Prover.py")

def run_test(Lean_statement, NL_statement):
    """Runs the proof pipeline."""
    if not torch.cuda.is_available():
        print("Aborting: GPU required for vLLM.")
        return

    repair_mathlib()
    patch_submodule()

    try:
        os.chdir(SUBMODULE_PATH)
        
        print("Loading LoT modules...")
        from LoT_Prover import LoT_Prover
        from prover.lean.verifier import Lean4ServerScheduler
        import prover.lean.verifier
        
        # Set workspace
        prover.lean.verifier.DEFAULT_LEAN_WORKSPACE = MATHLIB_PATH
        
        # Use a minimal header to avoid "unknown namespace" errors if Mathlib is partially built
        HEADER = "import Mathlib\nset_option maxHeartbeats 0\n"
        
        import LoT_Prover as LoT_Module
        import Prover as Prover_Module
        import Corrector as Corrector_Module
        
        # Correctly override the module-level globals
        LoT_Module.Lean4_HEADER = HEADER
        Prover_Module.Lean4_HEADER = HEADER
        Corrector_Module.Lean4_HEADER = HEADER
        
        print("\n--- STARTING INFERENCE ---")
        print(f"Theorem: {Lean_statement}")
        
        scheduler = Lean4ServerScheduler(max_concurrent_requests=1, timeout=300, name='verifier')
        # Updated to the requested model
        prover_inst = LoT_Prover("deepseek-ai/DeepSeek-Prover-V1.5-RL", scheduler=scheduler)
        
        results = prover_inst.LoT_search_single_thm(
            Lean_statement=Lean_statement,
            NL_statement=NL_statement,
            max_tokens=2048,
            LongCoT_control=True,
            print_result=True
        )
        
        print("\n" + "="*40)
        if results:
            print(f"SUCCESS!\nProof:\n{results['Proof']}")
        else:
            print("FAILED: Could not find valid proof.")
        print("="*40)
        
    except Exception as e:
        print(f"\n!!! EXECUTION FAILED !!!")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        os.chdir(ORIGINAL_CWD)

if __name__ == "__main__":
    import sys
    test_type = sys.argv[1] if len(sys.argv) > 1 else "default"
    
    if test_type == "test-arithmetic":
        Lean_statement = "theorem arithmetic_test : 2 + 2 = 4 := by"
        NL_statement = "Prove that 2 + 2 = 4."
    else:
        Lean_statement = "theorem mathlib_comm (a b : ℝ) : a + b = b + a := by"
        NL_statement = "Prove that for any two real numbers a and b, a + b = b + a."
        
    try:
        run_test(Lean_statement, NL_statement)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as e:
        print(f"Fatal error: {e}")
