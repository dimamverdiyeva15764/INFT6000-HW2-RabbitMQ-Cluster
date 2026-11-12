#!/usr/bin/env python3
"""Build the report's data-integrity table (section 8.5) from raw chaos results.

Reads results/chaos/<scenario>/run<k>/{validation.json, producer_summary.json, consumer_summary.json}
and prints a Markdown table (one row per scenario x run). Never edits raw files.

Usage: python3 scripts/p4/summarize_chaos.py [results/chaos] [> docs/evidence/p4-data-integrity.md]
"""
import json
import sys
from pathlib import Path


def load(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "results/chaos")
    runs = sorted(
        (p for p in root.glob("*/run*") if (p / "validation.json").exists()),
        key=lambda p: (p.parent.name, int(p.name[3:]) if p.name[3:].isdigit() else 0),
    )
    if not runs:
        print(f"No validation.json files found under {root}. Run scripts/p4/chaos_run.sh first.", file=sys.stderr)
        return 1
    print("| Scenario | Run | Confirmed | Received (unique) | **Lost** | Duplicates | Redelivered | "
          "Out-of-order (per consumer) | Producer republished | Producer reconnects | Consumer reconnects | Verdict |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    total_confirmed = total_lost = 0
    all_pass = True
    for run in runs:
        v, ps, cs = load(run / "validation.json"), load(run / "producer_summary.json"), load(run / "consumer_summary.json")
        total_confirmed += v.get("confirmed", 0)
        total_lost += v.get("lost", 0)
        all_pass &= v.get("verdict") == "PASS"
        print(
            f"| {run.parent.name} | {run.name[3:]} | {v.get('confirmed')} | {v.get('received_unique')} | "
            f"**{v.get('lost')}** | {v.get('duplicates')} | {v.get('redelivered_flag')} | "
            f"{v.get('out_of_order_per_consumer')} | {ps.get('republished', 'n/a')} | {ps.get('reconnects', 'n/a')} | "
            f"{cs.get('reconnects', 'n/a')} | {v.get('verdict')} |"
        )
    print()
    print(f"**Total:** {len(runs)} runs, {total_confirmed} confirmed messages, **{total_lost} lost**, "
          f"overall {'PASS' if all_pass and total_lost == 0 else 'FAIL'}.")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
