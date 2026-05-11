# 20 — Schemas

SQL scripts in this directory create the PostgreSQL schemas that namespace the baseball data.

## Planned Schemas

| Schema | Purpose |
|---|---|
| `raw` | Verbatim source data exactly as received |
| `staging` | Normalized/typed intermediary before core merge |
| `core` | Canonical, deduplicated production tables |
| `analytics` | Derived tables, aggregations, model outputs |
| `monitor` | Health and freshness tracking tables |

## Status

⚠️ **Pending** — tracked in [Phase 2 milestone](https://github.com/cbwinslow/mlb-baseball/milestones).
