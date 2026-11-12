# INFT 6000 - HW2: Distributed AMQP Messaging Cluster

A three-node RabbitMQ 3.13 cluster with a replicated quorum queue (Raft), multi-threaded Python producer and consumer clients with publisher confirms, manual acknowledgements and failover, Prometheus and Grafana monitoring, failure-injection and chaos tests, and a benchmark suite.

## Requirements

- Docker with Docker Compose v2 (`docker compose version`)
- `bash`, `curl` and Python 3 (on Windows, use WSL or Git Bash)

Installing Docker on Ubuntu or Debian:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker
docker compose version
```

## Quick start

```bash
cp .env.example .env            # demo credentials; the defaults work
./scripts/up.sh                 # start 3 nodes + Prometheus + Grafana, check the cluster, declare the queue
```

`up.sh` waits until all three nodes are healthy and clustered, declares the quorum queue `hw2.orders` (3 replicas) with its policy, and prints the Raft status. Wait for `Cluster is ready.` The first run downloads the images.

| Service | Address |
|---|---|
| AMQP | `localhost:5672`, `localhost:5673`, `localhost:5674` |
| RabbitMQ Management UI | http://localhost:15672 (also 15673, 15674), user `admin` / `admin123` |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000, user `admin` / `admin` (home dashboard: "HW2 - RabbitMQ cluster overview") |

Stop everything with `./scripts/down.sh`. Add `--purge` to also delete the volumes (all messages and Grafana data).

## Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate       # repeat in every new terminal
python3 -m pip install -r requirements.txt
```

## Running and testing

Run all commands from the repository root with the cluster started.

| What | Command | Result to expect |
|---|---|---|
| Unit tests (no cluster needed) | `python3 -m pytest -q common producer consumer` | 32 passed |
| Validator self-check (no cluster needed) | `./scripts/p4/validator_demo.sh` | planted lost, duplicate and reordered messages are all found |
| Cluster health | `python3 scripts/mgmt/mgmt_check.py` | `RESULT: HEALTHY` (exit 1 otherwise) |
| Raft leader and followers | `./scripts/mgmt/quorum_status.sh` | one leader, two followers of `hw2.orders` |
| Cluster membership | `./scripts/mgmt/cluster_status.sh` | 3 running nodes, no partitions |
| Monitoring targets and metrics | `./scripts/mgmt/check_prometheus.sh` | 7 scrape targets up |
| Monitoring end to end | `python3 scripts/mgmt/check_monitoring.py` | `MONITORING CHECK: PASS` |
| Smoke test | `./scripts/p4/smoke.sh` | 10,000 confirmed and received, `LOST 0`, `RESULT: PASS` |
| Chaos run under load | `./scripts/p4/chaos_run.sh leader-crash mytest1` | `LOST 0`, `RESULT: PASS` |
| Two nodes down under load | `./scripts/qa/quorum_loss_run.sh mytest1` | writes stop, then resume; `LOST 0` |
| Persistence | `./scripts/p4/persistence_test.sh` | same queue depth before and after a full restart, `LOST 0` |
| Failure scenario without load | `./scripts/failure/run_scenario.sh leader-crash` | leader before and after, election time |
| Chaos summary table | `python3 scripts/p4/summarize_chaos.py` | one row per run in `results/chaos/` |
| Benchmarks (about 70 min) | `python3 benchmarks/run_bench.py` then `python3 benchmarks/analyze.py` | tables and charts in `benchmarks/results/` |
| Prometheus plot of a run | `python3 scripts/mgmt/plot_prometheus.py --run results/chaos/<scenario>/<run> --out fig.png` | needs the Prometheus data of that run |

Chaos scenarios: `follower-crash`, `leader-crash`, `partition`, `rolling-restart`. Set `TARGET_FAILOVER=0` to let the clients pick a random node instead of starting on the node that will fail.

**Before you run tests, note:**

- `smoke.sh`, `chaos_run.sh` and `quorum_loss_run.sh` empty `hw2.orders` first.
- `chaos_run.sh` and `run_scenario.sh` really kill, restart or disconnect containers. The scripts bring the nodes back themselves; do not press Ctrl+C during a scenario.
- A chaos run writes to `results/chaos/<scenario>/run<name>/` and replaces that folder if it exists, so use a new run name. The runs `run1` to `run6` are the stored evidence.
- `persistence_test.sh` stops and restarts all three nodes.
- Do not run a benchmark and a chaos test at the same time.

## Troubleshooting

| Problem | Fix |
|---|---|
| Management UI on 15672 does not open | `docker compose ps`; if `rabbit1` is missing, a test was interrupted: `docker start rabbit1` (use 15673 meanwhile) |
| A node does not join the cluster | `./scripts/down.sh --purge`, then `./scripts/up.sh` |
| Port already in use | Stop a local RabbitMQ, Prometheus or Grafana, or change the host ports in `docker-compose.yml` |
| Publishing stops after two nodes are killed | Expected: there is no majority. Start one node again |
| `pip install` fails | Activate the virtual environment first, then rerun the install |

## Test environments and evidence

Results were collected in two environments and are kept apart:

- **Docker Compose deployment** (this repository as it is): health check, monitoring check, Grafana, a smoke test and a leader crash under load. Screenshots: `docs/evidence/docker/`.
- **Native test cluster**: RabbitMQ 3.13.7 with this repository's `rabbitmq.conf` and `enabled_plugins`, three nodes as separate processes on a 2-vCPU Linux machine, with the scripts' `docker` commands mapped onto these processes. The 24-run chaos campaign (`results/chaos/`, summary in `docs/evidence/data-integrity.md`), the persistence test (`results/persistence/`), the first campaign on the original code (`results/as-submitted/`), the smoke test in `results/smoke/` and all benchmarks (`benchmarks/results/`) come from here.

The first failure tests without load (2026-10-23, Docker Compose) are in `results/failure_*.log` and `docs/failure-test-plan.md`.

## Project layout

```
docker-compose.yml          3 RabbitMQ nodes, Prometheus, Grafana
.env.example                demo credentials and Erlang cookie
rabbitmq/                   broker configuration and enabled plugins
scripts/up.sh, down.sh      start, verify and stop the cluster
scripts/common.sh           shared shell helpers
scripts/failure/            failure injection (crash, partition, rolling restart)
scripts/mgmt/               health checks, Raft status, monitoring check, Prometheus plots
scripts/p4/                 smoke, chaos, persistence and validator test runners
scripts/qa/                 two-nodes-down (quorum loss) test
common/                     shared connection manager (failover, backoff) and JSON logging
producer/                   multi-threaded producer with publisher confirms
consumer/                   multi-threaded consumer with manual acks, and the validator
monitoring/                 Prometheus config and alert rules, Grafana provisioning and dashboards
benchmarks/                 benchmark runner, scenarios, analysis and results
docs/CONTRACT.md            interfaces: queue, message format, client CLIs, CSV columns
docs/design/                design notes: cluster, monitoring, clients
docs/c4/                    C4 diagrams (Context, Container, Component, Deployment): source + PNG
docs/failure-test-plan.md   failure scenarios and results
docs/evidence/              figures and screenshots
results/                    raw test results (logs, CSVs, validator output)
```
