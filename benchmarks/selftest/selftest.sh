#!/usr/bin/env bash
# Tests run_bench.py + analyze.py end to end with FAKE clients (no RabbitMQ needed, ~1.5 min).
# Output goes to benchmarks/results/selftest/ (git-ignored). Never use these numbers in the report.
set -euo pipefail
cd "$(dirname "$0")/../.."
rm -rf benchmarks/results/selftest
python3 benchmarks/run_bench.py --config benchmarks/selftest/selftest.yaml \
  --raw-dir benchmarks/results/selftest/raw --no-broker
python3 benchmarks/analyze.py --raw benchmarks/results/selftest/raw --out benchmarks/results/selftest
echo "SELFTEST OK - runner and analysis work. (Synthetic data: do not report.)"
