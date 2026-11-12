# Final QA Review - INFT6000 HW2, Group 4

*Reviewed 2026-11-11 against `INFT6000-HW2.pdf` (4 pages, rubric included) and `amqp-cluster-P4_1.zip`. No separate instructions from the professor or presentation requirements were provided, and the PDF asks for none, so none are assessed.*

## How it was tested

Docker Hub and the Grafana download site are blocked in the review environment, so **the Docker Compose stack itself could not be started**. Instead:

- A real 3-node RabbitMQ 3.13.7 cluster (Erlang/OTP 26) was run with the repository's own `rabbitmq/rabbitmq.conf` and `enabled_plugins`.
- Each node ran in its own Linux network namespace with hostname `rabbit1`, `rabbit2` or `rabbit3`, and host ports 5672-5674 and 15672-15674 were forwarded as in `docker-compose.yml`.
- The `docker` sub-commands the scripts use (`exec`, `inspect`, `kill`, `start`, `restart`, `network disconnect/connect`, `compose up/stop/start`) were mapped onto those nodes by a small shim. `scripts/up.sh` ran unmodified on top of it.
- Prometheus 2.53.0 ran with the repository's `prometheus.yml` and alert rules.
- Machine: 2 vCPU, 7 GB RAM.

**Not executed:** Docker Compose itself, Grafana, the Management UI in a browser.

Two test campaigns were run:

1. **As submitted** (frozen copy, no changes): unit tests, smoke, 12 chaos runs, persistence. Its benchmark numbers were discarded: the review's own port forwarder lacked `TCP_NODELAY` and added about 40 ms to most confirms. That was a test-harness fault, not a project fault.
2. **After fixes** (the delivered ZIP), with the forwarder corrected: smoke, 21 chaos runs, 3 quorum-loss runs, persistence, and the 33-run benchmark matrix.

## 1. Verdict

**Ready to submit after the team does the short list in section 7** (names and repository link, push to Git, one run on real Docker, Grafana screenshots, P1's missing screenshots).

The technical work is strong and now proven by execution:

- Every assignment requirement is implemented.
- 467,287 confirmed messages went through 24 failure runs with **0 lost**.
- A full-cluster restart kept all 50,000 messages.
- All four C4 diagrams exist and match the code.

Before this review, the submission had no evidence of data integrity under failure, no benchmark results, an incomplete Component diagram, a Deployment diagram without volumes, broken screenshot links, and several sections of the report unwritten.

## 2. Requirement compliance matrix

Status: PASS = implemented and executed; PARTIAL = implemented, part not verified or not evidenced; NOT TESTED = could not be executed here.

| # | Requirement (PDF) | Where implemented | How verified | Status | Missing / action |
|---|---|---|---|---|---|
| R1 | Multi-node AMQP cluster, RabbitMQ quorum queues / Raft | `docker-compose.yml`, `rabbitmq/rabbitmq.conf`, `scripts/up.sh` | T2: cluster formed from the repo's config, `hw2.orders` 3 voters, 1 leader | PASS | Run once on Docker (7.3) |
| R2 | Native management UI / HTTP API / CLI | Management plugin; `scripts/mgmt/*`; `rabbitmqctl` | T5: HTTP API and CLI scripts against the live cluster | PASS | UI not opened in a browser (screenshot only) |
| R3 | Prometheus + Grafana: queue depth, message rates, node health **(bonus)** | `monitoring/`, compose services | T3, T4, T9: 7/7 targets up, 69 dashboard queries run without error, alerts fired correctly | PARTIAL | Grafana never started here; open it once and screenshot (7.4) |
| R4 | Multi-threaded clients in Python/Java/Go | `producer/producer.py`, `consumer/consumer.py` | T1, T7, T8 | PASS | - |
| R5 | Publisher confirms | `common/connection.py` (`confirm_delivery`), `producer._publish_one` | Every chaos run; E3 (nack path) | PASS | - |
| R6 | Connection failover handling | `ConnectionManager.connect/reconnect` | Targeted runs: 4/4 producer and 4/4 consumer threads reconnected, 0 lost; E4 backoff | PASS | - |
| R7 | Manual acknowledgements | `consumer.handle_delivery` (`auto_ack=False`, ack after write) | T1 unit tests; chaos runs | PASS | - |
| D1 | Automated provisioning launching cluster **with** Prometheus/Grafana | `docker-compose.yml`, `scripts/up.sh` | `up.sh` executed through the shim; `docker compose config -q` valid | PARTIAL | Compose start itself only run by P1 in October; rerun on Docker (7.3) |
| D2 | Design document: topology, consensus, monitoring, failure recovery policies | `docs/design/P1..P3`, final report sections 3, 4, 5, 8.1 | Read against code; corrected one wrong statement (health check) | PASS | - |
| D2-C1 | C4 System Context | `docs/c4/context-diagram.*` | Matches code | PASS | - |
| D2-C2 | C4 Container: node containers, Raft sync layer, Prometheus | `docs/c4/container-diagram.*` | Ports checked against compose | PASS | - |
| D2-C3 | C4 Component: exchange router, quorum queue, connection handler; retry handler, channel pool | `docs/c4/component-diagram.*` | Was producer-only, no image; extended in review | PASS (after fix) | - |
| D2-C4 | C4 Deployment: network, ports, scrape ports, **volume mappings** | `docs/c4/deployment-diagram.*` | Had no volumes and no image; extended in review | PASS (after fix) | - |
| D3 | Producer/consumer source with stress testing | `--threads --duration/--count --rate --size --prefetch` | Benchmark matrix, chaos runs | PASS | - |
| D3 | Structured logging | `common/logging_setup.py` (JSON lines) | Logs of every run | PASS | - |
| D3 | Validation logic for ordering and persistence | `consumer/validate.py`, `scripts/p4/persistence_test.sh` | T6, T11 | PASS | - |
| D4 | Load-test metrics: latency and throughput | `benchmarks/run_bench.py`, `analyze.py` | T12: 33 runs | PASS | Rerun on the team's machine for final absolute numbers (optional) |
| D4 | Failure results: recovery during node crash or partition | `scripts/p4/chaos_run.sh`, `scripts/failure/run_scenario.sh` | T8: 21 runs + T10: 3 quorum-loss runs | PASS | - |
| S1 | Single version-controlled repository | ZIP has no `.git` | - | PARTIAL | Push to GitHub, tag `v1.0` (7.1) |
| S2 | Monitoring dashboards in the repo | `monitoring/grafana/dashboards/*.json` | Present, queries verified | PASS | - |
| S3 | Technical report | `docs/report/HW2-Final-Report.docx/.pdf` | Written from executed results | PASS | Add names and repository link (7.1) |

**Rubric-level checks**

| Rubric phrase | Status |
|---|---|
| "Flawless multi-node broker deployment using RabbitMQ Quorum Queues" | PASS (pending one Docker run) |
| "fully integrated Prometheus/Grafana monitoring and management UIs configured cleanly" | Prometheus PASS; Grafana PARTIAL (not started) |
| No "manual setup requirements" | PASS: one command |
| No "configuration warnings" | Likely one: `RABBITMQ_ERLANG_COOKIE` is a deprecated variable in 3.13 (check 7.5) |
| "publisher confirms, robust connection error handling, explicit acknowledgments, clean failover behavior under load" | PASS: targeted runs |
| C4 diagrams "precisely align with the code, cluster scripts, and management topology" | PASS: every port and volume copied from compose |
| "automatic leader election and zero data loss during node failures" | PASS: 12 crash runs, elections 447-964 ms, 0 lost |
| "Performance metrics thoroughly analyzed under high volume" | PASS: 33 runs, percentiles, analysis in report section 9 |

## 3. Contribution verification (four members)

| Member | Completed and verified | Missing or incomplete at submission | Bugs / integration problems found | Evidence | Ready |
|---|---|---|---|---|---|
| **Person 1** - cluster | 3-node compose cluster, config, `up.sh`/`down.sh`, `run_scenario.sh` (4 scenarios), design doc, Deployment diagram (Mermaid), idle S1-S3 runs on Docker | 9 screenshots referenced in `failure-test-plan.md` but **not in the ZIP**; S4 never run by P1; no under-load runs; Deployment diagram lacked volumes and image; report Part 1 short; macOS patch not applied | `declare -A` and `date +%3N` break on macOS bash/BSD date; `quorum_status` logs full of escape codes; design doc named the wrong health check | Review runs T2, T8 used P1's scripts unchanged | Yes after review fixes, **except the screenshots** |
| **Person 2** - monitoring, benchmarking | Prometheus (2 jobs), 8 alert rules + tests, Grafana provisioning + 3 dashboards, mgmt scripts, benchmark runner, analysis, contract, Container diagram, report drafts | Grafana never opened; no benchmark results or screenshots before the review | Election alert also fired for internal Raft groups (fixed); plot tool added | T3-T5, T9, T12 | Yes, after Grafana screenshot |
| **Person 3** - producer, shared library | `common/connection.py`, JSON logging, producer with confirms, retry with same `msg_id`, nack limit, stress options, 11 tests, design doc, Component diagram (producer side) | Report sections 2, 6, 10 not written (status notes only); no live failover test; Component diagram missing consumer and image | 3 unrelated `.whl` files and test outputs committed in the repo root / `producer/` (removed) | T1, E1-E5, targeted runs: 4/4 threads republished, 0 lost | Yes (report sections now written in the final report from the code) |
| **Person 4** - consumer, integrity | Consumer (manual ack after write, nack/requeue, reconnect, de-dup, SIGTERM), validator, smoke/chaos/persistence/summary scripts, 20 tests, Context diagram, report sections with placeholders | Scripts never run against the team's cluster; all result placeholders empty | `chaos_run.sh` did not ensure any client sat on the failed node (some runs tested no failover); fixed with targeted mode | T6-T8, T11 | Yes |

Workload balance: all four parts contain real code and tests. P3's report sections were missing; the final report now covers them from P3's code and design doc, which P3 should review.

## 4. Bonus compliance

The PDF names one bonus: **"Observability Stack: Prometheus + Grafana for metrics collection (queue depth, message rates, node health). (Bonus)"**. No point value is given, so none is estimated in points.

| Bonus element | Implementation | Verified | Likely awarded? |
|---|---|---|---|
| Prometheus collecting queue depth, message rates, node health | `prometheus.yml` (node + per-queue jobs) | Yes: 7/7 targets, all metrics present | Yes |
| Grafana dashboards | 3 provisioned dashboards | Queries only; Grafana not started | Likely, **if** the report or demo shows a screenshot |
| Alerting (beyond the brief) | 8 rules + unit tests | Yes: fired correctly during faults | Strengthens the bonus |

## 5. Test execution report

All commands were run from the repository root. Raw output is in `results/` and `benchmarks/results/`.

| ID | Command | Expected | Actual | Status |
|---|---|---|---|---|
| T1 | `python3 -m pytest -q common producer consumer` | all pass | 31 passed (as submitted); 32 passed after adding a test | PASS |
| T2 | `./scripts/up.sh` | 3 nodes, queue declared, leader + 2 followers | as expected | PASS |
| T3 | `./scripts/mgmt/check_prometheus.sh` | 7 targets up, RESULT OK | 7 up, OK | PASS |
| T4 | `promtool test rules monitoring/prometheus/tests/rabbitmq-alerts.test.yml` | SUCCESS | SUCCESS | PASS |
| T5 | `mgmt_check.py`, `quorum_status.sh`, `cluster_status.sh` | healthy; leader shown | healthy, readable output | PASS |
| T6 | `./scripts/p4/validator_demo.sh` | planted errors FAIL (exit 1), clean PASS | exactly 2 lost, 3 dup, 1 reorder found; clean PASS | PASS |
| T7 | `./scripts/p4/smoke.sh` | 10,000 / 10,000, lost 0 | 10,000 / 10,000, lost 0 | PASS |
| T8 | `./scripts/p4/chaos_run.sh <scenario> 1..6` | lost 0 every run | 21 runs + 3 of T10: 467,287 confirmed, 0 lost (as submitted: 12 runs, 138,896, 0 lost) | PASS |
| T9 | alert watcher during T8 | right alerts fire | NodeDown always; election alert on elections; QuorumLost only without majority | PASS |
| T10 | `./scripts/qa/quorum_loss_run.sh 1..3` | no confirms without majority, then resume, lost 0 | pauses of 31 to 38 s, lost 0 | PASS |
| T11 | `./scripts/p4/persistence_test.sh` | depth equal before/after full restart, lost 0 | 50,000 -> 50,000, lost 0 (both campaigns) | PASS |
| T12 | `python3 benchmarks/run_bench.py && python3 benchmarks/analyze.py` | 33 runs complete, charts | 33 of 33 ok; 315 msg/s (1 thread) to 774 msg/s (16 threads); broker counter within 0.4 % of client numbers | PASS |
| E1 | producer with wrong password | fail fast | exit 1 in < 1 s, 403 reported | PASS |
| E2 | producer / consumer, queue missing | fail with clear error | producer 404 exit 1; consumer stops after 10 tries with `queue_missing` | PASS |
| E3 | producer on a full queue (`reject-publish`) | nacks counted, retried, reported | 6 nacks, 5 retries, then clear error | PASS |
| E4 | producer, all hosts down, then Ctrl+C | backoff grows, clean stop | retries 0.7 -> 8.4 s; status `interrupted` | PASS |
| E5 | `--size 50` | rejected before connecting | exit 2, clear message | PASS |
| G1 | Grafana loads dashboards | home dashboard with data | **not executed** (Grafana unavailable) | NOT TESTED |
| D1 | `docker compose up` on Docker | stack starts | **not executed** here (P1 did it on 2026-10-23) | NOT TESTED |

## 6. Problems found and fixed

| # | Problem | Location | Fix | Re-tested |
|---|---|---|---|---|
| 1 | Unrelated binary packages and test output committed (`rabbitmq-0.2.0` 2017 PyPI wheel, `cffi`, `pycparser` wheels, `producer/confirmed.csv`, `producer_summary.json`) | repo root, `producer/` | Removed; P3's Word notes moved to `docs/team/` | n/a |
| 2 | Scripts fail on macOS default bash 3.2 (`declare -A`) and BSD `date` (`%3N`); election timing breaks | `scripts/common.sh`, `scripts/failure/run_scenario.sh` | `api_port()` function, `now_ms()` in Python | T2, T8 |
| 3 | Raft status in every log was unreadable terminal escape codes | `up.sh`, `run_scenario.sh`, `chaos_run.sh`, `persistence_test.sh` | `quorum_status_text()` (JSON -> plain text) | T8 logs |
| 4 | Chaos runs did not guarantee that any client was on the failed node | `scripts/p4/chaos_run.sh` | `TARGET_FAILOVER=1` puts every client on the victim; `RABBITMQ_HOSTS_SHUFFLE=0` in `ConnectionManager` (default unchanged) + unit test | T8 runs 4-6 |
| 5 | Component diagram showed only the producer; no image | `docs/c4/component-diagram.*` | Full C4-PlantUML diagram: both clients, shared library, broker internals; PNG | rendered |
| 6 | Deployment diagram lacked volume mappings, host ports, image; unpinned C4 library | `docs/c4/deployment-diagram.*` | New PlantUML from `docker-compose.yml`; PNG; pinned v2.11.0 | rendered |
| 7 | Election alert also fired for an internal Raft group without a queue label | `rabbitmq-alerts.yml` | `{queue!=""}` filter | promtool + live reload |
| 8 | Design doc named `rabbitmq-diagnostics ping` as health check | `docs/design/P1-cluster-design.md` | Corrected to `check_running` | n/a |
| 9 | `matplotlib` missing from root `requirements.txt` | `requirements.txt` | Added | n/a |
| 10 | No test of two nodes down (failure F4 in the design) | - | `scripts/qa/quorum_loss_run.sh` | T10 |
| 11 | Report: P3 sections missing, all results empty, no final assembled report | `docs/report/` | `HW2-Final-Report` (md, docx, pdf) from executed results | - |
| 13 | Raw CSVs (240 MB) too big for a comfortable Git push | `results/`, `benchmarks/results/raw/` | gzip-compressed (60 MB total, no file over 5 MB); `analyze.py` and `validate.py` read `.csv.gz` | re-analysis identical |
| 12 | `failure-test-plan.md` had "pending (P4)" everywhere and broken screenshot links | `docs/failure-test-plan.md` | Filled from runs; missing screenshots flagged | - |

## 7. Remaining issues and exact actions

| # | Issue | Owner | Exact action |
|---|---|---|---|
| 7.1 | Names, IDs and repository link are `[FILL]` in the report; the ZIP is not a Git repository | all | Replace `[FILL: ...]` in `docs/report/HW2-Final-Report.md`, rebuild or edit the `.docx`; then `git init && git add -A && git commit -m "HW2 final" && git remote add origin <url> && git push -u origin main && git tag v1.0 && git push --tags` |
| 7.2 | P1's 9 screenshots are missing | P1 | Copy `01-up-ready.png` ... `09-log-leader-crash.png` into `docs/evidence/`, or delete the links in section 6 of `docs/failure-test-plan.md` |
| 7.3 | Docker Compose stack not executed in this review | any | `./scripts/down.sh --purge && ./scripts/up.sh && python3 -m pytest -q common producer consumer && ./scripts/p4/smoke.sh && ./scripts/p4/chaos_run.sh leader-crash 7` - expect `RESULT: PASS` |
| 7.4 | Grafana never started (bonus evidence) | P2 | After 7.3, open http://localhost:3000, check "HW2 - RabbitMQ cluster overview" shows data, run `./scripts/p4/chaos_run.sh leader-crash 8` while it is open and save `docs/evidence/p2-grafana-leader-crash.png`; add it to report section 5 |
| 7.5 | Possible deprecation warning for `RABBITMQ_ERLANG_COOKIE` | P1 | `docker logs rabbit1 2>&1 | grep -i -E "deprecat|warning" | head`; if it appears, mount a cookie file instead (`./rabbitmq/.erlang.cookie:/var/lib/rabbitmq/.erlang.cookie:ro`, mode 400) and rerun 7.3 |
| 7.6 | Absolute benchmark numbers come from a 2-vCPU test machine | P2 (optional) | `python3 benchmarks/run_bench.py --force && python3 benchmarks/analyze.py` on the team machine, then update section 9 and Appendix C |
| 7.7 | P3 should review sections 2 and 6, P1 sections 3, 4 and 8.1 | P1, P3 | Read and correct wording only; numbers come from the files in `results/` |

## 8. Grading simulation

The rubric gives four criteria and their weights; the bonus has no stated value. Estimates are a reviewer's judgement, not a promise.

| Evaluation area | Max | Before review | After verified corrections | Reason | Required improvement |
|---|---|---|---|---|---|
| Cluster deployment & management | 30 | 25-27 | 27-29 | Solid cluster, one-command start, monitoring stack; no evidence Grafana works | 7.3, 7.4, 7.5 |
| Client implementation & resilience | 30 | 22-25 | 28-30 | Code was good but failover under load was unproven; now proven with targeted runs | - |
| Architecture documentation & C4 | 20 | 14-16 | 18-19 | Component and Deployment diagrams were incomplete; now complete and image-rendered | 7.7 (review wording) |
| Benchmarking & chaos testing | 20 | 9-12 | 18-19 | No load results or integrity evidence before; now 24 runs, 0 lost, 33 benchmark runs with analysis | 7.6 optional |
| Bonus (Prometheus + Grafana) | n/a | partial | likely | Not quantified in the PDF | 7.4 |
| **Total (of 100)** | 100 | **about 70-80** | **about 91-97** | | |

**Risks that could still reduce the grade**

- The professor runs `docker compose up` and something differs from the review environment. Do 7.3.
- The broken screenshot links or the `[FILL]` markers remain.
- Grafana shows "No data" on the professor's machine. It should not (the queries were checked), but confirm with 7.4.
- The report states that the measurements come from a non-Docker test machine; a strict grader may want Docker numbers (7.6).

**Top five improvements, by importance**

1. Run the stack once on Docker and save the output (7.3).
2. Grafana screenshot during a failure (7.4).
3. Fill in names and the repository link, push to Git, tag (7.1).
4. Add or remove P1's screenshots (7.2).
5. Rerun the benchmark on the team machine (7.6).

## 9. Submission readiness

**Code and evidence: ready. Submission package: ready once 7.1 to 7.4 are done (about one hour of work).**
