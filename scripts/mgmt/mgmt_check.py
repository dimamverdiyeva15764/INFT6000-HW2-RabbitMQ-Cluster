#!/usr/bin/env python3
"""Health check of the RabbitMQ cluster through the Management HTTP API.

Asks the first node whose API answers (host ports 15672, 15673, 15674), so it keeps
working when a node is down. Prints node health and the Raft leader/members of each
hw2.* queue, and exits with status 1 if anything is unhealthy:
  - a node not running, a network partition, a memory or disk alarm
  - a quorum queue with fewer online members than members, or no leader

Only the Python standard library is used.

Usage:
  python3 scripts/mgmt/mgmt_check.py
  python3 scripts/mgmt/mgmt_check.py --json results/mgmt_check_$(date +%Y%m%dT%H%M%S).json
  RABBITMQ_USER=admin RABBITMQ_PASS=admin123 python3 scripts/mgmt/mgmt_check.py --ports 15673,15674
"""
import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


class Api:
    def __init__(self, host, ports, user, password, timeout):
        self.host, self.ports, self.timeout = host, ports, timeout
        self.auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
        self.port = None

    def _get(self, port, path):
        req = urllib.request.Request(f"http://{self.host}:{port}/api/{path}",
                                     headers={"Authorization": self.auth})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:   # health checks answer 503 with a JSON body
            body = e.read()
            try:
                return e.code, json.loads(body or b"null")
            except ValueError:
                return e.code, {"error": body.decode(errors="replace")}

    def connect(self):
        errors = []
        for p in self.ports:
            try:
                status, _ = self._get(p, "overview")
                if status == 200:
                    self.port = p
                    return p
                errors.append(f"{p}: HTTP {status}")
            except Exception as e:  # connection refused, timeout
                errors.append(f"{p}: {e.__class__.__name__}")
        raise SystemExit("ERROR: no management API answered (" + "; ".join(errors) + ")")

    def get(self, path):
        return self._get(self.port, path)


def mb(x):
    return f"{x / 1024 / 1024:,.0f} MB" if isinstance(x, (int, float)) else "-"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--ports", default="15672,15673,15674")
    ap.add_argument("--vhost", default="/")
    ap.add_argument("--queue-pattern", default=r"^hw2\.")
    ap.add_argument("--timeout", type=float, default=5)
    ap.add_argument("--json", metavar="FILE", help="also save the full report as JSON")
    a = ap.parse_args()

    api = Api(a.host, [int(p) for p in a.ports.split(",")],
              os.environ.get("RABBITMQ_USER", "admin"), os.environ.get("RABBITMQ_PASS", "admin123"), a.timeout)
    port = api.connect()
    problems = []

    _, overview = api.get("overview")
    _, nodes = api.get("nodes")
    alarm_status, alarm_body = api.get("health/checks/alarms")
    vh = urllib.parse.quote(a.vhost, safe="")
    _, queues = api.get(f"queues/{vh}")
    queues = [q for q in (queues or []) if re.search(a.queue_pattern, q["name"])]

    print(f"Management API on port {port} | cluster '{overview.get('cluster_name')}' | "
          f"RabbitMQ {overview.get('rabbitmq_version')} | Erlang {overview.get('erlang_version')}")
    print(f"Checked at {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n")

    print(f"{'NODE':<16} {'RUNNING':<8} {'MEM USED/LIMIT':<22} {'DISK FREE':<12} {'ALARMS':<12} PARTITIONS")
    for n in sorted(nodes, key=lambda n: n["name"]):
        alarms = [k for k, flag in (("memory", n.get("mem_alarm")), ("disk", n.get("disk_free_alarm"))) if flag]
        parts = n.get("partitions") or []
        print(f"{n['name']:<16} {str(n.get('running')):<8} "
              f"{mb(n.get('mem_used')) + ' / ' + mb(n.get('mem_limit')):<22} {mb(n.get('disk_free')):<12} "
              f"{','.join(alarms) or 'none':<12} {','.join(parts) or 'none'}")
        if not n.get("running"):
            problems.append(f"node {n['name']} is not running")
        if alarms:
            problems.append(f"node {n['name']} has alarm(s): {','.join(alarms)}")
        if parts:
            problems.append(f"node {n['name']} sees a partition with {parts}")
    if alarm_status != 200:
        problems.append(f"health/checks/alarms returned {alarm_status}: {alarm_body}")

    print(f"\n{'QUEUE':<16} {'TYPE':<8} {'LEADER':<16} {'ONLINE/MEMBERS':<15} {'READY':>8} {'UNACKED':>8} {'CONSUMERS':>9}")
    for q in sorted(queues, key=lambda q: q["name"]):
        members, online = q.get("members") or [], q.get("online") or []
        print(f"{q['name']:<16} {q.get('type', '-'):<8} {q.get('leader') or '-':<16} "
              f"{f'{len(online)}/{len(members)}':<15} {q.get('messages_ready', 0):>8} "
              f"{q.get('messages_unacknowledged', 0):>8} {q.get('consumers', 0):>9}")
        if q.get("type") == "quorum":
            if not q.get("leader"):
                problems.append(f"queue {q['name']} has no leader")
            if len(online) < len(members):
                problems.append(f"queue {q['name']}: only {len(online)} of {len(members)} members online "
                                f"({', '.join(sorted(set(members) - set(online)))} offline)")
    if not queues:
        problems.append(f"no queue matches {a.queue_pattern} in vhost {a.vhost}")

    print()
    if problems:
        print("RESULT: UNHEALTHY")
        for p in problems:
            print("  -", p)
    else:
        print("RESULT: HEALTHY")

    if a.json:
        os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
        with open(a.json, "w") as f:
            json.dump({"checked_at": datetime.now(timezone.utc).isoformat(), "api_port": port,
                       "overview": {k: overview.get(k) for k in ("cluster_name", "rabbitmq_version", "erlang_version")},
                       "nodes": nodes, "queues": queues, "problems": problems}, f, indent=2, default=str)
        print(f"saved {a.json}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
