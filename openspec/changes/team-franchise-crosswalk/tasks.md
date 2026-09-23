## 1. Schema

- [x] 1.1 Add migration `migrations/0107_team_franchise.sql`: `core.team_franchise`
      (`id bigserial PRIMARY KEY`, `franchise_id text NOT NULL UNIQUE`,
      `franchise_name text`, `current_retro_team_id text`) and
      `core.team.franchise_id bigint REFERENCES core.team_franchise (id)`
      (nullable), with a supporting index on `core.team (franchise_id)`.
      Verify: migration applies cleanly against the disposable test
      database and `core.team_franchise`/`core.team.franchise_id` exist
      with the expected types.

## 2. Franchise resolution (`conform.py`)

- [x] 2.1 Add a new SQL resource (`conform_team_franchise_insert.sql`)
      that builds one `core.team_franchise` row per distinct `franchid`
      present in `raw.lahman_teams_franchises`, joined through
      `raw.lahman_teams.franchid`/`teamidretro` to `core.team.retro_team_id`
      to compute `current_retro_team_id` (greatest `first_year`) for that
      `franchid` (per design.md's Decisions — NOT `last_year = 9999`).
      **Amended post-review:** an initial version also computed
      `legacy_retro_team_id` (smallest `first_year`) for task 3.1/3.2 to
      anchor on. Reverted before merge: automated review (CodeRabbit) and
      real production data showed a franchise can have more than one
      historical code change (the Athletics span `PHA`/`KC1`/`OAK`/`ATH`),
      so an unconditional "oldest era" anchor misattributes every other
      era's real data, not just the one relocation being fixed. See
      design.md's "Reverted design" and ADR-292. Verify: a deterministic
      hand fixture with two synthetic team-eras for one franchise (older
      era `last_year = 9999`, newer era with a later `first_year`) asserts
      the newer era's code wins for `current_retro_team_id`.
- [x] 2.2 Add `_build_team_franchises(conn)` in `conform.py` (same shape as
      `_build_team_aliases`: catches `UndefinedTable` for the optional
      `raw.lahman_teams_franchises`/`raw.lahman_teams` prerequisites,
      returns the row count), and a backfill `UPDATE core.team SET
      franchise_id = ...` joining through the same crosswalk. Wire both
      into `run()` after `_build_teams()` and before `_build_team_aliases()`.
      Verify: `mlb conform` run against the test database populates
      `core.team_franchise` and `core.team.franchise_id` with non-zero
      counts; re-running produces identical counts (idempotent, matching
      this file's existing pattern).
- [x] 2.3 Fix `_build_team_aliases`'s row-selection predicate: replace
      `WHERE retro_team_id = %s AND last_year = 9999` with a join through
      the new franchise resolution so an alias attaches to the franchise's
      *current* era's `team_id`, not whichever era `last_year` happens to
      mark active. Verify: a regression test seeding the same
      OAK(1968-9999)/ATH(2025-2025) shape as `test_conform.py`'s existing
      ATH fixture asserts the seeded `"ATH"` Kalshi alias resolves to the
      `ATH`-row's `team_id`, not the `OAK`-row's.
- [x] 2.4 Real-Postgres integration test: seed the two documented
      non-contiguous-era cases from ADR-013 (HOU 1962-2012 vs 2013-2021,
      MIL 1970-1997 vs 1998-2021) and confirm each era still resolves to
      the correct distinct franchise/current-code (a case genuinely
      different from a relocation: id *reuse*, not a code *change*).
      Verify: test passes against the disposable test database.

## 3. Consumers

- [x] 3.1 **Scope note (owner decision, apply session):** this branch was
      cut from `main`, which does not yet have `team_strength_asof`/
      `team_wins_asof`/the `--as-of` `CASE WHEN` fix — those only exist on
      the still-open PR #242 branch. Updating them is deferred to a
      follow-up once #242 merges and rebases onto this change, not done
      here. What main *does* have: `load_schedule_from_db` (no ATH
      handling at all today) and the leftover duplicate `"ATH"` entry in
      `MLB_DIVISIONS["AL"]["AL West"]`. Remove the duplicate `"ATH"` entry
      from `MLB_DIVISIONS`. **`load_schedule_from_db` deliberately does
      NOT resolve through `core.team_franchise`** (amended post-review —
      see task 2.1/design.md): `ALL_MLB_TEAMS`/`MLB_DIVISIONS` is a
      hand-maintained Python list with no season-awareness the franchise
      table could resolve against, so keeps a narrow, explicit
      `CASE WHEN retro_team_id = 'ATH' THEN 'OAK' ELSE retro_team_id END`
      inline — the same shape as the original hand-patched fix this
      change otherwise replaces. Verify: a real-Postgres integration test
      seeding an `ATH`-coded 2025 game confirms `load_schedule_from_db`
      returns `"OAK"` for it, and `simulate_season_monte_carlo` runs
      without a `KeyError`.
- [x] 3.2 Update `mlb_baseball/report.py`'s two existing
      `CASE WHEN lt.teamidretro = 'ATH' THEN 'OAK' ELSE lt.teamidretro END`
      sites to resolve each row to its own matching, year-scoped
      `core.team` era via a `LATERAL` join, falling back to a same-franchise
      row (via `core.team.franchise_id`) only when a row's own code has no
      matching `core.team` row yet (amended post-review — see task
      2.1/design.md: an initial version routed everything through
      `core.team_franchise.legacy_retro_team_id`, which silently
      misattributed every other era of a multiply-relocated franchise's
      data). Verify: `tests/integration/test_report.py`'s existing
      ATH-related test, updated to assert each era resolves to its own
      real team_id/city (a real accuracy improvement over the old
      "Oakland forever" anchor, not a preserved quirk), plus new coverage
      for a franchise with more than one historical relocation and for the
      no-own-row-yet fallback path.
- [x] 3.3 Confirm no other call site duplicates this same hand-patch
      (`grep -rn "ATH" --include=*.py mlb_baseball/`) and update any found.
      Verify: the grep after this task shows only the new resolver's own
      code, test fixtures, and the untouched `conform.py`/`carry.py`
      entries design.md scoped out (stadium/rebrand data, not code
      resolution).

## 4. Health check

- [x] 4.1 Add an `mlb doctor` check: fails when a `core.team` row's
      `retro_team_id` has a matching `raw.lahman_teams` row (a crosswalk
      is expected) but `core.team.franchise_id` is still null; does not
      fail for a row with no `raw.lahman_teams` match at all (per the
      `team-identity` spec's two scenarios). Verify: two `mlb doctor`
      integration tests — one seeding an unresolved-but-expected row
      (fails), one seeding a genuinely-uncovered row (passes) — plus a
      clean run against a fully-conformed test database (passes).

## 5. Cross-cutting verification

- [x] 5.1 Run `uv run pytest tests/unit/test_season.py
      tests/integration/test_conform.py tests/integration/test_model_season.py
      tests/integration/test_report.py -v` and record actual pass/fail output.
      Result: 96 passed (one pre-existing test, `test_run_populates_team_player_and_game`,
      needed a one-line update for `run()`'s new `core.team_franchise` counts
      key — real, expected, fixed in the same run).
- [x] 5.2 Run `uv run ruff check mlb_baseball/conform.py
      mlb_baseball/model/season.py mlb_baseball/report.py` and
      `uv run mypy mlb_baseball/conform.py mlb_baseball/model/season.py
      mlb_baseball/report.py`, and record actual output.
- [x] 5.3 **Scope note:** did not run the raw `mlb conform`/`mlb doctor`
      CLI directly — this repo's `.env` `DATABASE_URL` points at
      production `mlb`, and `conform.run()` performs a destructive
      TRUNCATE + full rebuild; running it there would be an unauthorized
      destructive action, not a verification step. Equivalent coverage
      already exists and ran clean (task 5.1): `test_run_populates_team_player_and_game`
      (full `conform.run()`, asserts the new `core.team_franchise` counts
      key), `test_multi_source_conformance_rehearsal_ties_out_across_grains`
      (broad end-to-end rehearsal), and this change's own franchise test
      (runs `conform.run()` twice for idempotency, then calls
      `conform.health_check()` directly and asserts the new check passes
      cleanly on a realistically-conformed database) — all against the
      real disposable test database pytest owns, never production.
- [x] 5.4 Add a new ADR to `docs/DECISIONS.md` (style of ADR-013/028/029)
      recording this decision, including the `_build_team_aliases`
      side-bug found while designing this change.
- [x] 5.5 Update `mlb_baseball/AGENTS.md` or `conform.py`'s DOX (if one
      exists) to document the new `_build_team_franchises` step and
      `core.team_franchise`'s purpose, following this project's "update
      the owning DOX in the same change" rule.
