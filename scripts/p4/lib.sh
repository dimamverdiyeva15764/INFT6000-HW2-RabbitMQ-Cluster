#!/usr/bin/env bash
# Helpers shared by the scripts in scripts/p4/. Source, do not run.
# shellcheck source=scripts/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/../common.sh"

# common.sh turns on `set -e`; these scripts handle exit codes themselves.
set +e

PY="${PYTHON:-python3}"
HOSTS="${HOSTS:-localhost:5672,localhost:5673,localhost:5674}"

# Run a rabbitmqctl command on the first node that answers (a killed node is skipped).
ctl() {
  local n
  for n in "${NODES[@]}"; do
    if [[ "$(docker inspect -f '{{.State.Running}}' "$n" 2>/dev/null)" == "true" ]]; then
      if docker exec "$n" rabbitmqctl "$@" 2>/dev/null; then return 0; fi
    fi
  done
  return 1
}

# First RabbitMQ container that is running (for status snapshots during a fault).
alive_rabbit() {
  local n
  for n in "${NODES[@]}"; do
    [[ "$(docker inspect -f '{{.State.Running}}' "$n" 2>/dev/null)" == "true" ]] && { echo "$n"; return 0; }
  done
  echo rabbit1
}

# Number of messages in the queue (ready + unacked); empty if no node answers.
queue_depth() {
  ctl list_queues name messages --silent | awk -F'\t' -v q="$QUEUE_NAME" '$1==q {print $2}' | head -1
}

purge_queue() { ctl purge_queue "$QUEUE_NAME" >/dev/null; }

# Wait until queue_depth satisfies a test: wait_depth <eq|le> <N> <timeout_s>
# NOTE: right after a full restart the depth reads 0 for a few seconds while the
# quorum queue replays its Raft log, so we poll instead of reading once.
wait_depth() {
  local op="$1" want="$2" timeout="$3" start=$SECONDS d
  while (( SECONDS - start < timeout )); do
    d="$(queue_depth)"
    if [[ -n "$d" ]]; then
      if [[ "$op" == eq && "$d" -eq "$want" ]] || [[ "$op" == le && "$d" -le "$want" ]]; then
        echo "$d"; return 0
      fi
    fi
    sleep 1
  done
  echo "${d:-unknown}"; return 1
}

# Stop a background consumer with SIGTERM and wait for its clean exit (<= 30 s).
stop_consumer() {
  local pid="$1"
  kill -TERM "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null
}

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
