#!/usr/bin/env python3
"""Benchmark runner.

For every scenario x repetition in benchmarks/scenarios.yaml:
  1. waits until all 3 nodes run and hw2.orders has 3/3 members online
  2. purges hw2.orders (so every run starts from an empty queue)
  3. starts the consumer, then the producer (commands from scenarios.yaml / docs/CONTRACT.md)
  4. after the producer exits, waits until the queue is drained, then stops the consumer with SIGINT
  5. asks Prometheus for the broker-side rates during the run (independent of the client CSVs)
  6. saves everything to benchmarks/results/raw/<scenario>/rep<k>/  (never overwritten)

Usage (from the repository root, cluster running):
  python3 benchmarks/run_bench.py --dry-run            # print what would run
  python3 benchmarks/run_bench.py --only B1            # one group (or scenario id), all repeats
  python3 benchmarks/run_bench.py                      # whole matrix; re-running resumes missing runs
  python3 benchmarks/run_bench.py --only B2-p4 --repeats 1 --duration 20   # quick try
Needs: pip install -r benchmarks/requirements.txt  (pyyaml; analyze.py also needs pandas, matplotlib)
"""
import argparse
import base64
import json
import os
import platform
import shlex
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def now_iso(ts=None):
    return datetime.fromtimestamp(ts or time.time(), timezone.utc).isoformat(timespec="milliseconds")


def log(msg):
    print(f"[{now_iso()}] {msg}", flush=True)


class Broker:
    """Management HTTP API with failover across the three host ports."""

    def __init__(self, ports=(15672, 15673, 15674), vhost="/"):
        user = os.environ.get("RABBITMQ_USER", "admin")
        pw = os.environ.get("RABBITMQ_PASS", "admin123")
        self.auth = "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()
        self.ports, self.vhost = list(ports), urllib.parse.quote(vhost, safe="")

    def call(self, method, path, timeout=5):
        last = None
        for p in self.ports:
            req = urllib.request.Request(f"http://localhost:{p}/api/{path}", method=method,
                                         headers={"Authorization": self.auth})
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    body = r.read()
                    return json.loads(body) if body else None
            except urllib.error.HTTPError as e:
                raise RuntimeError(f"{method} {path}: HTTP {e.code} {e.read()[:200]!r}")
            except Exception as e:  # node down -> try the next port
                last = e
        raise RuntimeError(f"no management API reachable ({last})")

    def queue(self, name):
        return self.call("GET", f"queues/{self.vhost}/{urllib.parse.quote(name, safe='')}")

    def healthy(self, queue):
        nodes = self.call("GET", "nodes")
        q = self.queue(queue)
        ok = all(n.get("running") for n in nodes) and len(nodes) == 3 \
            and len(q.get("online") or []) == len(q.get("members") or []) == 3
        return ok, {"nodes_running": sum(bool(n.get("running")) for n in nodes),
                    "members_online": len(q.get("online") or []), "leader": q.get("leader")}

    def purge(self, queue):
        self.call("DELETE", f"queues/{self.vhost}/{urllib.parse.quote(queue, safe='')}/contents")

    def overview(self):
        o = self.call("GET", "overview")
        return {k: o.get(k) for k in ("cluster_name", "rabbitmq_version", "erlang_version")}


# Broker-side counters: average rate = increase over the exact measurement window / window length.
PROM_COUNTERS = {
    "published_rate": "rabbitmq_global_messages_received_total",
    "confirmed_rate": "rabbitmq_global_messages_confirmed_total",
    "delivered_rate": "rabbitmq_global_messages_delivered_consume_manual_ack_total",
    "acked_rate": "rabbitmq_global_messages_acknowledged_total",
    "redelivered_rate": "rabbitmq_global_messages_redelivered_total",
}
# Gauges: mean and max of the samples inside the window.
PROM_GAUGES = {
    "queue_depth": 'max(rabbitmq_detailed_queue_messages{queue="%(queue)s"})',
    "raft_commit_latency_s": 'max(rabbitmq_detailed_raft_entry_commit_latency_seconds{queue="%(queue)s"})',
    "memory_pct_of_watermark": "max(100 * rabbitmq_process_resident_memory_bytes / rabbitmq_resident_memory_limit_bytes)",
}


def _prom(prom_url, endpoint, params):
    with urllib.request.urlopen(f"{prom_url}/api/v1/{endpoint}?{urllib.parse.urlencode(params)}", timeout=10) as r:
        return json.load(r)["data"]["result"]


def prometheus_summary(prom_url, start, end, queue):
    """Broker view of the run. RabbitMQ refreshes its counters every 5 s, so values are +-5 s accurate."""
    win = max(int(end - start), 5)
    out = {"window_start": now_iso(start), "window_end": now_iso(end), "window_s": win}
    for name, metric in PROM_COUNTERS.items():
        q = f"sum(increase({metric}[{win}s])) / {win}"
        try:
            res = _prom(prom_url, "query", {"query": q, "time": end})
            out[name] = {"mean": float(res[0]["value"][1]) if res else None, "query": q}
        except Exception as e:
            out[name] = {"error": str(e), "query": q}
    for name, q in PROM_GAUGES.items():
        q = q % {"queue": queue}
        try:
            res = _prom(prom_url, "query_range", {"query": q, "start": start, "end": end, "step": 5})
            vals = [float(v) for _, v in res[0]["values"]] if res else []
            out[name] = {"mean": sum(vals) / len(vals) if vals else None,
                         "max": max(vals) if vals else None, "samples": len(vals), "query": q}
        except Exception as e:
            out[name] = {"error": str(e), "query": q}
    return out


def stop(proc, name, grace=30):
    if proc.poll() is not None:
        return proc.returncode
    proc.send_signal(signal.SIGINT)
    try:
        return proc.wait(grace)
    except subprocess.TimeoutExpired:
        log(f"{name} did not stop after SIGINT, sending SIGTERM")
        proc.terminate()
        try:
            return proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
            return proc.wait()


def git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                       stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return None


def run_one(sc, rep, raw_dir, cfg, args, broker):
    p = dict(cfg["defaults"])
    p.update(sc)
    if args.duration:
        p["duration"] = args.duration
    out = os.path.join(raw_dir, sc["id"], f"rep{rep}")
    if os.path.exists(os.path.join(out, "meta.json")) and not args.force:
        log(f"skip {sc['id']} rep{rep}: already done ({out})")
        return "skipped"
    fill = dict(p, out=shlex.quote(out))
    prod_cmd = cfg["commands"]["producer"].format(**fill)
    cons_cmd = cfg["commands"]["consumer"].format(**fill)
    if args.dry_run:
        print(f"\n# {sc['id']} rep{rep}\n  consumer: {cons_cmd}\n  producer: {prod_cmd}")
        return "dry-run"

    os.makedirs(out, exist_ok=True)
    meta = {"scenario": sc["id"], "group": sc.get("group"), "rep": rep, "params": p,
            "commands": {"producer": prod_cmd, "consumer": cons_cmd},
            "host": {"platform": platform.platform(), "machine": platform.machine(),
                     "cpu_count": os.cpu_count(), "python": platform.python_version()},
            "git_commit": git_commit()}

    if broker:
        t_wait = time.time()
        while True:
            ok, state = broker.healthy(p["queue"])
            if ok:
                break
            if time.time() - t_wait > 90:
                raise RuntimeError(f"cluster not healthy for 90 s: {state} - start it / heal it first")
            log(f"waiting for a healthy cluster: {state}")
            time.sleep(3)
        meta["cluster_before"] = state
        meta["broker"] = broker.overview()
        broker.purge(p["queue"])
        log(f"{sc['id']} rep{rep}: queue purged, leader={state['leader']}")

    with open(os.path.join(out, "consumer.log"), "w") as clog, \
            open(os.path.join(out, "producer.log"), "w") as plog:
        t_cons = time.time()
        cons = subprocess.Popen(shlex.split(cons_cmd), cwd=ROOT, stdout=clog, stderr=subprocess.STDOUT)
        time.sleep(p["consumer_start_delay"])
        if cons.poll() is not None:
            raise RuntimeError(f"consumer exited early (code {cons.returncode}), see {out}/consumer.log")
        t_pub_start = time.time()
        log(f"{sc['id']} rep{rep}: producer started ({p['producer_threads']} threads, {p['size']} B, "
            f"prefetch {p['prefetch']}, {p['duration']} s)")
        prod = subprocess.Popen(shlex.split(prod_cmd), cwd=ROOT, stdout=plog, stderr=subprocess.STDOUT)
        try:
            prod_rc = prod.wait(p["duration"] + 180)
        except subprocess.TimeoutExpired:
            log("producer did not finish in duration + 180 s, stopping it")
            prod_rc = stop(prod, "producer")
        t_pub_end = time.time()

        drained, depth = None, None
        if broker:
            while time.time() - t_pub_end < p["drain_timeout"]:
                q = broker.queue(p["queue"])
                depth = q.get("messages", 0)          # ready + unacknowledged
                if depth == 0:
                    drained = True
                    break
                time.sleep(2)
            else:
                drained = False
        else:
            time.sleep(1)
        t_drained = time.time()
        cons_rc = stop(cons, "consumer")
    t_end = time.time()

    meta.update({
        "timestamps": {"consumer_start": now_iso(t_cons), "publish_start": now_iso(t_pub_start),
                       "publish_end": now_iso(t_pub_end), "drained": now_iso(t_drained), "end": now_iso(t_end)},
        "timestamps_epoch": {"publish_start": t_pub_start, "publish_end": t_pub_end, "drained": t_drained},
        "exit_codes": {"producer": prod_rc, "consumer": cons_rc},
        "drained": drained, "queue_depth_after": depth,
    })
    if broker and not args.no_prometheus:
        meta["prometheus"] = prometheus_summary(args.prom_url, t_pub_start + p["warmup"], t_pub_end, p["queue"])
    for f in ("confirmed.csv", "received.csv"):
        meta.setdefault("files", {})[f] = os.path.exists(os.path.join(out, f))
    with open(os.path.join(out, "meta.json"), "w") as f:   # written last = run complete
        json.dump(meta, f, indent=2)
    status = "ok" if prod_rc == 0 and cons_rc == 0 and drained is not False and all(meta["files"].values()) else "CHECK"
    log(f"{sc['id']} rep{rep}: {status} (producer rc={prod_rc}, consumer rc={cons_rc}, drained={drained}, "
        f"files={meta['files']})")
    return status


def main():
    ap = argparse.ArgumentParser(description="Run the HW2 benchmark matrix")
    ap.add_argument("--config", default=os.path.join(ROOT, "benchmarks", "scenarios.yaml"))
    ap.add_argument("--raw-dir", default=os.path.join(ROOT, "benchmarks", "results", "raw"))
    ap.add_argument("--only", help="comma list of groups (B2) or scenario ids (B2-p4)")
    ap.add_argument("--repeats", type=int, help="override repeats from the config")
    ap.add_argument("--duration", type=int, help="override publish duration (s)")
    ap.add_argument("--prom-url", default=os.environ.get("PROM_URL", "http://localhost:9090"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="re-run runs that already have meta.json")
    ap.add_argument("--no-broker", action="store_true", help="selftest only: skip RabbitMQ API calls")
    ap.add_argument("--no-prometheus", action="store_true")
    args = ap.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)
    wanted = set(args.only.split(",")) if args.only else None
    scenarios = [s for s in cfg["scenarios"] if not wanted or s["id"] in wanted or s.get("group") in wanted]
    if not scenarios:
        sys.exit(f"no scenario matches --only {args.only}")
    repeats = args.repeats or cfg["defaults"]["repeats"]
    broker = None if (args.no_broker or args.dry_run) else Broker(vhost="/")
    log(f"{len(scenarios)} scenario(s) x {repeats} repeat(s) -> {args.raw_dir}")

    results = []
    for rep in range(1, repeats + 1):          # rep-major order: drift spreads over all scenarios
        for sc in scenarios:
            try:
                results.append((sc["id"], rep, run_one(sc, rep, args.raw_dir, cfg, args, broker)))
            except KeyboardInterrupt:
                log("interrupted - finished runs are kept; re-run the same command to resume")
                sys.exit(130)
            except Exception as e:
                log(f"{sc['id']} rep{rep}: FAILED - {e}")
                results.append((sc["id"], rep, "FAILED"))
            if not args.dry_run and results[-1][2] not in ("skipped",):
                time.sleep(cfg["defaults"]["cooldown"] if broker else 0)
    print()
    for sid, rep, st in results:
        print(f"  {sid:<14} rep{rep}  {st}")
    if any(st in ("FAILED", "CHECK") for _, _, st in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
