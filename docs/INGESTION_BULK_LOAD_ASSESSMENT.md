# Bulk-load assessment

This is the decision record for applying the MLB API analytics pattern
(durable artifact, bounded work item, scoped replacement, one COPY per batch,
and resume evidence) to other high-volume connectors. It is intentionally
evidence-led: a connector is not rewritten merely because it uses pandas.

## Measured production shape

The largest raw relations at the time of this assessment were:

| Source/table | Approximate size | Existing load unit | Decision |
| --- | ---: | --- | --- |
| `retrosheet_event` / `retrosheet_plays` | 8.6 / 10.2 GB | downloaded archive, parsed year/group scope, COPY | Keep; already uses the right durable-file and scoped-COPY pattern. |
| `statcast_pitch` | 8.0 GB | one week, scoped COPY, commit | Keep; this is already the desired bounded/retryable unit. |
| `kalshi_market` | 575 MB | whole API catalog, one DataFrame/COPY | Leave unchanged for ordinary update; the catalog response itself is the natural snapshot. |
| `mlb_win_prob` | 400+ MB and growing | 200-game artifact batch, scoped COPY | Implemented in this work. |
| `polymarket_market` | 165 MB | whole API catalog, one DataFrame/COPY | Leave unchanged for ordinary update; the response is already a complete source snapshot. |

All of these large tables showed zero estimated dead rows during the review.
That rules out table churn as the immediate reason to redesign them.

The live Stats API benchmark for a 48-game 1985 sample confirmed the same
separation: a single worker took 85.3 seconds after one slow upstream
response, while 4/8/12/16 workers took 1.17/0.405/0.380/0.370 seconds. A
second live 48-game test under sustained load measured 16/24/32 workers at
55.8/106.0/95.1 games per second. The test-database write comparison was
0.017 seconds for individual commits and 0.013 seconds for one COPY on that
small payload. The production backfill therefore uses the bounded maximum of
24 workers; its bottleneck is MLB API latency, not PostgreSQL row insertion.
The analytics path also recreates a worker session after a failed request and
caps an individual API retry delay at 15 seconds.  This does not remove
retries or 404 tracking; it prevents one unhealthy keep-alive connection or
overlong transient response from parking an entire parallel batch for the
generic five-minute retry ceiling.

## Priority order

1. **Complete and verify MLB Stats API first.** It had the demonstrated
   failure mode: hundreds of thousands of small upstream documents, serial
   calls, and ambiguous partial completion. It now has a dedicated artifact,
   item-ledger, replay, coverage, and bulk-COPY path.
2. **Kalshi and Polymarket historical price backfills, if they become active.**
   Their per-token/per-market history requests are independently retryable but
   currently load one scope at a time. If a measured run shows PostgreSQL time
   is material, introduce a bounded multi-scope `replace_dataframe_scopes`
   batch. Do not replace their ordinary full-catalog snapshot loads.
3. **Statcast only after a benchmark shows a database bottleneck.** Its
   weekly scope is already resumable and COPY-based; its limiting factor is
   Baseball Savant extraction and the deliberately polite pause, not row-wise
   PostgreSQL insertion.
4. **Retrosheet only after a representative parse/load benchmark.** Its files
   are already saved with checksums and parsed locally before scoped COPY.
   The likely limiting work is `cwevent`/`cwgame`, not writes; changing its
   chunk semantics would risk losing the proven year/group recovery boundary.

## Standard for any future conversion

Before changing a connector, measure separately:

1. upstream download/parse time;
2. CSV/DataFrame serialization time;
3. PostgreSQL delete/replace/COPY time;
4. rows, bytes, dead-row estimate, index/scan use, and cache-hit trend; and
5. an interrupted-run replay on `mlb_test`.

Only adopt a new batch size or staging table after the test database proves
idempotency and production-shaped timing. A whole-table delete/reload is
appropriate only for a source whose API response is itself a complete atomic
snapshot; it is not a substitute for item-level recovery on long backfills.
