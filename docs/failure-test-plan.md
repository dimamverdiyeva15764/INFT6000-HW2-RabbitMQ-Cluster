# Failure Test Plan and Results (Requirement #15)

`scripts/failure/run_scenario.sh` injects the failures. The data-loss proof compares the IDs the producer got confirms for with the IDs the consumer received (`consumer/validate.py`).

## 1. Test environment

| Item | Value |
|---|---|
| Broker | RabbitMQ 3.13.7 on Erlang 26.2.5.16 (`rabbitmq:3.13-management`) |
| Topology | 3 nodes: `rabbit@rabbit1`, `rabbit@rabbit2`, `rabbit@rabbit3` (Docker network `amqp-net`) |
| Queue | `hw2.orders` - quorum queue, 3 replicas (Raft), durable |
| Partition handling | `pause_minority` |
| Host | Linux, Docker Compose v2, 16 CPU cores |
| Fault injection | `scripts/failure/run_scenario.sh` (`docker kill`, `docker network disconnect`) |
| Date of runs | 2026-10-23 |

## 2. How to run

```bash
./scripts/up.sh                                    # start cluster
./scripts/failure/run_scenario.sh leader-crash     # fault only, idle cluster
./scripts/p4/chaos_run.sh leader-crash mytest1     # producer + consumer under load, fault, validator
```

`run_scenario.sh` writes `results/failure_<timestamp>.log` (timestamps, leader before/after, election time in ms, quorum status).

## 3. Scenarios

| ID | Scenario | Command | Fault injected | Expected behaviour | Pass criteria |
|---|---|---|---|---|---|
| S1 | Follower crash | `follower-crash` | `docker kill <follower>` | No election; leader unchanged; publishing continues with 2/3 majority | Leader unchanged, 0 lost messages |
| S2 | **Leader crash** | `leader-crash` | `docker kill <leader>` | Automatic Raft election; clients fail over to a surviving node | New leader elected (ms measured), 0 lost messages |
| S3 | **Network partition** | `partition` | `docker network disconnect amqp-net rabbit3` | Minority node pauses (`pause_minority`); majority elects a leader and continues; after heal the node catches up | Majority keeps serving, node rejoins and catches up, 0 lost / 0 duplicated-unacked |
| S4 | Rolling restart | `rolling-restart` | Restart each node one by one | Cluster stays available throughout | 3 nodes running after every step, 0 lost messages |

## 4. Results (measured on 2026-10-23)

| Scenario | Leader before | Leader after | Election time | Cluster whole again after | Messages sent (confirmed) | Messages received | Lost | Out-of-order | Log file |
|---|---|---|---|---|---|---|---|---|---|
| S1 Follower crash (`rabbit2` killed) | rabbit@rabbit1 | rabbit@rabbit1 (unchanged) | n/a (no election needed) | ~5.5 s | see 4b | see 4b | see 4b | see 4b | `results/failure_S1-follower-crash_terminal-capture.log` |
| S2 Leader crash (`rabbit1` killed) | rabbit@rabbit1 | rabbit@rabbit3 | 55 ms (observed) | ~10 s | see 4b | see 4b | see 4b | see 4b | `results/failure_S2-leader-crash_20261023T073304Z.log` |
| S3 Network partition (leader `rabbit3` isolated) | rabbit@rabbit3 | rabbit@rabbit1 during the partition (term 6); rabbit@rabbit3 again after heal (term 7) | not captured (see note) | ~11.3 s | see 4b | see 4b | see 4b | see 4b | `results/failure_S3-partition_20261023T073351Z.log` |
| S4 Rolling restart | see 4b | | | | | | | | |

## 4b. Results under load (native test cluster, 2026-11-11)

Each scenario was run 3 times with `scripts/p4/chaos_run.sh` (producer 4 threads, consumer 4 threads, 1 KB messages, fault 15 s after the start) and checked with `consumer/validate.py`. The cluster was a native 3-node RabbitMQ 3.13.7 with this repository's `rabbitmq.conf` (see README, "Test environments and evidence"). Raw evidence: `results/as-submitted/chaos/<scenario>/run<k>/` (first complete version of the code).

| Scenario | Runs | Election | Confirmed (per run) | Lost | Duplicates | Out-of-order per consumer |
|---|---|---|---|---|---|---|
| S1 follower crash | 3 | none (leader unchanged) | 11,063 / 10,286 / 10,819 | 0 | 0 / 0 / 0 | 0 |
| S2 leader crash | 3 | 531 / 749 / 316 ms | 10,792 / 10,298 / 10,813 | 0 | 0 / 0 / 0 | 0 |
| S3 partition (rabbit3) | 3 | run 1 (rabbit3 leader): new leader rabbit1, term 5 | 3,604 / 9,829 / 9,733 | 0 | 0 / 1 / 0 | 0 |
| S4 rolling restart | 3 | leader moved twice per run | 17,374 / 17,213 / 17,072 | 0 | 1 / 0 / 0 | 0 |

Total: 12 runs, 138,896 confirmed messages, **0 lost**. A second, larger campaign with the final code (including runs with every client on the failed node, and two nodes down) is in `results/chaos/` and `docs/evidence/data-integrity.md`: 24 runs, 467,287 confirmed, 0 lost. Persistence test (50,000 messages, all three nodes stopped and started): depth 50,000 before and after, 0 lost.

**Notes**

* *Election time (S2):* measured by polling the management API every 200 ms, starting when the `docker kill` command returned. The first poll already showed the new leader, so 55 ms is an upper bound on the remaining election time (the election may have finished even earlier, while `docker kill` was returning).
* *S3 election time:* the status check after the isolation returned about 62 s after the fault was injected, and the management API still reported the old leader (`rabbit3`) at that moment. The authoritative Raft view from `rabbitmq-queues quorum_status` (taken from `rabbit1`) shows `rabbit1` as leader in term 6 with `rabbit3` as `{nodedown,rabbit@rabbit3}`, so a new leader had been elected on the majority side. The exact election time was therefore not captured.
* *Message counters:* these scenarios were run on an idle cluster. The message counters under load are in section 4b.

## 5. Analysis

**S1 - Follower crash.** Killing the follower `rabbit2` did not change the Raft leader: `rabbit1` kept leading and `rabbit3` stayed a follower, so 2 of 3 members still formed a majority (`floor(3/2)+1 = 2`). After `rabbit2` was restarted, the cluster returned to 3 running nodes in about 5.5 seconds, and the quorum status showed all three members with the same last log index, so the recovered node was fully caught up.

**S2 - Leader crash.** Killing the leader `rabbit1` caused an automatic election: `rabbit3` became the new leader (term 5) and the queue stayed available with `rabbit2` as follower (last log index 7 on both surviving members). The new leader was observed 55 ms after the kill command returned. When `rabbit1` was restarted it rejoined as a follower, the cluster was whole again after about 10 seconds, and all three members showed the same last log index (7) and term (5), which means the old leader replayed and caught up with the committed log.

**S3 - Network partition.** The current leader `rabbit3` was isolated from the `amqp-net` network, which is the hardest case because the minority side held the leader. The majority side (`rabbit1` + `rabbit2`, 2 running nodes) elected `rabbit1` as leader in term 6 (last log index 8 on both `rabbit1` and `rabbit2`) while `rabbit3` was unreachable, so the queue kept working on the side that had a quorum. After the network was restored, `rabbit3` rejoined within about 11.3 seconds; all three members then reported the same last log index (9) and term (7), with `rabbit3` leading again. No member ended with a diverging log (identical index and term). The `pause_minority` policy keeps the isolated node from accepting writes on its own, which prevents split-brain.

**Summary against the pass criteria (cluster side):** S1 passed (leader unchanged), S2 passed (automatic election, no manual action), S3 passed (majority kept serving, isolated node rejoined and caught up). The zero-data-loss criterion is evidenced in section 4b: 12 runs under load, 0 lost messages.

## 6. Evidence

- Raw logs of S1 to S3 without load: `results/failure_*.log`.
- Raw files of every run under load (client CSVs, logs, validator output, Raft status before and after): `results/chaos/<scenario>/run<k>/` and `results/as-submitted/`.
- Per-run summary: `docs/evidence/data-integrity.md` (`python3 scripts/p4/summarize_chaos.py`).
- Prometheus plots of the faults: `docs/evidence/fig-leader-crash-run4.png`, `fig-partition-run1.png`, `fig-partition-run4.png`, `fig-rolling-restart-run2.png`, `fig-quorum-loss-run1.png`.
- Leader crash run 5, Raft status before and after and validator output: `docs/evidence/native-leadercrash-run5-quorum.png`, `native-leadercrash-run5-validation.png`.
