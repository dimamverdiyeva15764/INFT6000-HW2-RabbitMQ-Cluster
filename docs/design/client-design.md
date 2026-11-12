# Design: Producer and Shared Client Library

This section documents the producer implementation and the connection manager
shared with the consumer. Runtime names and queue
topology follow [`../CONTRACT.md`](../CONTRACT.md): the `/` vhost, default
exchange, and pre-provisioned quorum queue `hw2.orders`.

## Publishing flow

Each producer thread owns a `ConnectionManager`, connection, and channel.
Publisher confirms are enabled on that channel. Before publishing on a new
channel, the producer passively checks that the configured queue already
exists; it does not create or alter the queue.

The worker builds a UTF-8 JSON message with a per-thread sequence number and a
run-unique producer ID (`hostname-pid-tN`). The `msg_id` is
`producer_id-sequence`. The body is padded to exactly `--size` bytes. Properties
mark the message persistent (`delivery_mode=2`), set its content type to JSON,
and carry the same `msg_id` in `message_id`.

The default exchange routes directly to `hw2.orders`. After the broker confirms
a publish, the producer writes that message's ID, producer ID, sequence, send
timestamp, and confirm timestamp to `confirmed.csv`.

## Failover and retry behavior

`common/connection.py` reads hosts and credentials from environment variables
or uses the defaults in the integration contract. It randomizes the initial
host order, uses a 10-second heartbeat, and rotates to another host after a
transient connection failure. Backoff grows exponentially from 0.5 seconds to
10 seconds, with jitter. Authentication and vhost-access errors fail fast
instead of retrying forever.

If a connection is lost before a confirm arrives, the producer reconnects and
retries the same logical message with the same `msg_id` and sequence number.
The send timestamp reflects the publish attempt that eventually receives a
confirm. Because the broker may have accepted an attempt whose confirm was
lost, retries can result in duplicate deliveries; consumers should deduplicate
by `msg_id`. Explicit broker NACKs are counted and retried up to
`--nack-retry-limit`; an unroutable message is reported as an error.

## Load and result options

- `--duration S` stops starting new messages after S seconds and allows the
  current synchronous publish/retry to finish.
- `--count N` sends N logical messages per thread. If neither is specified,
  the producer sends 100 per thread.
- `--rate R` limits each thread independently; `0` means unthrottled.
- `--size B` sets the exact serialized body size; values too small for the
  required metadata are rejected before connecting.
- `--out DIR` writes `confirmed.csv` and `producer_summary.json`.

The summary distinguishes logical messages (`sent`, `confirmed`) from retry
attempts (`republished`) and includes NACKs, successful reconnects, run status,
elapsed time, errors, and confirm-latency percentiles. Logs are
JSON-lines so benchmark and failure runs can retain connection, retry, and
confirmation events. Latency percentiles use a bounded reservoir sample, so
summary memory use remains capped during high-throughput runs; the CSV retains
the exact timestamp for every confirmed message.

## Validation

Run the local tests from the repository root:

```powershell
python -m pytest -q
```

Run a short broker-backed check after starting the cluster:

```powershell
python .\producer\producer.py --threads 1 --count 1 --rate 0 --size 512 --out .\results\p3-smoke
```

The producer test suite checks exact body sizing, count and duration behavior,
passive queue declaration, CSV/summary output, and preservation of message IDs
across simulated connection loss.
