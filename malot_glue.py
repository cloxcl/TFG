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
    return os.path.join(os.getcwd(), name)

SUBMODULE_PATH = find_path("LeanOfThought-Official")
MATHLIB_PATH = os.path.join(SUBMODULE_PATH, "mathlib4") if SUBMODULE_PATH else None
ORIGINAL_CWD = os.getcwd()

# Ensure submodule is in path immediately
if SUBMODULE_PATH and os.path.exists(SUBMODULE_PATH):
    if SUBMODULE_PATH not in sys.path:
        sys.path.insert(0, SUBMODULE_PATH)
        print(f"Successfully added {SUBMODULE_PATH} to sys.path")

def setup_mathlib():
    """Restores and synchronizes Mathlib environment with forced manifest fix."""
    print(f"Setting up Mathlib at: {MATHLIB_PATH}")
    
    elan_bin = os.path.expanduser("~/.elan/bin")
    if elan_bin not in os.environ["PATH"]:
        os.environ["PATH"] = elan_bin + os.pathsep + os.environ["PATH"]
    
    if not shutil.which("lake"):
        subprocess.run("curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh -s -- -y", shell=True, check=True)

    try:
        with open(os.path.join(MATHLIB_PATH, "lean-toolchain"), 'r') as f:
            toolchain = f.read().strip()
        
        print(f"Using toolchain: {toolchain}")
        subprocess.run(["elan", "override", "set", toolchain], cwd=MATHLIB_PATH, check=True)
        
        # MANIFEST RESCUE: If manifest is broken, regenerate it
        print("Cleaning and refreshing manifest...")
        manifest_file = os.path.join(MATHLIB_PATH, "lake-manifest.json")
        if os.path.exists(manifest_file):
            os.remove(manifest_file)
        
        # This will recreate the manifest based on the current submodule state
        subprocess.run(["lake", "update"], cwd=MATHLIB_PATH, check=False)
        
        print("Fetching Mathlib cache binaries...")
        subprocess.run(["lake", "exe", "cache", "get"], cwd=MATHLIB_PATH, check=False)
        
        print("Building REPL bridge...")
        subprocess.run(["lake", "build", "repl"], cwd=MATHLIB_PATH, check=True)
        
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
        return True

def patch_submodule():
    """Fixes a critical bug in the submodule's theorem preprocessing."""
    prover_py = os.path.join(SUBMODULE_PATH, "Prover.py")
    if os.path.exists(prover_py):
        with open(prover_py, 'r') as f:
            content = f.read()
        
        old_code = "while not input_statement.endswith(\":=\"):"
        if old_code in content:
            print("Patching Prover.py...")
            new_code = "if \":=\" in input_statement: input_statement = input_statement[:input_statement.rfind(\":=\")];\n        while False:"
            content = content.replace(old_code, new_code)
            with open(prover_py, 'w') as f:
                f.write(content)

def run_test():
    """Runs the commutative test with Mathlib re-enabled."""
    patch_submodule()
    if not setup_mathlib(): return

    # Re-insert path just before imports to be absolutely sure
    if SUBMODULE_PATH not in sys.path:
        sys.path.insert(0, SUBMODULE_PATH)

    try:
        os.chdir(SUBMODULE_PATH)
        
        # Verify file exists
        if not os.path.exists("LoT_Prover.py"):
            print(f"CRITICAL ERROR: LoT_Prover.py not found in {os.getcwd()}")
            print(f"Files here: {os.listdir('.')}")
            return

        from LoT_Prover import LoT_Prover
        from prover.lean.verifier import Lean4ServerScheduler
        import prover.lean.verifier
        
        # Explicit headers for Real numbers
        HEADER = "import Mathlib.Data.Real.Basic\nset_option maxHeartbeats 0\n"
        import LoT_Prover as LoT_Module
        import Prover as Prover_Module
        LoT_Module.Lean4_HEADER = HEADER
        Prover_Module.Prove_writer.Lean4_HEADER = HEADER
        
        prover.lean.verifier.DEFAULT_LEAN_WORKSPACE = MATHLIB_PATH
        
        print("Initializing LoT_Prover...")
        scheduler = Lean4ServerScheduler(max_concurrent_requests=1, timeout=180, name='verifier')
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
            print("FAILED: No proof found.")
        print("="*30)
        
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        os.chdir("/content")

if __name__ == "__main__":
    run_test()
