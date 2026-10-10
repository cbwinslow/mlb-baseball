# Session handoff — 2026-10-10 (streamline-core-gold-direction)

Resume from `tasks.md`; this file only records where the last session stopped.

## Where the plan stands
- This change (30 tasks, none ticked) is the direction work: what `core`/`gold` should hold,
  conform rewrite, SQLMesh/DuckDB question. It exists only on branch
  `wip/uncommitted-2026-10-08` (not on main).
- New this session: `conform-design.md` (per-function destinations for `conform.py`; task 5.1,
  draft) and `metrics-trace.md` (metric-to-source trace; task 0.5, first pass).
- Agreed order: audit conform (done, draft) -> confirm per-function destinations ->
  time one gold query on Postgres vs DuckDB (3.1) and run the SQLMesh spike (3.2) ->
  rewrite conform one table at a time (named SQL, run-twice test, parity vs old writer).

## Key findings
- `conform` reads 30 of 150 raw tables; `core.play`/`core.pitch` hold 19 columns each vs
  168/122 raw. 29 of 45 documented metrics read `raw` directly for that reason.
- The five game-id/team-id backfills are one ordered chain; keep the order in Python.
- `_build_market` ignores `raw.polymarket_price` (604M rows) and `raw.kalshi_candle` (213M);
  pre-game prices come only from the recent snapshots. Needs its own change plus PIT tests.
- Owner policy (ADR-304, PR #391): internal use of all sources allowed; rights checked at
  publish time. Statcast fields added to `core` must stay out of the public export.

## Open PRs (merge when `test`/`secrets`/`lint` pass; AGENTS.md pre-authorizes)
- #389 task-list ticks (docs). #391 ADR-304 (docs). #390 mypy fix: merged.
- Network at the owner's home was dropping (eero red light); `gh`/`git push` may be slow.

## Production state
- The 2026-10-09 06:00 nightly died when the network dropped. Re-ran kalshi, statcast and
  retrosheet_event by hand (success), then `conform` (52 min, success). `report` then
  `predict` were started in sequence from a background shell; confirm both finished with
  `select source,status,finished_at from meta.ingestion_run where source in
  ('report','predict') order by started_at desc limit 4`, and re-run `mlb report` /
  `mlb predict` if not.
- Check the 06:00 nightly of 2026-10-10 for the same network problem; `mlb repair-runs`
  closes dead runs.
- Do not run `count(*)` on `raw.polymarket_price` (604M rows): use `pg_class.reltuples`.

## Still open from the task-list validation
- Genuinely open: `source-inventory` 3.4/6.2/6.3, `job-retries-alerts` 4.2,
  `model-readiness-audit` 4.3 (null-policy follow-up change not created),
  `retrosheet-state-engine` 4.3-4.6, `metric-catalog` 7.4 (owner reads catalog page),
  `operating-contract-v2` 3.2 (deferred), `odds-history-capture` 4.2/4.3/5.2/5.3/6.1.
- Not yet reviewed: `full-source-ingestion`, `pipeline-recovery`, `play-engine`,
  `stable-ids-incremental-conform`, `odds-bulk-history`, `negro-league-scope`.
