# Research Database v1 — plan

Executes `docs/superpowers/specs/2026-09-01-research-database-v1-design.md`.
Four workstreams. WS1 and WS4 start now; WS2 in parallel; WS3 after WS1's
command surface lands.

---

## WS1 — export & interop layer  → delegated to Agy

**Branch:** `feat/mlb-export-interop`

### Goal

`mlb export` becomes the research-data exporter. It writes any allow-listed
`raw` / `core` / `gold` relation to CSV, Excel, or Parquet, and can emit a
rights-filtered `public_safe` bundle for redistribution.

### Context Agy needs

- Read `docs/superpowers/specs/2026-09-01-research-database-v1-design.md` in
  full (sections A, "Data flow", "Error handling", "Testing").
- Read `CLAUDE.md` and `AGENTS.md` — the golden rules on database names,
  "Definition of done", "Testing", and "Naming convention" all bind this work.
- Current state: `mlb export` (cli.py:637, handler cli.py:3852) renders the
  daily *betting briefing* via `mlb_baseball/export.py`. `mlb dump` (cli.py:804,
  handler cli.py:4524) prints a hardcoded Shohei Ohtani record via
  `mlb_baseball/dump.py`. Neither is called from `scripts/` or cron — only from
  `tests/unit/test_export.py`, `tests/unit/test_dump.py`, and one line in
  `tests/unit/test_cli_dispatch.py`. `mlb daily` (cli.py:2970) already covers
  the daily-briefing use case, so the old `mlb export` behaviour is redundant
  and is removed, not preserved.
- `gold.game_export` (migration 0058) and `gold.player_season` /
  `gold.team_season` / `gold.division_standing` (migration 0030) are the
  primary wide relations to export. `tests/integration/test_game_export_view.py`
  exercises the view and stays.
- `mlb_baseball/source_profiles.py` — `PUBLIC_SAFE` is a frozenset of 8
  Retrosheet connector names. The relation→profile map for the bundle is new
  code; derive it from `docs/SOURCE_RIGHTS.md` + `docs/DATA_SOURCES.md` and
  keep it conservative (exclude anything touched by Statcast / MLB API /
  market data).

### Deliverables

1. `mlb export <relation> [--season N] [--format csv|xlsx|parquet] [--out PATH]`
   - `<relation>` validated against a fixed allow-list (`raw.*` / `core.*` /
     `gold.*` — tables and views the project intends researchers to read). No
     arbitrary SQL.
   - Read-only, `REPEATABLE READ` transaction; server-side cursor; stream to
     the writer.
   - `--season` applies only where the relation has an obvious season/date
     column; documented per relation.
   - Default `--out`: `<schema>.<relation>.<ext>` in the cwd.
2. `mlb export --profile public_safe --out DIR [--zip]`
   - Exports every rights-cleared relation to `DIR/<schema>.<relation>.parquet`.
   - Writes `DIR/MANIFEST.json`: per relation — name, row count, source-rights
     note, `generated_at`.
   - A relation in the map that is absent from the DB → skip with a logged
     warning, do not abort.
3. Delete `mlb_baseball/dump.py`, the `dump` subparser, and its handler.
   Entity-scoped export (one player/team/game) is a `--season`-style filter on
   `mlb export`, not a command. Update/remove `tests/unit/test_dump.py`.
4. Replace `mlb_baseball/export.py`'s briefing-renderer contents with the new
   exporter, or delete it and add a focused `mlb_baseball/export.py` — keep the
   module name. Rewrite `tests/unit/test_export.py` accordingly.
5. `mlb_baseball/export.py` exposes `health_check() -> list[Check]`
   (see `mlb_baseball/health.py`) — e.g. the allow-list relations resolve, the
   optional deps import. Wire it into `mlb doctor` (`mlb_baseball/doctor.py`).
6. `pyproject.toml`: new optional-dependency group `export = ["openpyxl>=3.1",
   "pyarrow>=16"]`. Import them lazily; a missing dep → a clear "install the
   export extra" message, not a raw ImportError.
7. Excel: refuse `.xlsx` when the relation exceeds 1,048,576 rows, with a
   message pointing at `.parquet` / `.csv`. Never silently truncate.
8. Docs in the same change: `docs/RESEARCH_QUERY_RUNBOOK.md` gets the new
   commands; `docs/DATA_DICTIONARY.md` / `docs/PUBLIC_API.md` updated if the
   surface they describe changed. (The full `USER_MANUAL.md` rewrite is WS3 —
   just don't leave those two stale.)

### Tests (Definition of done — all must pass)

- `tests/integration/` against `mlb_test`: seed fixture rows into a `gold`
  view, export each of the 3 formats, read the file back (pandas / pyarrow /
  openpyxl), assert row + column parity. Run twice → identical output.
- `public_safe` bundle: seed one public-safe relation and one restricted one;
  assert the restricted relation is absent from both the bundle and the
  manifest.
- `tests/unit/`: allow-list validation, rights-map lookup, Excel row-limit
  guard, missing-dependency message.
- `tests/unit/test_cli_dispatch.py`: every new flag parsed through
  `cli.main([...])` and real argparse.
- `uv run ruff check`, `uv run ruff format --check`, `uv run mypy mlb_baseball`
  clean.

### Rules for the delegated run

- Work only against an isolated test database. Command:
  `TEST_DATABASE_URL=postgresql://mlb:password@localhost:5432/mlb_test uv run pytest`
  (pytest clones a fresh DB per run). **Never touch the production `mlb`
  database.** No `DROP` / `TRUNCATE` / migration against it.
- Preserve all unrelated changes. Stay within the files this brief names plus
  their tests and docs.
- Follow the repo naming convention: one- or two-word names for anything new.
- Do **not** add other CLI subcommands or helper scripts. `mlb export` is the
  only new command.
- Return: changed files, exact commands run and their output, limitations /
  anything skipped, and the next gate. Do **not** commit, push, merge, open a
  PR, or start any other workstream.

### Review (Claude, before this counts as done)

Re-run the full test suite and linters locally, read the entire diff, verify
the `public_safe` map against `docs/SOURCE_RIGHTS.md` by hand, confirm the
frozen surface is untouched. Then open the PR.

---

## WS2 — fresh-DB init fix (issue #76)

**Branch:** `fix/issue-76-fresh-db-init`. Claude or a Claude subagent.
Stale serving-view migrations prevent a clean `mlb_test` bootstrap. Reproduce
on a fresh DB, fix the migration(s) so `migrate` runs clean start-to-finish,
add a test that a fresh database reaches the latest migration. No new commands.

## WS3 — docs for a stranger

**Branch:** `docs/outside-user-guide`. After WS1 merges.
Rewrite `docs/USER_MANUAL.md` so every command shown runs as written against a
clean bootstrap. Reframe `README.md`: research database is the product; model
ladder and website are separate, frozen. Fold in the new `mlb export` recipes.

## WS4 — board triage  (Claude, now)

Label every open issue `research-db` / `modeling` / `website`. Close or defer
(with a one-line reason) everything not `research-db`. Land or close PRs
#116–#119 after checking each diff + re-running tests.

---

## Frozen for the duration

`model/` prediction layer, `serve/` + serve-api + Astro, the ~150 unwired demo
commands. Not touched by any workstream above.
