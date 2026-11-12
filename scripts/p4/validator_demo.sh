#!/usr/bin/env bash
# Shows the validator catching planted errors, then passing a clean run.
# Needs no cluster and no Docker.
# Usage: ./scripts/p4/validator_demo.sh
set -uo pipefail
cd "$(dirname "$0")/../.."
PY="${PYTHON:-python3}"
D="$(mktemp -d)"
$PY - "$D" <<'PYEOF'
import csv, sys
d = sys.argv[1]; base = 10**18
with open(f"{d}/confirmed.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["msg_id","producer_id","seq","sent_ts_ns","confirm_ts_ns"])
    for s in range(1, 21): w.writerow([f"P-{s}","P",s,base+s*1000,base+s*1000+500])
def recv(path, drop=(), dup=(), swap=None):
    order = list(range(1, 21))
    if swap: a, b = swap; i, j = order.index(a), order.index(b); order[i], order[j] = order[j], order[i]
    with open(path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["msg_id","producer_id","seq","sent_ts_ns","recv_ts_ns","redelivered","consumer_id"])
        t = base + 10**7
        for s in order:
            t += 10**6
            if s in drop: continue
            w.writerow([f"P-{s}","P",s,base+s*1000,t,"false","c1"])
            if s in dup: t += 10**6; w.writerow([f"P-{s}","P",s,base+s*1000,t,"true","c1"])
recv(f"{d}/bad_received.csv", drop={5, 11}, dup={2, 8, 15}, swap=(17, 18))
recv(f"{d}/good_received.csv", dup={2, 8})
PYEOF
echo "##### 1) Planted errors: 2 messages lost, 3 duplicated, 1 reordered -> must FAIL (exit 1)"
$PY consumer/validate.py --confirmed "$D/confirmed.csv" --received "$D/bad_received.csv"; echo "exit code: $?"
echo
echo "##### 2) Clean run (2 harmless duplicates, nothing lost) -> must PASS (exit 0)"
$PY consumer/validate.py --confirmed "$D/confirmed.csv" --received "$D/good_received.csv"; echo "exit code: $?"
rm -rf "$D"
