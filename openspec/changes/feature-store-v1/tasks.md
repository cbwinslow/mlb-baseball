Scope: **slice 1 only** — the DuckDB build artifact, the ADR, the three `feat.*`
relations, `get_historical_features`, the two store-level leakage checks, and
`mlb verify`. Slices 2 (harness extraction) and 3 (Elo v2 + card + publish) are
separate OpenSpec changes; see `proposal.md` — Roadmap.

TDD applies to every task that adds behaviour: write the failing test, watch it
fail for the right reason, then make it pass. Tasks marked **[OWNER]** are the
owner's to run and are recorded, not gated in CI.

## 1. Decisions and contract (do first — everything else is judged against these)

- [ ] 1.1 **[OWNER]** Confirm the four open decisions in `DESIGN_REVIEW.md`
  (DuckDB path + resolver precedence; whether `mlb build` wraps or replaces
  `report`/`conform`/`features` and whether `mlb verify` subsumes `doctor`;
  the day-based window set; the `feat.game` curation rule). Verify: each of the
  four has a one-line recorded answer in `DESIGN_REVIEW.md`, and any answer that
  differs from the recommendation is reflected in `design.md` before task 2.1
  starts.
- [ ] 1.2 Fold `adr-features-in-duckdb.md` into `docs/DECISIONS.md` as the next
  ADR number (currently ADR-287; re-check the maximum at edit time — the file is
  newest-first). Verify: the ADR appears at the top of `docs/DECISIONS.md` in the
  file's existing `## ADR-NNN: <title>` / `**Decision:**` / `**Context:**` /
  `**Rationale:**` / `**Revisit if:**` shape, and no existing ADR number is
  reused.
- [ ] 1.3 Update `openspec/project.md`: the Postgres/DuckDB boundary in
  "Database engineering standards", and v1.1 progress in `NOW / NEXT / LATER`.
  Verify: the boundary sentence names `core` as the split point and cites the new
  ADR; `openspec validate --all` passes.
- [ ] 1.4 Confirm the `delivery` delta lands as written. Verify:
  `openspec validate --strict feature-store-v1` passes, and each MODIFIED
  requirement header matches `openspec/specs/delivery/spec.md` character for
  character (whitespace-insensitive) so archive does not create a duplicate.

## 2. The DuckDB build artifact

- [x] 2.1 Failing test first: `tests/unit/test_duckdb_path.py` asserts the
  resolver precedence from design D3 — explicit argument beats
  `MLB_DUCKDB_PATH` beats `~/.mlb/mlb.duckdb`, and the parent directory is
  created on first use. Verify: RED with no resolver, GREEN after it lands; the
  test uses `tmp_path` + `monkeypatch.setenv`, never the real `~/.mlb`.
- [x] 2.2 Move `duckdb` into `[project].dependencies` in the root
  `pyproject.toml`, and move `mlb-research` out of the `dev` extra into runtime
  dependencies (the `[tool.uv.sources]` workspace entry stays). Verify:
  `uv sync` resolves; `uv run python -c "import duckdb, mlb_research"` works;
  `uv run python -c "import mlb_research, mlb_baseball"` still shows
  `mlb_research` importing without `mlb_baseball` present in its module graph.
- [x] 2.3 **[OWNER]** Confirm `mlb-research` is resolvable from PyPI at the
  version the root package will require, or record that `mlb-baseball` installs
  from the repository only until it is. Verify: a written note in the PR naming
  the PyPI state; the risk in `design.md` is closed or restated.
- [ ] 2.4 Add `mlb build` to `mlb_baseball/cli.py`: `--db <path>` plus the
  existing `--profile` / `--skip` conventions, wrapping `migrate` → `conform` →
  `report` and then the feature build. Verify: `uv run mlb build --help` lists
  the flags; a unit test asserts the wrapped steps run in that order and that
  `mlb conform` / `mlb report` / `mlb features` still dispatch exactly as before
  (no renamed or removed subcommand).
- [ ] 2.5 Establish the DuckDB SQL home: decide between an inline
  `-- sqlfluff:dialect:duckdb` directive and a subdirectory with its own
  `.sqlfluff`; if the subdirectory wins, extend
  `mlb_baseball/sql/__init__.py::read_sql` to accept exactly one path segment
  while keeping its traversal guard (a failing unit test for `../` and absolute
  paths first). Verify: `uv run sqlfluff lint mlb_baseball/sql/` is clean with
  a DuckDB-syntax file present **and** the 97 existing PostgreSQL files still
  linted as `postgres`; `scripts/lint_sql_ownership.py` passes.

## 3. `feat.player_form` and `feat.pitcher_form`

- [ ] 3.1 Failing integration test `tests/integration/test_feat_form.py`: a
  fixture of two batters and two pitchers across four games asserts **one row per
  `(entity_id, event_ts, feature_version)`** (no `window` in any key), that every
  rate has its numerator and exposure columns populated alongside it, that a rate
  is `NULL` (not `0`) when its denominator is zero, that a rate is recomputed
  from summed components rather than averaged from per-game rates, and that
  `event_ts <= available_ts <= visible_ts`. Verify: RED before the builders,
  GREEN after.
- [ ] 3.2 `mlb_baseball/sql/feat_player_form.sql` (DuckDB dialect): rolling
  offensive counting stats, numerators, exposure and rates per window as
  **columns**, computed from completed games only and excluding the target game,
  shrunk toward an **as-of** league prior (a 2024 league rate can never prime a
  2023 row). Verify: sqlfluff clean; the 3.1 test's batter assertions pass.
- [ ] 3.3 `mlb_baseball/sql/feat_pitcher_form.sql`: rolling batters faced,
  K−BB%, RA9 and a FIP-like rate, same rules and column layout. Ship only the
  columns a game-grain consumer needs — this is not the start of a full pitcher
  grain. Verify: the 3.1 test's pitcher assertions pass; the shipped column list
  is enumerated in `docs/FEATURE_STORE.md`.
- [ ] 3.4 Compute and store `visible_ts = GREATEST(available_ts, created_ts)` in
  both builders, with the per-source `available_ts` lag read from one documented
  constant rather than duplicated per file. Verify: a unit test asserts
  `visible_ts` equals the maximum for rows on both sides of the tie, and that
  changing the lag constant moves `available_ts` in both relations.
- [ ] 3.5 Append-only semantics: a second `mlb build` with a bumped
  `feature_version` adds rows and leaves the prior version's rows byte-identical.
  Verify: an integration test that builds twice and asserts the v1 rows are
  unchanged and both versions are retrievable.

## 4. `feat.game`

- [ ] 4.1 Failing test: for a fixture game, `feat.game`'s home/away form columns
  equal what `get_historical_features` returns for the same entities at that
  game's first pitch. Verify: RED before the builder, GREEN after — this is the
  assertion that keeps the assembly and the retrieval path from drifting.
- [ ] 4.2 `mlb_baseball/sql/feat_game.sql`: one row per game at first pitch —
  game context plus home/away form columns retrieved as of first pitch, ~30–40
  columns per the curation rule confirmed in 1.1. Verify: 4.1 passes; the column
  count and the curation rule are both stated in `docs/FEATURE_STORE.md`.
- [ ] 4.3 Confirm no read of `gold.game_feature` entered the DuckDB build.
  Verify: `grep -rn "game_feature" mlb_baseball/sql/feat_*.sql` returns nothing,
  and the build runs against a database whose `gold.game_feature` is empty.

## 5. `get_historical_features`

- [ ] 5.1 Failing unit tests in `packages/mlb-research/tests/`: PIT-correct
  retrieval on a fixture (a request between two snapshots returns the earlier);
  a request before the first snapshot returns nulls, never a forward fill; one
  output row per input row, in input order; an unknown feature ref raises before
  any query runs, naming the valid refs. Verify: RED, then GREEN.
- [ ] 5.2 Implement `mlb_research.get_historical_features(entity_df, features,
  timestamp_col=..., db=None)` as one parameterized `ASOF LEFT JOIN` per
  relation on `t >= visible_ts`, with `db=None` resolving through the same
  precedence as task 2.1. Verify: 5.1 passes; the function body is one page or
  less; no `merge_asof`, no per-row Python loop over entities.
- [ ] 5.3 A row whose `created_ts` is after `t` is never returned, even when its
  `available_ts` is before `t`. Verify: a unit test builds two rows for one
  entity differing only in `created_ts` and asserts the later-created one is
  invisible at a `t` between them — this is the test that fails if `visible_ts`
  is replaced by `available_ts`.
- [ ] 5.4 Document the contract in `packages/mlb-research/README.md` and
  `docs/PUBLIC_API.md`: the signature, the `"view:feature"` ref format, the
  four clocks, and the explicit statement that this is Feast's shape without
  Feast. Verify: the example in each doc is copy-pasteable and matches the
  implemented signature.

## 6. Leakage checks and `mlb verify`

- [ ] 6.1 Failing unit tests for `mlb_research.leakage_checks`: the visibility
  check fails on a fixture whose builder backdates `created_ts`, and passes on a
  clean one; the doubleheader check fails on a fixture whose builder joins on
  game *date* instead of first-pitch timestamp, and passes on a clean one.
  Verify: RED on the leaky fixture and GREEN on the clean one for each — a check
  that cannot be made to fail is not a check.
- [ ] 6.2 Implement the two checks as callable functions returning pass/fail plus
  the evidence rows, with **no model, no labels, and no sklearn import**.
  Verify: 6.1 passes; `uv run python -c "import mlb_research.leakage_checks"`
  succeeds in an environment without sklearn or xgboost installed.
- [ ] 6.3 Add `mlb verify` to `mlb_baseball/cli.py`: run the two leakage checks
  against the resolved build, run the existing Baseball-Reference tie-out
  (`scripts/verify_baseball_reference_tie_out.py`), and report the build's
  `created_ts` range so a stale file is visible. Non-zero exit on any failure.
  Verify: `uv run mlb verify --help` works; an integration test asserts exit 0 on
  a clean fixture build and non-zero with a named failure on a leaky one;
  `mlb doctor` / `mlb audit` / `mlb preflight` are unchanged.
- [ ] 6.4 Run the two checks in CI against a fixture build. Verify: green in CI;
  red when the feature builder is deliberately made to include the target game.

## 7. Documentation

- [ ] 7.1 `docs/FEATURE_STORE.md` (new): the boundary at `core`, the four clocks
  and the derived `visible_ts`, the three relations and their columns, the
  windows-are-columns rule and why exposure ships with every rate, the retrieval
  contract, the two leakage checks and what they do *not* cover, the per-source
  `available_ts` lag assumptions, the no-Feast decision and its adoption trigger,
  and a plain statement that `gold.game_feature` is internal and never part of
  this surface. Verify: `mkdocs build --strict` and the link check pass.
- [ ] 7.2 Update `docs/DATA_DICTIONARY.md` (the `feat` relations and their
  grain), `docs/RESEARCH.md` (the `available_ts` lag as an honest limitation),
  and `docs/SQL_OWNERSHIP.md` (the DuckDB build SQL and its Python owner).
  Verify: `mkdocs build --strict` clean; `docs/SQL_OWNERSHIP.md` names a
  `read_sql(...)` caller for every new `.sql` file.
- [ ] 7.3 Update `README.md`'s status section and `docs/USER_MANUAL.md` with the
  three-command front door (`mlb bootstrap` → `mlb build` → `mlb verify`),
  stating that the other commands are unchanged. Verify: each documented command
  and flag exists in `uv run mlb --help` output — no invented flag names.

## 8. Verification

- [ ] 8.1 `openspec validate --strict feature-store-v1`; full `pre-commit`;
  `ruff format` + `ruff check` + `mypy mlb_baseball` + `sqlfluff lint` on every
  touched file. Verify: each command's exit code recorded in the PR.
- [ ] 8.2 Targeted suites green: `tests/unit/test_duckdb_path.py`,
  `tests/integration/test_feat_form.py`, `tests/integration/test_feat_game.py`,
  `tests/integration/test_verify.py`, `packages/mlb-research/tests/`, plus
  `tests/integration/test_export*.py` and the CLI dispatch tests as a
  no-regression check on the untouched commands.
- [ ] 8.3 Execution, not just tests: `mlb build --db <tmp>` against a disposable
  seeded database produces the file, `mlb verify --db <tmp>` exits 0, and a
  `get_historical_features` call against that file returns PIT-correct rows.
  Verify: the commands and their output recorded in the PR (per
  `verification.md` — a passing test suite is not an execution).
- [ ] 8.4 Scope audit before calling it done: the diff touches no migration, no
  `gold.game_feature` builder, no `model/experiment.py`, no `model/elo.py`, and
  no `conform.py`. Verify: `git diff --stat` reviewed against that list, and any
  `SHORTCUT:` markers added in this change are listed with their ceiling and
  trigger.
- [ ] 8.5 **[OWNER]** A full `mlb build` against production `mlb`, then
  `mlb verify` against the resulting file. Verify: recorded row counts per `feat`
  relation, the `created_ts` range, and both leakage checks passing on real data
  — the first time any of this runs at production scale.

---
### Progress notes (autonomous build, 2026-09-09)
- **2.1** done: mlb_research/paths.py + 6 tests (in packages/mlb-research/tests/, not tests/unit/ — the resolver is mlb_research code).
- **2.2** done: duckdb + mlb-research moved to [project].dependencies; mlb-research removed from dev extra; uv.lock updated; verified mlb_research imports without mlb_baseball.
- **2.3** [OWNER] resolved by check: mlb-research returns 404 on PyPI. mlb-baseball installs from the repo (workspace source) until both publish; recorded here, risk in design.md stands.
- **Clock model for a Retrosheet-keyed layer (no real first-pitch times in core.game):** event_ts = game_date::timestamp + game_number * interval '3 hours' (preserves doubleheader order: single game_number 0 -> midnight, DH 1 -> 3am, DH 2 -> 6am); available_ts = event_ts + interval '6 hours' (box score available after the game; a documented per-source lag). This makes DH game 1 invisible to DH game 2 and prior-day games visible. Documented in docs/FEATURE_STORE.md + docs/RESEARCH.md as the honest limitation.
- Build mechanism: DuckDB ATTACHes the Postgres DB read-only (postgres extension), each feat relation is a DuckDB CREATE-and-load from pg.gold.*; window frame ROWS UNBOUNDED PRECEDING..1 PRECEDING for entering values.
