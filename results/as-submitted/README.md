# Evidence from the code exactly as submitted (2026-11-11)

First test campaign on the native test cluster, with the first complete version of the scripts and clients: 12 chaos runs (S1 to S4, 3 each, clients on random nodes) and the persistence test. All passed with 0 lost; see `data-integrity.md`. Throughput in these runs is understated because the test cluster's port forwarder did not set TCP_NODELAY at that time; the integrity results are unaffected. The final evidence is in `results/chaos/`.
