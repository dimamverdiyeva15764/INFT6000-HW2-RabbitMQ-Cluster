"""Consumer logic tests using a fake channel (no broker needed)."""
import csv
import json
import types

import pytest

from consumer.consumer import MessageFormatError, SharedState, handle_delivery, parse_args, parse_message


class FakeChannel:
    def __init__(self):
        self.acked, self.nacked = [], []

    def basic_ack(self, delivery_tag):
        self.acked.append(delivery_tag)

    def basic_nack(self, delivery_tag, requeue):
        self.nacked.append((delivery_tag, requeue))


def body(producer, seq):
    return json.dumps(
        {"msg_id": f"{producer}-{seq}", "producer_id": producer, "seq": seq,
         "sent_ts_ns": 123, "payload": "x"}
    ).encode()


def method(tag, redelivered=False):
    return types.SimpleNamespace(delivery_tag=tag, redelivered=redelivered)


@pytest.fixture
def state(tmp_path):
    f = open(tmp_path / "received.csv", "w", newline="")
    yield SharedState(f), tmp_path / "received.csv"
    f.close()


def rows(path):
    with open(path, newline="") as f:
        return list(csv.reader(f))


def test_parse_message_ok_and_bad():
    assert parse_message(body("P", 7))["seq"] == 7
    for bad in (b"not json", b'{"msg_id":"a"}', b"\xff\xfe"):
        with pytest.raises(MessageFormatError):
            parse_message(bad)


def test_ack_only_after_row_is_written(state):
    st, path = state
    ch = FakeChannel()
    handle_delivery(ch, method(1), None, body("P", 1), st, "c1")
    assert ch.acked == [1] and ch.nacked == []
    # the row is already flushed to disk when the ack happened
    assert len(rows(path)) == 1 and rows(path)[0][0] == "P-1"


def test_duplicate_is_written_acked_but_counted_once(state):
    st, path = state
    ch = FakeChannel()
    handle_delivery(ch, method(1), None, body("P", 1), st, "c1")
    handle_delivery(ch, method(2, redelivered=True), None, body("P", 1), st, "c1")
    c = st.snapshot()
    assert (c["received"], c["unique"], c["duplicates"], c["redelivered"]) == (2, 1, 1, 1)
    assert ch.acked == [1, 2]
    assert [r[5] for r in rows(path)] == ["false", "true"]


def test_out_of_order_detected(state):
    st, _ = state
    ch = FakeChannel()
    for tag, seq in enumerate((1, 3, 2), start=1):
        handle_delivery(ch, method(tag), None, body("P", seq), st, "c1")
    assert st.snapshot()["out_of_order"] == 1


def test_out_of_order_is_per_consumer_thread(state):
    st, _ = state
    ch = FakeChannel()
    handle_delivery(ch, method(1), None, body("P", 5), st, "c1")
    handle_delivery(ch, method(2), None, body("P", 3), st, "c2")  # other consumer thread: fine
    assert st.snapshot()["out_of_order"] == 0


def test_redelivered_late_message_is_not_a_reorder(state):
    st, _ = state
    ch = FakeChannel()
    handle_delivery(ch, method(1), None, body("P", 5), st, "c1")
    handle_delivery(ch, method(2, redelivered=True), None, body("P", 3), st, "c1")
    assert st.snapshot()["out_of_order"] == 0


def test_out_of_order_is_per_producer(state):
    st, _ = state
    ch = FakeChannel()
    handle_delivery(ch, method(1), None, body("A", 5), st, "c1")
    handle_delivery(ch, method(2), None, body("B", 1), st, "c1")  # other producer: fine
    assert st.snapshot()["out_of_order"] == 0


def test_bad_message_is_nacked_with_requeue_and_not_acked(state):
    st, path = state
    ch = FakeChannel()
    handle_delivery(ch, method(9), None, b"garbage", st, "c1")
    assert ch.acked == [] and ch.nacked == [(9, True)]
    assert st.snapshot()["nacked"] == 1 and len(rows(path)) == 0


def test_processing_error_is_nacked(state, monkeypatch):
    st, _ = state
    ch = FakeChannel()
    monkeypatch.setattr(st, "record", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    handle_delivery(ch, method(4), None, body("P", 1), st, "c1")
    assert ch.nacked == [(4, True)] and ch.acked == []


def test_cli_defaults_and_validation():
    a = parse_args(["--threads", "4", "--prefetch", "50"])
    assert a.threads == 4 and a.prefetch == 50 and a.queue == "hw2.orders"
    assert len(a.hosts) == 3
    with pytest.raises(SystemExit):
        parse_args(["--threads", "0"])
