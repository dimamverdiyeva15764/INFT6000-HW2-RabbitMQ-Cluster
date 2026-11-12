"""Multi-threaded RabbitMQ consumer with manual acknowledgments.

What it guarantees
------------------
* ``auto_ack=False``: a message is acknowledged ONLY after it was parsed,
  de-duplicated and its row was written (and flushed) to ``received.csv``.
* If processing raises, the message is ``basic_nack(requeue=True)``-ed, so the
  broker gives it back (the queue's ``x-delivery-limit=10`` stops poison loops).
* If the connection/channel dies (node crash, partition) every thread reconnects
  through the shared ``ConnectionManager`` (host rotation + backoff) and
  re-subscribes. Messages that were delivered but not acked come back with
  ``redelivered=true``; they are written again (one row per delivery, as the
  contract requires) and logged as ``event=duplicate`` but never re-processed.
* SIGINT / SIGTERM: stop consuming, finish the message in hand (ack it), flush
  the CSV, write ``consumer_summary.json`` and exit 0 (well inside 30 s).

Delivery semantics: at-least-once from the broker + de-duplication by
``msg_id`` here = effectively-once processing.

Usage (see docs/CONTRACT.md section 4)::

    python3 consumer/consumer.py --hosts localhost:5672,localhost:5673,localhost:5674 \
        --queue hw2.orders --threads 4 --prefetch 100 --out results/run1
"""

import argparse
import csv
import json
import logging
import os
import signal
import socket
import sys
import threading
import time
from pathlib import Path

import pika

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.connection import ConnectionManager, ConnectionStoppedError
from common.logging_setup import configure_logging

logger = logging.getLogger("Consumer")

CSV_HEADER = [
    "msg_id",
    "producer_id",
    "seq",
    "sent_ts_ns",
    "recv_ts_ns",
    "redelivered",
    "consumer_id",
]
MAX_CONSECUTIVE_SETUP_FAILURES = 10


class MessageFormatError(ValueError):
    """The body is not a contract-shaped message."""


def parse_message(body):
    """Parse a contract message body (docs/CONTRACT.md section 2)."""
    try:
        data = json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)
        return {
            "msg_id": str(data["msg_id"]),
            "producer_id": str(data["producer_id"]),
            "seq": int(data["seq"]),
            "sent_ts_ns": int(data["sent_ts_ns"]),
        }
    except (KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
        raise MessageFormatError(f"invalid message body: {exc}") from exc


class SharedState:
    """Everything the consumer threads share, protected by one lock."""

    def __init__(self, csv_file):
        self._lock = threading.Lock()
        self._writer = csv.writer(csv_file)
        self._csv_file = csv_file
        self._seen = set()
        self._last_seq = {}  # (producer_id, consumer_id) -> highest seq seen so far
        self.counts = {
            "received": 0,
            "unique": 0,
            "duplicates": 0,
            "redelivered": 0,
            "out_of_order": 0,
            "nacked": 0,
            "reconnects": 0,
        }
        self.last_activity = time.monotonic()

    def record(self, msg, redelivered, consumer_id):
        """Write one delivery row; return (is_duplicate, out_of_order_info|None).

        The row is flushed before returning, so the caller can ack safely.
        """
        with self._lock:
            # Timestamp taken inside the lock so file order == timestamp order.
            recv_ts_ns = time.time_ns()
            self.counts["received"] += 1
            if redelivered:
                self.counts["redelivered"] += 1
            duplicate = msg["msg_id"] in self._seen
            reorder = None
            if duplicate:
                self.counts["duplicates"] += 1
            else:
                self._seen.add(msg["msg_id"])
                self.counts["unique"] += 1
                # Ordering guarantee checked here: one consumer thread sees each
                # producer's messages in increasing seq. (Across several competing
                # consumers the global arrival order is NOT defined by AMQP.)
                # Redelivered messages legitimately arrive late, so they are skipped.
                if not redelivered:
                    key = (msg["producer_id"], consumer_id)
                    last = self._last_seq.get(key, 0)
                    if msg["seq"] < last:
                        self.counts["out_of_order"] += 1
                        reorder = {"expected_greater_than": last, "actual": msg["seq"]}
                    else:
                        self._last_seq[key] = msg["seq"]
            self._writer.writerow(
                [
                    msg["msg_id"],
                    msg["producer_id"],
                    msg["seq"],
                    msg["sent_ts_ns"],
                    recv_ts_ns,
                    "true" if redelivered else "false",
                    consumer_id,
                ]
            )
            self._csv_file.flush()
            self.last_activity = time.monotonic()
            return duplicate, reorder

    def add_reconnects(self, n):
        with self._lock:
            self.counts["reconnects"] += n

    def add_nack(self):
        with self._lock:
            self.counts["nacked"] += 1

    def unique(self):
        with self._lock:
            return self.counts["unique"]

    def snapshot(self):
        with self._lock:
            return dict(self.counts)


def handle_delivery(channel, method, properties, body, state, consumer_id):
    """Process one delivery. Ack after the row is on disk, nack on any error."""
    try:
        msg = parse_message(body)
        duplicate, reorder = state.record(msg, bool(method.redelivered), consumer_id)
    except Exception as exc:  # noqa: BLE001 - any failure must give the message back
        state.add_nack()
        logger.error(
            "Processing failed; nack with requeue",
            extra={"event": "nack_requeue", "delivery_tag": method.delivery_tag, "error": str(exc)},
        )
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        return

    if duplicate:
        logger.warning(
            "Duplicate delivery ignored (acked, not reprocessed)",
            extra={
                "event": "duplicate",
                "msg_id": msg["msg_id"],
                "redelivered": bool(method.redelivered),
            },
        )
    if reorder:
        logger.warning(
            "Out-of-order message",
            extra={
                "event": "out_of_order",
                "msg_id": msg["msg_id"],
                "producer_id": msg["producer_id"],
                **reorder,
            },
        )
    channel.basic_ack(delivery_tag=method.delivery_tag)


def consumer_worker(number, args, state, stop_event):
    consumer_id = f"{socket.gethostname()}-{os.getpid()}-c{number}"
    manager = ConnectionManager(
        hosts=args.hosts,
        publisher_confirms=False,
        stop_event=stop_event,
        logger=logging.getLogger("ConnectionManager"),
    )
    failures = 0
    try:
        while not stop_event.is_set():
            try:
                channel = manager.get_channel()
                channel.basic_qos(prefetch_count=args.prefetch)
                logger.info(
                    "Subscribed",
                    extra={
                        "event": "subscribed",
                        "consumer_id": consumer_id,
                        "host": manager.connected_host,
                        "prefetch": args.prefetch,
                    },
                )
                # inactivity_timeout lets us poll stop_event and heartbeats.
                for item in channel.consume(
                    queue=args.queue, auto_ack=False, inactivity_timeout=1.0
                ):
                    if stop_event.is_set():
                        break
                    if item is None or item[0] is None:
                        continue
                    failures = 0
                    method, properties, body = item
                    handle_delivery(channel, method, properties, body, state, consumer_id)
                    if args.stop_after and state.unique() >= args.stop_after:
                        logger.info(
                            "Reached --stop-after",
                            extra={"event": "stop_after_reached", "unique": state.unique()},
                        )
                        stop_event.set()
                        break
                # Leaving the loop: unacked prefetched messages return to the queue
                # when the channel closes (they are NOT lost).
            except ConnectionStoppedError:
                break
            except (pika.exceptions.ProbableAuthenticationError,
                    pika.exceptions.ProbableAccessDeniedError) as exc:
                logger.error("Authentication failed", extra={"event": "auth_failed", "error": str(exc)})
                stop_event.set()
                raise
            except (
                pika.exceptions.AMQPError,  # includes ConnectionClosed, StreamLostError, ChannelClosed
                OSError,
            ) as exc:
                if stop_event.is_set():
                    break
                failures += 1
                code = getattr(exc, "reply_code", None)
                logger.warning(
                    "Connection/channel lost; reconnecting and re-subscribing",
                    extra={
                        "event": "consumer_reconnect",
                        "consumer_id": consumer_id,
                        "error": f"{type(exc).__name__}: {exc}",
                        "reply_code": code,
                        "attempt": failures,
                    },
                )
                if code == 404 and failures >= MAX_CONSECUTIVE_SETUP_FAILURES:
                    logger.error(
                        "Queue does not exist; run ./scripts/up.sh first",
                        extra={"event": "queue_missing", "queue": args.queue},
                    )
                    stop_event.set()
                    raise
                try:
                    manager.reconnect()
                except ConnectionStoppedError:
                    break
    finally:
        state.add_reconnects(manager.reconnect_count)
        manager.close()
        logger.info("Consumer worker finished", extra={"event": "worker_finished", "consumer_id": consumer_id})


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="RabbitMQ multi-threaded manual-ack consumer")
    p.add_argument(
        "--hosts",
        default=os.environ.get("RABBITMQ_HOSTS", "localhost:5672,localhost:5673,localhost:5674"),
        help="Comma-separated RabbitMQ endpoints",
    )
    p.add_argument("--queue", default="hw2.orders", help="Queue to consume (default hw2.orders)")
    p.add_argument("--threads", type=int, default=2, help="Consumer threads (one connection each)")
    p.add_argument("--prefetch", type=int, default=100, help="basic_qos prefetch_count per channel")
    p.add_argument("--out", default=".", help="Output directory")
    p.add_argument(
        "--idle-exit",
        type=float,
        default=0,
        help="Exit after this many seconds without a delivery (0 = run until signal)",
    )
    p.add_argument(
        "--stop-after",
        type=int,
        default=0,
        help="Exit after this many UNIQUE messages (0 = no limit); handy to drain a backlog",
    )
    args = p.parse_args(argv)
    if args.threads < 1:
        p.error("--threads must be at least 1")
    if args.prefetch < 1:
        p.error("--prefetch must be at least 1")
    if args.idle_exit < 0 or args.stop_after < 0:
        p.error("--idle-exit and --stop-after cannot be negative")
    args.hosts = [h.strip() for h in args.hosts.split(",") if h.strip()]
    if not args.hosts:
        p.error("--hosts must contain at least one endpoint")
    return args


def _write_summary(path, summary):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def run_consumer(args):
    configure_logging()
    os.makedirs(args.out, exist_ok=True)
    csv_path = os.path.join(args.out, "received.csv")
    summary_path = os.path.join(args.out, "consumer_summary.json")
    stop_event = threading.Event()
    errors = []

    def request_stop(signum, _frame):
        logger.warning(
            "Shutdown requested; finishing in-flight messages",
            extra={"event": "shutdown_requested", "signal": signal.Signals(signum).name},
        )
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    started = time.monotonic()
    with open(csv_path, "w", newline="", encoding="utf-8") as csv_file:
        csv.writer(csv_file).writerow(CSV_HEADER)
        csv_file.flush()
        state = SharedState(csv_file)

        def run_worker(number):
            try:
                consumer_worker(number, args, state, stop_event)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"c{number}: {type(exc).__name__}: {exc}")
                logger.error(
                    "Consumer worker failed",
                    extra={"event": "worker_failed", "worker": number, "error": str(exc)},
                )
                stop_event.set()

        threads = [
            threading.Thread(target=run_worker, args=(n,), name=f"consumer-{n}")
            for n in range(1, args.threads + 1)
        ]
        for t in threads:
            t.start()

        # Main thread: wait, watching for --idle-exit, while staying signal-responsive.
        while any(t.is_alive() for t in threads):
            time.sleep(0.5)
            if args.idle_exit and not stop_event.is_set():
                idle = time.monotonic() - state.last_activity
                if state.unique() > 0 and idle >= args.idle_exit:
                    logger.info(
                        "Idle timeout reached",
                        extra={"event": "idle_exit", "idle_s": round(idle, 1)},
                    )
                    stop_event.set()
        for t in threads:
            t.join()

    summary = state.snapshot()
    summary["elapsed_s"] = round(time.monotonic() - started, 3)
    summary["errors"] = errors
    summary["status"] = "failed" if errors else "ok"
    _write_summary(summary_path, summary)
    logger.info(
        "Consumer run finished",
        extra={"event": "run_finished", "csv": csv_path, "summary": summary_path, **summary},
    )
    return 1 if errors else 0


def main(argv=None):
    return run_consumer(parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
