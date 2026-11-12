#!/usr/bin/env python3
"""SELFTEST ONLY - NOT A REAL CLIENT, NO RABBITMQ. Writes a synthetic confirmed.csv with the
CLI and columns of docs/CONTRACT.md so run_bench.py / analyze.py can be tested before P3's
producer exists. Numbers it produces are invented and must never be reported."""
import argparse, csv, os, random, time
ap = argparse.ArgumentParser()
for f in ("--hosts", "--queue"): ap.add_argument(f)
for f, d in (("--threads", 1), ("--duration", 5), ("--rate", 0), ("--size", 1024), ("--count", 0)):
    ap.add_argument(f, type=int, default=d)
ap.add_argument("--out", required=True)
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
t0 = time.time_ns(); time.sleep(a.duration)
rate = (a.rate or 300) * a.threads
with open(os.path.join(a.out, "confirmed.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["msg_id", "producer_id", "seq", "sent_ts_ns", "confirm_ts_ns"])
    n = int(rate * a.duration)
    for i in range(n):
        t = a.threads and i % a.threads; pid = f"fake-t{t}"; seq = i // a.threads + 1
        s = t0 + int(i / rate * 1e9)
        w.writerow([f"{pid}-{seq}", pid, seq, s, s + int(random.lognormvariate(1.2, .4) * 1e6)])
print('{"event":"selftest_producer_done","confirmed":%d}' % n)
