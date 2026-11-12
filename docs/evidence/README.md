# Evidence screenshots

Put these 10 files in this folder (names must match exactly; they are referenced from `../failure-test-plan.md`):

| File | Content |
|---|---|
| 01-up-ready.png | Terminal: `up.sh` finished, quorum_status table |
| 02-ui-nodes.png | UI Overview -> Nodes: 3 nodes green |
| 03-ui-queues.png | UI Queues: `hw2.orders`, type quorum |
| 04-ui-queue-leader-before.png | `hw2.orders` page: leader + 3 members |
| 05-ui-node-down.png | Leader node down (S2) |
| 06-ui-recovered.png | 3 nodes green again (S2) |
| 07-ui-partition.png | Node isolated (S3) |
| 08-ui-partition-healed.png | Partition healed (S3) |
| 09-log-leader-crash.png | Terminal: leader-crash output (election time) |
| 10-log-partition.png | Terminal: partition scenario output |

Check that nothing is missing: `./scripts/check_evidence.sh`
