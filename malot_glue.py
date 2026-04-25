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

# Add the submodule to the Python path
SUBMODULE_PATH = os.path.join(os.getcwd(), "LeanOfThought-Official")
ORIGINAL_CWD = os.getcwd()

if os.path.exists(SUBMODULE_PATH):
    sys.path.append(SUBMODULE_PATH)
    print(f"Added {SUBMODULE_PATH} to sys.path")
else:
    print(f"Warning: {SUBMODULE_PATH} not found. Make sure you have cloned the submodule.")

def setup_lean():
    """Basic setup for Lean4 environment in Colab."""
    print("Checking for Lean4...")
    try:
        subprocess.run(["lean", "--version"], check=True, capture_output=True)
        print("Lean4 is already installed.")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Lean4 not found. You might need to install it using elan.")

def run_basic_arithmetic_test():
    """Verifies setup with a simple 2+2=4 theorem."""
    try:
        # Change directory to the submodule so relative paths inside it work
        os.chdir(SUBMODULE_PATH)
        print(f"Changed working directory to {os.getcwd()}")
        
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
            max_tokens=512
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
            max_tokens=1024
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
