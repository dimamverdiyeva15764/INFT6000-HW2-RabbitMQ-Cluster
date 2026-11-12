"""Zero-data-loss validator (owner: P4).

Joins what the producer got publisher-confirms for (``confirmed.csv``) with
what the consumer actually received (``received.csv``) and reports:

* confirmed ................ unique msg_ids the broker confirmed
* received (unique) ........ unique msg_ids the consumer saw
* LOST ..................... confirmed but never received   -> must be 0
* duplicates ............... extra deliveries of an already-seen msg_id
* out-of-order (per consumer) first deliveries (not redelivered) whose seq is lower
                             than the highest seq that SAME consumer already got from
                             that producer. RabbitMQ guarantees this is 0 for a queue.
* out-of-order (global) .... same check over the merged arrival order of all
                             consumers; only meaningful with ONE consumer thread
* unconfirmed-but-delivered  received but never confirmed (legal: the producer
                             crashed/lost the confirm; at-least-once)
* end-to-end latency ....... p50 / p95 / p99 / max of recv_ts - sent_ts (ms)

Exit code: 0 = PASS, 1 = FAIL (lost > 0, or per-consumer out-of-order > 0 with --strict-order).

Usage (docs/CONTRACT.md section 5)::

    python3 consumer/validate.py --confirmed DIR/confirmed.csv --received DIR/received.csv \
        [--json DIR/validation.json] [--strict-order]

Pure standard library: runs anywhere Python 3.9+ runs.
"""

import argparse
import csv
import gzip
import json
import sys


def _percentile(sorted_values, q):
    if not sorted_values:
        return None
    pos = (len(sorted_values) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def _read_rows(paths):
    for path in paths:
        opener = gzip.open if str(path).endswith(".gz") else open   # archived runs are gzip-compressed
        with opener(path, "rt", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                yield row


def validate(confirmed_paths, received_paths):
    """Return a dict with every metric. Accepts one path or a list of paths."""
    if isinstance(confirmed_paths, str):
        confirmed_paths = [confirmed_paths]
    if isinstance(received_paths, str):
        received_paths = [received_paths]

    confirmed = {}  # msg_id -> producer_id
    confirmed_rows = 0
    for row in _read_rows(confirmed_paths):
        confirmed_rows += 1
        confirmed[row["msg_id"]] = row["producer_id"]

    deliveries = []
    for row in _read_rows(received_paths):
        deliveries.append(
            (
                int(row["recv_ts_ns"]),
                row["msg_id"],
                row["producer_id"],
                int(row["seq"]),
                int(row["sent_ts_ns"]),
                str(row.get("redelivered", "")).strip().lower() == "true",
                row.get("consumer_id", "") or "?",
            )
        )
    deliveries.sort(key=lambda d: d[0])  # arrival order

    seen = set()
    last_seq = {}
    last_seq_consumer = {}
    out_of_order = 0
    out_of_order_consumer = 0
    redelivered_flag = 0
    latencies_ms = []
    per_producer = {}
    for _recv, msg_id, producer, seq, sent, redelivered, consumer in deliveries:
        if redelivered:
            redelivered_flag += 1
        if msg_id in seen:
            continue
        seen.add(msg_id)
        latencies_ms.append((_recv - sent) / 1e6)
        if seq < last_seq.get(producer, 0):
            out_of_order += 1
        else:
            last_seq[producer] = seq
        if not redelivered:
            key = (producer, consumer)
            if seq < last_seq_consumer.get(key, 0):
                out_of_order_consumer += 1
                per_producer.setdefault(producer, {"out_of_order": 0})["out_of_order"] += 1
            else:
                last_seq_consumer[key] = seq

    lost_ids = sorted(set(confirmed) - seen)
    unconfirmed_delivered = sorted(seen - set(confirmed))
    latencies_ms.sort()
    result = {
        "confirmed": len(confirmed),
        "confirmed_rows": confirmed_rows,
        "received_unique": len(seen),
        "received_deliveries": len(deliveries),
        "lost": len(lost_ids),
        "lost_ids_sample": lost_ids[:20],
        "duplicates": len(deliveries) - len(seen),
        "redelivered_flag": redelivered_flag,
        "out_of_order": out_of_order,
        "out_of_order_per_consumer": out_of_order_consumer,
        "unconfirmed_but_delivered": len(unconfirmed_delivered),
        "latency_ms": {
            "p50": _percentile(latencies_ms, 0.50),
            "p95": _percentile(latencies_ms, 0.95),
            "p99": _percentile(latencies_ms, 0.99),
            "max": latencies_ms[-1] if latencies_ms else None,
        },
        "per_producer_out_of_order": per_producer,
    }
    return result


def verdict(result, strict_order=False):
    ok = result["lost"] == 0 and result["confirmed"] > 0
    if strict_order and result["out_of_order_per_consumer"] > 0:
        ok = False
    return "PASS" if ok else "FAIL"


def _fmt(v):
    return "n/a" if v is None else f"{v:.2f}"


def print_table(result, status, strict_order=False):
    lat = result["latency_ms"]
    rows = [
        ("Confirmed by broker (unique)", result["confirmed"], ""),
        ("Received (unique)", result["received_unique"], ""),
        ("LOST (confirmed, never received)", result["lost"], "must be 0"),
        ("Duplicate deliveries", result["duplicates"], "allowed (at-least-once); consumer de-dups"),
        ("  of which flagged redelivered", result["redelivered_flag"], ""),
        ("Out-of-order, per consumer", result["out_of_order_per_consumer"],
         "must be 0 (queue order guarantee)" + (" [strict: fails run]" if strict_order else "")),
        ("Out-of-order, global arrival", result["out_of_order"],
         "info only (undefined with >1 competing consumer)"),
        ("Unconfirmed but delivered", result["unconfirmed_but_delivered"], "allowed (confirm lost in crash)"),
        ("Latency p50 / p95 / p99 / max (ms)",
         f"{_fmt(lat['p50'])} / {_fmt(lat['p95'])} / {_fmt(lat['p99'])} / {_fmt(lat['max'])}", ""),
    ]
    width = max(len(r[0]) for r in rows)
    print("=" * (width + 40))
    print("VALIDATION REPORT")
    print("=" * (width + 40))
    for name, value, note in rows:
        print(f"{name:<{width}}  {str(value):>22}  {note}")
    print("-" * (width + 40))
    if result["lost"]:
        print(f"Lost message ids (first {len(result['lost_ids_sample'])}): {result['lost_ids_sample']}")
    if result["confirmed"] == 0:
        print("No confirmed messages found - nothing was proven.")
    print(f"RESULT: {status}")


def main(argv=None):
    p = argparse.ArgumentParser(description="Validate zero data loss, duplicates and ordering")
    p.add_argument("--confirmed", nargs="+", required=True, help="producer confirmed.csv (one or more)")
    p.add_argument("--received", nargs="+", required=True, help="consumer received.csv (one or more)")
    p.add_argument("--json", help="also write the result as JSON to this path")
    p.add_argument("--strict-order", action="store_true",
                   help="also fail when per-consumer out-of-order > 0")
    args = p.parse_args(argv)

    result = validate(args.confirmed, args.received)
    status = verdict(result, args.strict_order)
    result["verdict"] = status
    print_table(result, status, args.strict_order)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
            f.write("\n")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
