#!/usr/bin/env python3
"""Plot what Prometheus recorded during a time window (owner: P2).

Use it to turn a chaos or benchmark run into a figure for the report, from the same
metrics the Grafana dashboards show:
  1. broker message rates (published, delivered, acknowledged)  - the dip and recovery
  2. RabbitMQ nodes up (scrape status)                           - which node was down
  3. Raft term of the queue per node                             - a step = leader election

Usage:
  python3 scripts/mgmt/plot_prometheus.py --start 2026-11-11T11:30:00Z --end 2026-11-11T11:32:00Z \
      --title "Leader crash, run 1" --out docs/evidence/p2-leader-crash-run1.png
  python3 scripts/mgmt/plot_prometheus.py --run results/chaos/leader-crash/run1 --out ...
      (takes the window from the run's producer.log)
Needs: matplotlib.  Prometheus at PROM_URL (default http://localhost:9090).
"""
import argparse
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
NODE_COLORS = {"rabbit1": "#2a78d6", "rabbit2": "#eb6834", "rabbit3": "#1baf7a"}
RATE_COLORS = ["#2a78d6", "#eb6834", "#1baf7a"]


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def query_range(url, q, start, end, step):
    p = urllib.parse.urlencode({"query": q, "start": start, "end": end, "step": step})
    with urllib.request.urlopen(f"{url}/api/v1/query_range?{p}", timeout=20) as r:
        return json.load(r)["data"]["result"]


def window_from_run(run_dir, pad):
    times = []
    with open(os.path.join(run_dir, "producer.log")) as f:
        for line in f:
            m = re.search(r'"ts":"([^"]+)"', line)
            if m:
                times.append(ts(m.group(1)))
    if not times:
        raise SystemExit(f"no timestamps in {run_dir}/producer.log")
    return min(times) - pad, max(times) + pad


def with_gaps(values, t0, step):
    """x/y lists with a break (None) wherever Prometheus has no sample, so a line is
    never drawn across a period in which nothing could be scraped."""
    xs, ys, last = [], [], None
    for t, v in values:
        t = float(t)
        if last is not None and t - last > 2.5 * step:
            xs.append(None); ys.append(None)
        xs.append(t - t0); ys.append(float(v)); last = t
    return [x if x is not None else float("nan") for x in xs], [y if y is not None else float("nan") for y in ys]


def node(metric):
    m = re.match(r"(rabbit\d+)", metric.get("instance", ""))
    return m.group(1) if m else metric.get("instance", "?")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--run", help="chaos/benchmark run folder with producer.log (sets the window)")
    ap.add_argument("--pad", type=float, default=10, help="seconds added before/after a --run window")
    ap.add_argument("--queue", default="hw2.orders")
    ap.add_argument("--title", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--prom-url", default=os.environ.get("PROM_URL", "http://localhost:9090"))
    a = ap.parse_args()
    if a.run:
        start, end = window_from_run(a.run, a.pad)
    elif a.start and a.end:
        start, end = ts(a.start), ts(a.end)
    else:
        ap.error("give --run or --start and --end")
    step = 2

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    rates = [("published", "rabbitmq_global_messages_received_total"),
             ("delivered", "rabbitmq_global_messages_delivered_consume_manual_ack_total"),
             ("acknowledged", "rabbitmq_global_messages_acknowledged_total")]
    fig, axes = plt.subplots(3, 1, figsize=(7.2, 6.6), dpi=150, sharex=True,
                             gridspec_kw={"height_ratios": [2.2, 1, 1.4]})
    fig.patch.set_facecolor(SURFACE)
    t0 = start

    ax = axes[0]
    for (label, metric), c in zip(rates, RATE_COLORS):
        res = query_range(a.prom_url, f"sum(rate({metric}[10s]))", start, end, step)
        if res:
            xs, ys = with_gaps(res[0]["values"], t0, step)
            ax.plot(xs, ys, color=c, linewidth=2, label=label)
    ax.set_ylabel("messages / s", color=INK2)
    ax.text(0.99, 0.97, "gaps = no node could be scraped", transform=ax.transAxes, ha="right", va="top", fontsize=7, color=INK2)
    ax.legend(frameon=False, fontsize=8, labelcolor=INK2, ncol=3, loc="lower left", bbox_to_anchor=(0, 1.0))

    ax = axes[1]
    res = query_range(a.prom_url, 'up{job="rabbitmq"}', start, end, step)
    for r in sorted(res, key=lambda r: node(r["metric"])):
        n = node(r["metric"])
        i = int(n[-1]) if n[-1].isdigit() else 0
        xs = [float(t) - t0 for t, v in r["values"]]
        ys = [i + 0.3 * (float(v) - 0.5) for t, v in r["values"]]
        ax.step(xs, ys, where="post", color=NODE_COLORS.get(n, INK2), linewidth=2, label=n)
    ax.set_yticks([1, 2, 3])
    ax.set_yticklabels(["rabbit1", "rabbit2", "rabbit3"])
    ax.set_ylim(0.4, 3.6)
    ax.set_ylabel("node up\n(high = up)", color=INK2)

    ax = axes[2]
    res = query_range(a.prom_url, f'rabbitmq_detailed_raft_term_total{{queue="{a.queue}"}}', start, end, step)
    for r in sorted(res, key=lambda r: node(r["metric"])):
        n = node(r["metric"])
        xs, ys = with_gaps(r["values"], t0, step)
        ax.step(xs, ys, where="post", color=NODE_COLORS.get(n, INK2), linewidth=2, label=n)
    terms = [float(v) for r in res for _, v in r["values"]]
    if terms:
        lo, hi = int(min(terms)), int(max(terms))
        ax.set_ylim(lo - 0.5, hi + 0.5)
        ax.set_yticks(range(lo, hi + 1))
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_ylabel(f"Raft term\n{a.queue}", color=INK2)
    ax.set_xlabel(f"seconds since {datetime.fromtimestamp(t0, timezone.utc).strftime('%H:%M:%S')} UTC", color=INK2)
    ax.legend(frameon=False, fontsize=8, labelcolor=INK2, ncol=3, loc="upper left")

    for ax in axes:
        ax.set_facecolor(SURFACE)
        ax.grid(axis="y", color=GRID, linewidth=1)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(GRID)
        ax.tick_params(colors=INK2, labelsize=8)
    axes[0].set_ylim(bottom=0)
    fig.suptitle(a.title or "Prometheus view of the run", x=0.02, ha="left", fontsize=11, color=INK)
    fig.tight_layout()
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    fig.savefig(a.out, facecolor=SURFACE)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
