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
else:
    print(f"Warning: {SUBMODULE_PATH} not found.")

def setup_lean():
    """Robust but minimal setup for Lean4 environment in Colab."""
    print("Checking Lean4 environment...")
    elan_bin = os.path.expanduser("~/.elan/bin")
    if elan_bin not in os.environ["PATH"]:
        os.environ["PATH"] = elan_bin + os.pathsep + os.environ["PATH"]
    
    if not shutil.which("lake"):
        print("Installing elan...")
        subprocess.run("curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh -s -- -y", shell=True, check=True)
    
    # Ensure the correct toolchain is linked
    subprocess.run(["elan", "default", "stable"], check=True)
    
    if os.path.exists(MATHLIB_PATH):
        print("Ensuring REPL is built in mathlib4...")
        # We build REPL because it's the bridge between Python and Lean
        subprocess.run(["lake", "build", "repl"], cwd=MATHLIB_PATH, check=True)
        
        # Link lake to where the verifier expects it
        os.makedirs(elan_bin, exist_ok=True)
        lake_path = shutil.which("lake")
        target = os.path.join(elan_bin, "lake")
        if lake_path and lake_path != target and not os.path.exists(target):
            try:
                os.symlink(lake_path, target)
            except FileExistsError:
                pass
    return True

def run_basic_arithmetic_test():
    """Verifies setup with a simple 2+2=4 theorem, dispensing with Mathlib."""
    if not setup_lean(): 
        print("Lean setup failed.")
        return

    try:
        os.chdir(SUBMODULE_PATH)
        import LoT_Prover
        import Prover
        import prover.lean.verifier
        
        # PRESCIND FROM MATHLIB: Use a minimal header that only uses Lean Core
        # This prevents the 'unknown namespace BigOperators' and massive build times
        MINIMAL_HEADER = "set_option maxHeartbeats 0\n"
        LoT_Prover.Lean4_HEADER = MINIMAL_HEADER
        Prover.Lean4_HEADER = MINIMAL_HEADER
        
        # Workspace MUST be mathlib4 to get the Lean toolchain, but we won't import Mathlib
        prover.lean.verifier.DEFAULT_LEAN_WORKSPACE = MATHLIB_PATH
        
        from LoT_Prover import LoT_Prover as LoT_Prover_Class
        from prover.lean.verifier import Lean4ServerScheduler
        
        # Provide a custom example to avoid loading Mathlib-dependent JSON
        simple_example = [{
            "Name": "add_zero",
            "NL": "Prove that n + 0 = n.",
            "Informal_statement": "For any natural number n, n + 0 = n.",
            "Statement": "theorem add_zero (n : Nat) : n + 0 = n :=",
            "Commented_proof": "  -- Use the built-in theorem for adding zero\n  Nat.add_zero n",
            "Proof": "theorem add_zero (n : Nat) : n + 0 = n := by\n  Nat.add_zero n"
        }]

        print("Initializing LoT_Prover (Prescinding from Mathlib)...")
        model_id = "RickyDeSkywalker/LoT-Solver" 
        
        scheduler = Lean4ServerScheduler(max_concurrent_requests=1, 
                                         timeout=30, 
                                         memory_limit=-1, 
                                         name='verifier')
        
        # example_num=1 tells the model to use our simple core-only example
        prover_inst = LoT_Prover_Class(model_id, 
                                      scheduler=scheduler, 
                                      example_list=simple_example, 
                                      example_num=1)
        
        Lean_statement = "theorem arithmetic_test : 2 + 2 = 4 := by"
        NL_statement = "Prove that 2 plus 2 equals 4."
        
        print(f"Running inference for: {Lean_statement}")
        results = prover_inst.LoT_search_single_thm(
            Lean_statement=Lean_statement,
            NL_statement=NL_statement,
            max_tokens=512,
            LongCoT_control=True
        )
        
        print("\n" + "="*30)
        print("ARITHMETIC TEST RESULTS:")
        if results:
            print(f"Status: SUCCESS")
            print(f"Proof Found: {results['Proof']}")
        else:
            print("Status: FAILED (No valid proof found in core Lean)")
        print("="*30)
        
    except Exception as e:
        print(f"Arithmetic test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        os.chdir(ORIGINAL_CWD)

if __name__ == "__main__":
    run_basic_arithmetic_test()
