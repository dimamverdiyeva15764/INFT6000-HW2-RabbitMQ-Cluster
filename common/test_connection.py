import pika
import pytest

from common.connection import ConnectionManager


class FakeChannel:
    def __init__(self):
        self.confirms_enabled = False

    def confirm_delivery(self):
        self.confirms_enabled = True


class FakeConnection:
    def __init__(self):
        self.channel_instance = FakeChannel()
        self.is_open = True

    def channel(self):
        return self.channel_instance

    def close(self):
        self.is_open = False


def test_connection_uses_environment_configuration(monkeypatch):
    seen = {}
    connection = FakeConnection()

    def connect(parameters):
        seen["parameters"] = parameters
        return connection

    monkeypatch.setenv("RABBITMQ_USER", "app")
    monkeypatch.setenv("RABBITMQ_PASS", "secret")
    monkeypatch.setenv("RABBITMQ_VHOST", "/")
    monkeypatch.setattr(pika, "BlockingConnection", connect)
    manager = ConnectionManager(hosts=["localhost:5673"], publisher_confirms=True)

    manager.connect()

    params = seen["parameters"]
    assert params.host == "localhost"
    assert params.port == 5673
    assert params.virtual_host == "/"
    assert params.credentials.username == "app"
    assert params.credentials.password == "secret"
    assert connection.channel_instance.confirms_enabled


def test_connection_rotates_hosts_after_transient_failure(monkeypatch):
    attempts = []
    connection = FakeConnection()

    def connect(parameters):
        attempts.append((parameters.host, parameters.port))
        if len(attempts) == 1:
            raise pika.exceptions.AMQPConnectionError("offline")
        return connection

    monkeypatch.setattr(pika, "BlockingConnection", connect)
    monkeypatch.setattr("common.connection.random.shuffle", lambda hosts: None)
    monkeypatch.setattr("common.connection.time.sleep", lambda _: None)
    manager = ConnectionManager(
        hosts=["node1:5672", "node2:5673"],
        publisher_confirms=False,
    )

    manager.connect()

    assert attempts == [("node1", 5672), ("node2", 5673)]
    assert manager.reconnect_count == 0


def test_reconnect_rotates_nodes_and_counts_successful_reconnection(monkeypatch):
    attempts = []

    def connect(parameters):
        attempts.append((parameters.host, parameters.port))
        return FakeConnection()

    monkeypatch.setattr(pika, "BlockingConnection", connect)
    monkeypatch.setattr("common.connection.random.shuffle", lambda hosts: None)
    manager = ConnectionManager(hosts=["node1:5672", "node2:5673"])

    manager.connect()
    manager.reconnect()

    assert attempts == [("node1", 5672), ("node2", 5673)]
    assert manager.reconnect_count == 1
    manager.close()


def test_authentication_errors_are_not_retried(monkeypatch):
    calls = []

    def connect(_parameters):
        calls.append(True)
        raise pika.exceptions.ProbableAuthenticationError("bad credentials")

    monkeypatch.setattr(pika, "BlockingConnection", connect)
    manager = ConnectionManager(hosts=["localhost:5672"])

    with pytest.raises(pika.exceptions.ProbableAuthenticationError):
        manager.connect()

    assert len(calls) == 1


def test_hosts_keep_given_order_when_shuffle_disabled(monkeypatch):
    """RABBITMQ_HOSTS_SHUFFLE=0 keeps the configured order (used by targeted chaos runs)."""
    monkeypatch.setenv("RABBITMQ_HOSTS_SHUFFLE", "0")
    manager = ConnectionManager(["localhost:5673", "localhost:5672", "localhost:5674"])
    assert manager._host_order == [0, 1, 2]
