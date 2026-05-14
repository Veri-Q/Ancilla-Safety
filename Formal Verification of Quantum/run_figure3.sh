#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "[figure3] Reproducing parameter-analysis figure"
echo "[figure3] Default timeout is 3600s per task, matching the paper budget; pass --timeout-s 420 for a fast run."
echo "[figure3] Default memory limit is 24GB per task; pass --mem-gb 32 for the paper memory budget."
python3 -m ae.run_suite figure3 "$@"
