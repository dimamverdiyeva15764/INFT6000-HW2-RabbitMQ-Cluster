# Evidence

| File | What it shows | Environment |
|---|---|---|
| `docker/docker-mgmt-check.png` | `mgmt_check.py`: 3 nodes running, no alarms or partitions, `hw2.orders` quorum with 3/3 members, HEALTHY | Docker Compose |
| `docker/docker-prometheus-targets.png` | Prometheus targets page: 7 of 7 targets UP | Docker Compose |
| `docker/docker-grafana-message-flow.png`, `docker/docker-grafana-queue.png` | Grafana HW2 dashboard during a message-processing run: message rates, per-node traffic, queue depth, consumers | Docker Compose |
| `docker/docker-check-monitoring.png` | `check_monitoring.py`: targets, alert rules, metrics, Grafana data source and dashboards, all panel queries; PASS | Docker Compose |
| `fig-*.png` | Prometheus plots of chaos runs (message rates, nodes up, Raft term), made with `scripts/mgmt/plot_prometheus.py` | Native test cluster |
| `native-leadercrash-run5-*.png` | Leader crash run 5: Raft status before and after (rabbit2 to rabbit1, term 25 to 26) and validator output (21,810 confirmed, 0 lost) | Native test cluster |
| `data-integrity.md` | One row per chaos run: confirmed, lost, duplicates, reconnects (`scripts/p4/summarize_chaos.py`) | Native test cluster |

Raw data for all of these is in `results/`.
