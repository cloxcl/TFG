# MA-LoT Colab Glue

This project provides a simplified "glue" setup for running MA-LoT (Model-Collaboration Lean-based Long Chain-of-Thought) tests on Google Colab using `uv`.

## How to use on Google Colab

1. **Clone this repository (and submodules):**
   ```bash
   !git clone --recurse-submodules <your-repo-url>
   %cd <repo-name>
   ```

2. **Install `uv`:**
   ```bash
   !pip install uv
   ```

3. **Run the glue script:**
   You can run a test using `uv run`. `uv` will automatically handle all dependencies defined in `malot_glue.py`.

   - To run a basic arithmetic test ($2+2=4$):
     ```bash
     !uv run malot_glue.py test-arithmetic
     ```

## Files

- `pyproject.toml`: Project configuration and dependencies.
- `malot_glue.py`: The main glue script with `uv` inline metadata.
- `LeanOfThought-Official/`: Submodule containing the MA-LoT implementation.
- `tests/`: Directory containing basic Lean4 test theorems.

## Note on Lean4
MA-LoT requires a Lean4 environment. The glue script checks for it, but you may need to install it manually in Colab if it's not present:
```bash
!curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh -s -- -y
# Then add to path or restart session
```
