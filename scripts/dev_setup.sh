#!/usr/bin/env bash
# Reproducible dev environment for hermes-minefield.
#
#   ./scripts/dev_setup.sh && source .venv/bin/activate
#
# Override the pinned dependency refs with MINEFIELD_REF / HERMES_REF.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MINEFIELD_REF="${MINEFIELD_REF:-12822f3ec6d8600df113e773d2e588f3659f0120}"
HERMES_REF="${HERMES_REF:-d350422b15863fc4c0b7962b122b625a0271516c}"
PYTHON="${PYTHON:-python3}"

if [ ! -d .venv ]; then
  "$PYTHON" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -q --upgrade pip

MF_DIR="_deps/model-serving-minefield"
if [ ! -d "$MF_DIR/.git" ]; then
  mkdir -p _deps
  git clone -q https://github.com/Blackwellboy/model-serving-minefield "$MF_DIR"
fi
git -C "$MF_DIR" fetch -q origin "$MINEFIELD_REF" 2>/dev/null || git -C "$MF_DIR" fetch -q origin
git -C "$MF_DIR" checkout -q "$MINEFIELD_REF"
python -m pip install -q -e "$MF_DIR"

# Hermes refuses wheel builds outside Nix (setup.py build guard), so
# `pip install git+...` fails. An editable install from a clone is the
# supported development route.
HERMES_DIR="_deps/hermes-agent"
if [ ! -d "$HERMES_DIR/.git" ]; then
  git clone -q --filter=blob:none https://github.com/NousResearch/hermes-agent "$HERMES_DIR"
fi
git -C "$HERMES_DIR" fetch -q origin "$HERMES_REF" 2>/dev/null || git -C "$HERMES_DIR" fetch -q origin
git -C "$HERMES_DIR" checkout -q "$HERMES_REF"
python -m pip install -q -e "$HERMES_DIR"
python -m pip install -q pytest pytest-cov PyYAML ruff
python -m pip install -q -e . --no-deps

echo "dev env ready: minefield@${MINEFIELD_REF:0:8} hermes@${HERMES_REF:0:8}"
echo "next: source .venv/bin/activate && pytest -q"
