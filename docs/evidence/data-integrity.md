| Scenario | Run | Confirmed | Received (unique) | **Lost** | Duplicates | Redelivered | Out-of-order (per consumer) | Producer republished | Producer reconnects | Consumer reconnects | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| follower-crash | 1 | 22160 | 22160 | **0** | 0 | 4 | 0 | 1 | 1 | 1 | PASS |
| follower-crash | 2 | 22426 | 22426 | **0** | 1 | 3 | 0 | 1 | 1 | 1 | PASS |
| follower-crash | 3 | 22029 | 22029 | **0** | 1 | 1 | 0 | 2 | 2 | 1 | PASS |
| follower-crash | 4 | 21971 | 21971 | **0** | 3 | 3 | 0 | 4 | 4 | 4 | PASS |
| follower-crash | 5 | 22061 | 22061 | **0** | 1 | 1 | 0 | 4 | 4 | 4 | PASS |
| follower-crash | 6 | 21891 | 21891 | **0** | 3 | 4 | 0 | 4 | 4 | 4 | PASS |
| leader-crash | 1 | 21257 | 21257 | **0** | 1 | 3 | 0 | 0 | 0 | 2 | PASS |
| leader-crash | 2 | 21579 | 21579 | **0** | 0 | 1 | 0 | 1 | 1 | 1 | PASS |
| leader-crash | 3 | 21735 | 21735 | **0** | 0 | 1 | 0 | 0 | 0 | 1 | PASS |
| leader-crash | 4 | 20842 | 20842 | **0** | 1 | 1 | 0 | 4 | 4 | 4 | PASS |
| leader-crash | 5 | 21810 | 21810 | **0** | 2 | 2 | 0 | 4 | 4 | 4 | PASS |
| leader-crash | 6 | 21483 | 21483 | **0** | 2 | 2 | 0 | 4 | 4 | 4 | PASS |
| partition | 1 | 7398 | 7398 | **0** | 0 | 275 | 0 | 1 | 1 | 3 | PASS |
| partition | 2 | 15666 | 15666 | **0** | 0 | 100 | 0 | 3 | 3 | 1 | PASS |
| partition | 3 | 18174 | 18174 | **0** | 0 | 100 | 0 | 2 | 2 | 1 | PASS |
| partition | 4 | 12429 | 12429 | **0** | 2 | 400 | 0 | 4 | 4 | 4 | PASS |
| partition | 5 | 12820 | 12820 | **0** | 3 | 400 | 0 | 4 | 4 | 4 | PASS |
| partition | 6 | 12537 | 12537 | **0** | 3 | 400 | 0 | 4 | 4 | 4 | PASS |
| quorum-loss | 1 | 9135 | 9135 | **0** | 0 | 0 | 0 | 5 | 5 | 5 | PASS |
| quorum-loss | 2 | 8801 | 8801 | **0** | 1 | 3 | 0 | 4 | 4 | 6 | PASS |
| quorum-loss | 3 | 8131 | 8131 | **0** | 3 | 3 | 0 | 5 | 5 | 7 | PASS |
| rolling-restart | 1 | 31983 | 31983 | **0** | 4 | 4 | 0 | 6 | 6 | 6 | PASS |
| rolling-restart | 2 | 34081 | 34081 | **0** | 4 | 3 | 0 | 6 | 6 | 5 | PASS |
| rolling-restart | 3 | 34888 | 34888 | **0** | 11 | 6 | 0 | 11 | 11 | 6 | PASS |

**Total:** 24 runs, 467287 confirmed messages, **0 lost**, overall PASS.
