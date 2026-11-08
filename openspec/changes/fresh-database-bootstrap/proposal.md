# Proposal

## Why

The project's second promise is that anyone can download it and rebuild the same database (`AGENTS.md`, "two halves"). The commands exist (`preflight`, `migrate`, `bootstrap`, `doctor`, `coverage`, `conform`, `audit`; `docs/BOOTSTRAP_RUNBOOK.md`), but no one has run the whole path against an empty database, and the owner has found gaps by hand each time (2026-10-11: the Kalshi and Polymarket price backfills are not part of `bootstrap`, so a new user would end with those tables short; `raw.mlb_person` misses current-roster players). The one-time rehearsal in `docs/CONFORMANCE_REHEARSAL.md` copies a sample from production, so it cannot catch a bootstrap step that only works on top of existing data.

## What Changes

- Run the documented path on a brand-new database with a bounded slice (two seasons, one recent and one old) and record every step that fails, is missing, or needs a hidden manual command.
- Fix each failure at its originating layer (connector, migration, conform, coverage registry), with tests.
- Add one command that chains the whole sequence for a new user (`preflight` -> `migrate` -> `bootstrap` -> the catch-up backfills -> `coverage` -> `conform` -> `audit`) and stops with a clear message when a step fails; it must be resumable and safe to re-run.
- Add an automated check that proves the sequence on a small fixture slice so the path cannot silently break again.
- Update `docs/BOOTSTRAP_RUNBOOK.md` to match, including time and disk estimates for a full build.

## Capabilities

### New Capabilities
- `fresh-bootstrap`: what a new user's single bootstrap run must produce on an empty database, how it reports progress and failures, and how it proves the result.

### Modified Capabilities

None.

## Impact

- Code: `mlb_baseball/cli.py` (new chaining command), connectors or the coverage registry where the rehearsal exposes gaps, migrations only if a fresh database cannot be built from the numbered files (the extension-session bug fixed in `migrate.run` on 2026-10-10 was found this way).
- Docs: `docs/BOOTSTRAP_RUNBOOK.md`, `changelog/`.
- Out of scope: new sources, paid services, changes to what any source stores, performance work.
