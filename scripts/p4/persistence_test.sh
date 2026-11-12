#!/usr/bin/env bash
# Persistence test: 50,000 persistent messages with NO consumer -> stop the WHOLE cluster ->
# start it again -> the same 50,000 must still be in the queue -> drain with the consumer -> validate.
# Usage: ./scripts/p4/persistence_test.sh [total=50000]
set -uo pipefail
source "$(dirname "$0")/lib.sh"
require_docker; require_cluster

TOTAL="${1:-50000}"; THREADS=4; PER_THREAD=$(( TOTAL / THREADS ))
OUT="results/persistence/$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p "$OUT"
TOTAL=$(( PER_THREAD * THREADS ))

log "1/6 Purging queue and publishing ${TOTAL} messages with no consumer running"
purge_queue
$PY producer/producer.py --hosts "$HOSTS" --threads $THREADS --count "$PER_THREAD" --size 256 --out "$OUT" \
  > "$OUT/producer.log" 2>&1 || { echo "producer failed, see $OUT/producer.log"; exit 1; }

BEFORE="$(wait_depth eq "$TOTAL" 60)" || { log "FAIL: depth before restart is ${BEFORE}, expected ${TOTAL}"; exit 1; }
log "2/6 Queue depth BEFORE restart: ${BEFORE}"
echo "$BEFORE" > "$OUT/depth_before.txt"

log "3/6 Stopping ALL nodes, then starting them again (full cluster restart)"
docker compose stop rabbit1 rabbit2 rabbit3 >/dev/null
docker compose start rabbit1 rabbit2 rabbit3 >/dev/null
wait_for "3 running nodes" 240 bash -c "[ \"\$(docker exec rabbit1 rabbitmqctl cluster_status --formatter json 2>/dev/null | $PY -c 'import sys,json;print(len(json.load(sys.stdin)[\"running_nodes\"]))' 2>/dev/null)\" = 3 ]" \
  || { log "FAIL: cluster did not come back"; exit 1; }

AFTER="$(wait_depth eq "$TOTAL" 180)"; AFTER_RC=$?
log "4/6 Queue depth AFTER restart: ${AFTER} (expected ${TOTAL})"
echo "$AFTER" > "$OUT/depth_after.txt"
quorum_status_text rabbit1 > "$OUT/quorum_status_after_restart.txt" 2>&1 || true

log "5/6 Draining with the consumer (manual acks)"
$PY consumer/consumer.py --hosts "$HOSTS" --threads 4 --prefetch 100 --stop-after "$TOTAL" --out "$OUT" \
  > "$OUT/consumer.log" 2>&1

log "6/6 Validating"
$PY consumer/validate.py --confirmed "$OUT/confirmed.csv" --received "$OUT/received.csv" --json "$OUT/validation.json" \
  | tee "$OUT/validation.txt"
VRC=${PIPESTATUS[0]}

if [[ "$AFTER_RC" -eq 0 && "$VRC" -eq 0 ]]; then
  log "PERSISTENCE TEST: PASS (depth ${BEFORE} -> ${AFTER}, lost = 0)"; exit 0
fi
log "PERSISTENCE TEST: FAIL (depth ${BEFORE} -> ${AFTER}, validator exit ${VRC})"; exit 1
