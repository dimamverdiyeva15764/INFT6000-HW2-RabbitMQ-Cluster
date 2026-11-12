#!/usr/bin/env python3
"""Generates dashboards/hw2-overview.json (owner: P2).

Edit the panel list here and re-run instead of hand-editing the JSON:
    python3 monitoring/grafana/build_hw2_dashboard.py
Metric names were checked against rabbitmq_prometheus v3.13.7 (the broker version
in docker-compose.yml). Per-queue metrics come from the "rabbitmq-detailed" job
(prefix rabbitmq_detailed_); node-level metrics from the "rabbitmq" job.
"""
import json
import os

DS = {"type": "prometheus", "uid": "prometheus"}
# Fixed colour per node (categorical slots 1-3), the same on every panel.
NODE_COLORS = {"rabbit1": "#2a78d6", "rabbit2": "#eb6834", "rabbit3": "#1baf7a"}
FLOW_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
GOOD, BAD, WARN = "#008300", "#e34948", "#eda100"


def per_node(expr):
    """Turn instance="rabbit1:15692" into node="rabbit1" for short legends."""
    return f'label_replace({expr}, "node", "$1", "instance", "(rabbit[0-9]+):.*")'


_id = [0]


def nid():
    _id[0] += 1
    return _id[0]


def target(expr, legend, ref="A", instant=False):
    t = {"datasource": DS, "expr": expr, "legendFormat": legend, "refId": ref}
    if instant:
        t.update({"instant": True, "range": False, "format": "table"})
    return t


def node_overrides():
    return [{"matcher": {"id": "byName", "options": n},
             "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": c}}]}
            for n, c in NODE_COLORS.items()]


def timeseries(title, targets, x, y, w=12, h=8, unit="short", desc="", overrides=None,
               step=False, colors=None, min0=True):
    ov = list(overrides or [])
    if colors:
        for t, c in zip(targets, colors):
            ov.append({"matcher": {"id": "byName", "options": t["legendFormat"]},
                       "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": c}}]})
    defaults = {
        "unit": unit,
        "color": {"mode": "palette-classic"},
        "custom": {"lineWidth": 2, "fillOpacity": 0, "showPoints": "never", "spanNulls": False,
                   "lineInterpolation": "stepAfter" if step else "linear",
                   "axisSoftMin": 0 if min0 else None, "gradientMode": "none"},
    }
    return {"id": nid(), "type": "timeseries", "title": title, "description": desc, "datasource": DS,
            "gridPos": {"x": x, "y": y, "w": w, "h": h}, "targets": targets,
            "fieldConfig": {"defaults": defaults, "overrides": ov},
            "options": {"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                        "tooltip": {"mode": "multi", "sort": "desc"}}}


def stat(title, targets, x, y, w=4, h=4, unit="short", steps=None, mappings=None, desc="",
         color_mode="background"):
    return {"id": nid(), "type": "stat", "title": title, "description": desc, "datasource": DS,
            "gridPos": {"x": x, "y": y, "w": w, "h": h}, "targets": targets,
            "fieldConfig": {"defaults": {
                "unit": unit, "mappings": mappings or [],
                "color": {"mode": "thresholds"},
                "thresholds": {"mode": "absolute", "steps": steps or [{"color": "text", "value": None}]}},
                "overrides": []},
            "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                        "colorMode": color_mode, "graphMode": "none", "textMode": "value_and_name",
                        "justifyMode": "center", "orientation": "horizontal"}}


def row(title, y):
    return {"id": nid(), "type": "row", "title": title, "collapsed": False,
            "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "panels": []}


Q = 'queue="$queue"'
rate = "$__rate_interval"
panels = []

# ---------------------------------------------------------------- health
y = 0
panels.append(row("Cluster health", y)); y += 1
panels.append(stat(
    "Nodes up (of 3)", [target('count(up{job="rabbitmq"} == 1) or vector(0)', "nodes up")], 0, y, w=4,
    steps=[{"color": BAD, "value": None}, {"color": WARN, "value": 2}, {"color": GOOD, "value": 3}],
    desc="Number of RabbitMQ nodes Prometheus can scrape. 2 = quorum still holds, 1 = majority lost."))
panels.append(stat(
    "Node status", [target(per_node('up{job="rabbitmq"}'), "{{node}}")], 4, y, w=8,
    steps=[{"color": BAD, "value": None}, {"color": GOOD, "value": 1}],
    mappings=[{"type": "value", "options": {"0": {"text": "DOWN", "index": 0}, "1": {"text": "UP", "index": 1}}}],
    desc="UP/DOWN per node (scrape of :15692)."))
panels.append(stat(
    "Queue depth", [target(f"max(rabbitmq_detailed_queue_messages{{{Q}}}) or vector(0)", "$queue")], 12, y, w=4,
    desc="Ready + unacknowledged messages in the selected queue."))
panels.append(stat(
    "Raft term", [target(f"max(rabbitmq_detailed_raft_term_total{{{Q}}})", "term")], 16, y, w=4,
    desc="Current Raft term of the queue. It grows by 1 for every leader election."))
panels.append(stat(
    "Firing alerts", [target('count(ALERTS{alertstate="firing", severity!="info"}) or vector(0)', "alerts")],
    20, y, w=4, steps=[{"color": GOOD, "value": None}, {"color": BAD, "value": 1}],
    desc="Prometheus alert rules in state firing (rules/rabbitmq-alerts.yml), info alerts excluded."))
y += 4
alerts_table = {
    "id": nid(), "type": "table", "title": "Active alerts (Prometheus rules)", "datasource": DS,
    "gridPos": {"x": 0, "y": y, "w": 24, "h": 5},
    "targets": [target('ALERTS{alertstate="firing"}', "", instant=True)],
    "transformations": [{"id": "organize", "options": {
        "excludeByName": {"Time": True, "Value": True, "__name__": True, "alertstate": True, "job": True},
        "indexByName": {"alertname": 0, "severity": 1, "instance": 2, "queue": 3}}}],
    "fieldConfig": {"defaults": {}, "overrides": []},
    "options": {"showHeader": True, "footer": {"show": False}},
}
panels.append(alerts_table); y += 5

# ---------------------------------------------------------------- message flow
panels.append(row("Message flow (cluster-wide)", y)); y += 1
flow = [
    target(f"sum(rate(rabbitmq_global_messages_received_total[{rate}]))", "published", "A"),
    target(f"sum(rate(rabbitmq_global_messages_confirmed_total[{rate}]))", "confirmed", "B"),
    target(f"sum(rate(rabbitmq_global_messages_delivered_consume_manual_ack_total[{rate}]))", "delivered (manual ack)", "C"),
    target(f"sum(rate(rabbitmq_global_messages_acknowledged_total[{rate}]))", "acknowledged", "D"),
]
panels.append(timeseries("Publish / confirm / deliver / ack rate", flow, 0, y, unit="msg/s", colors=FLOW_COLORS,
                         desc="Throughput seen by the broker. During a node failure the dip and recovery show here."))
panels.append(timeseries(
    "Publish rate per node",
    [target(per_node(f"sum by (instance) (rate(rabbitmq_global_messages_received_total[{rate}]))"), "{{node}}")],
    12, y, unit="msg/s", overrides=node_overrides(),
    desc="Which node the producers are connected to. After a crash the traffic moves to the surviving nodes."))
y += 8
panels.append(timeseries(
    "Redelivered rate",
    [target(f"sum(rate(rabbitmq_global_messages_redelivered_total[{rate}]))", "redelivered")],
    0, y, unit="msg/s", colors=FLOW_COLORS[:1],
    desc="Messages delivered again (consumer died or reconnected before acking). Expected after failover."))
panels.append(timeseries(
    "Connections per node",
    [target(per_node('rabbitmq_connections{job="rabbitmq"}'), "{{node}}")],
    12, y, overrides=node_overrides(), desc="Open AMQP connections per node (client failover moves them)."))
y += 8

# ---------------------------------------------------------------- queue
panels.append(row("Queue $queue", y)); y += 1
panels.append(timeseries(
    "Queue depth",
    [target(f"max(rabbitmq_detailed_queue_messages_ready{{{Q}}})", "ready", "A"),
     target(f"max(rabbitmq_detailed_queue_messages_unacked{{{Q}}})", "unacked", "B")],
    0, y, colors=FLOW_COLORS[:2], desc="max() across nodes: a queue may be reported by more than one node."))
panels.append(timeseries(
    "Consumers on queue",
    [target(f"max(rabbitmq_detailed_queue_consumers{{{Q}}})", "consumers")],
    12, y, colors=FLOW_COLORS[:1], step=True))
y += 8

# ---------------------------------------------------------------- raft
panels.append(row("Raft (quorum queue $queue)", y)); y += 1
panels.append(timeseries(
    "Raft term per node", [target(per_node(f"rabbitmq_detailed_raft_term_total{{{Q}}}"), "{{node}}")],
    0, y, w=8, step=True, overrides=node_overrides(), min0=False,
    desc="A step up = a new leader election. A node that disappears was down or partitioned."))
panels.append(timeseries(
    "Raft commit index per node", [target(per_node(f"rabbitmq_detailed_raft_log_commit_index{{{Q}}}"), "{{node}}")],
    8, y, w=8, overrides=node_overrides(), min0=False,
    desc="A restarted follower catches up when its line meets the others again."))
panels.append(timeseries(
    "Raft entry commit latency", [target(per_node(f"rabbitmq_detailed_raft_entry_commit_latency_seconds{{{Q}}}"), "{{node}}")],
    16, y, w=8, unit="s", overrides=node_overrides(),
    desc="Time for a log entry to be committed by a majority (2 of 3)."))
y += 8

# ---------------------------------------------------------------- resources
panels.append(row("Node resources", y)); y += 1
panels.append(timeseries(
    "Memory used (% of high watermark)",
    [target(per_node('100 * rabbitmq_process_resident_memory_bytes / rabbitmq_resident_memory_limit_bytes'), "{{node}}")],
    0, y, w=8, unit="percent", overrides=node_overrides(),
    desc="100% = memory alarm (vm_memory_high_watermark.relative = 0.6); publishers get blocked."))
panels.append(timeseries(
    "Free disk space", [target(per_node("rabbitmq_disk_space_available_bytes"), "{{node}}")],
    8, y, w=8, unit="bytes", overrides=node_overrides(), desc="Alarm below disk_free_limit = 1GB."))
panels.append(timeseries(
    "Channels per node", [target(per_node('rabbitmq_channels{job="rabbitmq"}'), "{{node}}")],
    16, y, w=8, overrides=node_overrides()))

dashboard = {
    "uid": "hw2-overview",
    "title": "HW2 - RabbitMQ cluster overview",
    "description": "INFT6000 HW2 (P2): node health, message rates, queue depth, Raft state and alerts.",
    "tags": ["hw2", "rabbitmq"],
    "timezone": "browser",
    "editable": False,
    "refresh": "5s",
    "time": {"from": "now-30m", "to": "now"},
    "schemaVersion": 39,
    "version": 1,
    "graphTooltip": 1,
    "templating": {"list": [{
        "name": "queue", "label": "Queue", "type": "query", "datasource": DS,
        "query": {"query": "label_values(rabbitmq_detailed_queue_messages, queue)", "refId": "q"},
        "definition": "label_values(rabbitmq_detailed_queue_messages, queue)",
        "current": {"selected": True, "text": "hw2.orders", "value": "hw2.orders"},
        "refresh": 2, "includeAll": False, "multi": False, "sort": 1}]},
    "annotations": {"list": [{
        "name": "Raft elections", "datasource": DS, "enable": True, "iconColor": BAD,
        "expr": 'ALERTS{alertname="RabbitMQRaftLeaderElection", alertstate="firing"}',
        "step": "5s", "titleFormat": "Leader election", "textFormat": "{{queue}}"}]},
    "panels": panels,
}

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboards", "hw2-overview.json")
with open(out, "w") as f:
    json.dump(dashboard, f, indent=2)
print(f"wrote {out} ({len(panels)} panels)")
