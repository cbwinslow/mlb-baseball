# ClickHouse decision benchmark

Plan 02F decision, 2026-08-06. PostgreSQL remains the authoritative store.
No ClickHouse replica is adopted at this point.

## Method and scope

All PostgreSQL commands were read-only `EXPLAIN (ANALYZE, BUFFERS)` queries
against the original `mlb` database as user `cbwinslow`. No table, database,
replica, extension, or ClickHouse object was created. The local `clickhouse`
binary exists, but no ClickHouse server was reachable: its conventional native
ports were not listening, and `127.0.0.1:8123` returned an unrelated HTTP 404.
There is therefore no valid ClickHouse-side latency or replication comparison
to claim.

## Dataset state

| Relation | Rows at benchmark | Relevance |
|---|---:|---|
| `core.pitch` | 13,428,264 | Pitch-level analytical scan |
| `gold.prediction` | 28,838 | Current prediction/site aggregate |
| `gold.game_feature` | 0 | Experiment extract unavailable; this is a pipeline completeness issue, not a warehouse benchmark result |

## PostgreSQL results

| Workload | Query shape | Execution time | Notes |
|---|---|---:|---|
| Pitch scan | 2024–2026 pitch-type aggregate with average velocity | 484.725 ms | Parallel scans of the three season partitions; 2.07M qualifying pitches |
| Rolling feature primitive | Two team-game streams with prior cumulative run differential window | 36.124 ms | Uses `core.game` season index; 13,158 rows |
| Site/prediction aggregate | 30-day predictions by model and generated day | 25.294 ms | Small sequential scan of 28,838 rows |
| Experiment extract | `gold.game_feature` training slice | Not runnable | Relation currently has zero rows |

The benchmark was one local read-only session. It does not claim a production
concurrency percentile; it establishes the current baseline and demonstrates
no latency failure for the workloads that exist today.

## Decision

**Decision: do not deploy ClickHouse or create an analytical replica.**

At current scale, the observed PostgreSQL timings are well within useful
interactive/research bounds, and the key planned feature relation is empty.
Adding replication now would introduce freshness, backfill, schema-evolution,
access-control, monitoring, and correctness-reconciliation work before it
solves a measured problem. PostgreSQL plus SQLMesh remains the path until
feature completeness and measured load justify a second store.

## Revisit gate

Re-run this benchmark with recorded dataset sizes, cold/warm runs, and at
least representative concurrent readers if any stated SLO fails after normal
PostgreSQL indexing/SQLMesh optimization:

- pitch/research scans exceed a 2 s p95 target at the required product
  concurrency;
- rolling feature rebuilds cannot fit their scheduled refresh window;
- experiment extracts exceed their agreed training preparation budget; or
- narrow public-site reads exceed a 250 ms p95 target behind the intended
  read-only serving path.

Any future ClickHouse proposal must demonstrate a reproducible replica,
source-to-replica lag/correctness checks, retention/backfill behavior, access
controls, operational cost, and the measured benefit over this baseline. It
does not replace PostgreSQL's transactional raw/core/meta contracts.
