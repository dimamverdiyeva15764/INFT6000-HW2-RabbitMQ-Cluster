| Scenario | Run | Confirmed | Received (unique) | **Lost** | Duplicates | Redelivered | Out-of-order (per consumer) | Producer republished | Producer reconnects | Consumer reconnects | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| follower-crash | 1 | 11063 | 11063 | **0** | 0 | 0 | 0 | 0 | 0 | 0 | PASS |
| follower-crash | 2 | 10286 | 10286 | **0** | 0 | 1 | 0 | 0 | 0 | 1 | PASS |
| follower-crash | 3 | 10819 | 10819 | **0** | 0 | 0 | 0 | 1 | 1 | 0 | PASS |
| leader-crash | 1 | 10792 | 10792 | **0** | 0 | 0 | 0 | 0 | 0 | 0 | PASS |
| leader-crash | 2 | 10298 | 10298 | **0** | 0 | 1 | 0 | 0 | 0 | 1 | PASS |
| leader-crash | 3 | 10813 | 10813 | **0** | 0 | 1 | 0 | 1 | 1 | 2 | PASS |
| partition | 1 | 3604 | 3604 | **0** | 0 | 100 | 0 | 1 | 1 | 1 | PASS |
| partition | 2 | 9829 | 9829 | **0** | 1 | 100 | 0 | 2 | 2 | 1 | PASS |
| partition | 3 | 9733 | 9733 | **0** | 0 | 100 | 0 | 2 | 2 | 1 | PASS |
| rolling-restart | 1 | 17374 | 17374 | **0** | 1 | 1 | 0 | 10 | 10 | 5 | PASS |
| rolling-restart | 2 | 17213 | 17213 | **0** | 0 | 0 | 0 | 6 | 6 | 6 | PASS |
| rolling-restart | 3 | 17072 | 17072 | **0** | 0 | 0 | 0 | 7 | 7 | 9 | PASS |

**Total:** 12 runs, 138896 confirmed messages, **0 lost**, overall PASS.
