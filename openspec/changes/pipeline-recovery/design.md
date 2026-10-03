## Context

See `proposal.md` for motivation. Measured facts (production `mlb`, 2026-10-02/03; verify before relying):

- Nightly 2 h 7 min: update 1347 s, conform 2624 s, report 841 s, predict 2838 s (`logs/mlb_daily_update.log`). Only conform and report are rebuilt in place; `conform.py:1840` truncates 23 tables in one transaction that commits after the rebuild, so readers of those tables wait on an ACCESS EXCLUSIVE lock.
- Even if conform and report cost nothing, update plus predict is about 70 minutes. The speed target therefore cannot be met by option A alone; `predict` and `update` need their own timing (tasks 2.x) before any claim.
- The 14:23 UTC `mlb nightly` run was a manual test of the unmerged supervisor (`nightly.py`), not the 06:00 cron job. The 06:00 job and all bootstrap runs that day succeeded.
- Database sizes: raw 51 GB (not rebuilt), core 6.4 GB, gold 4 GB. Free disk was 94 GB on 2026-10-02 and 251 GB on 2026-10-03 (cause unknown); it is re-measured in task 1.1 and 2.1 and never assumed. `mlb backup` writes one plain-SQL dump (`backup.py`) and restore is single-threaded, so even 251 GB does not make a whole-database restore test free. There is no point-in-time recovery or WAL archiving; this plan treats the dump as the only backup and records that limit.
- The workflow lock is a PostgreSQL advisory lock (`doctor.py`); PostgreSQL frees it when the holding session ends. `mlb repair-runs` only flips dead-pid `running` rows to failed (`ingest.py:264-301`). On 2026-10-03 no advisory lock was held, so the lock failure may already have cleared; task 1.4 re-checks.
- The polymarket/kalshi table checks live in the connectors (`connectors/polymarket.py`, `health_check()`), not `doctor.py`.
- `raw.polymarket_price` and `raw.kalshi_candle` come from an owner-triggered backfill never run (`polymarket.py:108`, `conform.py:1337`); `raw.*_snapshot` tables exist and are current.
- Option review (ce-pov panel, Codex and Grok, independent, read-only) and the author's frozen view all chose A. Peers also found the four gaps below.

## Goals / Non-Goals

**Goals:**
- A trustworthy starting state: every doctor failure classified, stale state cleared, backup taken.
- One speed approach (A), correct before it is fast.
- Provisional targets, stated as hypotheses to be replaced by measurement: normal night conform plus report under 10 minutes; whole nightly under about 80 minutes; no lock held on a read-served table for more than a few seconds.

**Non-Goals:**
- Changing statistic definitions, Elo or model logic.
- SQLMesh for `conform` identity; shadow-schema swap as a default path.
- Optimising `update` or `predict` beyond measuring them (separate change if the measurements justify it).
- Editing raw tables.

## Decisions

**D1: Option A is the single approach.** Stable ids fix the cause (ids re-issued nightly force gold to be emptied and refilled). B still rebuilds everything, and a rename does not move foreign keys (they reference table OIDs), so it needs dependency-aware cutover. C is ruled out by ADR-088/266/271 and `transforms/AGENTS.md`: identity reconciliation stays in Python. Alternatives kept as footnotes, not tasks.

**D2: Recovery before speed.** Speed work on a database with unclassified failures risks building on defects. Phase 1 ends with a written classification (`results.md`) and a verified backup.

**D3: Doctor checks are corrected, not silenced.** An optional-backfill check becomes informational. Each fix to a check has a test showing it fails on a real defect and passes on a healthy database.

**D4: Close the four spec gaps in `stable-ids-incremental-conform` first** (edit that change, not duplicate it):
1. `core.game` is upserted on natural keys and never deleted and reinserted by season (`design.md` D2 versus `tasks.md` 5.1 disagree today); a season rebuild updates and inserts, and removals are counted and reviewed.
2. The fingerprint includes a content checksum per season of the inputs, plus a transformation-code version and reference-data version, so a corrected value with the same row count and an unchanged key set is detected.
3. The equivalence test compares all non-key columns, not natural-key checksums (`tasks.md` 5.3).
4. `update` and `predict` are timed per step and recorded; `predict` is checked for rebuilding unchanged seasons.

**D5: Publish quickly, with lock rules.** Build into staging tables first (never hold the TRUNCATE lock while building), validate, then publish in a short transaction with `SET LOCAL lock_timeout` so maintenance fails fast instead of queueing behind readers. `DETACH PARTITION ... CONCURRENTLY` runs outside a transaction block with retry; `ATTACH` uses a validated CHECK matching the bounds so it does not scan. `ANALYZE` follows each bulk load.

**D7: Backup is a gate, not a note.** The first backup is sized against free disk, restored into an explicitly named disposable database (a script refuses `mlb`), and verified on all schemas, indexes and constraints. No production write follows until that pass is recorded; a fresh backup precedes each migration and the switch to incremental mode.

**D8: Doctor checks can say ERROR.** A check that raises is reported as ERROR, never as pass, and an optional-backfill check is informational only when its table is absent.

**D6: Pending downstream work survives failure.** If conform changes season S and report or predict fails, the dirty-season list persists in `meta` and the next run completes it.

**D9: Root cause first, at the owning layer.** Each failure is traced to the layer that creates the wrong value (raw, core, gold, model, or the check) before any change. The results table records the source cause and the file that owns it. Evidence at the start of this change: 1 of 50 catalog metrics is `validated`, 33 are `published` (formula from the literature, not tied out) and 16 are `implemented-untested`. Several doctor failures (catcher framing, first-pitch strike%, away wOBA) come from features that were built and shipped without that validation. The common cause is a missing gate between "implemented" and "feeds model inputs", not a bad architecture. Raw ingestion, identity and the nightly flow ties out and is kept.

**D10: Gate unvalidated features.** A metric marked `implemented-untested` is withheld from model inputs until validated. The mechanism (a catalog-driven exclusion list read by `mlb doctor` and the feature build, versus a column-level NULL) is decided in task 9.7 as an ADR before it is built. Alternative considered: leave features in place and only document them; rejected, because that is how the catcher-framing defect reached the gold table unnoticed.

**D11: Check bounds belong to the metric.** A health-check bound is a property of the metric's definition and is recorded with its citation in the metric's catalog entry; a bound is widened only on cited evidence (D9), never to clear a failure.

## Risks / Trade-offs

- [Incremental logic drifts from the full path] → equivalence test in CI on a fixture plus a one-off production comparison (read-only).
- [Naive upsert splits or merges players: `retro_id` unique only when present, `mlbam_id` not unique, `game_pk` unique only when populated] → strongest key first, never auto-merge, log conflicts, tests for doubleheader and reused-id cases.
- [Stale downstream results after a historical correction (Elo and running totals depend on earlier seasons)] → conform reports the earliest rebuilt season; recompute-forward is recorded as pending work, not silently skipped.
- [Targets are guesses] → they are labelled provisional and replaced by measured values in `results.md` before any acceptance.
- [Dirty-season list lost or `meta` restored from backup] → periodic full-rebuild guard and a doctor check on fingerprints.
- [Production writes] → every production command is named, targets `mlb` explicitly, follows a backup, and is run or approved by the owner. The assistant's tooling may block writes to production; commands are then given for the owner to run with `!`.

## Migration Plan

1. Phase 1 (read-only first): classify failures, then clear stale runs/lock, apply 0109, `mlb catalog build`, first backup and restore test.
2. Fix `doctor` checks; re-run `mlb doctor`; record results.
3. Measure phases (including `update` and `predict`).
4. Fix the four spec gaps in `stable-ids-incremental-conform`; then implement that change under its own tasks.
5. Switch the nightly script to incremental mode only after the equivalence test and a production comparison pass.
Rollback: `mlb conform --full` on the previous commit; restore from the verified backup if a migration misbehaves; nothing in raw is changed at any step.

## Open Questions

- Whether `report` career-grain tables are cheap enough to leave as full rebuilds (answered by timing).
- Whether lock time alone, after A, justifies the shadow-swap fallback (answered by measured lock waits).
