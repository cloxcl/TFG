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
    print("Setting up Mathlib environment (this may take a few minutes)...")
    
    # 1. Ensure elan/lake is in PATH
    elan_bin = os.path.expanduser("~/.elan/bin")
    if elan_bin not in os.environ["PATH"]:
        os.environ["PATH"] = elan_bin + os.pathsep + os.environ["PATH"]
    
    if not shutil.which("lake"):
        print("Installing elan...")
        subprocess.run("curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh -s -- -y", shell=True, check=True)

    if not os.path.exists(MATHLIB_PATH):
        print(f"Error: Mathlib path not found at {MATHLIB_PATH}. Did you clone with --recurse-submodules?")
        return False

    try:
        # 2. Update Mathlib to ensure we can find a valid cache
        print("Updating Mathlib manifest...")
        subprocess.run(["lake", "update"], cwd=MATHLIB_PATH, check=True)
        
        # 3. Fetch precompiled binaries (Crucial for speed!)
        print("Fetching Mathlib cache...")
        subprocess.run(["lake", "exe", "cache", "get"], cwd=MATHLIB_PATH, check=True)
        
        # 4. Build the REPL (the bridge for MA-LoT)
        print("Building Mathlib REPL...")
        subprocess.run(["lake", "build", "repl"], cwd=MATHLIB_PATH, check=True)
        
        # 5. Link lake for the verifier
        lake_path = shutil.which("lake")
        expected_path = os.path.expanduser("~/.elan/bin/lake")
        if lake_path and lake_path != expected_path and not os.path.exists(expected_path):
            os.makedirs(os.path.dirname(expected_path), exist_ok=True)
            os.symlink(lake_path, expected_path)
            
        print("Mathlib setup complete!")
        return True
    except Exception as e:
        print(f"Mathlib setup failed: {e}")
        return False

def run_arithmetic_test():
    """Verifies setup with 2+2=4 using full Mathlib headers."""
    if not setup_mathlib(): return

    try:
        os.chdir(SUBMODULE_PATH)
        
        # We NO LONGER patch headers. We want the real ones back.
        from LoT_Prover import LoT_Prover
        from prover.lean.verifier import Lean4ServerScheduler
        import prover.lean.verifier
        
        # Use mathlib4 as the official workspace
        prover.lean.verifier.DEFAULT_LEAN_WORKSPACE = MATHLIB_PATH
        
        print("Initializing LoT_Prover with Mathlib...")
        scheduler = Lean4ServerScheduler(max_concurrent_requests=1, timeout=60, name='verifier')
        
        # Note: We let the prover load the real examples from JSON now
        prover_inst = LoT_Prover("RickyDeSkywalker/LoT-Solver", scheduler=scheduler)
        
        # Theorem using Real numbers to prove Mathlib is working
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
