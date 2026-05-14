#!/usr/bin/env bash
set -euo pipefail

cd /workspace

if [ "$#" -eq 0 ]; then
    exec /bin/bash
fi

exec "$@"
