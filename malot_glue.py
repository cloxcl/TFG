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
MINIMAL_WORKSPACE = "/tmp/minimal_lean"
ORIGINAL_CWD = os.getcwd()

if os.path.exists(SUBMODULE_PATH):
    sys.path.append(SUBMODULE_PATH)
    print(f"Added {SUBMODULE_PATH} to sys.path")

def setup_minimal_lean():
    """Ensures a minimal Lean workspace is ready."""
    print(f"Setting up minimal Lean workspace at {MINIMAL_WORKSPACE}...")
    os.makedirs(MINIMAL_WORKSPACE, exist_ok=True)
    
    with open(os.path.join(MINIMAL_WORKSPACE, "lakefile.lean"), "w") as f:
        f.write('import Lake\nopen Lake DSL\npackage minimal where\n@[default_target]\nlean_lib Minimal\n')
    
    with open(os.path.join(MINIMAL_WORKSPACE, "lean-toolchain"), "w") as f:
        f.write('leanprover/lean4:stable\n')
        
    with open(os.path.join(MINIMAL_WORKSPACE, "Minimal.lean"), "w") as f:
        f.write('-- Minimal Lean File\n')
    
    # Add elan to PATH
    elan_bin = os.path.expanduser("~/.elan/bin")
    if elan_bin not in os.environ["PATH"]:
        os.environ["PATH"] = elan_bin + os.pathsep + os.environ["PATH"]
    
    try:
        subprocess.run(["lake", "build"], cwd=MINIMAL_WORKSPACE, check=True, capture_output=True)
        print("Minimal Lean workspace ready.")
        
        # Link lake for verifier
        lake_path = shutil.which("lake")
        expected_path = os.path.expanduser("~/.elan/bin/lake")
        if lake_path and lake_path != expected_path and not os.path.exists(expected_path):
            os.makedirs(os.path.dirname(expected_path), exist_ok=True)
            os.symlink(lake_path, expected_path)
            
        return True
    except Exception as e:
        print(f"Failed to setup minimal workspace: {e}")
        return False

def run_basic_arithmetic_test():
    """Verifies setup with 2+2=4 using a simplified inference path."""
    if not setup_minimal_lean(): return

    try:
        os.chdir(SUBMODULE_PATH)
        import LoT_Prover
        import Prover
        import prover.lean.verifier
        
        # AGGRESSIVE PATCHING
        MINIMAL_HEADER = "set_option maxHeartbeats 0\n"
        LoT_Prover.Lean4_HEADER = MINIMAL_HEADER
        Prover.Lean4_HEADER = MINIMAL_HEADER
        
        # Use our clean minimal workspace for verification
        prover.lean.verifier.DEFAULT_LEAN_WORKSPACE = MINIMAL_WORKSPACE
        
        from LoT_Prover import LoT_Prover as LoT_Prover_Class
        from prover.lean.verifier import Lean4ServerScheduler
        
        # Simple example to guide the model without Mathlib
        simple_example = [{
            "Name": "add_zero",
            "NL": "Prove that n + 0 = n.",
            "Informal_statement": "For any natural number n, n + 0 = n.",
            "Statement": "theorem add_zero (n : Nat) : n + 0 = n :=",
            "Commented_proof": "  -- Use the built-in theorem for adding zero\n  Nat.add_zero n",
            "Proof": "theorem add_zero (n : Nat) : n + 0 = n := by\n  Nat.add_zero n"
        }]

        print("Initializing LoT_Prover (Minimal Mode)...")
        scheduler = Lean4ServerScheduler(max_concurrent_requests=1, timeout=30, name='verifier')
        
        # We use example_num=1 and standard inference (LongCoT_control=False) 
        # to avoid the extraction bugs we saw earlier.
        prover_inst = LoT_Prover_Class("RickyDeSkywalker/LoT-Solver", 
                                      scheduler=scheduler, 
                                      example_list=simple_example, 
                                      example_num=1)
        
        Lean_statement = "theorem arithmetic_test : 2 + 2 = 4 := by"
        NL_statement = "Prove that 2 plus 2 equals 4."
        
        print(f"Running inference (Standard Inference)...")
        # LongCoT_control=False is safer for patched headers
        results = prover_inst.LoT_search_single_thm(
            Lean_statement=Lean_statement,
            NL_statement=NL_statement,
            max_tokens=1024,
            LongCoT_control=False,
            print_result=True # Let's see what the model actually says
        )
        
        print("\n" + "="*30)
        print("ARITHMETIC TEST RESULTS:")
        if results:
            print(f"Status: SUCCESS")
            print(f"Proof Found: {results['Proof']}")
        else:
            print("Status: FAILED")
        print("="*30)
        
    except Exception as e:
        print(f"Arithmetic test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        os.chdir(ORIGINAL_CWD)

if __name__ == "__main__":
    run_basic_arithmetic_test()
