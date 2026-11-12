# Evidence from the code exactly as submitted (2026-11-11)

The review first ran the team's scripts and clients unmodified (`amqp-cluster-P4_1.zip`): 12 chaos runs (S1 to S4, 3 each, clients on random nodes) and the persistence test. All passed with 0 lost; see `data-integrity.md`. Throughput in these runs is understated because the review's port forwarder lacked TCP_NODELAY (see `docs/QA-REVIEW.md`); the integrity results are unaffected. The final evidence is in `results/chaos/`.
