# INFT 6000 - HW2: Distributed AMQP Messaging Cluster

3-node RabbitMQ cluster with Raft-backed quorum queues, Prometheus + Grafana monitoring, and failure-injection scripts.

## Quick start

```bash
cp .env.example .env        # optional, defaults work
./scripts/up.sh             # start + verify cluster + declare quorum queue
```

| Service | URL / Address |
|---|---|
| AMQP | `localhost:5672`, `localhost:5673`, `localhost:5674` |
| Management UI | http://localhost:15672 (admin / admin123) |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 (admin / admin) |

Queue: `hw2.orders` (quorum, 3 replicas)

## Failure tests

```bash
./scripts/failure/run_scenario.sh leader-crash   # follower-crash | leader-crash | partition | rolling-restart | all
```

Stop: `./scripts/down.sh` (add `--purge` to delete volumes).

## Consumer, validation and chaos with data-loss proof (P4)

```bash
python3 -m pip install -r requirements.txt
./scripts/p4/validator_demo.sh                    # validator catches planted errors (no cluster needed)
./scripts/p4/smoke.sh                             # publish -> consume -> validate (lost must be 0)
./scripts/p4/chaos_run.sh leader-crash 1          # producer + consumer under load + fault + validator
./scripts/p4/persistence_test.sh                  # 50,000 msgs, restart ALL nodes, same depth, lost = 0
python3 scripts/p4/summarize_chaos.py             # evidence table for the report
```
The demo commands and the speaking script are in `docs/presentation/HW2_Group4_Final_Presentation_Script.docx`.

## Monitoring, management and benchmarks (P2)

```bash
./scripts/mgmt/check_prometheus.sh                # 7 scrape targets up, per-queue and Raft metrics
python3 scripts/mgmt/check_monitoring.py          # bonus end-to-end: targets, 8 rules, Grafana data source, 3 dashboards, every HW2 panel query via Grafana
python3 scripts/mgmt/mgmt_check.py                # node health, alarms, queue leader + members (exit 1 if unhealthy)
./scripts/mgmt/quorum_status.sh                   # Raft leader / followers of hw2.orders
python3 benchmarks/run_bench.py                   # 11 configurations x 3 repetitions
python3 benchmarks/analyze.py                     # tables + charts in benchmarks/results/
python3 scripts/mgmt/plot_prometheus.py --run results/chaos/leader-crash/run1 --out fig.png
./scripts/qa/quorum_loss_run.sh 1                 # two nodes down under load (no majority), then recovery
```

## Report and review

- Final report: `docs/report/HW2_Group4_Final_Report.docx` (and `.pdf`; source `.md`, rebuilt with `build_final_report.py`)
- Presentation: `docs/presentation/HW2_Group4_Final_Presentation.pptx` and its speaking script `HW2_Group4_Final_Presentation_Script.docx`
- Final review of requirements, tests and remaining issues: `docs/QA-REVIEW.md`
- Measured evidence: `results/chaos/`, `results/persistence/`, `benchmarks/results/`, `docs/evidence/` (native test cluster); `docs/evidence/docker/` and `results/docker/` (Docker Desktop)

## Layout

```
docker-compose.yml          cluster + monitoring (P1; monitoring configs P2)
rabbitmq/                   broker config + plugins (P1)
scripts/up.sh, down.sh      provisioning (P1)
scripts/failure/            failure injection (P1)
monitoring/                 Prometheus + Grafana config (P2)
docs/design/                design document sections (P1, P2)
docs/c4/                    C4 diagrams, .puml source + .png (Context P4, Container P2, Component P3, Deployment P1)
HANDOUT.md                  P1 hand-over notes (setup, Docker install)
docs/failure-test-plan.md   scenarios + results table (P1, P4)
common/                     shared RabbitMQ connection + logging helpers (P3)
producer/, consumer/        test clients (P3), consumer + validate.py (P4)
scripts/p4/                 P4 test runners: smoke, chaos_run, persistence_test, validator_demo, summarize_chaos
scripts/mgmt/               management, health check, Prometheus plots (P2)
scripts/qa/                 quorum-loss test added in the final review
benchmarks/                 benchmark runner, scenarios, analysis, results (P2)
docs/report/                final report (.docx, .pdf, .md source) and its build script
docs/team/                  P3's work report and demo guide
docs/presentation/          final slides, speaking script and their generators
results/                    logs and CSV evidence from failure, persistence and smoke tests
```
