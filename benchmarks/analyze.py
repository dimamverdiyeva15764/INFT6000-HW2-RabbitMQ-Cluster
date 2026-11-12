#!/usr/bin/env python3
"""Benchmark analysis.

Reads every run in benchmarks/results/raw/<scenario>/rep<k>/ (written by run_bench.py) and writes:
  benchmarks/results/summary_runs.csv       one row per run
  benchmarks/results/summary_scenarios.csv  mean and std over the repetitions
  benchmarks/results/summary.md             the same as a Markdown table
  benchmarks/results/fig_*.png              charts

Definitions (measurement window = [first send + warmup, last send]):
  publish throughput  = confirmed messages sent inside the window / window length      (msg/s)
  consume throughput  = first deliveries received inside the window / window length    (msg/s)
  end-to-end latency  = recv_ts_ns - sent_ts_ns of the FIRST delivery of each message  (ms)
  confirm latency     = confirm_ts_ns - sent_ts_ns                                       (ms)
  broker publish rate = mean of sum(rate(rabbitmq_global_messages_received_total)) from Prometheus
Loss and ordering are not judged here; that is the job of consumer/validate.py.
"""
import argparse
import glob
import json
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NS = 1e9

# Chart style shared by all figures.
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
C = ["#2a78d6", "#eb6834", "#1baf7a"]


def pct(s, q):
    return float(s.quantile(q)) if len(s) else float("nan")


def csv_path(d, name):
    """Raw CSVs may be stored gzip-compressed (name.csv.gz) to keep the repository small."""
    for p in (os.path.join(d, name), os.path.join(d, name + ".gz")):
        if os.path.exists(p):
            return p
    return None


def analyze_run(d, warmup_override=None):
    meta = json.load(open(os.path.join(d, "meta.json")))
    p = meta["params"]
    warmup = p.get("warmup", 5) if warmup_override is None else warmup_override
    row = {"scenario": meta["scenario"], "group": meta.get("group"), "rep": meta["rep"],
           "producer_threads": p["producer_threads"], "consumer_threads": p["consumer_threads"],
           "size_bytes": p["size"], "prefetch": p["prefetch"], "rate_per_thread": p["rate"],
           "duration_s": p["duration"], "producer_rc": meta["exit_codes"]["producer"],
           "consumer_rc": meta["exit_codes"]["consumer"], "drained": meta.get("drained"), "path": d}
    cf, rf = csv_path(d, "confirmed.csv"), csv_path(d, "received.csv")
    if not (cf and rf):
        row["status"] = "missing csv"
        return row
    conf = pd.read_csv(cf, usecols=["msg_id", "sent_ts_ns", "confirm_ts_ns"])
    recv = pd.read_csv(rf, usecols=["msg_id", "sent_ts_ns", "recv_ts_ns", "redelivered"])
    if conf.empty:
        row["status"] = "no confirmed messages"
        return row
    first = recv.sort_values("recv_ts_ns").drop_duplicates("msg_id", keep="first")
    t0 = conf["sent_ts_ns"].min()
    ws = t0 + warmup * NS
    we = conf["sent_ts_ns"].max()
    win = (we - ws) / NS
    if win <= 0:
        row["status"] = "window too short"
        return row
    in_conf = conf[conf["sent_ts_ns"] >= ws]
    in_first = first[first["sent_ts_ns"] >= ws]
    e2e = (in_first["recv_ts_ns"] - in_first["sent_ts_ns"]) / 1e6
    cl = (in_conf["confirm_ts_ns"] - in_conf["sent_ts_ns"]) / 1e6
    row.update({
        "status": "ok",
        "window_s": round(win, 2),
        "confirmed_total": len(conf),
        "deliveries_total": len(recv),
        "received_unique_total": len(first),
        "duplicate_deliveries": len(recv) - len(first),
        "redelivered_flag": int(recv["redelivered"].astype(str).str.lower().eq("true").sum()),
        "not_received_info": int((~conf["msg_id"].isin(first["msg_id"])).sum()),
        "pub_msg_s": len(conf[(conf["sent_ts_ns"] >= ws) & (conf["sent_ts_ns"] <= we)]) / win,
        "cons_msg_s": len(first[(first["recv_ts_ns"] >= ws) & (first["recv_ts_ns"] <= we)]) / win,
        "e2e_p50_ms": pct(e2e, .50), "e2e_p95_ms": pct(e2e, .95), "e2e_p99_ms": pct(e2e, .99),
        "e2e_max_ms": float(e2e.max()) if len(e2e) else float("nan"),
        "confirm_p50_ms": pct(cl, .50), "confirm_p99_ms": pct(cl, .99),
    })
    row["pub_MB_s"] = row["pub_msg_s"] * p["size"] / 1e6
    ps = os.path.join(d, "producer_summary.json")
    if os.path.exists(ps):
        s = json.load(open(ps))
        row.update({"nacked": s.get("nacked"), "republished": s.get("republished"), "reconnects": s.get("reconnects")})
    prom = meta.get("prometheus") or {}
    for k in ("published_rate", "delivered_rate"):
        row[f"broker_{k}"] = (prom.get(k) or {}).get("mean")
    row["broker_max_queue_depth"] = (prom.get("queue_depth") or {}).get("max")
    row["broker_raft_commit_latency_ms"] = ((prom.get("raft_commit_latency_s") or {}).get("mean") or float("nan")) * 1000
    return row


METRICS = ["pub_msg_s", "cons_msg_s", "pub_MB_s", "e2e_p50_ms", "e2e_p95_ms", "e2e_p99_ms", "confirm_p50_ms",
           "confirm_p99_ms", "broker_published_rate", "broker_max_queue_depth", "broker_raft_commit_latency_ms"]
KEYS = ["scenario", "group", "producer_threads", "consumer_threads", "size_bytes", "prefetch"]


def summarize(runs):
    ok = runs[runs["status"] == "ok"]
    g = ok.groupby(KEYS, dropna=False)
    s = g[METRICS].agg(["mean", "std"])
    s.columns = [f"{m}_{a}" for m, a in s.columns]
    s["reps"] = g.size()
    for c in ["duplicate_deliveries", "not_received_info"]:
        s[f"{c}_sum"] = g[c].sum()
    return s.reset_index()


def fmt(m, sd, d=0):
    if pd.isna(m):
        return "-"
    return f"{m:,.{d}f}" + ("" if pd.isna(sd) else f" ± {sd:,.{d}f}")


def markdown(summary):
    lines = ["| Scenario | Prod. thr. | Cons. thr. | Size (B) | Prefetch | Publish (msg/s) | Consume (msg/s) | "
             "E2E p50 (ms) | E2E p95 (ms) | E2E p99 (ms) | Confirm p99 (ms) | Reps |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for _, r in summary.iterrows():
        lines.append(f"| {r.scenario} | {r.producer_threads} | {r.consumer_threads} | {r.size_bytes} | {r.prefetch} | "
                     f"{fmt(r.pub_msg_s_mean, r.pub_msg_s_std)} | {fmt(r.cons_msg_s_mean, r.cons_msg_s_std)} | "
                     f"{fmt(r.e2e_p50_ms_mean, r.e2e_p50_ms_std, 1)} | {fmt(r.e2e_p95_ms_mean, r.e2e_p95_ms_std, 1)} | "
                     f"{fmt(r.e2e_p99_ms_mean, r.e2e_p99_ms_std, 1)} | {fmt(r.confirm_p99_ms_mean, r.confirm_p99_ms_std, 1)} | "
                     f"{r.reps} |")
    return "\n".join(lines) + "\n\nValues: mean ± standard deviation over the repetitions.\n"


# ------------------------------------------------------------------ charts
def style(ax, title, xlabel, ylabel):
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=11, color=INK, pad=24)
    ax.set_xlabel(xlabel, color=INK2)
    ax.set_ylabel(ylabel, color=INK2)
    ax.grid(axis="y", color=GRID, linewidth=1, linestyle="-")
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.xaxis.set_minor_locator(__import__("matplotlib").ticker.NullLocator())
    ax.set_ylim(bottom=0)


def legend_top(ax, n):
    ax.legend(frameon=False, fontsize=9, labelcolor=INK2, ncol=n, loc="lower left",
              bbox_to_anchor=(0, 1.0), borderaxespad=0.2, handlelength=1.6)


def series(ax, x, y, err, label, color):
    ax.errorbar(x, y, yerr=err, color=color, linewidth=2, marker="o", markersize=8, markeredgecolor=SURFACE,
                markeredgewidth=2, capsize=3, elinewidth=1, label=label, solid_capstyle="round")


def chart_lines(plt, sub, xcol, ylist, title, xlabel, ylabel, path, logx=False, xticks=None):
    fig, ax = plt.subplots(figsize=(6.4, 3.8), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    sub = sub.sort_values(xcol)
    for i, (col, label) in enumerate(ylist):
        series(ax, sub[xcol], sub[f"{col}_mean"], sub[f"{col}_std"].fillna(0), label, C[i])
    if logx:
        ax.set_xscale("log", base=2)
    if xticks:
        ax.set_xticks(xticks[0])
        ax.set_xticklabels(xticks[1])
    style(ax, title, xlabel, ylabel)
    if len(ylist) > 1:
        legend_top(ax, len(ylist))
        last = sub.iloc[-1]
        ends = sorted(float(last[f"{c}_mean"]) for c, _ in ylist)
        top = max(ends) or 1
        if all(b - a > 0.06 * top for a, b in zip(ends, ends[1:])):   # only when labels cannot collide
            for col, label in ylist:                                  # direct label at the line end
                ax.annotate(label, (last[xcol], last[f"{col}_mean"]), xytext=(8, 0), textcoords="offset points",
                            va="center", fontsize=8, color=INK2)
    ax.margins(x=0.12)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


def charts(summary, runs, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    made = []
    thr = [("pub_msg_s", "publish (confirmed)"), ("cons_msg_s", "consume (first delivery)")]
    lat = [("e2e_p50_ms", "p50"), ("e2e_p95_ms", "p95"), ("e2e_p99_ms", "p99")]

    b2 = summary[summary["group"].isin(["B2"])]
    if len(b2) >= 2:
        th = sorted(b2["producer_threads"].unique())
        tk = (th, [str(t) for t in th])
        made.append(chart_lines(plt, b2, "producer_threads", thr, "Throughput vs producer threads (4 consumers, 1 KB)",
                                "producer threads", "messages / s", os.path.join(out, "fig_b2_throughput.png"),
                                logx=True, xticks=tk))
        made.append(chart_lines(plt, b2, "producer_threads", lat, "End-to-end latency vs producer threads",
                                "producer threads", "latency (ms)", os.path.join(out, "fig_b2_latency.png"),
                                logx=True, xticks=tk))
    b3 = pd.concat([summary[summary["group"] == "B3"], summary[summary["scenario"] == "B2-p4"]])
    if len(b3) >= 2:
        sizes = sorted(b3["size_bytes"].unique())
        labels = [f"{s // 1024} KB" if s >= 1024 else f"{s} B" for s in sizes]
        made.append(chart_lines(plt, b3, "size_bytes", lat, "End-to-end latency vs message size (4 + 4 threads)",
                                "message body size", "latency (ms)", os.path.join(out, "fig_b3_latency.png"),
                                logx=True, xticks=(sizes, labels)))
        made.append(chart_lines(plt, b3, "size_bytes", [("pub_MB_s", "publish")], "Payload throughput vs message size",
                                "message body size", "MB / s", os.path.join(out, "fig_b3_mbps.png"),
                                logx=True, xticks=(sizes, labels)))
    b4 = summary[summary["group"] == "B4"]
    if len(b4) >= 2:
        pf = sorted(b4["prefetch"].unique())
        made.append(chart_lines(plt, b4, "prefetch", thr, "Throughput vs consumer prefetch", "prefetch (per channel)",
                                "messages / s", os.path.join(out, "fig_b4_throughput.png"), logx=True,
                                xticks=(pf, [str(x) for x in pf])))
        made.append(chart_lines(plt, b4, "prefetch", lat, "End-to-end latency vs consumer prefetch",
                                "prefetch (per channel)", "latency (ms)", os.path.join(out, "fig_b4_latency.png"),
                                logx=True, xticks=(pf, [str(x) for x in pf])))
    # per-second rates of the first baseline run: shows warm-up and steady state
    b1 = runs[(runs["group"] == "B1") & (runs["status"] == "ok")].sort_values("rep")
    if len(b1):
        d = b1.iloc[0]["path"]
        conf = pd.read_csv(csv_path(d, "confirmed.csv"), usecols=["sent_ts_ns"])
        recv = pd.read_csv(csv_path(d, "received.csv"), usecols=["msg_id", "recv_ts_ns"]).drop_duplicates("msg_id")
        t0 = conf["sent_ts_ns"].min()
        full = int((conf["sent_ts_ns"].max() - t0) // NS)      # drop the last, partial second
        p = ((conf["sent_ts_ns"] - t0) // NS).value_counts().sort_index().loc[:full - 1]
        c = ((recv["recv_ts_ns"] - t0) // NS).value_counts().sort_index().loc[:full - 1]
        fig, ax = plt.subplots(figsize=(6.4, 3.6), dpi=150)
        fig.patch.set_facecolor(SURFACE)
        ax.plot(p.index, p.values, color=C[0], linewidth=2, label="published (confirmed)")
        ax.plot(c.index, c.values, color=C[1], linewidth=2, label="consumed")
        warm = json.load(open(os.path.join(d, "meta.json")))["params"].get("warmup", 5)
        ax.axvline(warm, color=INK2, linewidth=1)
        ax.text(warm, ax.get_ylim()[1] * 0.02, "  end of warm-up", color=INK2, fontsize=8, va="bottom")
        style(ax, f"Baseline run ({b1.iloc[0]['scenario']} rep{b1.iloc[0]['rep']}): messages per second",
              "seconds since first send", "messages / s")
        legend_top(ax, 2)
        fig.tight_layout()
        path = os.path.join(out, "fig_b1_timeseries.png")
        fig.savefig(path, facecolor=SURFACE)
        plt.close(fig)
        made.append(path)
    return made


def main():
    ap = argparse.ArgumentParser(description="Analyze HW2 benchmark runs")
    ap.add_argument("--raw", default=os.path.join(ROOT, "benchmarks", "results", "raw"))
    ap.add_argument("--out", default=os.path.join(ROOT, "benchmarks", "results"))
    ap.add_argument("--warmup", type=float, help="override warm-up seconds")
    ap.add_argument("--no-charts", action="store_true")
    a = ap.parse_args()

    dirs = sorted(os.path.dirname(m) for m in glob.glob(os.path.join(a.raw, "*", "rep*", "meta.json")))
    if not dirs:
        sys.exit(f"no runs found under {a.raw} (run benchmarks/run_bench.py first)")
    runs = pd.DataFrame([analyze_run(d, a.warmup) for d in dirs])
    os.makedirs(a.out, exist_ok=True)
    runs.to_csv(os.path.join(a.out, "summary_runs.csv"), index=False)
    bad = runs[runs["status"] != "ok"]
    for _, r in bad.iterrows():
        print(f"  !! {r['scenario']} rep{r['rep']}: {r['status']} ({r['path']})")
    summary = summarize(runs)
    order = {k: i for i, k in enumerate(["B1", "B2", "B3", "B4"])}
    summary = summary.sort_values(["group", "producer_threads", "size_bytes", "prefetch"],
                                  key=lambda s: s.map(order) if s.name == "group" else s)
    summary.to_csv(os.path.join(a.out, "summary_scenarios.csv"), index=False)
    with open(os.path.join(a.out, "summary.md"), "w") as f:
        f.write(markdown(summary))
    print(f"{len(runs)} runs ({len(bad)} not usable), {len(summary)} scenarios -> {a.out}/summary_*.csv, summary.md")
    print(markdown(summary))
    if not a.no_charts:
        for p in charts(summary, runs, a.out):
            print("  chart:", p)


if __name__ == "__main__":
    main()
