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
import time
import shutil

# Add the submodule to the Python path
SUBMODULE_PATH = os.path.join(os.getcwd(), "LeanOfThought-Official")
ORIGINAL_CWD = os.getcwd()

if os.path.exists(SUBMODULE_PATH):
    sys.path.append(SUBMODULE_PATH)
    print(f"Added {SUBMODULE_PATH} to sys.path")
else:
    print(f"Warning: {SUBMODULE_PATH} not found. Make sure you have cloned the submodule.")

def setup_lean():
    """Robust setup for Lean4 environment in Colab."""
    print("Checking for Lean4...")
    
    # Try to find lake in the PATH
    lake_path = shutil.which("lake")
    
    if not lake_path:
        print("Lean4 (lake) not found. Installing via elan...")
        try:
            # Install elan
            subprocess.run("curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh -s -- -y", shell=True, check=True)
            # Add to PATH for this process
            elan_bin = os.path.expanduser("~/.elan/bin")
            os.environ["PATH"] = elan_bin + os.pathsep + os.environ["PATH"]
            lake_path = shutil.which("lake")
        except Exception as e:
            print(f"Failed to install elan: {e}")
            return False

    if lake_path:
        print(f"Lean4 found at: {lake_path}")
        # Ensure the submodule's expected path exists via symlink
        expected_path = os.path.expanduser("~/.elan/bin/lake")
        if lake_path != expected_path:
            os.makedirs(os.path.dirname(expected_path), exist_ok=True)
            if not os.path.exists(expected_path):
                print(f"Creating symlink: {expected_path} -> {lake_path}")
                try:
                    os.symlink(lake_path, expected_path)
                except FileExistsError:
                    pass
        
        # Build mathlib REPL if needed (required by the verifier)
        print("Ensuring mathlib4 REPL is available...")
        mathlib_path = os.path.join(SUBMODULE_PATH, "mathlib4")
        if os.path.exists(mathlib_path):
            try:
                # We need the 'repl' executable specifically
                subprocess.run([lake_path, "build", "repl"], cwd=mathlib_path, check=True)
                print("Mathlib4 REPL built successfully.")
            except Exception as e:
                print(f"Warning: Failed to build mathlib4 REPL: {e}")
        return True
    return False

def run_basic_arithmetic_test():
    """Verifies setup with a simple 2+2=4 theorem."""
    if not setup_lean():
        print("Aborting test: Lean4 setup failed.")
        return

    try:
        # Change directory to the submodule so relative paths inside it work
        os.chdir(SUBMODULE_PATH)
        
        from LoT_Prover import LoT_Prover
        from prover.lean.verifier import Lean4ServerScheduler
        
        print("Initializing LoT_Prover for arithmetic test...")
        model_id = "RickyDeSkywalker/LoT-Solver" 
        
        scheduler = Lean4ServerScheduler(max_concurrent_requests=1, 
                                         timeout=30, 
                                         memory_limit=-1, 
                                         name='verifier')
        
        prover = LoT_Prover(model_id, scheduler=scheduler)
        
        # Simple theorem to prove the setup
        Lean_statement = "theorem arithmetic_test : 2 + 2 = 4 := by"
        NL_statement = "Prove that 2 plus 2 equals 4."
        
        print(f"Running inference for: {Lean_statement}")
        results = prover.LoT_search_single_thm(
            Lean_statement=Lean_statement,
            NL_statement=NL_statement,
            max_tokens=512,
            LongCoT_control=True
        )
        print("Arithmetic Test Results:", results)
        
    except Exception as e:
        print(f"Arithmetic test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        os.chdir(ORIGINAL_CWD)

def run_test():
    """Example test run using LoT_Prover."""
    try:
        os.chdir(SUBMODULE_PATH)
        from LoT_Prover import LoT_Prover
        from prover.lean.verifier import Lean4ServerScheduler
        
        print("Initializing LoT_Prover...")
        model_id = "RickyDeSkywalker/LoT-Solver" 
        
        scheduler = Lean4ServerScheduler(max_concurrent_requests=4, 
                                         timeout=64, 
                                         memory_limit=-1, 
                                         name='verifier')
        
        prover = LoT_Prover(model_id, scheduler=scheduler)
        
        Lean_statement = "theorem test_thm (a b : ℝ) : a + b = b + a := by"
        NL_statement = "Prove that for any two real numbers a and b, a + b = b + a."
        
        print("Running inference...")
        results = prover.LoT_search_single_thm(
            Lean_statement=Lean_statement,
            NL_statement=NL_statement,
            max_tokens=1024,
            LongCoT_control=True
        )
        print("Results:", results)
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        os.chdir(ORIGINAL_CWD)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "test-arithmetic":
            run_basic_arithmetic_test()
        elif arg == "test":
            run_test()
        else:
            print(f"Unknown command: {arg}")
            print("Usage: uv run malot_glue.py [test|test-arithmetic]")
    else:
        print("Usage: uv run malot_glue.py [test|test-arithmetic]")
        setup_lean()
