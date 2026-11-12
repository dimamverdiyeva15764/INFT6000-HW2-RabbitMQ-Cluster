#!/usr/bin/env bash
# Quorum loss under load: stop TWO of the three nodes while the
# producer and consumer run, keep them down, then start them again and validate.
# Expected: no publish is confirmed while the majority is gone (CP behaviour), clients retry,
# the queue resumes when a second node returns, and lost = 0.
# Usage: ./scripts/qa/quorum_loss_run.sh [run=1]   Env: DOWN_FOR (s, default 20)
set -uo pipefail
source "$(dirname "$0")/../p4/lib.sh"
require_docker; require_cluster
RUN="${1:-1}"; DOWN_FOR="${DOWN_FOR:-20}"
OUT="results/chaos/quorum-loss/run${RUN}"; rm -rf "$OUT"; mkdir -p "$OUT"
CPID=""; PPID_=""
cleanup() { [[ -n "$CPID" ]] && kill -TERM "$CPID" 2>/dev/null; [[ -n "$PPID_" ]] && kill -TERM "$PPID_" 2>/dev/null; true; }
trap cleanup EXIT
log "== quorum-loss run ${RUN}: 60 s of load, two nodes down for ${DOWN_FOR} s ==" | tee "$OUT/scenario.log"
purge_queue
$PY consumer/consumer.py --hosts "$HOSTS" --threads 4 --prefetch 100 --out "$OUT" > "$OUT/consumer.log" 2>&1 & CPID=$!
sleep 3
$PY producer/producer.py --hosts "$HOSTS" --threads 4 --duration 60 --rate 100 --size 1024 --out "$OUT" > "$OUT/producer.log" 2>&1 & PPID_=$!
sleep 15
quorum_status_text rabbit1 >> "$OUT/scenario.log"
log "Injecting fault: docker kill rabbit2 rabbit3 (majority lost)" | tee -a "$OUT/scenario.log"
docker kill rabbit2 rabbit3 >/dev/null
sleep "$DOWN_FOR"
log "Depth seen while majority is down: $(queue_depth || echo unavailable)" | tee -a "$OUT/scenario.log"
log "Recovery: docker start rabbit2 rabbit3" | tee -a "$OUT/scenario.log"
docker start rabbit2 rabbit3 >/dev/null
three_running() { [[ "$(running_nodes rabbit1)" == "3" ]]; }   # a function: wait_for runs it in this shell
wait_for "3 running nodes" 180 three_running && log "Cluster is whole again." | tee -a "$OUT/scenario.log"
quorum_status_text rabbit1 >> "$OUT/scenario.log"
wait "$PPID_"; log "Producer exit $?" | tee -a "$OUT/scenario.log"; PPID_=""
wait_depth le 0 180 >/dev/null || log "WARNING: queue not empty after 180 s" | tee -a "$OUT/scenario.log"
sleep 2; stop_consumer "$CPID"; CPID=""
$PY consumer/validate.py --confirmed "$OUT/confirmed.csv" --received "$OUT/received.csv" --json "$OUT/validation.json" | tee "$OUT/validation.txt"
exit "${PIPESTATUS[0]}"
