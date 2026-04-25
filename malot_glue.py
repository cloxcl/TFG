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
def find_submodule():
    # Look for it recursively in case of nested folders in Colab
    for root, dirs, files in os.walk(os.getcwd()):
        if "LeanOfThought-Official" in dirs:
            return os.path.join(root, "LeanOfThought-Official")
    return os.path.join(os.getcwd(), "LeanOfThought-Official")

SUBMODULE_PATH = find_submodule()
MATHLIB_PATH = os.path.join(SUBMODULE_PATH, "mathlib4")
ORIGINAL_CWD = os.getcwd()

print(f"Submodule path: {SUBMODULE_PATH}")
if os.path.exists(SUBMODULE_PATH):
    sys.path.append(SUBMODULE_PATH)
else:
    print(f"Warning: {SUBMODULE_PATH} not found.")

def patch_submodule():
    """Fixes a critical bug in the submodule's theorem preprocessing."""
    prover_py = os.path.join(SUBMODULE_PATH, "Prover.py")
    if os.path.exists(prover_py):
        print("Patching Prover.py to fix theorem stripping bug...")
        with open(prover_py, 'r') as f:
            content = f.read()
        
        # The original code has a loop that strips the entire string if it doesn't end with ':='
        old_code = """    def _preprocess_theorem_statement(self,
                                      input_statement: str):
        while not input_statement.endswith(":="):
            input_statement = input_statement[:-1]

        if input_statement.endswith(":="):
            input_statement = input_statement[:-len(":=")]
        input_statement += ":= by"
        return input_statement"""
        
        new_code = """    def _preprocess_theorem_statement(self,
                                      input_statement: str):
        if ":=" in input_statement:
            input_statement = input_statement[:input_statement.rfind(":=")]
        input_statement = input_statement.strip()
        if not input_statement.endswith(":="):
            input_statement += " := by"
        else:
            input_statement += " by"
        return input_statement"""
        
        if old_code in content:
            new_content = content.replace(old_code, new_code)
            with open(prover_py, 'w') as f:
                f.write(new_content)
            print("Successfully patched Prover.py")
        else:
            print("Prover.py already patched or code not found.")

def setup_mathlib():
    """Restores and synchronizes Mathlib environment with forced cache."""
    print("Setting up Mathlib environment...")
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
        with open(toolchain_file, 'r') as f:
            toolchain = f.read().strip()
        print(f"Using toolchain: {toolchain}")
        
        # Force a refresh of the lake manifest
        print("Refreshing lake manifest...")
        subprocess.run(["elan", "run", toolchain, "lake", "update"], cwd=MATHLIB_PATH, check=False)
        
        # Use the '!' flag to force cache get even if it thinks it's diverged
        print("Forcing Mathlib cache download...")
        subprocess.run(["elan", "run", toolchain, "lake", "exe", "cache", "get!"], cwd=MATHLIB_PATH, check=False)
        
        print("Building Mathlib REPL...")
        subprocess.run(["elan", "run", toolchain, "lake", "build", "repl"], cwd=MATHLIB_PATH, check=True)
        
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
        print(f"Mathlib setup warning: {e}")
        return True # Try to proceed anyway

def run_test():
    """Verifies setup with a simple commutative theorem."""
    patch_submodule()
    if not setup_mathlib(): return

    try:
        os.chdir(SUBMODULE_PATH)
        from LoT_Prover import LoT_Prover
        from prover.lean.verifier import Lean4ServerScheduler
        import prover.lean.verifier
        import LoT_Prover as LoT_Module
        import Prover as Prover_Module
        
        # AGGRESSIVE PATCHING: Use a more specific header to help Lean find things faster
        NEW_HEADER = "import Mathlib.Data.Real.Basic\nset_option maxHeartbeats 0\n"
        LoT_Module.Lean4_HEADER = NEW_HEADER
        Prover_Module.Lean4_HEADER = NEW_HEADER
        
        prover.lean.verifier.DEFAULT_LEAN_WORKSPACE = MATHLIB_PATH
        
        print("Initializing LoT_Prover...")
        scheduler = Lean4ServerScheduler(max_concurrent_requests=1, timeout=120, name='verifier')
        prover_inst = LoT_Prover("RickyDeSkywalker/LoT-Solver", scheduler=scheduler)
        
        # Use a more explicit statement to avoid truncation
        Lean_statement = "theorem mathlib_comm (a b : ℝ) : a + b = b + a := by"
        NL_statement = "Prove that for any two real numbers a and b, a + b = b + a."
        
        print(f"Running inference for: {Lean_statement}")
        results = prover_inst.LoT_search_single_thm(
            Lean_statement=Lean_statement,
            NL_statement=NL_statement,
            max_tokens=2048, # Increased tokens to avoid truncation
            LongCoT_control=True,
            print_result=True
        )
        
        print("\n" + "="*30)
        if results:
            print(f"SUCCESS! Proof Found:\n{results['Proof']}")
        else:
            print("FAILED: No proof found. Usually missing oleans.")
        print("="*30)
        
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        os.chdir(ORIGINAL_CWD)

if __name__ == "__main__":
    run_test()
