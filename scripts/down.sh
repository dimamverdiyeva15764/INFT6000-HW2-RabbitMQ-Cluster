#!/usr/bin/env bash
# Stop the stack. Pass --purge to also delete volumes (all queue data!).
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "${1:-}" == "--purge" ]]; then
  docker compose down -v
else
  docker compose down
fi
