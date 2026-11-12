import logging
import os
import random
import threading
import time

import pika


DEFAULT_HOSTS = ("localhost:5672", "localhost:5673", "localhost:5674")


class ConnectionStoppedError(RuntimeError):
    """Raised when a caller requests shutdown while the client is reconnecting."""


def _parse_host(endpoint):
    endpoint = endpoint.strip()
    if not endpoint:
        raise ValueError("RabbitMQ host entries cannot be empty")

    if endpoint.startswith("["):
        host, separator, port_text = endpoint[1:].partition("]:")
        if not separator:
            raise ValueError(f"Invalid RabbitMQ endpoint: {endpoint!r}")
    elif ":" in endpoint:
        host, _, port_text = endpoint.rpartition(":")
    else:
        host, port_text = endpoint, "5672"

    try:
        port = int(port_text)
    except ValueError as exc:
        raise ValueError(f"Invalid RabbitMQ port in endpoint: {endpoint!r}") from exc
    if not host or not 1 <= port <= 65535:
        raise ValueError(f"Invalid RabbitMQ endpoint: {endpoint!r}")
    return host, port


class ConnectionManager:
    """Owns one Pika connection/channel and rotates through configured broker nodes."""

    def __init__(
        self,
        hosts=None,
        *,
        username=None,
        password=None,
        virtual_host=None,
        heartbeat=10,
        blocked_connection_timeout=30,
        publisher_confirms=False,
        stop_event=None,
        logger=None,
    ):
        if hosts is None:
            hosts = os.environ.get("RABBITMQ_HOSTS")
        if isinstance(hosts, str):
            hosts = [host.strip() for host in hosts.split(",") if host.strip()]
        self.hosts = list(hosts or DEFAULT_HOSTS)
        if not self.hosts:
            raise ValueError("At least one RabbitMQ host is required")
        self._endpoints = [_parse_host(host) for host in self.hosts]
        self._host_order = list(range(len(self.hosts)))
        # Hosts are tried in random order to spread clients over the nodes.
        # RABBITMQ_HOSTS_SHUFFLE=0 keeps the given order, so a failure test can put
        # every client on the node it is about to break (scripts/p4/chaos_run.sh).
        if os.environ.get("RABBITMQ_HOSTS_SHUFFLE", "1") != "0":
            random.shuffle(self._host_order)
        self.current_host_idx = 0

        self.username = username or os.environ.get("RABBITMQ_USER", "admin")
        self.password = password or os.environ.get("RABBITMQ_PASS", "admin123")
        self.virtual_host = (
            virtual_host
            if virtual_host is not None
            else os.environ.get("RABBITMQ_VHOST", "/")
        )
        self.heartbeat = heartbeat
        self.blocked_connection_timeout = blocked_connection_timeout
        self.publisher_confirms = publisher_confirms
        self.stop_event = stop_event or threading.Event()
        self.logger = logger or logging.getLogger("ConnectionManager")

        self.connection = None
        self.channel = None
        self.connected_host = None
        self.reconnect_count = 0
        self._ever_connected = False

    def _active(self):
        return (
            self.connection is not None
            and self.connection.is_open
            and self.channel is not None
            and self.channel.is_open
        )

    def connect(self):
        """Connect with exponential backoff; authentication/configuration errors fail fast."""
        if self._active():
            return self.channel
        self._close_current()

        attempt = 0
        while not self.stop_event.is_set():
            host_index = self._host_order[self.current_host_idx]
            host, port = self._endpoints[host_index]
            credentials = pika.PlainCredentials(self.username, self.password)
            parameters = pika.ConnectionParameters(
                host=host,
                port=port,
                virtual_host=self.virtual_host,
                credentials=credentials,
                heartbeat=self.heartbeat,
                blocked_connection_timeout=self.blocked_connection_timeout,
            )
            self.logger.info(
                "Connecting to RabbitMQ",
                extra={
                    "event": "connection_attempt",
                    "host": host,
                    "port": port,
                    "vhost": self.virtual_host,
                },
            )
            try:
                self.connection = pika.BlockingConnection(parameters)
                self.channel = self.connection.channel()
                if self.publisher_confirms:
                    self.channel.confirm_delivery()
                old_host = self.connected_host
                self.connected_host = f"{host}:{port}"
                if self._ever_connected:
                    self.reconnect_count += 1
                    self.logger.warning(
                        "RabbitMQ connection re-established",
                        extra={
                            "event": "connection_reestablished",
                            "previous_host": old_host,
                            "host": self.connected_host,
                            "reconnect_count": self.reconnect_count,
                        },
                    )
                else:
                    self.logger.info(
                        "Connected to RabbitMQ",
                        extra={
                            "event": "connected",
                            "host": self.connected_host,
                            "vhost": self.virtual_host,
                        },
                    )
                self._ever_connected = True
                return self.channel
            except (
                pika.exceptions.ProbableAuthenticationError,
                pika.exceptions.ProbableAccessDeniedError,
            ):
                self._close_current()
                raise
            except (pika.exceptions.AMQPConnectionError, OSError) as exc:
                self._close_current()
                attempt += 1
                backoff = min(0.5 * (2 ** (attempt - 1)), 10.0)
                delay = backoff + random.uniform(0.1, 0.5)
                self.logger.warning(
                    "RabbitMQ connection failed",
                    extra={
                        "event": "connection_failed",
                        "host": f"{host}:{port}",
                        "error": str(exc),
                        "retry_in_s": round(delay, 2),
                    },
                )
                self.current_host_idx = (self.current_host_idx + 1) % len(
                    self._host_order
                )
                if self.stop_event.wait(delay):
                    break

        raise ConnectionStoppedError("RabbitMQ connection attempt was cancelled")

    def get_channel(self):
        if not self._active():
            self.connect()
        return self.channel

    def reconnect(self):
        """Close the current connection and try the next configured node."""
        self._close_current()
        self.current_host_idx = (self.current_host_idx + 1) % len(self._host_order)
        return self.connect()

    def _close_current(self):
        connection = self.connection
        self.connection = None
        self.channel = None
        if connection is not None and connection.is_open:
            try:
                connection.close()
            except (pika.exceptions.AMQPError, OSError) as exc:
                self.logger.warning(
                    "Error while closing RabbitMQ connection",
                    extra={"event": "connection_close_failed", "error": str(exc)},
                )

    def close(self):
        self._close_current()
