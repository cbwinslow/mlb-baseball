# Close Issue #8 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring `team_prior_offense_defense_v1` up to its full admission-queue contract: a documented min-sample gate for OBP/SLG/ISO/BB%/K%, a retained PA/denominator column, a suspended/doubleheader regression test for the run-environment columns, and measured era-coverage evidence for OFF-01 — closing GitHub issue #8.

**Architecture:** Extend the existing `team_rate_retrosheet_update.sql` CTE chain to compute PA once and gate the five rate-stat outputs on documented minimum thresholds, expose PA as two new nullable columns via a new migration, add one new regression test proving the run-environment side already handles postponed/doubleheader games correctly (no new production logic needed there — it's a proof, not a fix), and run the existing `mlb field-census --exact` tool read-only to produce the era-coverage evidence OFF-01 asked for.

**Tech Stack:** Python 3.13, psycopg3, PostgreSQL, pytest against real `mlb_test`, Ruff, mypy, `gh` CLI (pre-authorized for this repo per `CLAUDE.md`).

## Global Constraints

- All migrations, fixtures, tests, and database writes target `mlb_test` only. Production `mlb` may be queried **read-only**, and only for the era-coverage measurement (Task 4).
- Preserve every existing migration, column, and test from commits through `db97d96`. Additive changes only — do not rename or drop any existing `gold.game_feature` column.
- Do not touch `team_woba_retrosheet_update.sql` (tracked separately in issue #9).
- Do not implement or expand into any other admission-queue row (OFF-04+, PIT-\*, PLN-\*, CTX-\*, STA-\*, etc.).
- Do not wire `team_rate.py` into `run()`/`build_feature_stage()` or `game_base_v1` — that stays a separate, later, explicitly-gated decision.
- No new runtime dependency.
- Naming: one-or-two-word column/file names, following this project's existing convention.
- Every SQL transformation lives as a named `.sql` resource under `mlb_baseball/sql/`, read via `mlb_baseball.sql.read_sql()`.
- Run the real test suite, Ruff, and mypy before claiming any task done.

---

## Background you need (read this before writing code)

**No existing min-sample gate exists anywhere in this codebase.** `offense.py`'s wOBA computation documents small-sample noise (its `health_check()` docstring explicitly calls out that early-season values reflect just 1-3 real games) but does not gate it — it's accepted, documented noise, not filtered. This plan is establishing **new precedent**, not following an existing one. The threshold and its rationale must be documented explicitly (in code comments and a new ADR) as a new decision, not presented as if it already existed.

**Chosen threshold (do not re-litigate without new evidence):** `MIN_PA = 10` for the PA-denominator stats (OBP, BB%, K%) and `MIN_AB = 8` for the AB-denominator stats (SLG, ISO). Rationale: a real batting-title "qualified" threshold (3.1 PA/team-game, ~502 PA/season) is a season-total qualification bar, not an early-season entering-value bar — using it here would leave most of a season NULL. 10 PA is roughly 2-3 games of a lineup regular's playing time: enough to smooth out the single-game extreme (e.g. a team going 4-for-4 in its first game producing an "entering" OBP of 1.0), while still producing a real, populated stat by the first week of a season. 8 AB is the same order of magnitude scaled down slightly since AB ⊆ PA (AB excludes walks/HBP/SF, which for most players run ~10-15% of PA).

**Postponed and suspended/resumed games are already handled correctly upstream — nothing new to build for that part of Task 3.** `docs/GAME_INSTANCE_IDENTITY.md` and migrations 0034-0046 established that: a postponed game observation in `raw.mlb_schedule` never produces its own `core.game` row (the makeup game's *actual played date* is what eventually gets a `core.game` row with real scores); `mlb_baseball/sql/game_feature_rebuild.sql`'s `completed` CTE additionally requires `home_score IS NOT NULL AND away_score IS NOT NULL`, and its `completed_schedule` CTE picks the highest-priority status (`Final` > `Completed Early` > `Forfeit` > else) per `(game_id, game_date)`. `team_rate.compute_run_environment()` has zero logic of its own beyond reading `gold.game_feature`'s own already-computed `home_wins`/`home_losses`/`home_runs_for`/`home_runs_allowed` and dividing — so Task 3 here is a **regression test proving the pass-through stays correct** through a postponed-observation-plus-doubleheader scenario, not new production code.

**Current `team_rate_retrosheet_update.sql`** (as of `db97d96`) computes the PA-shaped denominator `(ab_sum + bb_sum + sf_sum + hbp_sum)` three separate times inline in the `computed` CTE (for OBP, BB%, K%). Task 1 factors this into a single `pa_sum` column in the `rate` CTE, which Task 2 then also exposes as the new `home_pa`/`away_pa` columns.

Admission-queue IDs covered by this plan: **OFF-01** (min-sample + era coverage), **OFF-02** (AB threshold — doubleheader-ordering test for this row is already done, `db97d96`), **OFF-03** (retained PA), **OFF-08** (suspended/doubleheader test).

---

## File Structure

- Create: `migrations/0051_team_rate_min_sample.sql` — adds `home_pa`, `away_pa` nullable numeric columns.
- Modify: `mlb_baseball/sql/team_rate_retrosheet_update.sql` — factor out `pa_sum`, add min-sample gates, populate PA columns.
- Modify: `mlb_baseball/model/team_rate.py` — pass `min_pa`/`min_ab` params in `compute()`.
- Modify: `tests/integration/test_model_team_rate.py` — extend the hand-calc test for PA + gate assertions; add a below-threshold test; add the suspended/doubleheader run-environment test.
- Modify: `docs/FEATURE_ADMISSION_QUEUE.md`, `docs/DECISIONS.md` (new ADR), `docs/RAW_CORE_GOLD_FIELD_CENSUS.md` (era-coverage evidence), `plans/03-research-statistics-and-features.md`, `plans/PROGRESS.md`.

## Task 1: Factor out PA, add min-sample gates

**Files:**
- Modify: `mlb_baseball/sql/team_rate_retrosheet_update.sql`
- Modify: `mlb_baseball/model/team_rate.py`
- Modify: `tests/integration/test_model_team_rate.py`

**Interfaces:**
- Consumes: nothing new (same tables as before).
- Produces: `team_rate.compute()` now passes `min_pa`/`min_ab` SQL parameters; the SQL's `computed` CTE gains a `pa_sum` output column used by Task 2.

- [ ] **Step 1: Write the failing tests**

Add to `tests/integration/test_model_team_rate.py`, right after the existing `test_compute_rolling_rate_stats_match_hand_calculation` (which needs updating too — see Step 1b):

```python
def test_compute_gates_rate_stats_below_min_sample(db_conn):
    # ATL's only prior game (G1) has exactly 1 PA (a single, ab_fl='T',
    # bat_event_fl='T') -- 1 PA is below MIN_PA=10, so every PA-denominator
    # stat (OBP/BB%/K%) entering G2 must be NULL despite a real, nonzero
    # underlying value existing. PA itself is NOT gated -- it must still
    # report the real count (1) so a consumer can see why the rate is NULL.
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('ATL', 'Atlanta', 'Braves', 1966, 2025, 144), "
            "('NYA', 'New York', 'Yankees', 1913, 2025, 147) "
            "RETURNING id, retro_team_id"
        )
        teams = {retro_id: team_id for team_id, retro_id in cur.fetchall()}
        atl, nya = teams["ATL"], teams["NYA"]
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', 2020, '2020-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('G2', 2020, '2020-04-08', %(atl)s, %(nya)s, 2, 1, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype) "
            "VALUES ('G1', 'regular'), ('G2', 'regular')"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, bat_home_id, event_cd, ab_fl, sf_fl, bat_event_fl, _season) VALUES "
            "('G1', '1', '20', 'T', 'F', 'T', '2020'), "  # ATL's only PA: 1 single
            "('G1', '0', '2',  'T', 'F', 'T', '2020'), "  # NYA -- minimal
            "('G2', '1', '2', 'T', 'F', 'T', '2020'), "
            "('G2', '0', '2', 'T', 'F', 'T', '2020')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    team_rate.compute(db_conn)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT f.home_obp, f.home_bb_pct, f.home_k_pct, f.home_slg, f.home_iso "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "WHERE g.retro_game_id = 'G2'"
        )
        row = cur.fetchone()

    assert row == (None, None, None, None, None)

    _reset(db_conn)
```

- [ ] **Step 1b: Update the existing hand-calc test's expected PA**

In `test_compute_rolling_rate_stats_match_hand_calculation`, the comment already computes `PA = AB+BB+HBP+SF = 5+2+1+0 = 8`. Since `8 < MIN_PA(10)`, once the gate lands, this test's `g2` assertions for OBP/BB%/K% would flip to NULL — the test needs restructuring to stay above the gate threshold while still hand-verifiable. Add one more unintentional walk (a 10th event row: `('G1', '1', '14', 'F', 'F', 'T', '2020')`) so PA becomes 9... that's still below 10. Instead, add two more distinct walk events to push AB+BB+HBP+SF to 10: change the single extra BB you add to *two* extra unintentional-BB rows (event_cd='14' twice more). Recompute by hand and update every assertion in the test (OBP/SLG/ISO/BB%/K%) to match the new totals — do the arithmetic explicitly in a comment, the same way the existing test already does, and don't guess: run the test, read the actual computed value from the failure output, and verify it by hand-arithmetic before hard-coding it as the expected value (never copy an assertion from a failing test's actual-output without independently checking the arithmetic is what it *should* be).

- [ ] **Step 2: Run to verify failure**

Run: `TEST_DATABASE_URL=postgresql://mlb:NZkPF9Vcyq3vLYO3Z2KdRsv4NO4RqGE@localhost:5432/mlb_test uv run pytest tests/integration/test_model_team_rate.py -v`
Expected: the new gate test fails (current SQL has no gate, so G2's stats are populated, not NULL); the updated hand-calc test fails or needs the Step 1b rework reflected before it can pass.

- [ ] **Step 3: Update the SQL — factor out `pa_sum`, add the gates**

Edit `mlb_baseball/sql/team_rate_retrosheet_update.sql`'s `rate` and `computed` CTEs:

```sql
rate AS (
    SELECT game_id, team_id, ab_sum, hbp_sum, sf_sum, so_sum,
        (b1_sum + b2_sum + b3_sum + hr_sum) AS hits_sum,
        (b1_sum + 2 * b2_sum + 3 * b3_sum + 4 * hr_sum) AS tb_sum,
        (ubb_sum + ibb_sum) AS bb_sum,
        (ab_sum + ubb_sum + ibb_sum + sf_sum + hbp_sum) AS pa_sum
    FROM rolling
),
computed AS (
    SELECT game_id, team_id, pa_sum,
        CASE WHEN pa_sum >= %(min_pa)s THEN
            (hits_sum + bb_sum + hbp_sum)::numeric / NULLIF(pa_sum, 0)
        END AS obp,
        CASE WHEN ab_sum >= %(min_ab)s THEN tb_sum::numeric / ab_sum END AS slg,
        CASE WHEN ab_sum >= %(min_ab)s THEN
            (tb_sum::numeric / ab_sum) - (hits_sum::numeric / ab_sum)
        END AS iso,
        CASE WHEN pa_sum >= %(min_pa)s THEN bb_sum::numeric / pa_sum END AS bb_pct,
        CASE WHEN pa_sum >= %(min_pa)s THEN so_sum::numeric / pa_sum END AS k_pct
    FROM rate
)
```

Also add a short comment block above `rate` explaining the gate and citing ADR-062 (Task 5 creates it) — follow this module's established citation style (see the file's current top-of-file comment for the pattern).

- [ ] **Step 4: Update `team_rate.py::compute()` to pass the new parameters**

```python
MIN_PA = 10
MIN_AB = 8


def compute(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        (exists,) = fetch_one(cur)
        if not exists:
            return 0
        cur.execute(
            read_sql("team_rate_retrosheet_update.sql"),
            {"min_pa": MIN_PA, "min_ab": MIN_AB},
        )
        return cur.rowcount
```

Add module-level docstring documentation next to these constants explaining the rationale from the Background section above (new precedent, not copied from elsewhere; 10 PA / 8 AB reasoning) — this is the kind of design decision this codebase always documents inline, not just in the ADR.

- [ ] **Step 5: Run to verify pass**

Run: `TEST_DATABASE_URL=postgresql://mlb:NZkPF9Vcyq3vLYO3Z2KdRsv4NO4RqGE@localhost:5432/mlb_test uv run pytest tests/integration/test_model_team_rate.py -v`
Expected: all tests in the file pass (the hand-calc test with its Step 1b rework, plus the new gate test).

- [ ] **Step 6: Commit**

```bash
git add mlb_baseball/sql/team_rate_retrosheet_update.sql mlb_baseball/model/team_rate.py tests/integration/test_model_team_rate.py
git commit -m "Add documented min-sample gate for team rate stats (OFF-01/02)"
```

## Task 2: Retain PA as a column (OFF-03)

**Files:**
- Create: `migrations/0051_team_rate_min_sample.sql`
- Modify: `mlb_baseball/sql/team_rate_retrosheet_update.sql`
- Modify: `tests/integration/test_model_team_rate.py`

**Interfaces:**
- Consumes: `pa_sum` from Task 1's `rate`/`computed` CTEs.
- Produces: `gold.game_feature.home_pa`/`away_pa`, populated unconditionally (never gated) so it always reflects a consumer's actual confidence signal for the gated columns.

- [ ] **Step 1: Write the migration**

```sql
-- Retained PA denominator (OFF-03, ADR-062 follow-up to ADR-061). Exposes
-- the same plate-appearance count team_rate_retrosheet_update.sql already
-- computes internally for its OBP/BB%/K% denominators and min-sample gate
-- (migration 0051 companion), so a consumer can tell a genuinely NULL
-- (below-min-sample) row from a well-supported one instead of guessing.

ALTER TABLE gold.game_feature ADD COLUMN home_pa numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_pa numeric;
```

- [ ] **Step 2: Write the failing test**

Add a PA assertion to `test_compute_rolling_rate_stats_match_hand_calculation` (already reworked in Task 1) and to `test_compute_gates_rate_stats_below_min_sample` (assert `home_pa == Decimal("1")`, proving PA is populated even when every rate stat is NULL).

- [ ] **Step 3: Run to verify failure**

Run: `TEST_DATABASE_URL=postgresql://mlb:NZkPF9Vcyq3vLYO3Z2KdRsv4NO4RqGE@localhost:5432/mlb_test uv run pytest tests/integration/test_model_team_rate.py -v`
Expected: fails — `home_pa` column doesn't exist yet.

- [ ] **Step 4: Apply the migration, update the SQL's UPDATE clause**

Apply migration 0051 to `mlb_test` (same pattern as Task 1 of the original plan — `migrate.run()` with `DATABASE_URL` pointed at `mlb_test`). Then add `home_pa = ch.pa_sum, away_pa = ca.pa_sum` to the `UPDATE gold.game_feature f SET ...` clause in `team_rate_retrosheet_update.sql`.

- [ ] **Step 5: Run to verify pass, then commit**

Run the full `tests/integration/test_model_team_rate.py -v` suite, confirm green.

```bash
git add migrations/0051_team_rate_min_sample.sql mlb_baseball/sql/team_rate_retrosheet_update.sql tests/integration/test_model_team_rate.py
git commit -m "Retain PA as gold.game_feature.home_pa/away_pa (OFF-03)"
```

## Task 3: Suspended/doubleheader regression test for run-environment (OFF-08)

**Files:**
- Modify: `tests/integration/test_model_team_rate.py`

**Interfaces:**
- Consumes: `team_rate.compute_run_environment()`, `features.build(conn, strict=True)` (both already exist, unchanged by this task).
- Produces: nothing new — this task is test-only, proving existing behavior.

- [ ] **Step 1: Write the test**

```python
def test_compute_run_environment_unaffected_by_postponed_observation(db_conn):
    # A postponed schedule observation for a game_id never produces its own
    # core.game row (docs/GAME_INSTANCE_IDENTITY.md; only the real makeup
    # date's Final observation does) -- this proves compute_run_environment()
    # stays correct through that, since it only reads gold.game_feature's
    # own already-computed wins/losses/runs sums (mlb_baseball/sql/
    # game_feature_rebuild.sql, migration 0046), which already handle this.
    #
    # G1 (2020-04-01): ATL scores 5, allows 3.
    # A postponed observation for a game originally scheduled 2020-04-05
    # (never played that day -- no core.game row for it at all) sits in
    # raw.mlb_schedule alongside a *different*, later real game.
    # DH1 (game_number=1, 2020-04-08): ATL scores 6, allows 5.
    # DH2 (game_number=2, 2020-04-08, the actual makeup game, inserted
    #   before DH1 to also prove doubleheader game_number ordering holds
    #   for this function's pass-through): ATL scores 4, allows 2.
    #
    # Entering DH2: runs_for_avg = (5+6)/2 = 5.5, runs_allowed_avg = (3+5)/2 = 4.0
    # (must reflect G1+DH1 only -- the postponed observation contributes
    # nothing, and DH2 must not include itself).
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_schedule')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.mlb_schedule (game_id text, game_datetime text, "
                "game_date text, game_type text, status text, home_id text, away_id text, "
                "game_num text, venue_id text, _season text, _loaded_at timestamptz)"
            )
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('ATL', 'Atlanta', 'Braves', 1966, 2025, 144), "
            "('NYA', 'New York', 'Yankees', 1913, 2025, 147) "
            "RETURNING id, retro_team_id"
        )
        teams = {retro_id: team_id for team_id, retro_id in cur.fetchall()}
        atl, nya = teams["ATL"], teams["NYA"]
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, game_pk, season, game_date, game_number, "
            "home_team_id, away_team_id, home_score, away_score, game_type) VALUES "
            "('G1', 2001, 2020, '2020-04-01', 1, %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('DH2', 2003, 2020, '2020-04-08', 2, %(atl)s, %(nya)s, 4, 2, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, game_pk, season, game_date, game_number, "
            "home_team_id, away_team_id, home_score, away_score, game_type) VALUES "
            "('DH1', 2002, 2020, '2020-04-08', 1, %(atl)s, %(nya)s, 6, 5, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule "
            "(game_id, game_datetime, game_date, game_type, status, home_id, away_id, "
            "game_num, _season, _loaded_at) VALUES "
            "('2001', '2020-04-01T18:00:00Z', '2020-04-01', 'R', 'Final', '144', '147', '1', '2020', now()), "
            "('2002', '2020-04-08T17:00:00Z', '2020-04-08', 'R', 'Final', '144', '147', '1', '2020', now()), "
            "('2003', '2020-04-08T20:00:00Z', '2020-04-08', 'R', 'Final', '144', '147', '2', '2020', now()), "
            # Postponed-only observation: a game_id that never gets a
            # matching core.game row at all.
            "('2099', '2020-04-05T18:00:00Z', '2020-04-05', 'R', 'Postponed', '144', '147', '1', '2020', now())"
        )
    db_conn.commit()

    features.build(db_conn, strict=True)
    db_conn.commit()
    team_rate.compute_run_environment(db_conn)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT f.home_runs_for_avg, f.home_runs_allowed_avg "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "WHERE g.retro_game_id = 'DH2'"
        )
        row = cur.fetchone()

    assert row == (Decimal("5.5"), Decimal("4.0"))

    _reset(db_conn)
```

- [ ] **Step 2: Run to verify it passes as-is (proving, not fixing)**

Run: `TEST_DATABASE_URL=postgresql://mlb:NZkPF9Vcyq3vLYO3Z2KdRsv4NO4RqGE@localhost:5432/mlb_test uv run pytest tests/integration/test_model_team_rate.py::test_compute_run_environment_unaffected_by_postponed_observation -v`
Expected: PASS immediately (per the Background section, the underlying base contract already handles this correctly). If it fails, that means the Background section's assumption was wrong — stop and re-read `docs/GAME_INSTANCE_IDENTITY.md` and `game_feature_rebuild.sql`'s `completed`/`completed_schedule` CTEs directly before changing anything; do not guess a fix. This is the one place in this plan where "the test should already pass" is expected and correct, not a sign something is wrong with the test.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_model_team_rate.py
git commit -m "Add suspended/doubleheader regression test for run-environment (OFF-08)"
```

## Task 4: Era-coverage evidence for OFF-01

**Files:**
- Modify: `docs/RAW_CORE_GOLD_FIELD_CENSUS.md` or `docs/FEATURE_ADMISSION_QUEUE.md` (whichever already documents `mlb field-census` evidence — check both, follow the existing convention for where measured evidence lives).

**Interfaces:** none — this task runs an existing read-only tool and records output.

- [ ] **Step 1: Run the census tool read-only against production `mlb`**

```bash
DATABASE_URL=postgresql://mlb:NZkPF9Vcyq3vLYO3Z2KdRsv4NO4RqGE@localhost:5432/mlb \
  uv run mlb field-census --exact \
  --output-json artifacts/census/mlb_era_coverage.json \
  --output-markdown artifacts/census/mlb_era_coverage.md
```

This is read-only per `field_census.py`'s own design (repeatable-read, no writes) — confirm this before running by reading `mlb_baseball/field_census.py`'s top-of-file docstring if there's any doubt. If in doubt, do not run it against production; run it against `mlb_test` instead and note in the docs update that era coverage reflects the test database's sample, not full production history, and why.

- [ ] **Step 2: Extract the relevant fields' era coverage**

From the generated report, find the coverage rows for `raw.retrosheet_event.event_cd`, `.ab_fl`, `.sf_fl`, and `.bat_event_fl` — specifically whether `bat_event_fl` (needed by this feature family's min-sample-gated queries) has full historical coverage back to Retrosheet's 1910 start, or has a documented earlier gap. Record the actual measured null-rate/coverage-by-era numbers, not an assumption.

- [ ] **Step 3: Record the evidence**

Add a short, dated subsection to `docs/RAW_CORE_GOLD_FIELD_CENSUS.md` (follow its existing "verified database evidence, clearly separated from proposed future work" convention) documenting the measured `bat_event_fl`/`event_cd`/`ab_fl`/`sf_fl` era coverage specifically for OFF-01's admission-queue requirement. Cross-reference it from the OFF-01 row in `docs/FEATURE_ADMISSION_QUEUE.md`.

- [ ] **Step 4: Commit**

```bash
git add docs/RAW_CORE_GOLD_FIELD_CENSUS.md docs/FEATURE_ADMISSION_QUEUE.md artifacts/census/
git commit -m "Record measured era coverage for OFF-01 (field-census evidence)"
```

## Task 5: Docs close-out, ADR, full verification, issue close

**Files:**
- Modify: `docs/FEATURE_ADMISSION_QUEUE.md` (final wording for the 5 rows)
- Modify: `docs/DECISIONS.md` (new ADR — next available number after ADR-061)
- Modify: `plans/03-research-statistics-and-features.md`, `plans/PROGRESS.md`

- [ ] **Step 1: Update the 5 admission-queue rows**

Replace each row's "core formula implemented... outstanding" wording (added by the prior package) with final status: OFF-01 (min-sample gate + era coverage done), OFF-02 (AB threshold + doubleheader test done), OFF-03 (PA retained), OFF-08 (suspended/doubleheader test done). If any sub-item is intentionally still not done (e.g. era coverage only measured against `mlb_test` rather than production, per Task 4's fallback), say so explicitly in that row.

- [ ] **Step 2: Write the ADR**

Add `## ADR-062: Team rate stats gate on a new min-sample threshold (10 PA / 8 AB), not an existing precedent` to `docs/DECISIONS.md`, following the existing `**Decision:**`/`**Context:**`/`**Rationale:**`/`**Revisit if:**` structure. Content: the Background section of this plan, condensed — explicitly note this establishes new precedent (no prior min-sample gate existed in this codebase) and that `offense.py`'s wOBA remains deliberately ungated (a separate, not-revisited-here decision).

- [ ] **Step 3: Update plan/progress docs**

Add a paragraph to `plans/03-research-statistics-and-features.md`'s 03G section and a dated entry to `plans/PROGRESS.md`, following the established terse evidence-log style from the prior package's entries.

- [ ] **Step 4: Full verification**

```bash
uv run ruff check .
uv run ruff format --check migrations/ mlb_baseball/model/team_rate.py mlb_baseball/sql/team_rate_retrosheet_update.sql tests/integration/test_model_team_rate.py
uv run mypy mlb_baseball
TEST_DATABASE_URL=postgresql://mlb:NZkPF9Vcyq3vLYO3Z2KdRsv4NO4RqGE@localhost:5432/mlb_test uv run pytest -q
```
Expected: all clean, full suite green (719 + however many new tests this plan added, 0 failed). If a stray `test_audit_db.py` failure appears, it's the known pre-existing stale-table artifact (drop `raw.retrosheet_gameinfo`/`raw.retrosheet_event`/`raw.mlb_schedule` from `mlb_test` and re-run) — not a real regression.

- [ ] **Step 5: Commit and push**

```bash
git add docs/FEATURE_ADMISSION_QUEUE.md docs/DECISIONS.md plans/03-research-statistics-and-features.md plans/PROGRESS.md
git commit -m "Close out admission-queue contract for team_prior_offense_defense_v1 (ADR-062)"
git push
```

- [ ] **Step 6: Close (or update) issue #8**

If every item landed: `gh issue close 8 --repo cbwinslow/mlb-baseball --comment "<summary citing commit SHAs>"`. If Task 4's production run wasn't safe to do unattended and fell back to `mlb_test`-only evidence, leave the issue open with a comment explaining exactly what's left and why, rather than closing it prematurely.

---

## Self-Review Notes (already applied above)

- **Spec coverage:** OFF-01 min-sample+era-coverage → Tasks 1, 4. OFF-02 AB threshold → Task 1 (doubleheader-ordering piece already done in `db97d96`, not re-done here). OFF-03 retained PA → Task 2. OFF-08 suspended/doubleheader test → Task 3. Docs/ADR/issue close → Task 5.
- **Type/name consistency checked:** `pa_sum` (Task 1) flows into `home_pa`/`away_pa` (Task 2) via the same `computed` CTE column name across both tasks' SQL edits.
- **Deferred on purpose (not this plan's job):** everything in issue #9 (two-table gate, away-side health checks, naming, test isolation, `team_woba` bat_event_fl gap) and every other admission-queue row.
