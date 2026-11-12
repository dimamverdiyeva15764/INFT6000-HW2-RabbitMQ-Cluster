#!/usr/bin/env python3
"""SELFTEST ONLY - NOT A REAL CLIENT, NO RABBITMQ. Waits for SIGINT like the real consumer
(docs/CONTRACT.md section 4), then writes a synthetic received.csv from the fake confirmed.csv
(with a few duplicate deliveries). Numbers are invented and must never be reported."""
import argparse, csv, os, random, signal, time
ap = argparse.ArgumentParser()
for f in ("--hosts", "--queue"): ap.add_argument(f)
for f, d in (("--threads", 1), ("--prefetch", 100)): ap.add_argument(f, type=int, default=d)
ap.add_argument("--out", required=True)
a = ap.parse_args()
stop = []
signal.signal(signal.SIGINT, lambda *_: stop.append(1)); signal.signal(signal.SIGTERM, lambda *_: stop.append(1))
while not stop: time.sleep(0.1)
rows = list(csv.DictReader(open(os.path.join(a.out, "confirmed.csv")))) if os.path.exists(os.path.join(a.out, "confirmed.csv")) else []
with open(os.path.join(a.out, "received.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["msg_id", "producer_id", "seq", "sent_ts_ns", "recv_ts_ns", "redelivered", "consumer_id"])
    for i, r in enumerate(rows):
        rt = int(r["sent_ts_ns"]) + int(random.lognormvariate(1.6, .5) * 1e6 * (1 + a.prefetch / 500))
        w.writerow([r["msg_id"], r["producer_id"], r["seq"], r["sent_ts_ns"], rt, "false", f"fake-c{i % a.threads}"])
        if i % 997 == 0:
            w.writerow([r["msg_id"], r["producer_id"], r["seq"], r["sent_ts_ns"], rt + 5_000_000, "true", "fake-c0"])
print('{"event":"selftest_consumer_done","received":%d}' % len(rows))
