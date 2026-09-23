## 1. Schema

- [ ] 1.1 Add migration `migrations/0107_team_franchise.sql`: `core.team_franchise`
      (`id bigserial PRIMARY KEY`, `franchise_id text NOT NULL UNIQUE`,
      `franchise_name text`, `current_retro_team_id text`) and
      `core.team.franchise_id bigint REFERENCES core.team_franchise (id)`
      (nullable), with a supporting index on `core.team (franchise_id)`.
      Verify: migration applies cleanly against the disposable test
      database and `core.team_franchise`/`core.team.franchise_id` exist
      with the expected types.

## 2. Franchise resolution (`conform.py`)

- [ ] 2.1 Add a new SQL resource (e.g. `conform_team_franchise_insert.sql`)
      that builds one `core.team_franchise` row per distinct `franchid`
      present in `raw.lahman_teams_franchises`, joined through
      `raw.lahman_teams.franchid`/`teamidretro` to `core.team.retro_team_id`
      to compute `current_retro_team_id` as the `retro_team_id` of the
      resolved `core.team` row with the greatest `first_year` for that
      `franchid` (per design.md's Decisions — NOT `last_year = 9999`).
      Verify: a deterministic hand fixture with two synthetic team-eras for
      one franchise (older era `last_year = 9999`, newer era with a later
      `first_year`) asserts the newer era's code wins.
- [ ] 2.2 Add `_build_team_franchises(conn)` in `conform.py` (same shape as
      `_build_team_aliases`: catches `UndefinedTable` for the optional
      `raw.lahman_teams_franchises`/`raw.lahman_teams` prerequisites,
      returns the row count), and a backfill `UPDATE core.team SET
      franchise_id = ...` joining through the same crosswalk. Wire both
      into `run()` after `_build_teams()` and before `_build_team_aliases()`.
      Verify: `mlb conform` run against the test database populates
      `core.team_franchise` and `core.team.franchise_id` with non-zero
      counts; re-running produces identical counts (idempotent, matching
      this file's existing pattern).
- [ ] 2.3 Fix `_build_team_aliases`'s row-selection predicate: replace
      `WHERE retro_team_id = %s AND last_year = 9999` with a join through
      the new franchise resolution so an alias attaches to the franchise's
      *current* era's `team_id`, not whichever era `last_year` happens to
      mark active. Verify: a regression test seeding the same
      OAK(1968-9999)/ATH(2025-2025) shape as `test_conform.py`'s existing
      ATH fixture asserts the seeded `"ATH"` Kalshi alias resolves to the
      `ATH`-row's `team_id`, not the `OAK`-row's.
- [ ] 2.4 Real-Postgres integration test: seed the two documented
      non-contiguous-era cases from ADR-013 (HOU 1962-2012 vs 2013-2021,
      MIL 1970-1997 vs 1998-2021) and confirm each era still resolves to
      the correct distinct franchise/current-code (a case genuinely
      different from a relocation: id *reuse*, not a code *change*).
      Verify: test passes against the disposable test database.

## 3. Consumers

- [ ] 3.1 Update `mlb_baseball/model/season.py` (`load_schedule_from_db`,
      `team_strength_asof`, `team_wins_asof`) to resolve each team's
      current code via a join through `core.team_franchise` instead of the
      inline `CASE WHEN 'ATH' THEN 'OAK'` added in the prior fix; delete
      that inline SQL. Verify: `tests/integration/test_model_season.py`'s
      existing `test_ath_team_code_normalizes_to_oak` (and the rest of that
      file) still passes unchanged in behavior.
- [ ] 3.2 Update `mlb_baseball/report.py`'s two existing
      `CASE WHEN lt.teamidretro = 'ATH' THEN 'OAK' ELSE lt.teamidretro END`
      sites to resolve through `core.team_franchise` instead. Verify:
      `tests/integration/test_report.py`'s existing ATH-related test still
      passes.
- [ ] 3.3 Confirm no other call site duplicates this same hand-patch
      (`grep -rn "ATH" --include=*.py mlb_baseball/`) and update any found.
      Verify: the grep after this task shows only the new resolver's own
      code, test fixtures, and the untouched `conform.py`/`carry.py`
      entries design.md scoped out (stadium/rebrand data, not code
      resolution).

## 4. Health check

- [ ] 4.1 Add an `mlb doctor` check: fails when a `core.team` row's
      `retro_team_id` has a matching `raw.lahman_teams` row (a crosswalk
      is expected) but `core.team.franchise_id` is still null; does not
      fail for a row with no `raw.lahman_teams` match at all (per the
      `team-identity` spec's two scenarios). Verify: two `mlb doctor`
      integration tests — one seeding an unresolved-but-expected row
      (fails), one seeding a genuinely-uncovered row (passes) — plus a
      clean run against a fully-conformed test database (passes).

## 5. Cross-cutting verification

- [ ] 5.1 Run `uv run pytest tests/unit/test_season.py
      tests/integration/test_conform.py tests/integration/test_model_season.py
      tests/integration/test_report.py -v` and record actual pass/fail output.
- [ ] 5.2 Run `uv run ruff check mlb_baseball/conform.py
      mlb_baseball/model/season.py mlb_baseball/report.py` and
      `uv run mypy mlb_baseball/conform.py mlb_baseball/model/season.py
      mlb_baseball/report.py`, and record actual output.
- [ ] 5.3 Run `mlb conform` end to end against the test database and
      confirm `mlb doctor` passes cleanly afterward.
- [ ] 5.4 Add a new ADR to `docs/DECISIONS.md` (style of ADR-013/028/029)
      recording this decision, including the `_build_team_aliases`
      side-bug found while designing this change.
- [ ] 5.5 Update `mlb_baseball/AGENTS.md` or `conform.py`'s DOX (if one
      exists) to document the new `_build_team_franchises` step and
      `core.team_franchise`'s purpose, following this project's "update
      the owning DOX in the same change" rule.
