#!/usr/bin/env bash
# Verify the Prometheus side of the monitoring stack:
#   1. every scrape target is UP
#   2. one rabbitmq_identity_info series per node (needed by the Grafana joins)
#   3. per-queue metrics for hw2.orders arrive, and from which node(s)
#   4. lists the RabbitMQ metric names this broker version really exposes
# Usage: ./scripts/mgmt/check_prometheus.sh            (Prometheus on localhost:9090)
#        PROM_URL=http://host:9090 ./scripts/mgmt/check_prometheus.sh
set -euo pipefail
PROM_URL="${PROM_URL:-http://localhost:9090}"
QUEUE_NAME="${QUEUE_NAME:-hw2.orders}"
fail=0

query() {  # query <promql>  -> prints one line per series: <instance> <value>
  curl -s "${PROM_URL}/api/v1/query" --data-urlencode "query=$1" | python3 -c '
import sys, json
for r in json.load(sys.stdin)["data"]["result"]:
    m = r["metric"]
    print("   ", m.get("job", "-"), m.get("instance", "-"), m.get("queue", ""), r["value"][1])'
}

echo "== 1. Scrape targets (${PROM_URL})"
curl -s "${PROM_URL}/api/v1/targets" | python3 -c '
import sys, json
t = json.load(sys.stdin)["data"]["activeTargets"]
down = 0
for x in sorted(t, key=lambda x: (x["labels"]["job"], x["labels"]["instance"])):
    print("    %-18s %-16s %s %s" % (x["labels"]["job"], x["labels"]["instance"], x["health"].upper(), x["lastError"]))
    down += x["health"] != "up"
print("    -> %d targets, %d not up" % (len(t), down))
sys.exit(1 if down else 0)' || fail=1

echo "== 2. rabbitmq_identity_info (expect exactly 3 series, job=rabbitmq)"
query 'rabbitmq_identity_info'
n=$(curl -s "${PROM_URL}/api/v1/query" --data-urlencode 'query=count(rabbitmq_identity_info)' \
    | python3 -c 'import sys,json;r=json.load(sys.stdin)["data"]["result"];print(r[0]["value"][1] if r else 0)')
[[ "$n" == "3" ]] || { echo "    !! expected 3, got $n"; fail=1; }

echo "== 3. Per-queue depth of ${QUEUE_NAME} (which nodes report it?)"
query "rabbitmq_detailed_queue_messages{queue=\"${QUEUE_NAME}\"}"
echo "   Raft term per node for ${QUEUE_NAME}:"
query "rabbitmq_detailed_raft_term_total{queue=\"${QUEUE_NAME}\"}"

echo "== 4. RabbitMQ metric names exposed (paste this list to the team chat / Claude)"
curl -s "${PROM_URL}/api/v1/label/__name__/values" | python3 -c '
import sys, json
names = [n for n in json.load(sys.stdin)["data"] if n.startswith("rabbitmq_")]
groups = ("rabbitmq_detailed_", "rabbitmq_raft_", "rabbitmq_global_messages_", "rabbitmq_queue")
for n in names:
    if n.startswith(groups) or n in ("rabbitmq_connections", "rabbitmq_channels", "rabbitmq_consumers",
        "rabbitmq_alarms_memory_used_watermark", "rabbitmq_alarms_free_disk_space_watermark",
        "rabbitmq_process_resident_memory_bytes", "rabbitmq_resident_memory_limit_bytes",
        "rabbitmq_disk_space_available_bytes"):
        print("   ", n)
print("    (%d rabbitmq_* names in total)" % len(names))'

echo
if (( fail )); then echo "RESULT: FAIL - see the lines marked above"; exit 1; fi
echo "RESULT: OK"
