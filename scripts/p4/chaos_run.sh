#!/usr/bin/env bash
# One chaos run under load: the consumer and producer run, a fault is injected with
# scripts/failure/run_scenario.sh, then the validator checks the result.
#
# Usage: ./scripts/p4/chaos_run.sh <follower-crash|leader-crash|partition|rolling-restart> [run_number=1]
# Env:   DURATION (producer seconds, default 60; 100 for rolling-restart)  RATE (msg/s/thread, default 100)
#        FAULT_AT (seconds after producer start, default 15)
# Output: results/chaos/<scenario>/run<k>/  (confirmed.csv, received.csv, logs, quorum status, validation.json/.txt)
set -uo pipefail
source "$(dirname "$0")/lib.sh"
require_docker; require_cluster

SCENARIO="${1:?usage: $0 <follower-crash|leader-crash|partition|rolling-restart> [run]}"
RUN="${2:-1}"
case "$SCENARIO" in rolling-restart) DEFAULT_DURATION=100 ;; *) DEFAULT_DURATION=60 ;; esac
DURATION="${DURATION:-$DEFAULT_DURATION}"; RATE="${RATE:-100}"; FAULT_AT="${FAULT_AT:-15}"
OUT="results/chaos/${SCENARIO}/run${RUN}"; rm -rf "$OUT"; mkdir -p "$OUT"

# Targeted failover (default on): every client first connects to the node the fault
# will hit, so each run really tests client failover. TARGET_FAILOVER=0 keeps the
# random host order.
TARGET_FAILOVER="${TARGET_FAILOVER:-1}"
if [[ "$TARGET_FAILOVER" == "1" && "$SCENARIO" != "rolling-restart" ]]; then
  LEADER="$(queue_leader rabbit1 | sed 's/rabbit@//')"
  case "$SCENARIO" in
    leader-crash)   VICTIM="$LEADER" ;;
    follower-crash) for n in "${NODES[@]}"; do [[ "$n" != "$LEADER" ]] && VICTIM="$n" && break; done ;;
    partition)      VICTIM="rabbit3" ;;
  esac
  VPORT=$(( $(api_port "$VICTIM") - 10000 ))
  HOSTS="localhost:${VPORT}"
  for p in 5672 5673 5674; do [[ "$p" != "$VPORT" ]] && HOSTS="${HOSTS},localhost:${p}"; done
  export RABBITMQ_HOSTS_SHUFFLE=0
  log "Targeted failover: all clients start on ${VICTIM} (hosts ${HOSTS})"
  echo "victim=${VICTIM} hosts=${HOSTS}" > "$OUT/target.txt"
fi

CPID=""; PPID_=""
cleanup() { [[ -n "$CPID" ]] && kill -TERM "$CPID" 2>/dev/null; [[ -n "$PPID_" ]] && kill -TERM "$PPID_" 2>/dev/null; true; }
trap cleanup EXIT

log "== ${SCENARIO} run ${RUN}: ${DURATION}s of load (4 producer threads x ${RATE}/s, 4 consumer threads) =="
purge_queue
$PY consumer/consumer.py --hosts "$HOSTS" --threads 4 --prefetch 100 --out "$OUT" > "$OUT/consumer.log" 2>&1 &
CPID=$!
sleep 3
$PY producer/producer.py --hosts "$HOSTS" --threads 4 --duration "$DURATION" --rate "$RATE" --size 1024 --out "$OUT" \
  > "$OUT/producer.log" 2>&1 &
PPID_=$!

sleep "$FAULT_AT"
quorum_status_text "$(alive_rabbit)" > "$OUT/quorum_status_before.txt" 2>&1 || true
log "Injecting fault: ${SCENARIO}"
bash ./scripts/failure/run_scenario.sh "$SCENARIO" > "$OUT/scenario.log" 2>&1
SCEN_RC=$?
[[ "$SCEN_RC" -ne 0 ]] && log "WARNING: fault script exited ${SCEN_RC} - see $OUT/scenario.log (was the fault really injected?)"
log "Fault script finished (exit ${SCEN_RC}); waiting for the producer to finish..."

wait "$PPID_"; PROD_RC=$?; PPID_=""
log "Producer exit ${PROD_RC}. Waiting for the consumer to drain the queue..."
DEPTH="$(wait_depth le 0 180)" || log "WARNING: queue not empty after 180 s (depth=${DEPTH})"
sleep 2
ctl list_queues name messages --silent > "$OUT/queue_depth_after.txt" || true
quorum_status_text "$(alive_rabbit)" > "$OUT/quorum_status_after.txt" 2>&1 || true

stop_consumer "$CPID"; CONS_RC=$?; CPID=""
log "Consumer exit ${CONS_RC} (0 = clean shutdown)"

log "Validating"
$PY consumer/validate.py --confirmed "$OUT/confirmed.csv" --received "$OUT/received.csv" --json "$OUT/validation.json" \
  | tee "$OUT/validation.txt"
RC=${PIPESTATUS[0]}
log "Evidence saved in $OUT"
exit "$RC"
