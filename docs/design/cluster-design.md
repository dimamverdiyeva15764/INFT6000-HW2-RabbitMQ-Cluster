# Design: Cluster Topology, Consensus Configuration, Failure Recovery Policies

*INFT 6000 - Homework 2 - Distributed AMQP Messaging Cluster*

---

## 1. Technology Choice

| Item | Choice | Reason |
|---|---|---|
| AMQP broker | **RabbitMQ 3.13** | Native clustering + Quorum Queues (Raft) - explicitly named in the "Excellent" rubric row |
| Replicated queue type | **Quorum queue** | Raft-based, replicated, durable, safe on node failure |
| Provisioning | **Docker Compose** | Reproducible single-command launch of cluster + monitoring |
| Peer discovery | `classic_config` | Static, deterministic node list - no external service needed |

## 2. Cluster Topology

The cluster consists of **three RabbitMQ nodes** (`rabbit1`, `rabbit2`, `rabbit3`) on a dedicated Docker bridge network `amqp-net`. All nodes are peers; there is no master node at broker level. For every quorum queue one node is elected **Raft leader** and the other two are **followers**.

| Node | Hostname / Erlang node name | AMQP (host) | Management (host) | Prometheus metrics (host) | Volume |
|---|---|---|---|---|---|
| rabbit1 | `rabbit1` / `rabbit@rabbit1` | 5672 | 15672 | 15692 | `rabbit1_data` |
| rabbit2 | `rabbit2` / `rabbit@rabbit2` | 5673 | 15673 | 15693 | `rabbit2_data` |
| rabbit3 | `rabbit3` / `rabbit@rabbit3` | 5674 | 15674 | 15694 | `rabbit3_data` |

Inside the Docker network every node listens on the standard ports:

| Port | Protocol | Purpose |
|---|---|---|
| 5672 | AMQP 0-9-1 | Client traffic (producers/consumers) |
| 15672 | HTTP | Management UI + HTTP API |
| 15692 | HTTP | Prometheus metrics endpoint (`rabbitmq_prometheus`) |
| 4369 | TCP | EPMD (Erlang port mapper) |
| 25672 | TCP | Erlang distribution - inter-node clustering **and Raft replication traffic** |

Clients receive the list of all three AMQP endpoints and perform client-side failover (implemented in `common/connection.py`).

## 3. Consensus Configuration (Raft / Quorum Queues)

Quorum queues use the **Raft consensus algorithm**:

* Each quorum queue forms a **Raft group of 3 members** (`x-quorum-initial-group-size = 3`): 1 leader + 2 followers.
* A write (publish) is **committed only when a majority of members (2 of 3) have written it to their log on disk** (fsync). Only then does the broker send the publisher confirm.
* **Majority formula:** `quorum = floor(N/2) + 1 = floor(3/2) + 1 = 2`. The cluster tolerates `N - quorum = 1` failed node.
* If the leader fails, followers detect missing heartbeats, one becomes a candidate, and wins an election with 2 votes (its own + the other follower). Clients then continue on the new leader.
* `x-delivery-limit = 10` prevents poison messages from looping forever.
* `quorum_queue.continuous_membership_reconciliation` keeps the group size at 3 when a node rejoins.

Declaration used by the provisioning script:

```json
{
  "durable": true,
  "auto_delete": false,
  "arguments": {
    "x-queue-type": "quorum",
    "x-quorum-initial-group-size": 3,
    "x-delivery-limit": 10
  }
}
```

Policy `hw2-quorum` (pattern `^hw2\.`): `max-length = 1000000`, `overflow = reject-publish`. With `reject-publish` the broker sends a **nack** to the publisher instead of silently dropping data, so no message is lost without the producer knowing.

Related broker settings (`rabbitmq/rabbitmq.conf`):

| Setting | Value | Why |
|---|---|---|
| `cluster_partition_handling` | `pause_minority` | A node that sees less than half of the cluster stops serving - prevents split-brain |
| `heartbeat` | `10` | Dead TCP connections are detected within seconds |
| `vm_memory_high_watermark.relative` | `0.6` | Back-pressure before the node runs out of memory |
| `disk_free_limit.absolute` | `1GB` | Protects the Raft log from running out of disk |

## 4. Provisioning

Everything starts with one command:

```bash
./scripts/up.sh
```

Steps performed by the script:

1. `docker compose up -d` - starts 3 RabbitMQ nodes, Prometheus, Grafana.
2. Waits until each node's Docker health check (`rabbitmq-diagnostics -q check_running`) passes.
3. Waits until `rabbitmqctl cluster_status` shows 3 running nodes (automatic join through `classic_config`; all nodes share one Erlang cookie).
4. Declares the quorum queue `hw2.orders` through the HTTP API and sets the policy.
5. Prints `rabbitmq-queues quorum_status` to show the leader and followers.

Persistent volumes (`rabbitN_data` -> `/var/lib/rabbitmq`) hold the Raft log and message store, so data survives container restarts.

## 5. Failure Recovery Policies

| # | Failure | Detection | Automatic reaction | Data-loss risk | Recovery |
|---|---|---|---|---|---|
| F1 | **Follower node crash** | Leader stops receiving Raft acks from it | Leader keeps committing with the other follower (2/3 majority). No election. | None - every confirmed message is on >= 2 disks | Restart node; it rejoins, receives missing log entries from the leader |
| F2 | **Leader node crash** | Followers miss leader heartbeats (election timeout) | One follower wins the election and becomes the new leader; clients reconnect to a surviving node | None - the new leader has all committed entries | Restart old leader; it becomes a follower and catches up |
| F3 | **Network partition (1 node isolated)** | Isolated node sees only itself (1 of 3) | Minority node pauses (`pause_minority`); majority (2 of 3) keeps working and re-elects a leader if needed | None - the minority cannot commit | Heal network; the paused node resumes and replicates the missing entries |
| F4 | **Two nodes down** | Majority lost (1 of 3) | The queue stops accepting commits (cannot reach quorum); publishers get no confirm / block | None for confirmed data - unavailability instead of inconsistency (CP behaviour) | Bring at least one node back to regain the majority |
| F5 | **Rolling restart / maintenance** | Planned | Nodes restarted one by one; majority is always present | None | Wait for the cluster to be whole (3 nodes) before restarting the next node |

**Design principle (CAP):** the quorum queue chooses *consistency + partition tolerance*. Under a partition the minority side becomes unavailable rather than accepting writes that could be lost or diverge.

**Client-side policy (implemented in the producer and consumer, required by the cluster design):** publisher confirms enabled; messages published as persistent; consumers use manual acks; clients keep the list of all 3 endpoints and reconnect with exponential backoff.

## 6. Mapping to Requirements

| Requirement | Satisfied by |
|---|---|
| #1 Multi-node AMQP cluster (quorum queues / Raft) | `docker-compose.yml`, `rabbitmq/rabbitmq.conf`, `scripts/up.sh` |
| #2 Automated provisioning (cluster part) | `scripts/up.sh`, `docker-compose.yml` |
| #9 Design document (topology, consensus, failure recovery) | This document |
| #13 C4 Deployment diagram | `docs/c4/deployment-diagram.md` |
| #15 Failure test scenarios | `scripts/failure/run_scenario.sh`, `docs/failure-test-plan.md` |
