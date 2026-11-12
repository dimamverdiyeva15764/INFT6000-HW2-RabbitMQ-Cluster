"""Validator tests: build small fake CSVs with KNOWN problems and assert exactly those are found."""
import csv

import pytest

from consumer.validate import main, validate, verdict

CONF_HEADER = ["msg_id", "producer_id", "seq", "sent_ts_ns", "confirm_ts_ns"]
RECV_HEADER = ["msg_id", "producer_id", "seq", "sent_ts_ns", "recv_ts_ns", "redelivered", "consumer_id"]


def write_csv(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return str(path)


def make_run(tmp_path, n=20, drop=(), dup=(), swap=None):
    """n messages from one producer P; drop=seqs never received; dup=seqs delivered twice;
    swap=(a, b) seqs whose arrival order is exchanged."""
    conf, recv = [], []
    base = 1_000_000_000_000
    arrival = list(range(1, n + 1))
    if swap:
        a, b = swap
        ia, ib = arrival.index(a), arrival.index(b)
        arrival[ia], arrival[ib] = arrival[ib], arrival[ia]
    for s in range(1, n + 1):
        conf.append([f"P-{s}", "P", s, base + s * 1000, base + s * 1000 + 500])
    t = base + 10_000_000
    for s in arrival:
        t += 1_000_000
        if s in drop:
            continue
        recv.append([f"P-{s}", "P", s, base + s * 1000, t, "false", "c1"])
        if s in dup:
            t += 1_000_000
            recv.append([f"P-{s}", "P", s, base + s * 1000, t, "true", "c1"])
    return (
        write_csv(tmp_path / "confirmed.csv", CONF_HEADER, conf),
        write_csv(tmp_path / "received.csv", RECV_HEADER, recv),
    )


def test_clean_run_passes(tmp_path):
    c, r = make_run(tmp_path)
    res = validate(c, r)
    assert (res["confirmed"], res["received_unique"], res["lost"]) == (20, 20, 0)
    assert res["duplicates"] == 0 and res["out_of_order"] == 0
    assert verdict(res) == "PASS"
    assert main(["--confirmed", c, "--received", r]) == 0


def test_planted_errors_found_exactly(tmp_path):
    """The spec test: exactly 2 lost, 3 duplicates, 1 reorder."""
    c, r = make_run(tmp_path, n=20, drop={5, 11}, dup={2, 8, 15}, swap=(17, 18))
    res = validate(c, r)
    assert res["lost"] == 2
    assert res["lost_ids_sample"] == ["P-11", "P-5"] or set(res["lost_ids_sample"]) == {"P-5", "P-11"}
    assert res["duplicates"] == 3
    assert res["redelivered_flag"] == 3
    assert res["out_of_order"] == 1 and res["out_of_order_per_consumer"] == 1
    assert verdict(res) == "FAIL"
    assert main(["--confirmed", c, "--received", r]) == 1


def test_duplicates_alone_do_not_fail(tmp_path):
    c, r = make_run(tmp_path, dup={3, 4})
    res = validate(c, r)
    assert res["duplicates"] == 2 and res["lost"] == 0
    assert verdict(res) == "PASS"


def test_out_of_order_fails_only_in_strict_mode(tmp_path):
    c, r = make_run(tmp_path, swap=(3, 4))
    assert main(["--confirmed", c, "--received", r]) == 0
    assert main(["--confirmed", c, "--received", r, "--strict-order"]) == 1


def test_unconfirmed_but_delivered_is_reported_not_failed(tmp_path):
    c, r = make_run(tmp_path)
    with open(r, "a", newline="") as f:
        csv.writer(f).writerow(["P-99", "P", 99, 1, 2_000_000_000_000, "false", "c1"])
    res = validate(c, r)
    assert res["unconfirmed_but_delivered"] == 1 and res["lost"] == 0
    assert verdict(res) == "PASS"


def test_nothing_confirmed_is_not_a_pass(tmp_path):
    c = write_csv(tmp_path / "c.csv", CONF_HEADER, [])
    r = write_csv(tmp_path / "r.csv", RECV_HEADER, [])
    assert verdict(validate(c, r)) == "FAIL"


def test_latency_percentiles(tmp_path):
    c, r = make_run(tmp_path, n=10)
    lat = validate(c, r)["latency_ms"]
    assert lat["p50"] is not None and lat["p50"] <= lat["p95"] <= lat["p99"] <= lat["max"]


def test_json_output(tmp_path):
    import json
    c, r = make_run(tmp_path, drop={1})
    out = tmp_path / "v.json"
    assert main(["--confirmed", c, "--received", r, "--json", str(out)]) == 1
    assert json.loads(out.read_text())["verdict"] == "FAIL"


def test_two_consumers_interleaving_is_not_a_reorder(tmp_path):
    """Competing consumers: c1 gets odd seqs, c2 even, arrival interleaved/late.
    Global order may be shuffled but each consumer still sees increasing seq."""
    base = 10**12
    conf = [[f"P-{s}", "P", s, base, base + 1] for s in range(1, 9)]
    arrival = [(2, "c2"), (1, "c1"), (4, "c2"), (3, "c1"), (6, "c2"), (5, "c1"), (8, "c2"), (7, "c1")]
    recv = [[f"P-{s}", "P", s, base, base + 10_000 * (i + 1), "false", c] for i, (s, c) in enumerate(arrival)]
    c = write_csv(tmp_path / "c.csv", CONF_HEADER, conf)
    r = write_csv(tmp_path / "r.csv", RECV_HEADER, recv)
    res = validate(c, r)
    assert res["out_of_order"] == 4          # global arrival looks shuffled ...
    assert res["out_of_order_per_consumer"] == 0   # ... but queue order per consumer is intact
    assert main(["--confirmed", c, "--received", r, "--strict-order"]) == 0


def test_redelivered_late_arrival_not_counted_per_consumer(tmp_path):
    base = 10**12
    conf = [[f"P-{s}", "P", s, base, base + 1] for s in range(1, 4)]
    recv = [
        ["P-1", "P", 1, base, base + 1, "false", "c1"],
        ["P-3", "P", 3, base, base + 2, "false", "c1"],
        ["P-2", "P", 2, base, base + 3, "true", "c1"],   # came back after a crash
    ]
    c = write_csv(tmp_path / "c.csv", CONF_HEADER, conf)
    r = write_csv(tmp_path / "r.csv", RECV_HEADER, recv)
    res = validate(c, r)
    assert res["lost"] == 0 and res["out_of_order_per_consumer"] == 0
