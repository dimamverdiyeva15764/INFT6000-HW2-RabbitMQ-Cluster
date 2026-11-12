#!/usr/bin/env bash
# Cluster membership + alarms via the CLI tools (owner: P2).
# Uses the first RabbitMQ container that is running, so it still works when
# a node has been killed by a failure test.
# Works with macOS's default bash 3.2 (no associative arrays, no GNU date).
# Usage: ./scripts/mgmt/cluster_status.sh
set -euo pipefail
NODES="rabbit1 rabbit2 rabbit3"

via=""
for n in $NODES; do
  state=$(docker inspect -f '{{.State.Running}}' "$n" 2>/dev/null || echo false)
  echo "container $n: running=$state"
  if [ -z "$via" ] && [ "$state" = "true" ]; then via="$n"; fi
done
if [ -z "$via" ]; then echo "ERROR: no RabbitMQ container is running. Start with ./scripts/up.sh" >&2; exit 1; fi

echo
echo "== rabbitmqctl cluster_status (asked via $via)"
docker exec "$via" rabbitmqctl cluster_status

echo
echo "== Alarms on each running node"
for n in $NODES; do
  if [ "$(docker inspect -f '{{.State.Running}}' "$n" 2>/dev/null || echo false)" = "true" ]; then
    printf '%s: ' "$n"
    if docker exec "$n" rabbitmq-diagnostics -q check_local_alarms >/dev/null 2>&1; then echo "no alarms"
    else echo "ALARM or node not responding"; fi
  fi
done
