# C4 Level 2 - Container Diagram

Shows the runtime containers of the system and how they talk to each other: the three RabbitMQ nodes, the Raft sync layer that replicates the quorum queue, the monitoring stack, the test clients and the management/benchmark tools.

- **Source (C4-PlantUML):** [`container-diagram.puml`](container-diagram.puml) - render with https://www.plantuml.com/plantuml or `java -jar plantuml.jar -tpng container-diagram.puml`
- **Rendered:** `container-diagram.png` (use this one in the report)
- A Mermaid copy is below so GitHub shows it without tools.

![Container diagram](container-diagram.png)

## Every element maps to the code

| Diagram element | Where it is defined | Ports / values in the diagram |
|---|---|---|
| rabbit1, rabbit2, rabbit3 | `docker-compose.yml` services, `rabbitmq/rabbitmq.conf` (`classic_config`) | AMQP 5672, UI/API 15672, metrics 15692 (inside `amqp-net`); host 5672-5674 / 15672-15674 |
| Raft sync layer | quorum queue `hw2.orders` declared in `scripts/up.sh` (`x-queue-type=quorum`, group size 3); `cluster_partition_handling = pause_minority` | Erlang distribution 25672 |
| Prometheus | `docker-compose.yml` service `prometheus`, `monitoring/prometheus/prometheus.yml`, `monitoring/prometheus/rules/rabbitmq-alerts.yml` | scrape 15692 every 5 s, UI 9090 |
| Grafana | `docker-compose.yml` service `grafana`, `monitoring/grafana/provisioning/`, `monitoring/grafana/dashboards/*.json` | 3000, datasource `http://prometheus:9090` |
| Management & benchmark tools | `scripts/mgmt/*`, `benchmarks/run_bench.py`, `benchmarks/analyze.py` | HTTP API 15672-15674, Prometheus 9090 |
| Producer app | `producer/` (CLI in `docs/CONTRACT.md` section 3) | host ports 5672-5674 |
| Consumer app | `consumer/` (CLI in `docs/CONTRACT.md` section 4) | host ports 5672-5674 |

If a port, service or container name changes in `docker-compose.yml`, update this diagram and the Deployment diagram.

## Mermaid version

```mermaid
flowchart TB
    OPS(["Operator"])
    subgraph SYS["Distributed AMQP Messaging Cluster"]
        direction TB
        TOOLS["Management & benchmark tools<br/>bash, Python 3"]
        PROD["Producer app<br/>Python, pika, confirms"]
        CONS["Consumer app<br/>Python, pika, manual acks"]
        R1["rabbit1<br/>RabbitMQ 3.13.7<br/>5672 / 15672 / 15692"]
        R2["rabbit2<br/>RabbitMQ 3.13.7<br/>5672 / 15672 / 15692"]
        R3["rabbit3<br/>RabbitMQ 3.13.7<br/>5672 / 15672 / 15692"]
        RAFT[["Raft sync layer - quorum queue hw2.orders<br/>1 leader + 2 followers, commit = 2 of 3<br/>Erlang distribution :25672"]]
        PROM["Prometheus v2.53.0<br/>scrape 5 s, 8 alert rules"]
        GRAF["Grafana 11.1.0<br/>3 dashboards"]
    end
    OPS -->|runs| TOOLS
    OPS -->|HTTP 3000| GRAF
    TOOLS -->|starts| PROD
    TOOLS -->|starts / SIGINT| CONS
    TOOLS -->|HTTP API 15672-15674| R2
    PROD -->|AMQP publish + confirms| R1
    CONS -->|AMQP consume + ack| R3
    R1 -->|replicate, vote :25672| RAFT
    R2 -->|replicate, vote :25672| RAFT
    R3 -->|replicate, vote :25672| RAFT
    PROM -->|scrape :15692| R1
    PROM -->|scrape :15692| R2
    PROM -->|scrape :15692| R3
    GRAF -->|PromQL :9090| PROM
```
