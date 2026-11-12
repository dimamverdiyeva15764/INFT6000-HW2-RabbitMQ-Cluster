#!/usr/bin/env bash
# Shared helpers for the provisioning and failure-test scripts.
set -euo pipefail

RABBITMQ_USER="${RABBITMQ_USER:-admin}"
RABBITMQ_PASS="${RABBITMQ_PASS:-admin123}"
QUEUE_NAME="${QUEUE_NAME:-hw2.orders}"
NODES=(rabbit1 rabbit2 rabbit3)
# Management API host port of each node (a function, because bash 3.2 has no
# associative arrays).
api_port() {
  case "$1" in
    rabbit1) echo 15672 ;; rabbit2) echo 15673 ;; rabbit3) echo 15674 ;;
    *) echo "unknown node: $1" >&2; return 1 ;;
  esac
}

# Portable clock: macOS/BSD "date" has no %N (milliseconds), so use python3.
now_ms() { python3 -c 'import time; print(int(time.time() * 1000))'; }
log() { echo "[$(python3 -c 'import datetime as d; print(d.datetime.now(d.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"))')] $*"; }

# Raft status of the queue as plain text (the default table output contains
# line-drawing escape codes that break log files).
quorum_status_text() {
  local via="$1" q="${2:-$QUEUE_NAME}"
  docker exec "$via" rabbitmq-queues quorum_status "$q" --formatter json -q 2>/dev/null | python3 -c '
import sys, json
cols = ["Node Name", "Raft State", "Membership", "Last Log Index", "Commit Index", "Term"]
try:
    rows = json.load(sys.stdin)
except ValueError:
    sys.exit("(quorum status unavailable - is a majority of nodes up?)")
print("  ".join("%-18s" % c for c in cols))
for r in rows:
    print("  ".join("%-18s" % r.get(c, "") for c in cols))'
}

# Fail fast with a clear message if Docker is missing or not usable.
require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: 'docker' is not installed. See README.md, Requirements (install Docker first)." >&2
    exit 1
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "ERROR: cannot talk to the Docker daemon. Is it running? Is your user in the 'docker' group?" >&2
    echo "       Try: sudo systemctl start docker ; sudo usermod -aG docker \$USER ; then log out/in." >&2
    exit 1
  fi
  if ! docker compose version >/dev/null 2>&1; then
    echo "ERROR: 'docker compose' (v2 plugin) is missing. Install docker-compose-plugin." >&2
    exit 1
  fi
}

# Fail fast if the cluster is not running (used by the failure scenarios).
require_cluster() {
  for n in "${NODES[@]}"; do
    if [[ "$(docker inspect -f '{{.State.Running}}' "$n" 2>/dev/null)" != "true" ]]; then
      echo "ERROR: container '$n' is not running. Start the cluster first: ./scripts/up.sh" >&2
      exit 1
    fi
  done
  if [[ -z "$(queue_leader rabbit1)" ]]; then
    echo "ERROR: queue '${QUEUE_NAME}' has no leader / does not exist. Run ./scripts/up.sh first." >&2
    exit 1
  fi
}

# Call the management HTTP API of a given node.
api() {
  local node="$1" path="$2"; shift 2
  curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" "$@" \
    "http://localhost:$(api_port "$node")/api/${path}"
}

# Print the current Raft leader node of the quorum queue (empty if none).
queue_leader() {
  local via="${1:-rabbit1}"
  api "$via" "queues/%2F/${QUEUE_NAME}" \
    | python3 -c 'import sys,json
try:
    print(json.load(sys.stdin).get("leader",""))
except Exception:
    print("")'
}

# Print the number of running nodes as seen by a given node.
running_nodes() {
  local via="${1:-rabbit1}"
  docker exec "$via" rabbitmqctl cluster_status --formatter json 2>/dev/null \
    | python3 -c 'import sys,json
try:
    print(len(json.load(sys.stdin).get("running_nodes",[])))
except Exception:
    print(0)'
}

# Wait (up to N seconds) until a command prints the expected value.
wait_for() {
  local desc="$1" timeout="$2"; shift 2
  local start=$SECONDS
  until "$@"; do
    if (( SECONDS - start >= timeout )); then
      log "TIMEOUT waiting for: ${desc}"; return 1
    fi
    sleep 1
  done
}
