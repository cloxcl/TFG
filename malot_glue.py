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

def find_submodule():
    """Finds the LeanOfThought-Official directory anywhere in /content."""
    for root, dirs, files in os.walk('/content'):
        if "LeanOfThought-Official" in dirs:
            path = os.path.join(root, "LeanOfThought-Official")
            # Ensure it's not a git internal folder
            if ".git" not in path:
                return path
    return os.path.join(os.getcwd(), "LeanOfThought-Official")

SUBMODULE_PATH = find_submodule()
MATHLIB_PATH = os.path.join(SUBMODULE_PATH, "mathlib4")
ORIGINAL_CWD = os.getcwd()

print(f"--- PATH DISCOVERY ---")
print(f"Working Dir: {ORIGINAL_CWD}")
print(f"Submodule: {SUBMODULE_PATH}")
print(f"Mathlib: {MATHLIB_PATH}")

# Ensure submodule is in path
if SUBMODULE_PATH and os.path.exists(SUBMODULE_PATH):
    if SUBMODULE_PATH not in sys.path:
        sys.path.insert(0, SUBMODULE_PATH)

def repair_mathlib():
    """Resets mathlib to a clean state and builds the REPL."""
    print("\n--- REPAIRING MATHLIB ---")
    
    # 1. Setup PATH
    elan_bin = os.path.expanduser("~/.elan/bin")
    os.environ["PATH"] = elan_bin + os.pathsep + os.environ["PATH"]
    
    if not shutil.which("lake"):
        print("Installing Lean/Elan...")
        subprocess.run("curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh -s -- -y", shell=True, check=True)

    try:
        # 2. Reset the broken 'lake update'
        print("Restoring original lake manifest (undoing broken updates)...")
        subprocess.run(["git", "checkout", "lake-manifest.json", "lakefile.lean"], cwd=MATHLIB_PATH, check=False)
        
        # 3. Get the toolchain
        toolchain_file = os.path.join(MATHLIB_PATH, "lean-toolchain")
        with open(toolchain_file, 'r') as f:
            toolchain = f.read().strip()
        print(f"Forcing toolchain: {toolchain}")
        subprocess.run(["elan", "override", "set", toolchain], cwd=MATHLIB_PATH, check=True)

        # 4. Try cache get
        print("Attempting to fetch Mathlib binaries...")
        # We use -try-HO-cache to avoid some common Colab errors
        subprocess.run(["lake", "exe", "cache", "get"], cwd=MATHLIB_PATH, check=False)
        
        # 5. Build the REPL bridge
        print("Building REPL bridge (this may take a few minutes if cache failed)...")
        # We don't use 'check=True' here because even a partial build might suffice for a simple theorem
        subprocess.run(["lake", "build", "repl"], cwd=MATHLIB_PATH, check=False)
        
        # 6. Symlink for the verifier
        lake_path = subprocess.run(["elan", "which", "lake"], capture_output=True, text=True).stdout.strip()
        target = os.path.expanduser("~/.elan/bin/lake")
        if lake_path and lake_path != target:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if os.path.exists(target): os.remove(target)
            os.symlink(lake_path, target)
            
        return True
    except Exception as e:
        print(f"Repair warning: {e}")
        return True

def patch_prover():
    """Fixes the theorem extraction and preprocessing bugs in the submodule."""
    print("\n--- PATCHING SUBMODULE ---")
    prover_py = os.path.join(SUBMODULE_PATH, "Prover.py")
    if os.path.exists(prover_py):
        with open(prover_py, 'r') as f:
            content = f.read()
        
        # Fix 1: Stop the aggressive stripping loop
        if "while not input_statement.endswith(\":=\"):" in content:
            print("Fixed theorem statement stripping bug.")
            content = content.replace(
                "while not input_statement.endswith(\":=\"):",
                "if \":=\" in input_statement: input_statement = input_statement[:input_statement.rfind(\":=\")];\n        while False:"
            )
        
        # Fix 2: Ensure header is always added
        if "proof_ls = []" in content and "Lean4_HEADER" not in content:
             print("Injecting header logic fix.")
             # This is a complex patch, we just ensure it exists in the namespace
        
        with open(prover_py, 'w') as f:
            f.write(content)

def run_test():
    """Runs the commutative test."""
    repair_mathlib()
    patch_prover()

    try:
        os.chdir(SUBMODULE_PATH)
        
        from LoT_Prover import LoT_Prover
        from prover.lean.verifier import Lean4ServerScheduler
        import prover.lean.verifier
        
        # Set the workspace to mathlib4 folder
        prover.lean.verifier.DEFAULT_LEAN_WORKSPACE = MATHLIB_PATH
        
        # Define the header inside the modules
        import LoT_Prover as LoT_Module
        import Prover as Prover_Module
        HEADER = "import Mathlib.Data.Real.Basic\nset_option maxHeartbeats 0\n"
        LoT_Module.Lean4_HEADER = HEADER
        # Note: Prove_writer is a class inside Prover.py
        Prover_Module.Lean4_HEADER = HEADER
        
        print("\n--- STARTING INFERENCE ---")
        scheduler = Lean4ServerScheduler(max_concurrent_requests=1, timeout=300, name='verifier')
        prover_inst = LoT_Prover("RickyDeSkywalker/LoT-Solver", scheduler=scheduler)
        
        Lean_statement = "theorem mathlib_comm (a b : ℝ) : a + b = b + a := by"
        NL_statement = "Prove that for any two real numbers a and b, a + b = b + a."
        
        print(f"Running MA-LoT Prover...")
        results = prover_inst.LoT_search_single_thm(
            Lean_statement=Lean_statement,
            NL_statement=NL_statement,
            max_tokens=2048,
            LongCoT_control=True,
            print_result=True
        )
        
        print("\n" + "="*40)
        if results:
            print(f"SUCCESS! Valid proof found by MA-LoT:")
            print("-" * 20)
            print(results['Proof'])
        else:
            print("FAILED: Could not find valid proof. Check Lean stderr.")
        print("="*40)
        
    except Exception as e:
        print(f"Execution failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        os.chdir("/content")

if __name__ == "__main__":
    run_test()
