#!/usr/bin/env bash
set -e

echo "[*] Setting up ORACLE GRC Dashboard Development Environment"

# 1. Install uv if missing
if ! command -v uv &> /dev/null; then
    echo "[-] uv package manager not found. Installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# 2. Create virtual environment and sync dependencies
echo "[*] Creating virtual environment and installing dependencies..."
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev,test]"

# 3. Setup Pre-commit hooks
if command -v pre-commit &> /dev/null; then
    echo "[*] Installing pre-commit hooks..."
    pre-commit install
fi

# 4. Run type checks and linters
echo "[*] Running static analysis..."
mypy --strict src/
ruff check src/

echo "[+] Setup complete. Run 'source .venv/bin/activate' to enter the environment."
