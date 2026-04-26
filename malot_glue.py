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
import torch
import time
import re

# FORCE vLLM to use CUDA
os.environ["VLLM_TARGET_DEVICE"] = "cuda"

def find_submodule():
    """Finds the LeanOfThought-Official directory anywhere in /content."""
    for root, dirs, files in os.walk('/content'):
        if "LeanOfThought-Official" in dirs and ".git" not in root:
            return os.path.join(root, "LeanOfThought-Official")
    return os.path.join(os.getcwd(), "LeanOfThought-Official")

SUBMODULE_PATH = find_submodule()
MATHLIB_PATH = os.path.join(SUBMODULE_PATH, "mathlib4")
ORIGINAL_CWD = os.getcwd()

print(f"--- HARDWARE CHECK ---")
cuda_available = torch.cuda.is_available()
print(f"CUDA Available: {cuda_available}")
if cuda_available:
    print(f"GPU Name: {torch.cuda.get_device_name(0)}")
else:
    print("!!! ERROR: NO GPU DETECTED !!!")
    print("Go to Runtime > Change runtime type and select 'T4 GPU'.")

print(f"\n--- PATH CHECK ---")
print(f"Submodule: {SUBMODULE_PATH}")
print(f"Mathlib: {MATHLIB_PATH}")

# Force path addition
if SUBMODULE_PATH and os.path.exists(SUBMODULE_PATH):
    if SUBMODULE_PATH not in sys.path:
        sys.path.insert(0, SUBMODULE_PATH)

def extract_from_lean_file(file_path):
    """Extracts theorem statement and NL description from a .lean file."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
        
    with open(file_path, 'r') as f:
        content = f.read()

    # 1. Try to find the NL description in a docstring /-- ... -/
    nl_match = re.search(r'/--\s*(.*?)\s*-/', content, re.DOTALL)
    nl_statement = nl_match.group(1).strip() if nl_match else f"Prove the theorem defined in {os.path.basename(file_path)}"

    # 2. Extract the theorem statement (from 'theorem' up to ':=')
    matches = list(re.finditer(r'(theorem|lemma)\s+[\s\S]*?:=', content))
    if matches:
        fl_statement = matches[-1].group(0).strip()
        # Ensure it ends with 'by' for the prover to complete it
        if not fl_statement.endswith("by"):
            fl_statement += " by"
    else:
        # Fallback logic
        fl_statement = content.strip()
        if ":=" in fl_statement and not fl_statement.endswith("by"):
            fl_statement = fl_statement.split(":=")[0] + ":= by"

    return fl_statement, nl_statement

def repair_mathlib():
    # ... rest of the function (lines 53-102) ...
    """Resets mathlib to a clean state and builds the REPL."""
    print("\n--- REPAIRING MATHLIB ---")
    
    elan_bin = os.path.expanduser("~/.elan/bin")
    os.environ["PATH"] = elan_bin + os.pathsep + os.environ["PATH"]
    os.environ["ELAN_HOME"] = os.path.expanduser("~/.elan")
    
    if not shutil.which("lake"):
        print("Installing elan...")
        subprocess.run("curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh -s -- -y", shell=True, check=True)

    try:
        # 1. Reset manifest
        print("Restoring original manifest...")
        subprocess.run(["git", "checkout", "lake-manifest.json"], cwd=MATHLIB_PATH, check=False)
        
        # 2. Setup Toolchain
        toolchain_file = os.path.join(MATHLIB_PATH, "lean-toolchain")
        if os.path.exists(toolchain_file):
            with open(toolchain_file, 'r') as f:
                toolchain = f.read().strip()
            print(f"Forcing toolchain: {toolchain}")
            subprocess.run(["elan", "override", "set", toolchain], cwd=MATHLIB_PATH, check=True)

        # 3. Get binaries (even if partial)
        print("Fetching binaries (cache get)...")
        try:
            subprocess.run("yes | lake exe cache get", shell=True, cwd=MATHLIB_PATH, check=False, timeout=600)
        except subprocess.TimeoutExpired:
            print("Cache fetch timed out, proceeding anyway...")
        
        # 4. Build REPL
        print("Building REPL bridge...")
        subprocess.run("yes | lake build REPL", shell=True, cwd=MATHLIB_PATH, check=False, timeout=300)
        
        # 5. Symlink for verifier
        lake_path = subprocess.run(["elan", "which", "lake"], capture_output=True, text=True).stdout.strip()
        target = os.path.expanduser("~/.elan/bin/lake")
        if lake_path and lake_path != target:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if os.path.exists(target): os.remove(target)
            try:
                os.symlink(lake_path, target)
            except OSError:
                print("Failed to create lake symlink")
            
        return True
    except Exception as e:
        print(f"Mathlib setup warning: {e}")
        return True

def patch_submodule():
    """Applies critical fixes to the research code."""
    print("\n--- PATCHING SUBMODULE ---")
    
    # 1. Prover.py fixes
    prover_py = os.path.join(SUBMODULE_PATH, "Prover.py")
    if os.path.exists(prover_py):
        with open(prover_py, 'r') as f:
            content = f.read()
        
        # Fix aggressive stripping bug
        content = content.replace(
            "while not input_statement.endswith(\":=\"):",
            "if \":=\" in input_statement: input_statement = input_statement[:input_statement.rfind(\":=\")];\n        while False:"
        )
        
        # Add newline after 'by' for better model guidance
        content = content.replace(
            "input_statement += \":= by\"",
            "input_statement += \":= by\\n\""
        )
        
        # Fix extraction logic to return FIRST block (your proof) instead of LAST (hallucinations)
        # And handle same-line backticks
        old_extract_end = 'return code_blocks[-1]'
        new_extract_end = 'return code_blocks[0]'
        content = content.replace(old_extract_end, new_extract_end)
        
        old_extract_mid = 'elif "```" in line.strip() and inside_code_block:'
        new_extract_mid = 'elif "```" in line and inside_code_block:\n                if line.strip() != "```": current_block.append(line.split("```")[0])'
        content = content.replace(old_extract_mid, new_extract_mid)
        
        # Add stop string to prevent hallucinations in stage 2
        content = content.replace(
            "postCoT_sampling_para = SamplingParams(",
            "postCoT_sampling_para = SamplingParams(\n            stop=[\"```\"],"
        )
        
        with open(prover_py, 'w') as f:
            f.write(content)
        print("Patched Prover.py")

    # 2. LoT_Prover.py fixes
    lot_prover_py = os.path.join(SUBMODULE_PATH, "LoT_Prover.py")
    if os.path.exists(lot_prover_py):
        with open(lot_prover_py, 'r') as f:
            content = f.read()
        
        # Fix model ID check
        content = content.replace(
            "if \"lot-solver\" in self.model_id.lower():",
            "if \"lot-solver\" in self.model_id.lower() or \"prover-v1.5\" in self.model_id.lower():"
        )
        
        # Fix indexing bug when filtering proofs
        content = content.replace(
            "eval_results = self.run_lean_verification(thm_prove_ls)",
            "eval_results = self.run_lean_verification(processed_thm_prove_ls)"
        )
        
        with open(lot_prover_py, 'w') as f:
            f.write(content)
        print("Patched LoT_Prover.py")

def run_test(Lean_statement, NL_statement):
    """Runs the proof pipeline."""
    if not torch.cuda.is_available():
        print("Aborting: GPU required for vLLM.")
        return

    repair_mathlib()
    patch_submodule()

    try:
        os.chdir(SUBMODULE_PATH)
        
        print("Loading LoT modules...")
        from LoT_Prover import LoT_Prover
        from prover.lean.verifier import Lean4ServerScheduler
        import prover.lean.verifier
        
        # Set workspace
        prover.lean.verifier.DEFAULT_LEAN_WORKSPACE = MATHLIB_PATH
        
        # Header override
        HEADER = "import Mathlib\nset_option maxHeartbeats 0\n"
        
        import LoT_Prover as LoT_Module
        import Prover as Prover_Module
        import Corrector as Corrector_Module
        
        LoT_Module.Lean4_HEADER = HEADER
        Prover_Module.Lean4_HEADER = HEADER
        Corrector_Module.Lean4_HEADER = HEADER
        
        print("\n--- STARTING INFERENCE ---")
        print(f"Theorem: {Lean_statement}")
        
        scheduler = Lean4ServerScheduler(max_concurrent_requests=1, timeout=300, name='verifier')
        prover_inst = LoT_Prover("deepseek-ai/DeepSeek-Prover-V1.5-RL", scheduler=scheduler)
        
        results = prover_inst.LoT_search_single_thm(
            Lean_statement=Lean_statement,
            NL_statement=NL_statement,
            max_tokens=2048,
            LongCoT_control=True,
            print_result=True
        )
        
        print("\n" + "="*40)
        if results:
            print(f"SUCCESS!\nProof:\n{results['Proof']}")
        else:
            print("FAILED: Could not find valid proof.")
        print("="*40)
        
    except Exception as e:
        print(f"\n!!! EXECUTION FAILED !!!")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        os.chdir(ORIGINAL_CWD)

if __name__ == "__main__":
    import sys
    arg = sys.argv[1] if len(sys.argv) > 1 else "default"
    
    if arg.endswith(".lean") or os.path.exists(arg):
        print(f"Reading from file: {arg}")
        try:
            Lean_statement, NL_statement = extract_from_lean_file(arg)
        except Exception as e:
            print(f"Error reading file: {e}")
            sys.exit(1)
    elif arg in ["test-arithmetic", "test_arithmetic"]:
        Lean_statement = "theorem arithmetic_test : 2 + 2 = 4 := by"
        NL_statement = "Prove that 2 + 2 = 4."
    else:
        # Default behavior: mathlib comm test
        Lean_statement = "theorem mathlib_comm (a b : ℝ) : a + b = b + a := by"
        NL_statement = "Prove that for any two real numbers a and b, a + b = b + a."
        
    try:
        run_test(Lean_statement, NL_statement)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as e:
        print(f"Fatal error: {e}")
