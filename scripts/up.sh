#!/usr/bin/env bash
# One-command provisioning: start the 3-node RabbitMQ cluster + Prometheus/Grafana,
# verify the cluster, then declare the quorum queue and HA-related policies.
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=scripts/common.sh
source scripts/common.sh

require_docker

[[ -f .env ]] || cp .env.example .env
set -a; source .env; set +a

log "Starting containers..."
docker compose up -d

log "Waiting for all RabbitMQ nodes to become healthy..."
for n in "${NODES[@]}"; do
  wait_for "$n healthy" 180 \
    bash -c "[ \"\$(docker inspect -f '{{.State.Health.Status}}' $n)\" = healthy ]"
  log "$n is healthy"
done

# Nodes form the cluster automatically (classic_config). Verify it.
log "Waiting for a 3-node cluster..."
wait_for "3 running nodes" 120 bash -c "[ \"\$(docker exec rabbit1 rabbitmqctl cluster_status --formatter json 2>/dev/null | python3 -c 'import sys,json;print(len(json.load(sys.stdin)[\"running_nodes\"]))' 2>/dev/null)\" = 3 ]"
docker exec rabbit1 rabbitmqctl cluster_status

# Declare the quorum queue (replicated on all 3 nodes through Raft).
log "Declaring quorum queue '${QUEUE_NAME}'..."
curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" -X PUT \
  -H 'content-type: application/json' \
  -d '{"durable":true,"auto_delete":false,"arguments":{"x-queue-type":"quorum","x-quorum-initial-group-size":3,"x-delivery-limit":10}}' \
  "http://localhost:15672/api/queues/%2F/${QUEUE_NAME}"

# Policy: cap queue length and keep dead-lettering off (a message must never vanish).
log "Setting policy..."
docker exec rabbit1 rabbitmqctl set_policy hw2-quorum "^hw2\\." \
  '{"max-length":1000000,"overflow":"reject-publish"}' \
  --apply-to queues --priority 1

log "Quorum status:"
quorum_status_text rabbit1

cat <<EOF

Cluster is ready.
  AMQP endpoints : localhost:5672, localhost:5673, localhost:5674
  Management UI  : http://localhost:15672  (user: ${RABBITMQ_USER})
  Prometheus     : http://localhost:9090
  Grafana        : http://localhost:3000
  Queue          : ${QUEUE_NAME} (quorum, 3 replicas)
EOF
