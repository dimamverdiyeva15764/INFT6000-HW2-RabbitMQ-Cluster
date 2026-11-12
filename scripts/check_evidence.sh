#!/usr/bin/env bash
# Verify that every screenshot referenced by docs/failure-test-plan.md exists.
set -euo pipefail
cd "$(dirname "$0")/.."
missing=0
for f in $(grep -o 'evidence/[^)]*\.png' docs/failure-test-plan.md | sort -u); do
  if [[ -f "docs/$f" ]]; then echo "OK       docs/$f"; else echo "MISSING  docs/$f"; missing=1; fi
done
if (( missing )); then echo "Some screenshots are missing."; exit 1; fi
echo "All screenshots present."
