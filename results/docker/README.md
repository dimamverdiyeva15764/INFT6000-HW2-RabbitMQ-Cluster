# Docker Desktop test results

Report section 8.6 and presentation slide 7 refer to two runs made on the team's Mac with Docker Desktop:

- `scripts/p4/smoke.sh`: 10,000 confirmed, 10,000 received, 0 lost, 0 duplicates, PASS
- `scripts/p4/chaos_run.sh leader-crash`: 23,680 confirmed, 23,680 received, 0 lost, 2 duplicates, PASS

TODO before submission: copy the result folders of these two runs here
(for example `results/docker/smoke/` and `results/docker/leader-crash/`, each with
`confirmed.csv`, `received.csv`, `validation.txt`, `validation.json`).
The screenshots of the Docker health and monitoring checks are in `docs/evidence/docker/`.
