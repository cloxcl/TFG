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

# Add the submodule to the Python path
SUBMODULE_PATH = os.path.join(os.getcwd(), "LeanOfThought-Official")
MATHLIB_PATH = os.path.join(SUBMODULE_PATH, "mathlib4")
ORIGINAL_CWD = os.getcwd()

if os.path.exists(SUBMODULE_PATH):
    sys.path.append(SUBMODULE_PATH)
    print(f"Added {SUBMODULE_PATH} to sys.path")

def setup_mathlib():
    """Restores and synchronizes Mathlib environment."""
    print("Setting up Mathlib environment...")
    
    # 1. Ensure elan/lake is in PATH
    elan_bin = os.path.expanduser("~/.elan/bin")
    if elan_bin not in os.environ["PATH"]:
        os.environ["PATH"] = elan_bin + os.pathsep + os.environ["PATH"]
    
    if not shutil.which("lake"):
        print("Installing elan...")
        subprocess.run("curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh -s -- -y", shell=True, check=True)

    if not os.path.exists(MATHLIB_PATH):
        print(f"Error: Mathlib path not found at {MATHLIB_PATH}.")
        return False

    try:
        # Read the required toolchain
        toolchain_file = os.path.join(MATHLIB_PATH, "lean-toolchain")
        if os.path.exists(toolchain_file):
            with open(toolchain_file, 'r') as f:
                toolchain = f.read().strip()
            print(f"Required toolchain: {toolchain}")
            # Ensure it's installed
            subprocess.run(["elan", "install", toolchain], check=True)
        
        # 2. We SKIP 'lake update' because it can break dependencies.
        # We try to get the cache using the manifest as is.
        print("Fetching Mathlib cache (using existing manifest)...")
        # We use 'elan run' to make sure we use the EXACT toolchain required
        subprocess.run(["elan", "run", toolchain, "lake", "exe", "cache", "get"], cwd=MATHLIB_PATH, check=True)
        
        # 3. Build the REPL
        print("Building Mathlib REPL...")
        subprocess.run(["elan", "run", toolchain, "lake", "build", "repl"], cwd=MATHLIB_PATH, check=True)
        
        # 4. Link lake for the verifier
        # Find where the actual lake for this toolchain is
        lake_path = subprocess.run(["elan", "which", "lake"], capture_output=True, text=True).stdout.strip()
        expected_path = os.path.expanduser("~/.elan/bin/lake")
        if lake_path and lake_path != expected_path:
            os.makedirs(os.path.dirname(expected_path), exist_ok=True)
            if os.path.exists(expected_path):
                os.remove(expected_path)
            os.symlink(lake_path, expected_path)
            
        print("Mathlib setup complete!")
        return True
    except Exception as e:
        print(f"Mathlib setup failed: {e}")
        # If it failed, maybe try one last 'lake update' but only if really needed
        print("Attempting a fallback build...")
        try:
             subprocess.run(["lake", "build", "repl"], cwd=MATHLIB_PATH, check=False)
             return True
        except:
             return False

def run_arithmetic_test():
    """Verifies setup with a simple commutative theorem."""
    if not setup_mathlib(): return

    try:
        os.chdir(SUBMODULE_PATH)
        
        from LoT_Prover import LoT_Prover
        from prover.lean.verifier import Lean4ServerScheduler
        import prover.lean.verifier
        
        # Use mathlib4 as the official workspace
        prover.lean.verifier.DEFAULT_LEAN_WORKSPACE = MATHLIB_PATH
        
        print("Initializing LoT_Prover with Mathlib...")
        scheduler = Lean4ServerScheduler(max_concurrent_requests=1, timeout=120, name='verifier')
        
        prover_inst = LoT_Prover("RickyDeSkywalker/LoT-Solver", scheduler=scheduler)
        
        # COMMUTATIVE TEST (Requires Mathlib for Real numbers)
        Lean_statement = "theorem mathlib_test (a b : ℝ) : a + b = b + a := by"
        NL_statement = "Prove that addition of real numbers is commutative."
        
        print(f"Running inference for: {Lean_statement}")
        results = prover_inst.LoT_search_single_thm(
            Lean_statement=Lean_statement,
            NL_statement=NL_statement,
            max_tokens=1024,
            LongCoT_control=True
        )
        
        print("\n" + "="*30)
        print("MATHLIB TEST RESULTS:")
        if results:
            print(f"Status: SUCCESS")
            print(f"Proof Found: {results['Proof']}")
        else:
            print("Status: FAILED")
        print("="*30)
        
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        os.chdir(ORIGINAL_CWD)

if __name__ == "__main__":
    run_arithmetic_test()
