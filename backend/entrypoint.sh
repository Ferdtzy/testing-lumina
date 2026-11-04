#!/bin/sh
set -e

if [ "${RUN_WARMUP:-0}" = "1" ]; then
  echo "[entrypoint] Running model warmup..."
  python warmup.py
  echo "[entrypoint] Warmup completed."
fi

echo "[entrypoint] Executing: $@"
exec "$@"
