# Team Prior Offense/Defense (`team_prior_offense_defense_v1`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the `team_prior_offense_defense_v1` feature family recommended by Plan 03G's field census/admission queue: five prior-completed-game team batting rate stats (OBP, SLG, ISO, BB%, K%) plus prior runs-scored/runs-allowed averages, all point-in-time-safe and gated the same way every existing `gold.game_feature` enrichment family is.

**Architecture:** Two independent enrichment steps, following the exact pattern already established by `mlb_baseball/model/offense.py` (team wOBA): a new migration adds nullable columns to `gold.game_feature`; a new `mlb_baseball/model/team_rate.py` module owns two `compute*()` functions, each backed by a named SQL resource under `mlb_baseball/sql/`; Python owns only the `to_regclass` existence gate, parameters, and row count — the transformation itself is a reviewable `.sql` file (per `docs/SQL_OWNERSHIP.md`). Neither function is wired into `run()`/`build_feature_stage()` — every sibling family (starter, bullpen, park, oaa, speed, framing, war, woba) is currently reachable only via its own `compute()` and via `model.health_check()`, not via the live pipeline, because production `gold.game_feature` population itself remains blocked behind Plan 01F. This package does not change that; it only adds a new, equally-dormant-until-wired family, exactly matching existing precedent.

**Tech Stack:** Python 3.13, psycopg3, PostgreSQL, pytest against a real `mlb_test` database (session-scoped fixture in `tests/conftest.py`), Ruff, mypy.

## Global Constraints

- All migrations, fixtures, tests, and database writes target `mlb_test` only (via `TEST_DATABASE_URL`); production `mlb` must never be written to. `tests/conftest.py::_assert_test_database_url` already enforces "test" must appear in the target dbname — do not bypass it.
- Do not weaken or touch the `game_base_v1` experiment feature set (`mlb_baseball/model/experiment.py::BASE_COLUMNS`/`LOG5_COLUMNS`) or the immutable snapshot contract. The new columns are *not* added to that tuple in this package — that is a separate, later gated decision per `docs/FEATURE_REGISTRY.md` ("later feature families must be registered separately rather than being silently added to `gold.game_feature`").
- Every new column must be point-in-time safe: computed only from games strictly before the row's own game (Retrosheet path) or from already-entering-value columns on the same row (run-environment path). Never read the current game's own outcome.
- No new runtime dependency, no new raw data source, no schema/table beyond the one migration's `ALTER TABLE` statements.
- Follow the project's one-or-two-word naming convention for new columns and files.
- Every SQL transformation lives as a named `.sql` resource under `mlb_baseball/sql/`, read via `mlb_baseball.sql.read_sql()` — never an inline f-string query for the transformation itself.
- Docs (`docs/FEATURE_REGISTRY.md`, `docs/TABLE_CONTRACTS.md`, `docs/DECISIONS.md`, `docs/FEATURE_ADMISSION_QUEUE.md`, `plans/03-research-statistics-and-features.md`, `plans/PROGRESS.md`) must be updated in the same change, not as a follow-up.
- Run the real test suite, Ruff, and mypy before claiming done; commit only after they pass.

---

## Background you need (read this before writing code)

`gold.game_feature` already has these relevant columns from the base rebuild (`mlb_baseball/sql/game_feature_rebuild.sql`, migration `0012`): `home_wins`, `home_losses`, `away_wins`, `away_losses`, `home_runs_for`, `home_runs_allowed`, `away_runs_for`, `away_runs_allowed` — all **season-to-date sums entering the row's game**, not per-game averages. `home_wins + home_losses` (when both non-NULL) is exactly the count of prior completed games this season, i.e. `games_played`. This means the "run environment" half of this package needs **no new raw-table dependency at all** — it's a pure derived UPDATE reading columns `gold.game_feature` already has, the same way `offense.py::compute_wrc_plus` reads `home_woba`/`park_factor` that a prior step already set (see that function's own docstring).

The OBP/SLG/ISO/BB%/K% half **does** need `raw.retrosheet_event`, exactly like `offense.py::compute()` (team wOBA). Confirmed event codes already used and documented elsewhere in this codebase (do not re-derive from scratch — cite these):
- `event_cd = '3'` → strikeout (`mlb_baseball/model/starter.py` module docstring)
- `event_cd = '14'` → unintentional walk, `'15'` → intentional walk (`starter.py` docstring)
- `event_cd = '16'` → HBP; `'20'/'21'/'22'/'23'` → 1B/2B/3B/HR (`mlb_baseball/model/offense.py` docstring)
- `ab_fl = 'T'` → at-bat flag; `sf_fl = 'T'` → sacrifice-fly flag (`offense.py`)

Standard formulas (FanGraphs glossary / universal sabermetric definitions — these are public-domain arithmetic, not a provider's proprietary constants, so none of the "don't blend provider metrics" `docs/DATA_SOURCES.md` cautions apply):
- `OBP = (H + BB + HBP) / (AB + BB + HBP + SF)`, where `H = 1B+2B+3B+HR`, `BB = UBB+IBB`.
- `SLG = TB / AB`, where `TB = 1*1B + 2*2B + 3*3B + 4*HR`.
- `ISO = SLG - AVG`, where `AVG = H / AB`.
- `BB% = BB / PA`, `K% = SO / PA`, where `PA = AB + BB + HBP + SF` (this excludes sacrifice bunts and catcher's interference, which this codebase does not currently track from `raw.retrosheet_event` — an honest, documented gap, same posture as `offense.py`'s own denominator caveat).

All of it uses the same rolling-window shape already proven in `mlb_baseball/sql/team_woba_retrosheet_update.sql`: `SUM(...) OVER (PARTITION BY team_id, season ORDER BY game_date, game_id ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)` — i.e. every completed game *before* this one, within the same season, excluding the current game itself. That's what makes it point-in-time safe.

Admission-queue IDs covered: **OFF-01** (OBP), **OFF-02** (SLG/ISO), **OFF-03** (BB%/K%), **OFF-08** (run environment), **DEF-01** (run prevention) from `docs/FEATURE_ADMISSION_QUEUE.md`.

---

## File Structure

- Create: `migrations/0050_team_prior_offense_defense.sql` — 14 new nullable columns on `gold.game_feature`.
- Create: `mlb_baseball/sql/team_rate_retrosheet_update.sql` — OBP/SLG/ISO/BB%/K% rolling UPDATE.
- Create: `mlb_baseball/sql/team_run_environment_update.sql` — derived runs-for/allowed average UPDATE.
- Create: `mlb_baseball/model/team_rate.py` — `compute()`, `compute_run_environment()`, `health_check()`.
- Modify: `mlb_baseball/model/__init__.py` — import `team_rate`, add its checks to `health_check()`.
- Create: `tests/integration/test_model_team_rate.py` — hand-computed fixture tests, gating tests, health-check tests.
- Modify: `docs/FEATURE_REGISTRY.md` — extend the compatibility-enrichment row.
- Modify: `docs/TABLE_CONTRACTS.md` — extend the same row in the gold contracts table.
- Modify: `docs/DECISIONS.md` — new `ADR-061`.
- Modify: `docs/FEATURE_ADMISSION_QUEUE.md` — mark OFF-01/02/03/08 and DEF-01 implemented.
- Modify: `plans/03-research-statistics-and-features.md` — 03G "implemented" note.
- Modify: `plans/PROGRESS.md` — dated evidence entry.

## Task 1: Migration — add the 14 columns

**Files:**
- Create: `migrations/0050_team_prior_offense_defense.sql`

**Interfaces:**
- Produces: columns `home_obp`, `away_obp`, `home_slg`, `away_slg`, `home_iso`, `away_iso`, `home_bb_pct`, `away_bb_pct`, `home_k_pct`, `away_k_pct`, `home_runs_for_avg`, `away_runs_for_avg`, `home_runs_allowed_avg`, `away_runs_allowed_avg`, all `numeric`, all nullable, on `gold.game_feature`. Every later task's SQL/tests reference exactly these names.

- [ ] **Step 1: Write the migration**

```sql
-- Team prior offense/defense (ADR-061, Plan 03G admission queue OFF-01/
-- OFF-02/OFF-03/OFF-08/DEF-01, docs/FEATURE_ADMISSION_QUEUE.md). Prior
-- rolling within-season OBP/SLG/ISO/BB%/K% from raw.retrosheet_event
-- (see mlb_baseball/model/team_rate.py::compute, same shape as
-- 0018_team_woba.sql) plus prior runs-for/allowed averages derived
-- directly from already-computed home_runs_for/home_wins/home_losses
-- (see team_rate.py::compute_run_environment) -- no new raw dependency
-- for the run-environment half.

ALTER TABLE gold.game_feature ADD COLUMN home_obp numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_obp numeric;
ALTER TABLE gold.game_feature ADD COLUMN home_slg numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_slg numeric;
ALTER TABLE gold.game_feature ADD COLUMN home_iso numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_iso numeric;
ALTER TABLE gold.game_feature ADD COLUMN home_bb_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_bb_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN home_k_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_k_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN home_runs_for_avg numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_runs_for_avg numeric;
ALTER TABLE gold.game_feature ADD COLUMN home_runs_allowed_avg numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_runs_allowed_avg numeric;
```

- [ ] **Step 2: Apply it to `mlb_test` and confirm**

Run: `TEST_DATABASE_URL=postgresql:///mlb_test uv run python -c "from mlb_baseball import migrate; migrate.run()"`
Expected: exits with no error; `0050_team_prior_offense_defense.sql` is now recorded as applied. (The `tests/conftest.py` session fixture will also run every migration automatically before the test suite — this manual step is just to confirm the file itself is syntactically valid before writing code against it.)

- [ ] **Step 3: Commit**

```bash
git add migrations/0050_team_prior_offense_defense.sql
git commit -m "Add team_prior_offense_defense_v1 columns to gold.game_feature"
```

## Task 2: Run-environment derived update (`compute_run_environment`)

**Files:**
- Create: `mlb_baseball/sql/team_run_environment_update.sql`
- Create: `mlb_baseball/model/team_rate.py` (this task writes the module skeleton + this one function; Task 3 adds `compute()`)
- Test: `tests/integration/test_model_team_rate.py` (this task writes the first two tests; Task 3 adds the rest)

**Interfaces:**
- Consumes: `gold.game_feature.{home,away}_{wins,losses,runs_for,runs_allowed}` (already populated by `features.build()`, from Task 1's Background section).
- Produces: `team_rate.compute_run_environment(conn: psycopg.Connection) -> int` — later tasks and `model/__init__.py` call this by name.

- [ ] **Step 1: Write the failing test**

```python
"""Regression coverage for mlb_baseball.model.team_rate -- prior rolling
team OBP/SLG/ISO/BB%/K% (ADR-061, admission queue OFF-01/02/03) and prior
runs-for/allowed averages (OFF-08/DEF-01).
"""

from decimal import Decimal

from mlb_baseball.model import features, team_rate


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM raw.retrosheet_event")
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM raw.retrosheet_gameinfo")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def _insert_three_games(db_conn):
    # ATL home in G1 (5-3 win) and G2 (2-6 loss); G3 is what we assert on.
    # Entering G3: runs_for_avg = (5+2)/2 = 3.5, runs_allowed_avg = (3+6)/2 = 4.5.
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
            "('G2', 2020, '2020-04-08', %(atl)s, %(nya)s, 2, 6, 'regular'), "
            "('G3', 2020, '2020-04-15', %(atl)s, %(nya)s, 1, 1, 'regular')",
            {"atl": atl, "nya": nya},
        )
    db_conn.commit()


def test_compute_run_environment_matches_hand_calculation(db_conn):
    _reset(db_conn)
    _insert_three_games(db_conn)
    features.build(db_conn)
    db_conn.commit()

    updated = team_rate.compute_run_environment(db_conn)
    db_conn.commit()

    assert updated == 3
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_runs_for_avg, f.home_runs_allowed_avg "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1:] for r in cur.fetchall()}

    assert rows["G1"] == (None, None)  # first game -- nothing prior
    assert rows["G3"] == (Decimal("3.5"), Decimal("4.5"))

    _reset(db_conn)


def test_compute_run_environment_is_idempotent(db_conn):
    _reset(db_conn)
    _insert_three_games(db_conn)
    features.build(db_conn)
    db_conn.commit()

    team_rate.compute_run_environment(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_runs_for_avg FROM gold.game_feature f "
            "JOIN core.game g ON g.id = f.game_id WHERE g.retro_game_id = 'G3'"
        )
        (first_run,) = cur.fetchone()

    team_rate.compute_run_environment(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_runs_for_avg FROM gold.game_feature f "
            "JOIN core.game g ON g.id = f.game_id WHERE g.retro_game_id = 'G3'"
        )
        (second_run,) = cur.fetchone()

    assert first_run == second_run == Decimal("3.5")

    _reset(db_conn)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `TEST_DATABASE_URL=postgresql:///mlb_test uv run pytest tests/integration/test_model_team_rate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mlb_baseball.model.team_rate'`.

- [ ] **Step 3: Write the SQL resource**

```sql
-- Prior runs-for/allowed averages, derived from already-populated
-- gold.game_feature columns (OFF-08/DEF-01) -- no new raw dependency.
-- home_wins + home_losses is exactly the count of prior completed
-- season games, since features.build() only ever sets both from the
-- same season-to-date window (see game_feature_rebuild.sql).

UPDATE gold.game_feature
SET home_runs_for_avg = CASE WHEN (home_wins + home_losses) > 0
        THEN home_runs_for::numeric / (home_wins + home_losses) END,
    home_runs_allowed_avg = CASE WHEN (home_wins + home_losses) > 0
        THEN home_runs_allowed::numeric / (home_wins + home_losses) END,
    away_runs_for_avg = CASE WHEN (away_wins + away_losses) > 0
        THEN away_runs_for::numeric / (away_wins + away_losses) END,
    away_runs_allowed_avg = CASE WHEN (away_wins + away_losses) > 0
        THEN away_runs_allowed::numeric / (away_wins + away_losses) END
WHERE TRUE;
```

- [ ] **Step 4: Write the module skeleton**

```python
"""Team prior offense/defense (ADR-061, Plan 03G admission queue
OFF-01 OBP, OFF-02 SLG/ISO, OFF-03 BB%/K%, OFF-08/DEF-01 run
environment). Same point-in-time-safe, no-leakage shape as team wOBA
(mlb_baseball/model/offense.py, ADR-036): every rate is a rolling,
within-season value computed only from games strictly before the one
it's attached to.

compute() reconstructs OBP/SLG/ISO/BB%/K% from raw.retrosheet_event's
per-play data using the same event_cd mapping already confirmed and
used elsewhere in this codebase (3=K, 14/15=UBB/IBB, 16=HBP, 20/21/22/23
=1B/2B/3B/HR -- see mlb_baseball/model/starter.py and offense.py module
docstrings). PA = AB+BB+HBP+SF; this excludes sacrifice bunts and
catcher's interference, which raw.retrosheet_event's ab_fl/sf_fl flags
don't separately expose here -- a real, documented gap, not a silent
approximation, same posture as offense.py's own wOBA denominator note.

compute_run_environment() needs no raw.retrosheet_event dependency at
all: home_runs_for/home_runs_allowed/home_wins/home_losses are already
entering-value sums set by features.build() (mlb_baseball/sql/
game_feature_rebuild.sql), so the per-game average is a pure derived
UPDATE off gold.game_feature's own already-computed columns -- the same
"read a prior step's output, don't recompute it" shape as
offense.py::compute_wrc_plus reading home_woba/park_factor.

Scope: the rate-stat half covers 1910-2025 only (raw.retrosheet_event's
known range); no 2026+ raw.mlb_playbyplay equivalent is built in this
package -- an honest, documented gap, same as starter.py/offense.py
before their own compute_live() follow-ups landed.
"""

import psycopg

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import Check
from mlb_baseball.sql import read_sql


def compute_run_environment(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute(read_sql("team_run_environment_update.sql"))
        return cur.rowcount


def health_check() -> list[Check]:
    return []
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `TEST_DATABASE_URL=postgresql:///mlb_test uv run pytest tests/integration/test_model_team_rate.py -v`
Expected: `2 passed`.

- [ ] **Step 6: Commit**

```bash
git add mlb_baseball/sql/team_run_environment_update.sql mlb_baseball/model/team_rate.py tests/integration/test_model_team_rate.py
git commit -m "Add prior runs-for/allowed average feature (OFF-08/DEF-01)"
```

## Task 3: Retrosheet rate stats (`compute` — OBP/SLG/ISO/BB%/K%)

**Files:**
- Create: `mlb_baseball/sql/team_rate_retrosheet_update.sql`
- Modify: `mlb_baseball/model/team_rate.py` — add `compute()`
- Modify: `tests/integration/test_model_team_rate.py` — add the rate-stat tests

**Interfaces:**
- Consumes: `raw.retrosheet_event`, `raw.retrosheet_gameinfo` (same tables `offense.py::compute()` already reads).
- Produces: `team_rate.compute(conn: psycopg.Connection) -> int`.

- [ ] **Step 1: Write the failing tests (append to the same test file)**

```python
def _ensure_retrosheet_tables(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.retrosheet_event ("
                "game_id text, bat_home_id text, event_cd text, "
                "ab_fl text, sf_fl text, _season text)"
            )
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        if not cur.fetchone()[0]:
            cur.execute("CREATE TABLE raw.retrosheet_gameinfo (gid text, gametype text)")
    db_conn.commit()


def test_compute_rolling_rate_stats_match_hand_calculation(db_conn):
    # ATL (home) in G1: 1 single, 1 double, 1 unintentional BB, 1
    # intentional BB, 1 HBP, 1 strikeout, 2 generic outs.
    #   AB = single + double + 2 generic outs + strikeout = 5
    #      (ab_fl='T' on every batted/struck-out plate appearance below)
    #   H = 1B(1) + 2B(1) = 2; TB = 1*1 + 2*1 = 3
    #   BB = ubb(1) + ibb(1) = 2; HBP = 1; SF = 0; SO = 1
    #   OBP = (H+BB+HBP)/(AB+BB+HBP+SF) = (2+2+1)/(5+2+1+0) = 5/8 = 0.625
    #   SLG = TB/AB = 3/5 = 0.6
    #   AVG = H/AB = 2/5 = 0.4; ISO = SLG-AVG = 0.2
    #   PA = AB+BB+HBP+SF = 5+2+1+0 = 8
    #   BB% = 2/8 = 0.25; K% = 1/8 = 0.125
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
            "(game_id, bat_home_id, event_cd, ab_fl, sf_fl, _season) VALUES "
            "('G1', '1', '20', 'T', 'F', '2020'), "  # single
            "('G1', '1', '21', 'T', 'F', '2020'), "  # double
            "('G1', '1', '14', 'F', 'F', '2020'), "  # unintentional BB
            "('G1', '1', '15', 'F', 'F', '2020'), "  # intentional BB
            "('G1', '1', '16', 'F', 'F', '2020'), "  # HBP
            "('G1', '1', '3',  'T', 'F', '2020'), "  # strikeout
            "('G1', '1', '2',  'T', 'F', '2020'), "  # generic out
            "('G1', '1', '2',  'T', 'F', '2020'), "  # generic out
            "('G1', '0', '2',  'T', 'F', '2020'), "  # NYA (away) -- minimal
            # G2 needs at least one event row per side for the rolling
            # window's "current row" to exist at all.
            "('G2', '1', '2', 'T', 'F', '2020'), "
            "('G2', '0', '2', 'T', 'F', '2020')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = team_rate.compute(db_conn)
    db_conn.commit()

    assert updated == 2
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_obp, f.home_slg, f.home_iso, "
            "f.home_bb_pct, f.home_k_pct "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1:] for r in cur.fetchall()}

    assert rows["G1"] == (None, None, None, None, None)  # first game
    g2 = rows["G2"]
    assert g2[0] == Decimal("0.625")   # OBP
    assert g2[1] == Decimal("0.6")     # SLG
    assert g2[2] == Decimal("0.2")     # ISO
    assert g2[3] == Decimal("0.25")    # BB%
    assert g2[4] == Decimal("0.125")   # K%

    _reset(db_conn)


def test_compute_returns_zero_without_retrosheet_event_table(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_event")
    db_conn.commit()

    assert team_rate.compute(db_conn) == 0
```

- [ ] **Step 2: Run to verify failure**

Run: `TEST_DATABASE_URL=postgresql:///mlb_test uv run pytest tests/integration/test_model_team_rate.py -v`
Expected: FAIL — `AttributeError: module 'mlb_baseball.model.team_rate' has no attribute 'compute'`.

- [ ] **Step 3: Write the SQL resource**

```sql
-- Prior rolling team OBP/SLG/ISO/BB%/K% (OFF-01/02/03), same shape as
-- team_woba_retrosheet_update.sql: SUM(...) OVER an UNBOUNDED PRECEDING
-- .. 1 PRECEDING window, so the value entering a game reflects every
-- completed game strictly before it, within the same season.

WITH regular_games AS (
    SELECT g.id AS game_id, g.season, g.game_date, g.retro_game_id,
        g.home_team_id, g.away_team_id
    FROM core.game g
    WHERE g.game_type = 'regular'
),
team_game_stats AS (
    SELECT
        rg.game_id, rg.season, rg.game_date,
        CASE WHEN re.bat_home_id = '1' THEN rg.home_team_id ELSE rg.away_team_id END AS team_id,
        count(*) FILTER (WHERE re.event_cd = '14') AS ubb,
        count(*) FILTER (WHERE re.event_cd = '15') AS ibb,
        count(*) FILTER (WHERE re.event_cd = '16') AS hbp,
        count(*) FILTER (WHERE re.event_cd = '20') AS b1,
        count(*) FILTER (WHERE re.event_cd = '21') AS b2,
        count(*) FILTER (WHERE re.event_cd = '22') AS b3,
        count(*) FILTER (WHERE re.event_cd = '23') AS hr,
        count(*) FILTER (WHERE re.event_cd = '3') AS so,
        count(*) FILTER (WHERE re.ab_fl = 'T') AS ab,
        count(*) FILTER (WHERE re.sf_fl = 'T') AS sf
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    GROUP BY rg.game_id, rg.season, rg.game_date,
        CASE WHEN re.bat_home_id = '1' THEN rg.home_team_id ELSE rg.away_team_id END
),
rolling AS (
    SELECT game_id, team_id,
        SUM(ubb) OVER w AS ubb_sum, SUM(ibb) OVER w AS ibb_sum, SUM(hbp) OVER w AS hbp_sum,
        SUM(b1) OVER w AS b1_sum, SUM(b2) OVER w AS b2_sum, SUM(b3) OVER w AS b3_sum,
        SUM(hr) OVER w AS hr_sum, SUM(so) OVER w AS so_sum,
        SUM(ab) OVER w AS ab_sum, SUM(sf) OVER w AS sf_sum
    FROM team_game_stats
    WINDOW w AS (
        PARTITION BY team_id, season ORDER BY game_date, game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),
rate AS (
    SELECT game_id, team_id, ab_sum, hbp_sum, sf_sum, so_sum,
        (b1_sum + b2_sum + b3_sum + hr_sum) AS hits_sum,
        (b1_sum + 2 * b2_sum + 3 * b3_sum + 4 * hr_sum) AS tb_sum,
        (ubb_sum + ibb_sum) AS bb_sum
    FROM rolling
),
computed AS (
    SELECT game_id, team_id,
        CASE WHEN (ab_sum + bb_sum + sf_sum + hbp_sum) > 0 THEN
            (hits_sum + bb_sum + hbp_sum)::numeric / (ab_sum + bb_sum + sf_sum + hbp_sum)
        END AS obp,
        CASE WHEN ab_sum > 0 THEN tb_sum::numeric / ab_sum END AS slg,
        CASE WHEN ab_sum > 0 THEN
            (tb_sum::numeric / ab_sum) - (hits_sum::numeric / ab_sum)
        END AS iso,
        CASE WHEN (ab_sum + bb_sum + sf_sum + hbp_sum) > 0 THEN
            bb_sum::numeric / (ab_sum + bb_sum + sf_sum + hbp_sum)
        END AS bb_pct,
        CASE WHEN (ab_sum + bb_sum + sf_sum + hbp_sum) > 0 THEN
            so_sum::numeric / (ab_sum + bb_sum + sf_sum + hbp_sum)
        END AS k_pct
    FROM rate
)
UPDATE gold.game_feature f
SET home_obp = ch.obp, away_obp = ca.obp,
    home_slg = ch.slg, away_slg = ca.slg,
    home_iso = ch.iso, away_iso = ca.iso,
    home_bb_pct = ch.bb_pct, away_bb_pct = ca.bb_pct,
    home_k_pct = ch.k_pct, away_k_pct = ca.k_pct
FROM regular_games rg
LEFT JOIN computed ch ON ch.game_id = rg.game_id AND ch.team_id = rg.home_team_id
LEFT JOIN computed ca ON ca.game_id = rg.game_id AND ca.team_id = rg.away_team_id
WHERE f.game_id = rg.game_id;
```

- [ ] **Step 4: Add `compute()` to `mlb_baseball/model/team_rate.py`**

```python
def compute(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        (exists,) = fetch_one(cur)
        if not exists:
            return 0
        cur.execute(read_sql("team_rate_retrosheet_update.sql"))
        return cur.rowcount
```

- [ ] **Step 5: Run to verify pass**

Run: `TEST_DATABASE_URL=postgresql:///mlb_test uv run pytest tests/integration/test_model_team_rate.py -v`
Expected: `4 passed`.

- [ ] **Step 6: Commit**

```bash
git add mlb_baseball/sql/team_rate_retrosheet_update.sql mlb_baseball/model/team_rate.py tests/integration/test_model_team_rate.py
git commit -m "Add prior team OBP/SLG/ISO/BB%/K% feature (OFF-01/02/03)"
```

## Task 4: Health checks, `mlb doctor` wiring

**Files:**
- Modify: `mlb_baseball/model/team_rate.py` — real `health_check()`
- Modify: `mlb_baseball/model/__init__.py:20-33` (the `from mlb_baseball.model import (...)` block and the `health_check()` function at the bottom)
- Modify: `tests/integration/test_model_team_rate.py` — add health-check test

**Interfaces:**
- Consumes: `team_rate.compute`, `team_rate.compute_run_environment` (already produced by Tasks 2-3).
- Produces: `team_rate.health_check() -> list[Check]`, wired into `mlb_baseball.model.health_check()` so `mlb doctor` surfaces it automatically (`doctor.py:212` already calls `model.health_check()`).

- [ ] **Step 1: Write the failing test**

First, query real bounds from `mlb_test` so the health check isn't guessed:

Run: `TEST_DATABASE_URL=postgresql:///mlb_test uv run python -c "
from mlb_baseball.db import get_connection
with get_connection() as conn, conn.cursor() as cur:
    cur.execute('SELECT min(home_obp), max(home_obp), min(home_slg), max(home_slg), min(home_runs_for_avg), max(home_runs_for_avg) FROM gold.game_feature')
    print(cur.fetchone())
"`

If `gold.game_feature` is empty in `mlb_test` at this point (likely, since only the rehearsal populates it and this suite tears down after each test), use the same generous-but-real-bug-catching bounds style as `offense.py::health_check()` — mathematically OBP/BB%/K% are hard-bounded `[0, 1]`; SLG/ISO are hard-bounded `[0, 4]` (four total bases every at-bat is the theoretical ceiling); runs-for/allowed averages use `[0, 30]` (a team's entering-average runs/game legitimately spiking from a 20-run single game in a 1-2 game sample is real small-sample noise, not a bug — same reasoning `offense.py` documents for `home_woba`'s early-season range). Add this test:

```python
def test_health_check_flags_an_implausible_value(db_conn):
    _reset(db_conn)
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
            "home_score, away_score, game_type) "
            "VALUES ('G1', 2024, '2024-04-01', %s, %s, 5, 3, 'regular')",
            (atl, nya),
        )
    db_conn.commit()
    features.build(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE gold.game_feature SET home_obp = 5.0 "
            "WHERE game_id = (SELECT id FROM core.game WHERE retro_game_id = 'G1')"
        )
    db_conn.commit()

    checks = team_rate.health_check()
    obp_check = next(c for c in checks if "obp" in c.name)

    assert not obp_check.ok
    assert "1 rows" in obp_check.detail

    _reset(db_conn)
```

- [ ] **Step 2: Run to verify failure**

Run: `TEST_DATABASE_URL=postgresql:///mlb_test uv run pytest tests/integration/test_model_team_rate.py::test_health_check_flags_an_implausible_value -v`
Expected: FAIL — `health_check()` currently returns `[]`, so `next(...)` raises `StopIteration`.

- [ ] **Step 3: Implement `health_check()`**

```python
def health_check() -> list[Check]:
    """Bounds are mathematical ceilings (OBP/BB%/K% in [0,1]; SLG/ISO in
    [0,4], four total bases per at-bat) except runs-for/allowed averages,
    which use a generous [0,30] to tolerate real early-season small-sample
    swings (same posture as offense.py's home_woba bound, which documents
    the identical tradeoff)."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT "
            "count(*) FILTER (WHERE home_obp IS NOT NULL AND (home_obp < 0 OR home_obp > 1)), "
            "count(*) FILTER (WHERE home_slg IS NOT NULL AND (home_slg < 0 OR home_slg > 4)), "
            "count(*) FILTER (WHERE home_iso IS NOT NULL AND (home_iso < -1 OR home_iso > 4)), "
            "count(*) FILTER (WHERE home_bb_pct IS NOT NULL AND (home_bb_pct < 0 OR home_bb_pct > 1)), "
            "count(*) FILTER (WHERE home_k_pct IS NOT NULL AND (home_k_pct < 0 OR home_k_pct > 1)), "
            "count(*) FILTER (WHERE home_runs_for_avg IS NOT NULL "
            "  AND (home_runs_for_avg < 0 OR home_runs_for_avg > 30)), "
            "count(*) FILTER (WHERE home_runs_allowed_avg IS NOT NULL "
            "  AND (home_runs_allowed_avg < 0 OR home_runs_allowed_avg > 30)) "
            "FROM gold.game_feature"
        )
        bad_obp, bad_slg, bad_iso, bad_bb, bad_k, bad_rf, bad_ra = fetch_one(cur)

    def _check(name: str, bad: int, bounds: str) -> Check:
        if bad:
            return Check(name, False, f"{bad} rows outside {bounds}")
        return Check(name, True, f"all computed values within {bounds}")

    return [
        _check("home_obp plausible range", bad_obp, "0-1"),
        _check("home_slg plausible range", bad_slg, "0-4"),
        _check("home_iso plausible range", bad_iso, "-1-4"),
        _check("home_bb_pct plausible range", bad_bb, "0-1"),
        _check("home_k_pct plausible range", bad_k, "0-1"),
        _check("home_runs_for_avg plausible range", bad_rf, "0-30"),
        _check("home_runs_allowed_avg plausible range", bad_ra, "0-30"),
    ]
```

- [ ] **Step 4: Wire into `mlb_baseball/model/__init__.py`**

In the `from mlb_baseball.model import (...)` block (currently lines 20-33), add `team_rate` in alphabetical order:

```python
from mlb_baseball.model import (
    bullpen,
    elo,
    evaluation,
    features,
    framing,
    gbm,
    log5,
    market,
    oaa,
    offense,
    park,
    speed,
    starter,
    team_rate,
    war,
)
```

In `health_check()` (bottom of the file), add it to the aggregate list, matching the existing one-call-per-line style:

```python
def health_check() -> list[Check]:
    return (
        features.health_check()
        + log5.health_check()
        + gbm.health_check()
        + starter.health_check()
        + park.health_check()
        + offense.health_check()
        + team_rate.health_check()
        + war.health_check()
        + bullpen.health_check()
        + oaa.health_check()
        + speed.health_check()
        + framing.health_check()
        + market.health_check()
    )
```

- [ ] **Step 5: Run to verify pass**

Run: `TEST_DATABASE_URL=postgresql:///mlb_test uv run pytest tests/integration/test_model_team_rate.py -v`
Expected: `5 passed`.

- [ ] **Step 6: Commit**

```bash
git add mlb_baseball/model/team_rate.py mlb_baseball/model/__init__.py tests/integration/test_model_team_rate.py
git commit -m "Wire team_rate health checks into mlb doctor"
```

## Task 5: Docs — registry, contracts, ADR, queue, plan status

**Files:**
- Modify: `docs/FEATURE_REGISTRY.md`
- Modify: `docs/TABLE_CONTRACTS.md`
- Modify: `docs/DECISIONS.md`
- Modify: `docs/FEATURE_ADMISSION_QUEUE.md`
- Modify: `plans/03-research-statistics-and-features.md`
- Modify: `plans/PROGRESS.md`

- [ ] **Step 1: `docs/FEATURE_REGISTRY.md`** — this file currently has no row for the existing per-family enrichment columns (starter/bullpen/etc.) beyond the `game_base_v1` row; `docs/TABLE_CONTRACTS.md` is where that combined row lives. Add a short paragraph after the existing `game_base_v1` row's explanatory text:

```markdown
`team_prior_offense_defense_v1` (`mlb_baseball/model/team_rate.py`, ADR-061)
adds prior rolling OBP/SLG/ISO/BB%/K% (admission queue OFF-01/02/03) and
prior runs-for/allowed averages (OFF-08/DEF-01) as compatibility enrichment
columns on `gold.game_feature`, the same status as the existing starter/
bullpen/park/oaa/speed/framing/war/woba columns: not part of `game_base_v1`,
not wired into the live pipeline yet, tested and health-checked in isolation.
```

- [ ] **Step 2: `docs/TABLE_CONTRACTS.md`** — extend the existing combined row (currently `| Starter, bullpen, framing, OAA, speed, WAR families | ... |`) to also name this family:

Find: `| Starter, bullpen, framing, OAA, speed, WAR families | Game-team or game-player feature family |`
Replace with: `| Starter, bullpen, framing, OAA, speed, WAR, team-rate/run-environment families | Game-team or game-player feature family |`

- [ ] **Step 3: `docs/DECISIONS.md`** — append a new ADR after ADR-060, following the exact `## ADR-NNN: Title` / `**Decision:**` / `**Context:**` / `**Rationale:**` / `**Revisit if:**` structure used by every prior entry:

```markdown
## ADR-061: Team prior offense/defense uses public sabermetric formulas, not provider metrics; run environment is derived, not recomputed

**Decision:** `mlb_baseball/model/team_rate.py` adds two independent enrichment steps to `gold.game_feature`: `compute()` reconstructs prior rolling team OBP/SLG/ISO/BB%/K% from `raw.retrosheet_event` (same event_cd mapping as `starter.py`/`offense.py`); `compute_run_environment()` derives prior runs-for/allowed averages purely from columns `features.build()` already sets (`home_wins`/`home_losses`/`home_runs_for`/`home_runs_allowed`), with no new raw dependency.

**Context:** Plan 03G's field census and admission queue (`docs/FEATURE_ADMISSION_QUEUE.md`, OFF-01/02/03/08, DEF-01) identified these as the highest-confidence next feature family: standard, publicly-defined formulas (OBP/SLG/ISO/BB%/K% are universal sabermetric arithmetic, not a provider's proprietary weights — unlike wOBA's FanGraphs-sourced linear weights, ADR-036), strong historical Retrosheet coverage, and a run-environment half that turned out to need no new source at all once `home_runs_for`/`home_wins`/`home_losses` were confirmed already point-in-time-safe sums on the same row.

**Rationale:** PA is defined here as `AB+BB+HBP+SF` (excluding sacrifice bunts and catcher's interference, which `raw.retrosheet_event`'s `ab_fl`/`sf_fl` flags don't separately expose in this codebase) — an honest, documented denominator gap rather than a silent approximation, the same posture `offense.py` already takes for its own wOBA denominator. Deriving runs-for/allowed averages from already-computed columns instead of re-querying `core.game`/`raw.retrosheet_event` avoids a second source of truth for the same underlying counts and keeps the new columns trivially cheap to compute. Neither function is wired into `run()`/`build_feature_stage()`, matching every existing sibling enrichment family (starter, bullpen, park, oaa, speed, framing, war, woba) — live-pipeline wiring remains a separate decision blocked behind Plan 01F's production cutover gate, not something this package should quietly change.

**Revisit if:** a future package needs sacrifice-bunt/catcher's-interference-inclusive PA, or needs these columns inside the `game_base_v1` experiment feature set — both are real, separately-gated follow-ups per `docs/FEATURE_REGISTRY.md`'s "later feature families must be registered separately" rule, not an oversight here.
```

- [ ] **Step 4: `docs/FEATURE_ADMISSION_QUEUE.md`** — in the "Ranked proposals" table, append " — implemented, `team_rate.py` (ADR-061)" to the "Priority / cost" cell of the five rows: `OFF-01`, `OFF-02`, `OFF-03`, `OFF-08`, `DEF-01`. Example for the OFF-01 row:

Find: `| OFF-01 team prior OBP | game-team; \`(H+BB+HBP)/(AB+BB+HBP+SF)\` | Retrosheet/API events before game cutoff | NULL below denominator/min-sample; measure historical eras | no current-game PA; hand fixture and future-event exclusion | now / low |`
Replace the trailing cell `| now / low |` with `| now / low — implemented, \`team_rate.py\` (ADR-061) |`

Do the same targeted edit for the `OFF-02`, `OFF-03`, `OFF-08`, and `DEF-01` rows (their trailing `| now / low |`/`| now / medium |` cells get the same `— implemented, \`team_rate.py\` (ADR-061)` suffix).

- [ ] **Step 5: `plans/03-research-statistics-and-features.md`** — under the `### 03G` section's `**Implemented first slice:**` paragraph, add a new paragraph:

```markdown
**First implemented feature family:** `team_prior_offense_defense_v1`
(`mlb_baseball/model/team_rate.py`, ADR-061) adds prior rolling team
OBP/SLG/ISO/BB%/K% and prior runs-for/allowed averages as
`gold.game_feature` enrichment columns, covering admission-queue items
OFF-01/02/03/08 and DEF-01. Same compatibility-column status as every
existing enrichment family: tested and health-checked in isolation, not
wired into the live pipeline or into `game_base_v1`.
```

- [ ] **Step 6: `plans/PROGRESS.md`** — add a new dated entry under the "Current state summary" heading's existing rehearsal entries (after the "First point-in-time feature rehearsal" section), following the file's established terse evidence-log style:

```markdown
### Team prior offense/defense — YYYY-MM-DD (test database only)

- `team_prior_offense_defense_v1` (`mlb_baseball/model/team_rate.py`, ADR-061)
  adds prior rolling team OBP/SLG/ISO/BB%/K% (admission queue OFF-01/02/03)
  and prior runs-for/allowed averages (OFF-08/DEF-01) as `gold.game_feature`
  enrichment columns. Migration `0050` adds 14 nullable columns.
- Hand-computed fixture tests passed for both the Retrosheet-based rate
  stats and the derived run-environment average; health checks added and
  wired into `mlb doctor` via `model.health_check()`.
- Not wired into `run()`/`build_feature_stage()` or `game_base_v1` — same
  dormant-until-wired status as every existing sibling enrichment family,
  consistent with Plan 01F's production-cutover block.
```

(Replace `YYYY-MM-DD` with the actual date the work lands.)

- [ ] **Step 7: Commit**

```bash
git add docs/FEATURE_REGISTRY.md docs/TABLE_CONTRACTS.md docs/DECISIONS.md docs/FEATURE_ADMISSION_QUEUE.md plans/03-research-statistics-and-features.md plans/PROGRESS.md
git commit -m "Document team_prior_offense_defense_v1 (ADR-061, plan/queue status)"
```

## Task 6: Full verification and final commit

**Files:** none new — this task only runs checks.

- [ ] **Step 1: Ruff**

Run: `uv run ruff format --check . && uv run ruff check .`
Expected: no diffs, no errors. If Ruff reformats anything, `git add` the reformatted files as part of this task's commit.

- [ ] **Step 2: mypy**

Run: `uv run mypy mlb_baseball`
Expected: no errors attributable to `mlb_baseball/model/team_rate.py` or `mlb_baseball/model/__init__.py`.

- [ ] **Step 3: Full test suite**

Run: `TEST_DATABASE_URL=postgresql:///mlb_test uv run pytest -q`
Expected: all tests pass (the pre-existing suite was `714 passed, 0 failures, 1 skipped` before this package; expect `714 + N` passed where `N` is the number of new tests added across Tasks 2-4, 0 failures, 1 skipped).

- [ ] **Step 4: `mlb doctor` sanity check**

Run: `TEST_DATABASE_URL=postgresql:///mlb_test DATABASE_URL=postgresql:///mlb_test uv run mlb doctor`
Expected: the new `home_obp`/`home_slg`/`home_iso`/`home_bb_pct`/`home_k_pct`/`home_runs_for_avg`/`home_runs_allowed_avg plausible range` checks appear in the `model` section output (they may report "no rows" or pass trivially if `gold.game_feature` is empty at doctor-run time — that's expected, not a failure, matching every other enrichment family's health check today).

- [ ] **Step 5: Final review commit (if Step 1 reformatted anything)**

```bash
git add -A
git status  # confirm only expected files changed
git commit -m "Apply ruff formatting for team_prior_offense_defense_v1"
git push
```

If Step 1 made no changes, just run `git push` to publish the commits from Tasks 1-5.

---

## Self-Review Notes (already applied above)

- **Spec coverage:** OFF-01 (OBP) → Task 3; OFF-02 (SLG/ISO) → Task 3; OFF-03 (BB%/K%) → Task 3; OFF-08 (run environment) → Task 2; DEF-01 (run prevention) → Task 2 (same derived UPDATE covers both "runs scored" and "runs allowed" sides). Docs requirement (`docs/FEATURE_REGISTRY.md`, `docs/TABLE_CONTRACTS.md`, ADR, queue status, plan status) → Task 5. Test/health-check requirement from `CLAUDE.md`'s "Definition of done" → Tasks 2-4. Verification-before-completion → Task 6.
- **Type/name consistency checked:** `team_rate.compute`, `team_rate.compute_run_environment`, `team_rate.health_check` are the only three public names, used identically across Tasks 2, 3, 4, and the `model/__init__.py` wiring in Task 4.
- **Deferred on purpose (do not implement here, matching the admission queue's own "later"/"blocked" ratings):** OFF-04 BABIP, OFF-05/06 wOBA-project/wRC-project (wOBA/wRC+ already exist separately, ADR-036/037), DEF-02/03 play-derived defense/OAA, and everything rated `later`/`blocked`/`reject` in `docs/FEATURE_ADMISSION_QUEUE.md`.
