#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "[kick-the-tires] Preparing smoke-test run"
python3 -m ae.run_suite smoke "$@"
echo "[kick-the-tires] Completed successfully"
