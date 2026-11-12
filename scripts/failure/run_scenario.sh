#!/usr/bin/env bash
# Failure-injection scenarios for the 3-node RabbitMQ quorum cluster.
# Each scenario logs timestamps, the Raft leader before and after, and the
# election time. scripts/p4/chaos_run.sh runs the same faults under load.
#
# Usage:
#   ./run_scenario.sh follower-crash
#   ./run_scenario.sh leader-crash
#   ./run_scenario.sh partition
#   ./run_scenario.sh rolling-restart
#   ./run_scenario.sh all
set -euo pipefail
cd "$(dirname "$0")/../.."
# shellcheck source=scripts/common.sh
source scripts/common.sh
set -a; [[ -f .env ]] && source .env; set +a

require_docker
require_cluster

RESULTS_DIR="results"
mkdir -p "$RESULTS_DIR"
REPORT="${RESULTS_DIR}/failure_$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee -a "$REPORT") 2>&1

# Return any node that is currently up and answering the API.
alive_node() {
  for n in "$@"; do
    if [[ "$(docker inspect -f '{{.State.Running}}' "$n" 2>/dev/null)" == "true" ]] \
       && [[ -n "$(api "$n" overview 2>/dev/null | head -c1)" ]]; then
      echo "$n"; return 0
    fi
  done
  return 1
}

# Wait until a leader different from $1 is reported by a surviving node.
measure_election() {
  local old_leader="$1" via="$2" start_ms now_ms new
  start_ms=$(now_ms)
  while true; do
    new=$(queue_leader "$via")
    if [[ -n "$new" && "$new" != "$old_leader" ]]; then
      now_ms=$(now_ms)
      log "New leader: ${new}  (election took $((now_ms - start_ms)) ms)"
      return 0
    fi
    if (( $(now_ms) - start_ms > 60000 )); then
      log "FAIL: no new leader within 60 s"; return 1
    fi
    sleep 0.2
  done
}

wait_cluster_full() {
  log "Waiting for the cluster to return to 3 running nodes..."
  wait_for "3 running nodes" 180 bash -c \
    "[ \"\$(docker exec rabbit1 rabbitmqctl cluster_status --formatter json 2>/dev/null | python3 -c 'import sys,json;print(len(json.load(sys.stdin)[\"running_nodes\"]))' 2>/dev/null)\" = 3 ]"
  log "Cluster is whole again."
}

show_quorum() { quorum_status_text "$1" || true; }

# ---------------------------------------------------------------- scenarios
follower_crash() {
  log "=== S1: crash a FOLLOWER node ==="
  local leader follower via
  leader=$(queue_leader rabbit1 | sed 's/rabbit@//')
  for n in "${NODES[@]}"; do [[ "$n" != "$leader" ]] && follower="$n" && break; done
  via="$leader"
  log "Leader=rabbit@${leader}  victim(follower)=${follower}"
  log "Injecting fault: docker kill ${follower}"
  docker kill "$follower" >/dev/null
  sleep 5
  log "Leader after crash: $(queue_leader "$via")  (expected: unchanged, writes continue with 2/3 majority)"
  show_quorum "$via"
  log "Recovery: docker start ${follower}"
  docker start "$follower" >/dev/null
  wait_cluster_full
  show_quorum "$via"
}

leader_crash() {
  log "=== S2: crash the LEADER node ==="
  local leader via
  leader=$(queue_leader rabbit1 | sed 's/rabbit@//')
  for n in "${NODES[@]}"; do [[ "$n" != "$leader" ]] && via="$n" && break; done
  log "Current leader: rabbit@${leader}"
  log "Injecting fault: docker kill ${leader}"
  docker kill "$leader" >/dev/null
  measure_election "rabbit@${leader}" "$via"
  show_quorum "$via"
  log "Recovery: docker start ${leader} (rejoins as follower, replays Raft log)"
  docker start "$leader" >/dev/null
  wait_cluster_full
  show_quorum "$via"
}

network_partition() {
  log "=== S3: network partition - isolate ONE node (minority side) ==="
  local victim="rabbit3" via leader_before
  via="rabbit1"
  leader_before=$(queue_leader "$via")
  log "Leader before partition: ${leader_before}"
  log "Injecting fault: docker network disconnect amqp-net ${victim}"
  docker network disconnect amqp-net "$victim"
  sleep 15
  # Majority side (rabbit1+rabbit2) must keep serving; victim pauses (pause_minority).
  log "Leader seen from majority side: $(queue_leader "$via")"
  log "Nodes running (majority view): $(running_nodes "$via") (expected 2)"
  if [[ "$(queue_leader "$via")" == "rabbit@${victim}" ]]; then
    measure_election "rabbit@${victim}" "$via" || true
  fi
  show_quorum "$via"
  log "Healing partition: docker network connect amqp-net ${victim}"
  docker network connect amqp-net "$victim"
  wait_cluster_full
  show_quorum "$via"
}

rolling_restart() {
  log "=== S4: rolling restart of all nodes (one at a time) ==="
  for n in "${NODES[@]}"; do
    local via
    via=$(alive_node $(printf '%s\n' "${NODES[@]}" | grep -v "^${n}$"))
    log "Restarting ${n} (observer: ${via})"
    docker restart "$n" >/dev/null
    wait_cluster_full
    log "Leader after restart of ${n}: $(queue_leader "$via")"
  done
  show_quorum rabbit1
}

case "${1:-}" in
  follower-crash)  follower_crash ;;
  leader-crash)    leader_crash ;;
  partition)       network_partition ;;
  rolling-restart) rolling_restart ;;
  all) follower_crash; leader_crash; network_partition; rolling_restart ;;
  *) echo "Usage: $0 {follower-crash|leader-crash|partition|rolling-restart|all}"; exit 1 ;;
esac
log "Scenario finished. Log: ${REPORT}"
