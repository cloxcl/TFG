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

def find_path(name):
    """Recursively search for a folder or file starting from /content."""
    for root, dirs, files in os.walk('/content'):
        if name in dirs:
            return os.path.join(root, name)
    # Fallback to local search if not in /content
    for root, dirs, files in os.walk(os.getcwd()):
        if name in dirs:
            return os.path.join(root, name)
    return None

SUBMODULE_PATH = find_path("LeanOfThought-Official")
MATHLIB_PATH = os.path.join(SUBMODULE_PATH, "mathlib4") if SUBMODULE_PATH else None

def setup_mathlib():
    """Restores and synchronizes Mathlib environment with forced cleanup."""
    print(f"Submodule path: {SUBMODULE_PATH}")
    print(f"Mathlib path: {MATHLIB_PATH}")
    
    if not SUBMODULE_PATH or not os.path.exists(SUBMODULE_PATH):
        print("Error: Could not find LeanOfThought-Official submodule.")
        return False

    elan_bin = os.path.expanduser("~/.elan/bin")
    if elan_bin not in os.environ["PATH"]:
        os.environ["PATH"] = elan_bin + os.pathsep + os.environ["PATH"]
    
    if not shutil.which("lake"):
        print("Installing Lean/Elan...")
        subprocess.run("curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh -s -- -y", shell=True, check=True)

    # CRITICAL: Remove existing build files that might be corrupted
    build_dir = os.path.join(MATHLIB_PATH, ".lake", "build")
    if os.path.exists(build_dir):
        print("Cleaning up old build files...")
        shutil.rmtree(build_dir)

    try:
        # Read the required toolchain
        toolchain_file = os.path.join(MATHLIB_PATH, "lean-toolchain")
        with open(toolchain_file, 'r') as f:
            toolchain = f.read().strip()
        
        print(f"Using toolchain: {toolchain}")
        subprocess.run(["elan", "override", "set", toolchain], cwd=MATHLIB_PATH, check=True)
        
        # Try to get cache. 
        print("Fetching Mathlib cache binaries...")
        subprocess.run(["lake", "exe", "cache", "get"], cwd=MATHLIB_PATH, check=False)
        
        print("Building REPL bridge...")
        subprocess.run(["lake", "build", "repl"], cwd=MATHLIB_PATH, check=True)
        
        # Link lake for the verifier
        lake_path = subprocess.run(["elan", "which", "lake"], capture_output=True, text=True).stdout.strip()
        expected_path = os.path.expanduser("~/.elan/bin/lake")
        if lake_path and lake_path != expected_path:
            os.makedirs(os.path.dirname(expected_path), exist_ok=True)
            if os.path.exists(expected_path): os.remove(expected_path)
            os.symlink(lake_path, expected_path)
            
        print("Mathlib setup complete!")
        return True
    except Exception as e:
        print(f"Setup warning: {e}. Attempting to proceed anyway...")
        return True

def run_test():
    """Runs the commutative test with Mathlib re-enabled."""
    if not setup_mathlib(): return

    try:
        os.chdir(SUBMODULE_PATH)
        from LoT_Prover import LoT_Prover
        from prover.lean.verifier import Lean4ServerScheduler
        import prover.lean.verifier
        import LoT_Prover as LoT_Module
        import Prover as Prover_Module
        
        # Help Lean by providing a focused import
        NEW_HEADER = "import Mathlib.Data.Real.Basic\nset_option maxHeartbeats 0\n"
        LoT_Module.Lean4_HEADER = NEW_HEADER
        Prover_Module.Lean4_HEADER = NEW_HEADER
        
        # Set workspace to Mathlib so it can find the Real definitions
        prover.lean.verifier.DEFAULT_LEAN_WORKSPACE = MATHLIB_PATH
        
        print("Initializing LoT_Prover...")
        scheduler = Lean4ServerScheduler(max_concurrent_requests=1, timeout=120, name='verifier')
        prover_inst = LoT_Prover("RickyDeSkywalker/LoT-Solver", scheduler=scheduler)
        
        Lean_statement = "theorem mathlib_comm (a b : ℝ) : a + b = b + a := by"
        NL_statement = "Prove that for any two real numbers a and b, a + b = b + a."
        
        print(f"Running inference for: {Lean_statement}")
        results = prover_inst.LoT_search_single_thm(
            Lean_statement=Lean_statement,
            NL_statement=NL_statement,
            max_tokens=2048,
            LongCoT_control=True,
            print_result=True
        )
        
        print("\n" + "="*30)
        if results:
            print(f"SUCCESS! Proof Found:\n{results['Proof']}")
        else:
            print("FAILED: Could not find valid proof. Lean environment might still be missing files.")
        print("="*30)
        
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        os.chdir("/content")

if __name__ == "__main__":
    run_test()
