#!/usr/bin/env bash
# Raft leader / members of every hw2.* quorum queue (owner: P2).
# Usage: ./scripts/mgmt/quorum_status.sh            (all queues matching ^hw2\.)
#        QUEUE_PATTERN='^hw2\.orders$' ./scripts/mgmt/quorum_status.sh
# Works with macOS's default bash 3.2.
set -euo pipefail
NODES="rabbit1 rabbit2 rabbit3"
QUEUE_PATTERN="${QUEUE_PATTERN:-^hw2\.}"

via=""
for n in $NODES; do
  if [ "$(docker inspect -f '{{.State.Running}}' "$n" 2>/dev/null || echo false)" = "true" ]; then via="$n"; break; fi
done
[ -n "$via" ] || { echo "ERROR: no RabbitMQ container is running" >&2; exit 1; }

echo "== Quorum queues (asked via $via)"
docker exec "$via" rabbitmqctl -q list_queues name type leader members online messages_ready messages_unacknowledged consumers \
  | { IFS= read -r header; echo "$header"; grep -E "$QUEUE_PATTERN" || true; }

queues=$(docker exec "$via" rabbitmqctl -q list_queues name type | awk -v p="$QUEUE_PATTERN" '$2=="quorum" && $1 ~ p {print $1}')
for q in $queues; do
  echo
  echo "== rabbitmq-queues quorum_status $q"
  # JSON + python formatting: the default pretty table prints terminal line-drawing
  # codes that turn into garbage in log files ("--formatter table" fails in 3.13).
  docker exec "$via" rabbitmq-queues quorum_status "$q" --formatter json -q 2>/dev/null | python3 -c '
import sys, json
cols = ["Node Name", "Raft State", "Membership", "Last Log Index", "Commit Index", "Term"]
rows = json.load(sys.stdin)
print("  ".join("%-26s" % c if i < 2 else "%-14s" % c for i, c in enumerate(cols)))
for r in rows:
    print("  ".join("%-26s" % r.get(c, "") if i < 2 else "%-14s" % r.get(c, "") for i, c in enumerate(cols)))
' || echo "(could not read status - is a majority up?)"
done
