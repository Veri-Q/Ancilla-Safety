#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

COMMAND="all"
if [[ $# -gt 0 && "${1}" != -* ]]; then
  COMMAND="$1"
  shift
fi

case "$COMMAND" in
  all|table1|table2|figure3|table3|generate-tables)
    ;;
  *)
    echo "Usage: $0 [all|table1|table2|figure3|table3|generate-tables] [--output-dir DIR] [--timeout-s SEC] [--mem-gb GB]" >&2
    exit 2
    ;;
esac

echo "[run-all] Starting artifact stage: ${COMMAND}"
echo "[run-all] Tip: stages can be run independently as table1, table2, figure3, and table3."
echo "[run-all] Default staged/full timeout is 3600s per task, matching the paper budget; pass --timeout-s 420 for a fast run."
echo "[run-all] Default staged/full memory limit is 24GB per task; pass --mem-gb 32 for the paper memory budget."
python3 -m ae.run_suite "$COMMAND" "$@"
echo "[run-all] Stage completed: ${COMMAND}"
