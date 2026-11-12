#!/usr/bin/env python3
"""End-to-end check of the monitoring stack (the HW2 bonus) - owner: P2.

It proves more than "the containers are running":
  1. Prometheus is ready and all 7 scrape targets are UP.
  2. All 8 alert rules are loaded and healthy (and shows which are firing).
  3. The three metrics the assignment names are present:
     queue depth, message rates, node health.
  4. Grafana is up, its Prometheus data source answers,
     and the 3 dashboards were provisioned.
  5. Every query of the "HW2 - RabbitMQ cluster overview" dashboard is sent
     THROUGH Grafana to Prometheus and must return data.

Standard library only (no virtual environment needed). Read-only: it changes nothing.

Usage (from the repository root, stack started with ./scripts/up.sh):
  python3 scripts/mgmt/check_monitoring.py
  python3 scripts/mgmt/check_monitoring.py --prom http://localhost:9090 --grafana http://localhost:3000
Grafana login: GRAFANA_USER / GRAFANA_PASS from the environment or .env (default admin / admin).
Exit code 0 = everything OK, 1 = at least one check failed.
"""
import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

EXPECTED_TARGETS = 7          # prometheus + 3 x rabbitmq + 3 x rabbitmq-detailed
EXPECTED_RULES = 8
EXPECTED_DASHBOARDS = {"HW2 - RabbitMQ cluster overview", "RabbitMQ-Overview", "RabbitMQ-Quorum-Queues-Raft"}
HW2_DASHBOARD_UID = "hw2-overview"
# Panels that may legitimately be empty: no alert firing means no ALERTS series.
MAY_BE_EMPTY = {"Active alerts (Prometheus rules)"}

failures = []


def ok(msg):
    print(f"  [OK]   {msg}")


def bad(msg):
    print(f"  [FAIL] {msg}")
    failures.append(msg)


def info(msg):
    print(f"         {msg}")


def read_env_file(path=".env"):
    values = {}
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    values[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return values


def get_json(url, auth=None, timeout=5):
    req = urllib.request.Request(url)
    if auth:
        token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
        req.add_header("Authorization", "Basic " + token)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def prom_query(base, expr, auth=None):
    url = base + "/api/v1/query?" + urllib.parse.urlencode({"query": expr})
    data = get_json(url, auth)
    if data.get("status") != "success":
        raise RuntimeError(data.get("error", "query failed"))
    return data["data"]["result"]


def check_prometheus(prom, queue):
    print(f"== 1. Prometheus ({prom})")
    try:
        targets = get_json(prom + "/api/v1/targets")["data"]["activeTargets"]
    except Exception as exc:  # noqa: BLE001
        bad(f"Prometheus not reachable: {exc}")
        return False
    up = [t for t in targets if t.get("health") == "up"]
    for t in sorted(targets, key=lambda t: (t["labels"].get("job", ""), t["labels"].get("instance", ""))):
        info(f"{t['labels'].get('job', ''):<18} {t['labels'].get('instance', ''):<16} {t.get('health', '').upper()}")
    if len(up) == EXPECTED_TARGETS and len(targets) == EXPECTED_TARGETS:
        ok(f"{len(up)}/{EXPECTED_TARGETS} scrape targets UP")
    else:
        bad(f"{len(up)} of {len(targets)} targets UP (expected {EXPECTED_TARGETS}/{EXPECTED_TARGETS})")

    print("== 2. Alert rules")
    try:
        groups = get_json(prom + "/api/v1/rules")["data"]["groups"]
        rules = [r for g in groups for r in g.get("rules", []) if r.get("type") == "alerting"]
        for r in rules:
            info(f"{r['name']:<28} health={r.get('health', '?'):<5} state={r.get('state', '?')}")
        healthy = [r for r in rules if r.get("health") == "ok"]
        if len(rules) == EXPECTED_RULES and len(healthy) == EXPECTED_RULES:
            ok(f"{EXPECTED_RULES} alert rules loaded and evaluating without errors")
        else:
            bad(f"{len(rules)} alert rules loaded, {len(healthy)} healthy (expected {EXPECTED_RULES})")
        firing = [r["name"] for r in rules if r.get("state") == "firing"]
        info("Firing now: " + (", ".join(firing) if firing else "none"))
    except Exception as exc:  # noqa: BLE001
        bad(f"cannot read rules: {exc}")

    print("== 3. Metrics named in the assignment (queue depth, message rates, node health)")
    checks = [
        ("Node health: RabbitMQ nodes up", 'count(up{job="rabbitmq"} == 1)'),
        ("Queue depth of " + queue, f'max(rabbitmq_detailed_queue_messages{{queue="{queue}"}})'),
        ("Message rate in (msg/s, 1m)", "sum(rate(rabbitmq_global_messages_received_total[1m]))"),
        ("Confirm rate (msg/s, 1m)", "sum(rate(rabbitmq_global_messages_confirmed_total[1m]))"),
        ("Deliver rate, manual ack (msg/s, 1m)", "sum(rate(rabbitmq_global_messages_delivered_consume_manual_ack_total[1m]))"),
        ("Raft term of " + queue, f'max(rabbitmq_detailed_raft_term_total{{queue="{queue}"}})'),
    ]
    for label, expr in checks:
        try:
            res = prom_query(prom, expr)
            if res:
                ok(f"{label:<40} = {float(res[0]['value'][1]):.2f}")
            else:
                bad(f"{label:<40} no data  ({expr})")
        except Exception as exc:  # noqa: BLE001
            bad(f"{label}: {exc}")
    return True


def check_grafana(graf, auth, queue):
    print(f"== 4. Grafana ({graf})")
    try:
        health = get_json(graf + "/api/health")
        if health.get("database") == "ok":
            ok(f"Grafana {health.get('version', '?')} is up (database ok)")
        else:
            bad(f"Grafana health: {health}")
    except Exception as exc:  # noqa: BLE001
        bad(f"Grafana not reachable: {exc}")
        return
    try:
        ds = get_json(graf + "/api/datasources/uid/prometheus", auth)
        ok(f"data source '{ds.get('name')}' -> {ds.get('url')} (provisioned)")
    except urllib.error.HTTPError as exc:
        bad(f"data source uid 'prometheus' not found or login refused (HTTP {exc.code}); check GRAFANA_USER/GRAFANA_PASS")
        return
    except Exception as exc:  # noqa: BLE001
        bad(f"data source: {exc}")
        return
    try:
        dashboards = get_json(graf + "/api/search?type=dash-db", auth)
        titles = {d.get("title") for d in dashboards}
        for t in sorted(titles):
            info(f"dashboard: {t}")
        missing = EXPECTED_DASHBOARDS - titles
        if missing:
            bad("dashboards missing: " + ", ".join(sorted(missing)))
        else:
            ok("all 3 dashboards provisioned")
    except Exception as exc:  # noqa: BLE001
        bad(f"dashboard search: {exc}")

    print("== 5. HW2 dashboard: every panel query sent through Grafana to Prometheus")
    try:
        dash = get_json(graf + f"/api/dashboards/uid/{HW2_DASHBOARD_UID}", auth)["dashboard"]
    except Exception as exc:  # noqa: BLE001
        bad(f"cannot load dashboard {HW2_DASHBOARD_UID}: {exc}")
        return
    proxy = graf + "/api/datasources/proxy/uid/prometheus"
    total = with_data = 0
    for panel in dash.get("panels", []):
        for target in panel.get("targets", []):
            expr = target.get("expr")
            if not expr:
                continue
            expr = expr.replace("$__rate_interval", "1m").replace("$queue", queue)
            total += 1
            title = panel.get("title", "?")
            try:
                res = prom_query(proxy, expr, auth)
            except Exception as exc:  # noqa: BLE001
                bad(f"{title}: query error through Grafana: {exc}")
                continue
            if res:
                with_data += 1
            elif title in MAY_BE_EMPTY:
                with_data += 1
                info(f"{title}: empty (no alert firing right now - expected)")
            else:
                bad(f"{title}: no data")
    if total and with_data == total:
        ok(f"{with_data}/{total} panel queries return data through Grafana")
    elif total:
        info(f"{with_data}/{total} panel queries return data")


def main():
    env = read_env_file()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--prom", default="http://localhost:9090")
    ap.add_argument("--grafana", default="http://localhost:3000")
    ap.add_argument("--user", default=os.environ.get("GRAFANA_USER", env.get("GRAFANA_USER", "admin")))
    ap.add_argument("--password", default=os.environ.get("GRAFANA_PASS", env.get("GRAFANA_PASS", "admin")))
    ap.add_argument("--queue", default=os.environ.get("QUEUE_NAME", env.get("QUEUE_NAME", "hw2.orders")))
    args = ap.parse_args()

    check_prometheus(args.prom.rstrip("/"), args.queue)
    check_grafana(args.grafana.rstrip("/"), (args.user, args.password), args.queue)
    print("=" * 60)
    if failures:
        print(f"MONITORING CHECK: FAIL ({len(failures)} problem(s))")
        return 1
    print("MONITORING CHECK: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
