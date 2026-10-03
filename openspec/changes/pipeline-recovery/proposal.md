## Why

The nightly pipeline takes about 2 h 7 min (update 22, conform 44, report 14, predict 47; `logs/mlb_daily_update.log`) and `mlb doctor` on production `mlb` reports 27 failed checks out of 370 (2026-10-02). The work to fix both has split into several half-applied ideas: stable ids and incremental rebuild (`stable-ids-incremental-conform`), an unfinished `mlb nightly` supervisor (`job-retries-alerts`), freshness checks (`pipeline-freshness`), a shadow-schema swap idea, and a SQLMesh idea. The owner needs one plan, with a trustworthy starting state first and measurable done-when criteria.

A read-only panel (ce-pov, Codex gpt-6.1-sol and Grok grok-4.7, 2026-10-03) judged the three speed options independently and both chose option A. This change adopts that decision.

## What Changes

- **Phase 1, recovery (no behavior change to data):** establish what is truly broken versus a stale or wrongly written check. Observed 2026-10-02/03: four `meta.ingestion_run` rows (statcast, kalshi, polymarket, retrosheet_box) stuck `running` since 14:23 UTC with dead pids, from an interrupted manual test of the new `mlb nightly`; a workflow-lock failure (on 2026-10-03 no advisory lock was held, so it may already have cleared); migrations 0108/0109 not applied to production (they sit on branch `plan/stable-ids-and-job-retries`); `meta.metric` empty although 50 metric YAML files exist; no backup ever run; doctor checks that look for tables created only by an owner-triggered backfill (`raw.polymarket_price`, `raw.kalshi_candle`; `polymarket.py:108`, `conform.py:1337`) and report them as failures.
- **Phase 1, data-quality triage:** each remaining doctor failure (out-of-domain model values, `feat` health check raising `home_pa_30d` binder error, regular-season envelope violations, prediction-count fan-out) is classified as a real defect, a wrong check, or accepted, with evidence, before any fix.
- **Phase 2, speed, option A only:** make `conform` incremental with stable ids, as designed in `stable-ids-incremental-conform`, after fixing four gaps found in review: the `core.game` upsert versus delete-by-season contradiction (`design.md` D2 versus `tasks.md` 5.1), a change fingerprint that misses corrections, an equivalence test that checks only keys, and no timing yet for `update` and `predict`.
- **Fallback, not planned work:** a short-transaction swap (option B) is considered only if measured lock time, not total time, remains the problem after A.
- **Rejected:** SQLMesh for `conform` identity (ADR-088, ADR-266, ADR-271; `transforms/AGENTS.md`). SQLMesh stays an option for set-based gold after a tie-out.
- **Safety rules apply to every step:** backup first, explicit target database named in every command, `mlb` is production and `mlb_test` or run-specific temp databases are for tests, raw tables are never edited.

## Capabilities

### New Capabilities
- `pipeline-operations`: what a healthy nightly pipeline means: no stale runs or locks after a failure, health checks that test only what the system is meant to contain, a recorded backup, per-phase timing in every run, and incremental rebuilds that equal full rebuilds.

### Modified Capabilities

(none; `stable-ids-incremental-conform` introduces its own `incremental-conform` capability and is not duplicated here)

## Impact

- Code: `mlb_baseball/doctor.py` (check reporting) and the connector health checks (`connectors/polymarket.py`, kalshi), `mlb_baseball/nightly.py`, `mlb_baseball/conform.py`, `mlb_baseball/report.py`, `scripts/mlb_daily_update.sh`, and the conform and report changes owned by `stable-ids-incremental-conform`.
- Database (production `mlb`, always owner-approved, one command at a time): apply migration 0109, `mlb repair-runs`, `mlb catalog build`, first `mlb backup`, later the `stable-ids-incremental-conform` migrations.
- Docs: `openspec/project.md` NOW/NEXT, `docs/DECISIONS.md` (ADR for the single-approach decision), `openspec/HANDOFF.md`.
- Supersedes ad-hoc planning of speed work in the other open changes; they remain the owners of their own code tasks.
