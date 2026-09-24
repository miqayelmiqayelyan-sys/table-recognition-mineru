#!/usr/bin/env bash
# Thin wrapper — same as: source .venv/bin/activate && python3 genie_local.py
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "${ROOT}"
source "${ROOT}/.venv/bin/activate"
export PYTHONPATH="${ROOT}/src"
export MINERU_MODEL_SOURCE="${MINERU_MODEL_SOURCE:-huggingface}"
python3 genie_local.py
