#!/usr/bin/env bash
# P4 smoke test (no faults): publish N messages, consume them all, validate.
# Usage: ./scripts/p4/smoke.sh [messages_per_thread=2500]
set -uo pipefail
source "$(dirname "$0")/lib.sh"
require_docker; require_cluster

PER_THREAD="${1:-2500}"; THREADS=4
OUT="results/smoke/$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p "$OUT"

log "Purging queue ${QUEUE_NAME}"; purge_queue
log "Publishing $((PER_THREAD * THREADS)) messages (publisher confirms on) -> $OUT"
$PY producer/producer.py --hosts "$HOSTS" --threads $THREADS --count "$PER_THREAD" --size 1024 --out "$OUT" \
  > "$OUT/producer.log" 2>&1 || { echo "producer failed, see $OUT/producer.log"; exit 1; }
log "Consuming (manual acks, 4 threads, prefetch 100) until idle..."
$PY consumer/consumer.py --hosts "$HOSTS" --threads 4 --prefetch 100 --idle-exit 5 --out "$OUT" \
  > "$OUT/consumer.log" 2>&1 || { echo "consumer failed, see $OUT/consumer.log"; exit 1; }
log "Validating"
$PY consumer/validate.py --confirmed "$OUT/confirmed.csv" --received "$OUT/received.csv" --json "$OUT/validation.json" \
  | tee "$OUT/validation.txt"
exit "${PIPESTATUS[0]}"
