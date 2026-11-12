# HANDOUT - P1 Part (Cluster & Infrastructure)

*INFT 6000 - HW2 - Distributed AMQP Messaging Cluster*
*From: P1 -> To: P2 (next), P3, P4. Read this first: what exists, what I did, how to start, what is left for you.*

---

## 0. START HERE (5 steps, ~10 minutes)

1. Install Docker if needed (section 2).
2. Unzip the repo, open a terminal in the `amqp-cluster` folder:
   ```bash
   cd amqp-cluster
   chmod +x scripts/*.sh scripts/failure/*.sh
   ./scripts/up.sh
   ```
   Wait for **"Cluster is ready."** (the first run downloads images, a few minutes).
3. Open the Management UI: http://localhost:15672 (`admin` / `admin123`). Overview -> Nodes must show 3 green nodes. Queues -> `hw2.orders` must show type `quorum`.
4. Check monitoring (P2): http://localhost:9090/targets (3 RabbitMQ targets should be UP) and http://localhost:3000 (Grafana, `admin` / `admin`).
5. Read section 5 ("What is left for you") for your own tasks.

Stop everything: `./scripts/down.sh` (add `--purge` to delete all data for a clean start).

## 1. What P1 delivered

| Req # | Item | Where | Status |
|---|---|---|---|
| 1 | 3-node RabbitMQ cluster, quorum queues (Raft) | `docker-compose.yml`, `rabbitmq/` | Done, tested on a real machine |
| 2 | Automated provisioning (cluster part) | `scripts/up.sh`, `scripts/down.sh` | Done, tested |
| 9 | Design document sections (topology, consensus, failure recovery) | `docs/design/P1-cluster-design.md` | Done |
| 13 | C4 Deployment diagram | `docs/c4/deployment-diagram.md` | Done (update if ports/services change) |
| 15 | Failure test scenarios + results | `scripts/failure/run_scenario.sh`, `docs/failure-test-plan.md`, `results/`, `docs/evidence/` | Done for S1, S2, S3; P4's data-loss numbers still pending |

## 2. Prerequisites

* Docker + Docker Compose v2 (`docker compose version`)
* `bash`, `curl`, `python3` (Windows: use WSL or Git Bash)

Install Docker on Ubuntu/Debian (if `docker: command not found`):

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker
docker run --rm hello-world
docker compose version
```

## 3. What I did and how (short story)

1. **Cluster:** 3 RabbitMQ 3.13 containers on the Docker network `amqp-net`. They join each other automatically (static peer list `classic_config` in `rabbitmq/rabbitmq.conf`, shared Erlang cookie from `.env`). Management and Prometheus plugins are enabled in `rabbitmq/enabled_plugins`.
2. **Quorum queue:** `up.sh` creates `hw2.orders` through the HTTP API with `x-queue-type=quorum`, 3 replicas (1 Raft leader + 2 followers), and a policy that rejects publishes (nack) instead of dropping messages when the queue is full.
3. **Consensus rule:** a message is confirmed when 2 of 3 nodes wrote it to disk (`floor(3/2)+1 = 2`), so 1 node can fail without losing confirmed data. `pause_minority` stops an isolated node so there is no split-brain.
4. **Failure tests:** `scripts/failure/run_scenario.sh` injects faults with `docker kill` / `docker network disconnect`, measures the new leader and writes a log to `results/`. I ran S1 (follower crash), S2 (leader crash) and S3 (partition) on 2026-10-23 and took screenshots of the Management UI before, during and after.
5. **Docs:** design text, C4 Deployment diagram (Mermaid + PlantUML) and the results/analysis in `docs/failure-test-plan.md`.

## 4. Results summary (details and screenshots: `docs/failure-test-plan.md`)

| Scenario | Leader before -> after | Observation |
|---|---|---|
| S1 follower crash (`rabbit2`) | rabbit1 -> rabbit1 | No election; cluster whole again after ~5.5 s |
| S2 leader crash (`rabbit1`) | rabbit1 -> rabbit3 | Automatic election, observed 55 ms after the kill; whole again after ~10 s |
| S3 partition (leader `rabbit3` isolated) | rabbit3 -> rabbit1 (during), rabbit3 again after heal | Majority (2 nodes) elected a leader and kept committing; isolated node rejoined after ~11.3 s; all 3 members at the same log index |

Raw logs: `results/`. Screenshots: `docs/evidence/` (list in `docs/evidence/README.md`; check with `./scripts/check_evidence.sh`).

**Honest limits:** these runs were done on an idle cluster. "Zero data loss under load" must come from P4's validator running together with P3's producer during S2 and S3. Prometheus targets and Grafana were started by the compose file, but I did not verify dashboards - that is P2's part.

## 5. What is left for you

### P2 - Monitoring / Management
* `monitoring/prometheus/prometheus.yml` is only a **placeholder** I made so `docker compose up` works. Replace/extend it. Targets `rabbit1:15692`, `rabbit2:15692`, `rabbit3:15692` are already correct (`rabbitmq_prometheus` plugin is enabled).
* Grafana: datasource config goes into `monitoring/grafana/provisioning/`, dashboard JSON into `monitoring/grafana/dashboards/` (both folders are already mounted read-only).
* Take the Grafana screenshot of the throughput dip + recovery at the fault time and add it to `docs/failure-test-plan.md` (section 6, "Other evidence").
* If you add services or ports, update `docker-compose.yml` **and tell me** (Deployment diagram). Your Container diagram must match: 3 broker containers + Raft/Erlang-distribution sync layer (port 25672) + Prometheus (+ Grafana).
* Your design-document sections go to `docs/design/` (e.g. `P2-monitoring-design.md`). Load-test metrics (latency/throughput) are also yours.

### P3 - Producer
* Connect with **all 3 endpoints** (`localhost:5672`, `5673`, `5674`); on connection loss reconnect (exponential backoff) to another node.
* Publisher confirms ON, persistent messages (delivery_mode=2), queue `hw2.orders`.
* **Do not re-declare** the queue with different arguments. If you declare it, use exactly `durable=true`, `x-queue-type=quorum`, `x-quorum-initial-group-size=3`, `x-delivery-limit=10`, otherwise `PRECONDITION_FAILED`.
* Put a unique increasing message ID in every message (P4's validator needs it). Code goes to `producer/`.

### P4 - Consumer / Validation / Data-loss proof
* Connect with all 3 endpoints, **manual acks**, ack only after processing. Duplicates are possible after a crash -> dedupe by message ID.
* Validator: `sent_confirmed_ids` vs `received_ids` -> lost, duplicated, out-of-order.
* Run producer + consumer **while** executing `./scripts/failure/run_scenario.sh leader-crash` and `partition`; add your numbers to the "pending (P4)" cells in `docs/failure-test-plan.md`. Code goes to `consumer/`; your C4 System Context diagram goes to `docs/c4/`.

## 6. Connection details

| Item | Value |
|---|---|
| AMQP endpoints (give clients ALL THREE) | `localhost:5672`, `localhost:5673`, `localhost:5674` |
| Username / password | `admin` / `admin123` |
| Virtual host / queue | `/` / `hw2.orders` (quorum, already declared by `up.sh`) |
| Management UI | http://localhost:15672 (also :15673, :15674 - use these when rabbit1 is down) |
| Prometheus / Grafana | http://localhost:9090 / http://localhost:3000 |

## 7. Useful commands

```bash
docker compose ps                                              # container status (a killed node is MISSING here)
docker exec rabbit1 rabbitmqctl cluster_status                 # cluster members
docker exec rabbit1 rabbitmq-queues quorum_status hw2.orders   # who is leader / followers
docker logs -f rabbit2                                         # node logs
docker start rabbit1                                           # bring a dead node back
./scripts/failure/run_scenario.sh leader-crash                 # follower-crash | leader-crash | partition | rolling-restart
./scripts/check_evidence.sh                                    # are all screenshots present?
```

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| UI on :15672 does not open | `docker compose ps` - if `rabbit1` is missing a failure test was interrupted: `docker start rabbit1` (meanwhile use :15673) |
| Node does not join the cluster | `./scripts/down.sh --purge`, then `./scripts/up.sh` |
| `PRECONDITION_FAILED` on queue declare | Your arguments differ from the existing queue - see P3 notes |
| Port already in use | Stop local RabbitMQ/Grafana/Prometheus or change host ports in `docker-compose.yml` |
| Publish blocked after killing 2 nodes | Expected (majority lost). Start one node again |
| Failure script interrupted with Ctrl+C | Run `docker compose ps` and start any missing node; do not press Ctrl+C during a scenario |

## 9. Rules so we don't break each other's work

1. Only edit your own folders/files; ask the owner for changes elsewhere.
2. Port/service changes in `docker-compose.yml` -> tell P1 (Deployment diagram) and P2 (Container diagram).
3. `.env` stays out of git (demo credentials only).
4. Commit small and often: `git pull --rebase` before `git push`.
5. Every C4 diagram must match the real code and compose file (rubric: "precisely align with the code").
