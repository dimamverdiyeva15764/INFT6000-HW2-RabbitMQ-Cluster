# Integration contract (all members)

*Draft by P2 from P1's actual configuration, 2026-10-28. P3 and P4 confirm or propose changes in one PR; after that, changes need all four to agree.*

Everything below is what the code **already uses** (P1) or what P2's benchmark runner, P4's validator and P2's `analyze.py` **will read**. If a value here and the code disagree, the code is wrong.

**Current client implementation follows this deployed contract:** vhost `/`, default exchange, and queue `hw2.orders`. The earlier team plan describes a different topology (`hw2` vhost, `hw2.direct`, and `hw2.q.*` queues). Do not mix the two configurations; P1/P2 should approve a coordinated cluster-and-client change before replacing this contract.

## 1. Cluster (fixed by P1 - do not change without telling P1 and P2)

| Item | Value |
|---|---|
| Nodes / containers | `rabbit1`, `rabbit2`, `rabbit3` (Erlang names `rabbit@rabbit1` ...), network `amqp-net` |
| AMQP endpoints (host) | `localhost:5672` (rabbit1), `localhost:5673` (rabbit2), `localhost:5674` (rabbit3) |
| Management API / UI (host) | `localhost:15672` / `15673` / `15674` |
| Credentials | `admin` / `admin123` (from `.env`; read `RABBITMQ_USER`, `RABBITMQ_PASS` env vars, default to these) |
| Virtual host | `/` |
| Queue | `hw2.orders` - quorum, durable, 3 replicas, `x-delivery-limit=10`; declared by `scripts/up.sh` |
| Policy `hw2-quorum` | `max-length=1000000`, `overflow=reject-publish` (a full queue **nacks** publishes) |
| Exchange | none declared - publish to the **default exchange** `""` with routing key `hw2.orders` |
| Queue declare in clients | `passive=True`, or exactly: `durable=True, arguments={"x-queue-type":"quorum","x-quorum-initial-group-size":3,"x-delivery-limit":10}` - anything else gives `PRECONDITION_FAILED` |

## 2. Message format (P3 writes, P4 reads)

- Body: UTF-8 JSON `{"msg_id": "<producer_id>-<seq>", "producer_id": "<host>-<pid>-t<thread>", "seq": <int, starts at 1 per producer_id>, "sent_ts_ns": <time.time_ns() immediately before basic_publish>, "payload": "<padding>"}`
- The body is padded so the **whole body is `--size` bytes** (so message size in the benchmark is the real body size).
- Properties: `delivery_mode=2` (persistent), `message_id=msg_id`, `content_type="application/json"`.
- `msg_id` is unique for the whole run and **stays the same when a message is republished** after a failover.

## 2b. Shared client library (P3)

The connection/failover code both clients use lives in **`common/connection.py`** at the repository root. `ConnectionManager` tries the configured host list in shuffled order, uses heartbeat 10 s and exponential backoff with jitter, and emits JSON-line connection/failover events. Credentials and vhost come from `RABBITMQ_USER`, `RABBITMQ_PASS`, and `RABBITMQ_VHOST`, defaulting to `admin`, `admin123`, and `/`. The producer enables publisher confirms; a consumer can use the same manager without confirms. `producer/producer.py` imports the shared module after adding the repository root to `sys.path`. Python 3.9+ and `pika` only (`pip install pika`).

## 3. Producer CLI (P3) - `producer/producer.py`

```
python3 producer/producer.py --hosts localhost:5672,localhost:5673,localhost:5674 \
    --queue hw2.orders --threads 4 --duration 60 --rate 0 --size 1024 --out <DIR>
```

| Flag | Meaning |
|---|---|
| `--hosts` | comma-separated endpoints, tried in random order, failover on error |
| `--queue` | routing key / queue (default `hw2.orders`) |
| `--threads N` | N publishing threads, **one connection + channel per thread**, publisher confirms on |
| `--duration S` | publish for S seconds, then finish any in-flight publish and exit |
| `--count N` | stop after N logical messages per thread instead of using `--duration`; defaults to 100 if neither mode is supplied |
| `--rate R` | messages/s **per thread**; `0` = as fast as confirms allow |
| `--size B` | exact serialized JSON body size in bytes; must fit the message metadata |
| `--out DIR` | output folder (created if missing) |
| `--nack-retry-limit N` | maximum retries for broker NACKs (default 5); connection-loss retries continue until a broker is reachable |

Writes:
- `DIR/confirmed.csv` - one row per **confirmed** message: `msg_id,producer_id,seq,sent_ts_ns,confirm_ts_ns`
- `DIR/producer_summary.json` - `sent` and `confirmed` count logical messages; `nacked` counts broker NACK/unroutable responses; `republished` counts retry attempts; `reconnects` counts successful connections after the initial one. Also includes status, elapsed time, errors, and reservoir-sampled confirm-latency p50/p95/p99 (with sample and total counts).
- JSON-lines log on stdout/stderr with connection, failover, confirmation, and run-summary events (the runner saves it as `producer.log`).

## 4. Consumer CLI (P4) - `consumer/consumer.py`

```
python3 consumer/consumer.py --hosts localhost:5672,localhost:5673,localhost:5674 \
    --queue hw2.orders --threads 4 --prefetch 100 --out <DIR>
```

| Flag | Meaning |
|---|---|
| `--hosts`, `--queue` | as producer |
| `--threads N` | N consumer threads, one connection + channel each, **manual acks** |
| `--prefetch P` | `basic_qos(prefetch_count=P)` per channel |
| `--out DIR` | output folder |

Runs until it receives **SIGINT or SIGTERM**, then stops consuming, acks what it has processed, flushes the CSV and exits 0 within 30 s (the benchmark runner relies on this).

Writes:
- `DIR/received.csv` - one row per **delivery** (duplicates included): `msg_id,producer_id,seq,sent_ts_ns,recv_ts_ns,redelivered,consumer_id`  (`redelivered` = `true`/`false`)
- `DIR/consumer_summary.json` - `{"received":..,"unique":..,"duplicates":..,"redelivered":..,"reconnects":..}`

## 5. Validator (P4) - `consumer/validate.py`

```
python3 consumer/validate.py --confirmed DIR/confirmed.csv --received DIR/received.csv [--json DIR/validation.json]
```
Prints confirmed, received (unique), **lost** (confirmed but never received), duplicates, out-of-order per `producer_id`; exit 1 if lost > 0. Used for every chaos run (P1/P4) and optionally on benchmark runs.

## 6. Timestamps and clocks

All `*_ts_ns` are `time.time_ns()` (wall clock, nanoseconds). Producer and consumer run on the **same machine** in every test, so end-to-end latency = `recv_ts_ns - sent_ts_ns` is valid.

## 7. Where results go

| What | Folder | Owner |
|---|---|---|
| Benchmark raw runs | `benchmarks/results/raw/<scenario>/rep<k>/` | P2 (runner writes it) |
| Benchmark summaries + charts | `benchmarks/results/` | P2 (`analyze.py`) |
| Chaos logs | `results/failure_*.log` | P1 |
| Chaos client CSVs + validator output | `results/chaos/<scenario>/run<k>/` | P3/P4 |
| Screenshots | `docs/evidence/` | everyone (prefix `p2-`, `p3-`, `p4-`) |

Raw result files are never edited by hand.
