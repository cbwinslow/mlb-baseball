# Design

## Context

The ingredients already exist: `mlb preflight` (no writes), `mlb migrate`, `mlb bootstrap --profile` (all registered sources, continues past a failed source, exits non-zero), `mlb coverage` (expected vs held, prints the fix command), `mlb repair` (a short list of safe fixes), `mlb conform`, `mlb audit`, `mlb doctor`. Known gaps as of 2026-10-11: the expensive backfills (Kalshi candles, Polymarket price history) are deliberately outside `bootstrap()`/`update()`; `raw.mlb_person` is loaded only for ids in `raw.mlb_roster`.

## Goals / Non-Goals

**Goals:** a new user reaches a complete, audited database with documented commands and no hidden steps; every failure names its step and fix; the path is proven on an empty database.

**Non-Goals:** speeding up ingestion, adding sources, adopting an orchestrator (Dagster/Prefect/Airflow were considered on 2026-10-11 and rejected for now: the run ledger, `coverage`, `repair` and `doctor` already cover the need).

## Decisions

1. **Rehearse before designing the command.** Run the path on an empty database first; the failures found decide what the chaining command must do. Alternative (design the command from the runbook alone) rejected: that is how the current gaps went unseen.
2. **Slice, not full history.** Two seasons plus the reference tables keep a rehearsal to hours; the full build is estimated from per-source timings in `meta.ingestion_run`, not run.
3. **Chain via the existing commands.** The new command calls the same functions the separate commands call and stops on the first failed hard step; backfills are included but each reports its own progress through the run ledger.
4. **Target database is explicit.** The rehearsal uses a named disposable database created for the run, never `mlb` and never a test database reused by pytest.

## Risks / Trade-offs

- [Network cost and politeness: a rehearsal hits every source] -> bounded slice; honour each connector's rate limits; record request counts.
- [Some sources need keys or are not redistributable] -> the profile (`local_research` vs `public_safe`) decides; the rehearsal runs the default profile and lists skipped sources with reasons.
- [Fresh-database failures may be fixed in code that production never exercises] -> every fix gets a test that starts from an empty schema.

## Open Questions

- Should the chaining command live at `mlb bootstrap --full` or as a new `mlb setup`? Decide after the rehearsal shows what it must cover.
