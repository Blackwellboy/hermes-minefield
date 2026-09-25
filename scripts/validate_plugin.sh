#!/usr/bin/env bash
# Run `hermes plugins validate` on exactly the files git tracks (plus new,
# non-ignored files), copied to a scratch dir. The validator's security scan
# walks the whole directory, so validating the checkout in place would also
# scan .venv/ and _deps/ — and would not match what the catalog installs.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
DEST="$TMP/hermes-minefield"
mkdir -p "$DEST"
( cd "$ROOT" && git ls-files -co --exclude-standard -z | xargs -0 -I{} cp --parents {} "$DEST/" )
hermes plugins validate "$DEST" "$@"
