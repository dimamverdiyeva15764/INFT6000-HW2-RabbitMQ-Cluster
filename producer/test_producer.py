import csv
import json

import pika

from producer import producer


class FakeChannel:
    def __init__(self, failure=None):
        self.failure = failure
        self.queue_declarations = []
        self.publishes = []

    def queue_declare(self, **kwargs):
        self.queue_declarations.append(kwargs)

    def basic_publish(self, **kwargs):
        self.publishes.append(kwargs)
        if self.failure is not None:
            failure = self.failure
            self.failure = None
            raise failure


class FakeConnectionManager:
    instances = []
    fail_first_publish = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.reconnect_count = 0
        self.channels = []
        self._new_channel()
        self.instances.append(self)

    def _new_channel(self):
        failure = self.fail_first_publish if not self.channels else None
        channel = FakeChannel(failure=failure)
        self.channels.append(channel)
        return channel

    def connect(self):
        return None

    def get_channel(self):
        return self.channels[-1]

    def reconnect(self):
        self.reconnect_count += 1
        self._new_channel()

    def close(self):
        return None


def patch_connection_manager(monkeypatch, fail_first_publish=None):
    FakeConnectionManager.instances = []
    FakeConnectionManager.fail_first_publish = fail_first_publish
    monkeypatch.setattr(producer, "ConnectionManager", FakeConnectionManager)


def test_build_message_body_is_exact_size_and_has_contract_fields():
    msg_id, sent_ts_ns, body = producer.build_message_body(
        "host-123-t1", 1, 1024
    )

    decoded = json.loads(body)
    assert len(body) == 1024
    assert msg_id == "host-123-t1-1"
    assert decoded == {
        "msg_id": msg_id,
        "producer_id": "host-123-t1",
        "seq": 1,
        "sent_ts_ns": sent_ts_ns,
        "payload": decoded["payload"],
    }


def test_build_message_body_rejects_size_too_small():
    try:
        producer.build_message_body("host-123-t1", 1, 1)
    except ValueError as exc:
        assert "at least" in str(exc)
    else:
        raise AssertionError("an impossible message size must be rejected")


def test_confirm_latency_summary_uses_bounded_sample(monkeypatch):
    monkeypatch.setattr(producer, "MAX_LATENCY_SAMPLES", 2)
    stats = producer.RunStats()
    stats.confirmed(1.0)
    stats.confirmed(2.0)
    stats.confirmed(3.0)

    summary = stats.summary(1.0, [])

    assert summary["confirm_latency_ms"]["samples"] == 2
    assert summary["confirm_latency_ms"]["total"] == 3


def test_producer_count_mode_writes_confirmed_csv_and_summary(tmp_path, monkeypatch):
    patch_connection_manager(monkeypatch)
    out = tmp_path / "run"

    result = producer.main([
        "--threads", "1",
        "--count", "3",
        "--rate", "0",
        "--size", "512",
        "--out", str(out),
    ])

    assert result == 0
    with (out / "confirmed.csv").open(newline="", encoding="utf-8") as csv_file:
        rows = list(csv.DictReader(csv_file))
    summary = json.loads((out / "producer_summary.json").read_text(encoding="utf-8"))

    assert len(rows) == 3
    assert summary["sent"] == summary["confirmed"] == 3
    assert summary["nacked"] == summary["republished"] == summary["reconnects"] == 0
    manager = FakeConnectionManager.instances[0]
    assert manager.kwargs["publisher_confirms"] is True
    assert all(
        len(publish["body"]) == 512
        for publish in manager.channels[0].publishes
    )
    assert all(
        publish["properties"].delivery_mode == 2
        and publish["properties"].message_id == json.loads(publish["body"])["msg_id"]
        for publish in manager.channels[0].publishes
    )
    assert all(
        declaration == {"queue": "hw2.orders", "durable": True, "passive": True}
        for declaration in FakeConnectionManager.instances[0].channels[0].queue_declarations
    )


def test_duration_mode_runs_for_requested_time(tmp_path, monkeypatch):
    patch_connection_manager(monkeypatch)
    out = tmp_path / "duration"

    result = producer.main([
        "--threads", "1",
        "--duration", "0.08",
        "--rate", "40",
        "--size", "256",
        "--out", str(out),
    ])
    summary = json.loads((out / "producer_summary.json").read_text(encoding="utf-8"))

    assert result == 0
    assert 0.07 <= summary["elapsed_s"] < 0.5
    assert summary["confirmed"] >= 2


def test_retries_same_message_id_after_connection_loss(tmp_path, monkeypatch):
    patch_connection_manager(
        monkeypatch,
        fail_first_publish=pika.exceptions.StreamLostError("simulated lost connection"),
    )
    out = tmp_path / "retry"

    result = producer.main([
        "--threads", "1",
        "--count", "1",
        "--size", "256",
        "--out", str(out),
    ])

    assert result == 0
    manager = FakeConnectionManager.instances[0]
    first_body = json.loads(manager.channels[0].publishes[0]["body"])
    second_body = json.loads(manager.channels[1].publishes[0]["body"])
    summary = json.loads((out / "producer_summary.json").read_text(encoding="utf-8"))

    assert first_body["msg_id"] == second_body["msg_id"]
    assert first_body["producer_id"] == second_body["producer_id"]
    assert first_body["seq"] == second_body["seq"]
    assert manager.reconnect_count == 1
    assert summary["sent"] == summary["confirmed"] == 1
    assert summary["republished"] == summary["reconnects"] == 1


def test_nack_retry_keeps_message_id_and_reports_nack(tmp_path, monkeypatch):
    patch_connection_manager(
        monkeypatch,
        fail_first_publish=pika.exceptions.NackError([]),
    )
    out = tmp_path / "nack"

    result = producer.main([
        "--threads", "1",
        "--count", "1",
        "--size", "256",
        "--out", str(out),
    ])

    manager = FakeConnectionManager.instances[0]
    first = json.loads(manager.channels[0].publishes[0]["body"])
    second = json.loads(manager.channels[1].publishes[0]["body"])
    summary = json.loads((out / "producer_summary.json").read_text(encoding="utf-8"))

    assert result == 0
    assert first["msg_id"] == second["msg_id"]
    assert summary["nacked"] == 1
    assert summary["republished"] == summary["reconnects"] == 1
