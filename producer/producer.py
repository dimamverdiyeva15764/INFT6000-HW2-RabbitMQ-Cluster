import argparse
import csv
import json
import logging
import os
import random
import socket
import sys
import threading
import time
from pathlib import Path

import pika

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.connection import ConnectionManager
from common.logging_setup import configure_logging


logger = logging.getLogger("Producer")
MAX_LATENCY_SAMPLES = 100_000


def build_message_body(producer_id, seq, size_bytes, msg_id=None, sent_ts_ns=None):
    """Return a contract-shaped UTF-8 JSON message padded to exactly size_bytes."""
    msg_id = msg_id or f"{producer_id}-{seq}"
    sent_ts_ns = sent_ts_ns if sent_ts_ns is not None else time.time_ns()
    message = {
        "msg_id": msg_id,
        "producer_id": producer_id,
        "seq": seq,
        "sent_ts_ns": sent_ts_ns,
        "payload": "",
    }
    empty_body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    if len(empty_body) > size_bytes:
        raise ValueError(
            f"Message metadata needs {len(empty_body)} bytes; --size must be at least that"
        )
    message["payload"] = "A" * (size_bytes - len(empty_body))
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    if len(body) != size_bytes:
        raise RuntimeError("Could not construct a message of the requested byte size")
    return msg_id, sent_ts_ns, body


class RunStats:
    def __init__(self):
        self._lock = threading.Lock()
        self._counts = {
            "sent": 0,
            "confirmed": 0,
            "nacked": 0,
            "republished": 0,
            "reconnects": 0,
        }
        self._confirm_latencies_ms = []
        self._confirm_latency_total = 0

    def increment(self, key, amount=1):
        with self._lock:
            self._counts[key] += amount

    def confirmed(self, latency_ms):
        with self._lock:
            self._counts["confirmed"] += 1
            self._confirm_latency_total += 1
            if len(self._confirm_latencies_ms) < MAX_LATENCY_SAMPLES:
                self._confirm_latencies_ms.append(latency_ms)
            else:
                replacement = random.randrange(self._confirm_latency_total)
                if replacement < MAX_LATENCY_SAMPLES:
                    self._confirm_latencies_ms[replacement] = latency_ms
            return self._counts["confirmed"]

    @staticmethod
    def _percentile(sorted_values, quantile):
        if not sorted_values:
            return None
        position = (len(sorted_values) - 1) * quantile
        lower = int(position)
        upper = min(lower + 1, len(sorted_values) - 1)
        fraction = position - lower
        return sorted_values[lower] + (
            sorted_values[upper] - sorted_values[lower]
        ) * fraction

    def summary(self, elapsed_s, errors):
        with self._lock:
            result = dict(self._counts)
            latencies = sorted(self._confirm_latencies_ms)
        result["elapsed_s"] = round(elapsed_s, 3)
        result["errors"] = list(errors)
        result["confirm_latency_ms"] = {
            "samples": len(latencies),
            "total": self._confirm_latency_total,
            "p50": self._percentile(latencies, 0.50),
            "p95": self._percentile(latencies, 0.95),
            "p99": self._percentile(latencies, 0.99),
        }
        return result


def _publish_one(
    manager,
    producer_id,
    seq,
    size_bytes,
    exchange,
    queue,
    writer,
    writer_lock,
    stats,
    nack_retry_limit,
):
    msg_id = f"{producer_id}-{seq}"
    retries = 0
    verified_channel = None

    while True:
        if retries:
            stats.increment("republished")
        channel = manager.get_channel()
        try:
            if channel is not verified_channel:
                channel.queue_declare(queue=queue, durable=True, passive=True)
                if exchange:
                    channel.exchange_declare(
                        exchange=exchange,
                        exchange_type="direct",
                        durable=True,
                    )
                    channel.queue_bind(
                        exchange=exchange,
                        queue=queue,
                        routing_key=queue,
                    )
                verified_channel = channel

            sent_ts_ns = time.time_ns()
            _, _, body = build_message_body(
                producer_id,
                seq,
                size_bytes,
                msg_id=msg_id,
                sent_ts_ns=sent_ts_ns,
            )
            channel.basic_publish(
                exchange=exchange,
                routing_key=queue,
                body=body,
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type="application/json",
                    message_id=msg_id,
                ),
                mandatory=True,
            )
        except pika.exceptions.UnroutableError as exc:
            stats.increment("nacked")
            raise RuntimeError(f"Message {msg_id} was unroutable: {exc}") from exc
        except pika.exceptions.NackError as exc:
            stats.increment("nacked")
            retries += 1
            if retries > nack_retry_limit:
                raise RuntimeError(
                    f"Message {msg_id} was nacked {retries} times; stopping"
                ) from exc
            logger.warning(
                "Broker nacked a publish; reconnecting and retrying",
                extra={
                    "event": "publish_nacked",
                    "msg_id": msg_id,
                    "retry": retries,
                    "error": str(exc),
                },
            )
            manager.reconnect()
            verified_channel = None
            continue
        except (pika.exceptions.AMQPConnectionError, OSError) as exc:
            retries += 1
            logger.warning(
                "Publish confirmation was interrupted; retrying the same message ID",
                extra={
                    "event": "publish_retry",
                    "msg_id": msg_id,
                    "retry": retries,
                    "error": str(exc),
                },
            )
            manager.reconnect()
            verified_channel = None
            continue

        confirm_ts_ns = time.time_ns()
        with writer_lock:
            writer.writerow(
                [msg_id, producer_id, seq, sent_ts_ns, confirm_ts_ns]
            )
        latency_ms = (confirm_ts_ns - sent_ts_ns) / 1_000_000
        confirmed_count = stats.confirmed(latency_ms)
        if confirmed_count == 1 or confirmed_count % 1000 == 0:
            logger.info(
                "Publish confirmed",
                extra={
                    "event": "publish_confirmed",
                    "msg_id": msg_id,
                    "producer_id": producer_id,
                    "seq": seq,
                    "confirmed": confirmed_count,
                    "confirm_latency_ms": round(latency_ms, 3),
                },
            )
        return


def producer_worker(
    worker_number,
    hosts,
    count,
    duration,
    rate_per_sec,
    size_bytes,
    exchange,
    queue,
    nack_retry_limit,
    stop_event,
    writer,
    writer_lock,
    stats,
    start_gate,
    run_state,
):
    producer_id = f"{socket.gethostname()}-{os.getpid()}-t{worker_number}"
    manager = None
    try:
        manager = ConnectionManager(
            hosts=hosts,
            publisher_confirms=True,
            stop_event=stop_event,
            logger=logging.getLogger("ConnectionManager"),
        )
        manager.connect()
        start_gate.wait()
        run_started = run_state["started_at"]

        interval = 1.0 / rate_per_sec if rate_per_sec > 0 else 0
        next_publish_at = time.monotonic()
        deadline = run_started + duration if duration is not None else None
        seq = 0

        while not stop_event.is_set():
            if count is not None and seq >= count:
                break
            if deadline is not None and time.monotonic() >= deadline:
                break
            if interval:
                wait_s = next_publish_at - time.monotonic()
                if wait_s > 0 and stop_event.wait(wait_s):
                    break
                if deadline is not None and time.monotonic() >= deadline:
                    break

            seq += 1
            stats.increment("sent")
            _publish_one(
                manager,
                producer_id,
                seq,
                size_bytes,
                exchange,
                queue,
                writer,
                writer_lock,
                stats,
                nack_retry_limit,
            )
            if interval:
                next_publish_at = max(
                    next_publish_at + interval,
                    time.monotonic(),
                )

        logger.info(
            "Producer worker finished",
            extra={"event": "worker_finished", "producer_id": producer_id, "sent": seq},
        )
    finally:
        if manager is not None:
            stats.increment("reconnects", manager.reconnect_count)
            manager.close()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="RabbitMQ multi-threaded producer")
    parser.add_argument(
        "--hosts",
        default=os.environ.get(
            "RABBITMQ_HOSTS", "localhost:5672,localhost:5673,localhost:5674"
        ),
        help="Comma-separated RabbitMQ endpoints",
    )
    parser.add_argument("--threads", type=int, default=2, help="Producer thread count")
    run_mode = parser.add_mutually_exclusive_group()
    run_mode.add_argument(
        "--count",
        type=int,
        help="Messages per thread; default is 100 when --duration is not set",
    )
    run_mode.add_argument(
        "--duration",
        type=float,
        help="Run for this many seconds, then finish in-flight publishes",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=0.0,
        help="Messages per second per thread; 0 means unthrottled",
    )
    parser.add_argument("--size", type=int, default=256, help="Exact JSON body size in bytes")
    parser.add_argument(
        "--exchange",
        default="",
        help="Optional direct exchange; default contract uses the default exchange",
    )
    parser.add_argument(
        "--routing-key",
        "--queue",
        dest="queue",
        default="hw2.orders",
        help="Queue name (default: hw2.orders)",
    )
    parser.add_argument("--out", default=".", help="Output directory")
    parser.add_argument(
        "--nack-retry-limit",
        type=int,
        default=5,
        help="Maximum retries for broker NACKs; connection loss is retried until reconnected",
    )
    args = parser.parse_args(argv)

    if args.threads < 1:
        parser.error("--threads must be at least 1")
    if args.count is not None and args.count < 1:
        parser.error("--count must be at least 1")
    if args.duration is not None and args.duration <= 0:
        parser.error("--duration must be greater than 0")
    if args.rate < 0:
        parser.error("--rate cannot be negative")
    if args.size < 1:
        parser.error("--size must be at least 1")
    if args.nack_retry_limit < 0:
        parser.error("--nack-retry-limit cannot be negative")
    args.hosts = [host.strip() for host in args.hosts.split(",") if host.strip()]
    if not args.hosts:
        parser.error("--hosts must contain at least one endpoint")
    if args.count is None and args.duration is None:
        args.count = 100

    producer_id = f"{socket.gethostname()}-{os.getpid()}-t1"
    try:
        build_message_body(producer_id, 1, args.size)
    except ValueError as exc:
        parser.error(str(exc))
    return args


def _write_summary(path, summary):
    temporary_path = f"{path}.tmp"
    with open(temporary_path, "w", encoding="utf-8") as summary_file:
        json.dump(summary, summary_file, indent=2)
        summary_file.write("\n")
    os.replace(temporary_path, path)


def run_producer(args):
    configure_logging()
    os.makedirs(args.out, exist_ok=True)
    csv_path = os.path.join(args.out, "confirmed.csv")
    summary_path = os.path.join(args.out, "producer_summary.json")
    stats = RunStats()
    errors = []
    errors_lock = threading.Lock()
    stop_event = threading.Event()
    writer_lock = threading.Lock()
    setup_started = time.monotonic()
    run_state = {"started_at": None}
    start_gate = threading.Barrier(
        args.threads,
        action=lambda: run_state.__setitem__("started_at", time.monotonic()),
    )

    with open(csv_path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            ["msg_id", "producer_id", "seq", "sent_ts_ns", "confirm_ts_ns"]
        )
        threads = []
        for worker_number in range(1, args.threads + 1):
            def run_worker(number=worker_number):
                try:
                    producer_worker(
                        number,
                        args.hosts,
                        args.count,
                        args.duration,
                        args.rate,
                        args.size,
                        args.exchange,
                        args.queue,
                        args.nack_retry_limit,
                        stop_event,
                        writer,
                        writer_lock,
                        stats,
                        start_gate,
                        run_state,
                    )
                except Exception as exc:
                    start_gate.abort()
                    with errors_lock:
                        errors.append(str(exc))
                    logger.error(
                        "Producer worker failed",
                        extra={
                            "event": "worker_failed",
                            "worker": number,
                            "error": str(exc),
                        },
                    )
                    stop_event.set()

            thread = threading.Thread(
                target=run_worker,
                name=f"producer-{worker_number}",
            )
            threads.append(thread)
            thread.start()

        interrupted = False
        try:
            for thread in threads:
                thread.join()
        except KeyboardInterrupt:
            interrupted = True
            stop_event.set()
            logger.warning("Shutdown requested; stopping producer workers",
                           extra={"event": "shutdown_requested"})
            for thread in threads:
                thread.join()

    run_started = run_state["started_at"] or setup_started
    elapsed_s = time.monotonic() - run_started
    summary = stats.summary(elapsed_s, errors)
    summary["status"] = "interrupted" if interrupted else ("failed" if errors else "ok")
    _write_summary(summary_path, summary)
    logger.info(
        "Producer run finished",
        extra={
            "event": "run_finished",
            "status": summary["status"],
            "sent": summary["sent"],
            "confirmed": summary["confirmed"],
            "nacked": summary["nacked"],
            "republished": summary["republished"],
            "reconnects": summary["reconnects"],
            "csv": csv_path,
            "summary": summary_path,
        },
    )
    if interrupted:
        return 130
    return 1 if errors else 0


def main(argv=None):
    return run_producer(parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
