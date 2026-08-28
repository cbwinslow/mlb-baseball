# Bucket B Metrics Wiring — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fold the ~110 "Engine" packages (ADR-089–258) into the project's real feature pipeline — connected to real data, invented composite constants replaced with data-derived or cited values, raw components exposed as model features — without discarding the work.

**Architecture:** Build three pieces of shared infrastructure (a published-constants reference set, a one-time FanGraphs "Guts!" snapshot, a real-percentile helper). Do one triage pass assigning every package `WIRE` / `RELABEL` / `RETIRE`. Build 3 reference implementations end-to-end as templates. Then fan the `WIRE` conversions out to subagents, one package per task, each following a reference PR + the rubric, with Claude/Fable reviewing every diff.

**Tech Stack:** Python 3.11, `uv`, PostgreSQL 16 (`mlb` / `mlb_test`), `psycopg`, `pytest` + `pytest-postgresql`, `playwright` (new, task 2 only), existing `mlb_baseball/model/*.py` + `mlb_baseball/sql/*.sql` + numbered `migrations/` pattern.

**Spec:** `docs/superpowers/specs/2026-08-28-bucket-b-triage-rubric.md`

## Global Constraints

- $0/month budget. No paid API/DB/hosting. New data sources only via a `docs/DATA_SOURCES.md` row added in the same change (spec, "tie-out reference infrastructure").
- Object/schema/table/column names: one word, two at most (`CLAUDE.md` "Naming convention"). Source-faithful raw names (e.g. `raw.fangraphs_guts` columns mirroring FanGraphs' own) are the documented exception.
- Every DB-touching test runs against `mlb_test` only; `tests/conftest.py::_assert_test_database_url` unchanged. Mock the network, never the database (`CLAUDE.md` "Testing").
- Every connector/module exposes `health_check() -> list[Check]` using the shared helpers in `mlb_baseball/health.py` (`CLAUDE.md` "Operational health checks").
- A new CLI subcommand needs a dispatch-level test through `cli.main([...])` and real argparse (`CLAUDE.md`, `tests/unit/test_cli_dispatch.py`).
- Re-running any ingestion/build step is idempotent, proven by a test (`CLAUDE.md` "Definition of done" item 3).
- No provider metric name (wOBA, wRC+, FIP, xwOBA, SIERA…) unless the exact formula and constants match (`docs/FEATURE_ADMISSION_QUEUE.md` "Evidence rules").
- Commit each green step. Branch per task; PR into `main`; never push to `main` directly (`CLAUDE.md` "GitHub workflow").
- `RELABEL` and `RETIRE` outcomes are confirmed with the owner per package before any deletion or downgrade (spec).

---

## File Structure

**New — shared infrastructure:**
- `docs/reference/tango_the_book.md` — transcribed RE24 matrix, base/out run expectancy, linear weights, with page citations.
- `docs/reference/statcast_glossary.md` — VAA/HAA/active-spin/barrel/xStat definitions with Baseball Savant URLs.
- `docs/reference/fangraphs_guts.md` — what the Guts! table is, its columns, the ToS note, refresh procedure.
- `mlb_baseball/connectors/fangraphs.py` — one-time Playwright snapshot of the Guts! table → `raw.fangraphs_guts`. `bootstrap()`/`update()` = the same full reload.
- `migrations/0087_fangraphs_guts.sql` (number TBD at execution — use the next free one) — `raw.fangraphs_guts`.
- `mlb_baseball/model/_distribution.py` — `percentiles(conn, expr, grain, breaks) -> dict` helper.
- `tests/unit/test_distribution.py`, `tests/integration/test_fangraphs.py`, `tests/integration/test_model_distribution.py`.

**New — triage record:**
- `docs/PACKAGE_VALIDATION_STATUS.md` — extended with a per-package outcome table (WIRE/RELABEL/RETIRE + reason).

**Per reference implementation (`poptime`, `vaa`, and — if owner confirms — `lineup_protect`):**
- Modify: `mlb_baseball/model/<name>.py` (add a `compute(conn)` that reads real data; keep or thin the CLI).
- Create: `mlb_baseball/sql/<name>_update.sql`, `mlb_baseball/sql/<name>_health_check.sql`.
- Create: `migrations/00NN_<name>.sql` (gold.game_feature columns).
- Modify: `mlb_baseball/model/__init__.py::enrich_feature_stage` (add the `compute` call in dependency order).
- Modify: `docs/FEATURE_ADMISSION_QUEUE.md` (new row), `docs/FEATURE_REGISTRY.md` (new row), `docs/THEORY_AND_METHODOLOGY.md` (cite each constant), `docs/DECISIONS.md` (new ADR).
- Create: `tests/integration/test_model_<name>.py`.

---

## Task 1: Published-constants reference set

**Files:**
- Create: `docs/reference/tango_the_book.md`
- Create: `docs/reference/statcast_glossary.md`
- Test: none (documentation; the link-check CI job covers dead links)

**Interfaces:**
- Consumes: nothing.
- Produces: two reference docs that `WIRE` conversions cite when replacing invented constants with published values.

- [ ] **Step 1: Create `docs/reference/tango_the_book.md`**

Transcribe from *The Book: Playing the Percentages in Baseball* (Tango/Lichtman/Dolphin, 2006) — the copy the project already cites in `docs/THEORY_AND_METHODOLOGY.md` §141 entry 2:
- The 24-state base/out run-expectancy matrix (1999–2002 values as published).
- The linear weights table (out, BB, HBP, 1B, 2B, 3B, HR, SB, CS).
- Each with the exact page number.

Header must say: "Transcribed reference values for tie-out only. Not a substitute for computing these from our own Retrosheet data (`gold.run_expectancy_24`, ADR-090); use these to *check* our computed values, per `plans/06`."

- [ ] **Step 2: Create `docs/reference/statcast_glossary.md`**

For every Statcast metric an Engine package names (VAA, HAA, active spin %, spin efficiency, barrel, sweet-spot%, hard-hit%, xBA/xSLG/xwOBA, IVB, HB), record: the metric name, Baseball Savant's own definition (quoted, with the `baseballsavant.mlb.com/...` glossary URL), and which `raw.statcast_*` columns supply its inputs.

- [ ] **Step 3: Add both to `docs/MAP.md`**

Under a new "Reference constants" heading, one line each.

- [ ] **Step 4: Commit**

```bash
git add docs/reference/tango_the_book.md docs/reference/statcast_glossary.md docs/MAP.md
git commit -m "docs: published-constants reference set for Bucket B tie-out"
```

---

## Task 2: FanGraphs "Guts!" one-time snapshot connector

**Owner gate:** do not start until the owner has approved the `docs/DATA_SOURCES.md` exception (spec, open question 2).

**Files:**
- Create: `mlb_baseball/connectors/fangraphs.py`
- Create: `migrations/00NN_fangraphs_guts.sql` (next free number)
- Create: `docs/reference/fangraphs_guts.md`
- Modify: `docs/DATA_SOURCES.md` (new row), `mlb_baseball/registry.py` (register connector), `docs/SOURCE_RIGHTS.md` (profile)
- Test: `tests/integration/test_fangraphs.py`
- Modify: `pyproject.toml` (add `playwright` to an `[project.optional-dependencies]` group — it is not a runtime dep of the pipeline)

**Interfaces:**
- Consumes: nothing.
- Produces: `raw.fangraphs_guts` — one row per season, columns `season INT`, `woba`, `woba_scale`, `wbb`, `whbp`, `w1b`, `w2b`, `w3b`, `whr`, `runsb`, `runcs`, `lg_r_pa`, `lg_r_w`, `cfip` (names mirror FanGraphs' own Guts! column labels, snake_cased — the documented raw-layer exception to the one-word rule).
- `fangraphs.bootstrap(conn) -> dict[str,int]` and `fangraphs.update(conn) -> dict[str,int]` — identical (full reload; the table is small and rarely changes).

- [ ] **Step 1: Write the failing integration test**

```python
# tests/integration/test_fangraphs.py
import pytest
from mlb_baseball.connectors import fangraphs

FIXTURE_HTML = """<table><thead><tr><th>Season</th><th>wOBA</th><th>wOBAScale</th>
<th>wBB</th><th>wHBP</th><th>w1B</th><th>w2B</th><th>w3B</th><th>wHR</th>
<th>runSB</th><th>runCS</th><th>R/PA</th><th>R/W</th><th>cFIP</th></tr></thead>
<tbody><tr><td>2023</td><td>.318</td><td>1.204</td><td>.696</td><td>.726</td>
<td>.883</td><td>1.244</td><td>1.569</td><td>2.004</td><td>.200</td><td>-.390</td>
<td>.118</td><td>9.65</td><td>3.185</td></tr></tbody></table>"""

def test_bootstrap_lands_one_row_per_season(db_conn, monkeypatch):
    monkeypatch.setattr(fangraphs, "_fetch_guts_html", lambda: FIXTURE_HTML)
    counts = fangraphs.bootstrap(db_conn)
    db_conn.commit()
    assert counts["raw.fangraphs_guts"] == 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT season, woba, whr FROM raw.fangraphs_guts WHERE season = 2023")
        assert cur.fetchone() == (2023, 0.318, 2.004)

def test_rerunning_truncates_instead_of_duplicating(db_conn, monkeypatch):
    monkeypatch.setattr(fangraphs, "_fetch_guts_html", lambda: FIXTURE_HTML)
    fangraphs.bootstrap(db_conn); db_conn.commit()
    fangraphs.bootstrap(db_conn); db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.fangraphs_guts")
        assert cur.fetchone()[0] == 1
```

- [ ] **Step 2: Run it, verify it fails**

Run: `uv run pytest tests/integration/test_fangraphs.py -v`
Expected: FAIL — `ModuleNotFoundError: mlb_baseball.connectors.fangraphs`.

- [ ] **Step 3: Write the migration**

`migrations/00NN_fangraphs_guts.sql`: `CREATE TABLE raw.fangraphs_guts (season integer primary key, woba double precision, woba_scale double precision, wbb double precision, whbp double precision, w1b double precision, w2b double precision, w3b double precision, whr double precision, runsb double precision, runcs double precision, lg_r_pa double precision, lg_r_w double precision, cfip double precision, _loaded_at timestamptz not null default now());` — follow the exact header-comment style of the most recent existing migration.

- [ ] **Step 4: Write `mlb_baseball/connectors/fangraphs.py`**

- `_fetch_guts_html()` — uses Playwright headless Chromium to load `https://www.fangraphs.com/guts.aspx?type=cn`, waits for the results table, returns `page.content()`. Wrapped so the whole function is what the test monkeypatches.
- `_parse_guts(html) -> list[dict]` — pure function, `pandas.read_html` or manual parse, one dict per season row, keys = the `raw.fangraphs_guts` column names.
- `bootstrap(conn)` / `update(conn)` — `_fetch_guts_html()` → `_parse_guts` → `TRUNCATE raw.fangraphs_guts` → `load_dataframe(...)` (use the existing helper, see `mlb_baseball/load.py`) → return `{"raw.fangraphs_guts": n}`. Explicit error on an empty/malformed parse (never silent).
- `health_check()` — `check_table_has_rows("raw.fangraphs_guts")` + a check that the current season is present.

- [ ] **Step 5: Run the tests, verify they pass**

Run: `uv run pytest tests/integration/test_fangraphs.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Register + document**

- `mlb_baseball/registry.py`: add `fangraphs` to `CONNECTORS`.
- `docs/DATA_SOURCES.md`: new row — Source "FanGraphs Guts! (one-time reference snapshot)", Provides "yearly wOBA/FIP constants & event run values", Cost "Free", Access "one-time Playwright snapshot of `guts.aspx`, not an ongoing scrape", Notes: ToS-sensitive, reference constants only, `local_research` profile, never re-scraped on a cron.
- `docs/SOURCE_RIGHTS.md`: `fangraphs` → `local_research`.
- `docs/reference/fangraphs_guts.md`: what it is, the column list, refresh = "run `mlb ingest fangraphs --mode bootstrap` manually, once a season".

- [ ] **Step 7: CLI dispatch test + run full connector suite**

Add `tests/unit/test_cli_dispatch.py` case: `mlb ingest fangraphs --mode bootstrap` reaches `fangraphs.bootstrap`. Run `uv run pytest tests/unit/test_cli_dispatch.py tests/integration/test_fangraphs.py -q`.

- [ ] **Step 8: Commit**

```bash
git add mlb_baseball/connectors/fangraphs.py migrations/ docs/ tests/ pyproject.toml mlb_baseball/registry.py
git commit -m "feat(fangraphs): one-time Guts! reference-constant snapshot connector"
```

---

## Task 3: Real-percentile helper

**Files:**
- Create: `mlb_baseball/model/_distribution.py`
- Test: `tests/unit/test_distribution.py`, `tests/integration/test_model_distribution.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `percentiles(conn, *, table: str, expr: str, where: str | None, breaks: tuple[float, ...]) -> dict[float, float]` — returns `{break: value}` computed with `percentile_cont` over `expr` from `table` (optionally filtered by `where`). Raises `ValueError` on an empty result or a break outside `(0, 1)`.

- [ ] **Step 1: Write the failing unit test (input validation only — no DB)**

```python
# tests/unit/test_distribution.py
import pytest
from mlb_baseball.model._distribution import percentiles

class _FakeConn:
    def cursor(self): raise AssertionError("should not reach the DB")

def test_rejects_break_out_of_range():
    with pytest.raises(ValueError, match="between 0 and 1"):
        percentiles(_FakeConn(), table="raw.x", expr="v", where=None, breaks=(0.5, 1.5))
```

- [ ] **Step 2: Run it, verify it fails**

Run: `uv run pytest tests/unit/test_distribution.py -v` → FAIL (module missing).

- [ ] **Step 3: Write `_distribution.py`**

```python
"""Real percentile breakpoints from our own data, so a metric tier
('elite = p90') is computed, not guessed (Bucket B rubric, WIRE)."""
from __future__ import annotations
import psycopg
from psycopg import sql

def percentiles(conn: psycopg.Connection, *, table: str, expr: str,
                where: str | None, breaks: tuple[float, ...]) -> dict[float, float]:
    for b in breaks:
        if not 0.0 < b < 1.0:
            raise ValueError(f"percentile break must be between 0 and 1, got {b}")
    arr = "ARRAY[" + ", ".join(str(b) for b in breaks) + "]"
    q = f"SELECT percentile_cont({arr}) WITHIN GROUP (ORDER BY ({expr})) FROM {table}"
    if where:
        q += f" WHERE {where}"
    with conn.cursor() as cur:
        cur.execute(q)
        row = cur.fetchone()
    if row is None or row[0] is None:
        raise ValueError(f"no rows for percentile query over {table}")
    return dict(zip(breaks, row[0]))
```

Note: `expr`/`table`/`where` are trusted internal strings (metric definitions written by us, never user input) — same convention as `mlb_baseball/model/leverage_index.py`'s `SET LOCAL` statements.

- [ ] **Step 4: Run the unit test, verify it passes**

Run: `uv run pytest tests/unit/test_distribution.py -v` → PASS.

- [ ] **Step 5: Write + run the integration test**

```python
# tests/integration/test_model_distribution.py
from mlb_baseball.model._distribution import percentiles

def test_percentiles_over_a_real_table(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("CREATE TEMP TABLE t (v double precision)")
        cur.executemany("INSERT INTO t VALUES (%s)", [(float(i),) for i in range(1, 101)])
    got = percentiles(db_conn, table="t", expr="v", where=None, breaks=(0.1, 0.5, 0.9))
    assert round(got[0.5]) == 50
    assert got[0.1] < got[0.9]
```

Run: `uv run pytest tests/integration/test_model_distribution.py -v` → PASS.

- [ ] **Step 6: Commit**

```bash
git add mlb_baseball/model/_distribution.py tests/unit/test_distribution.py tests/integration/test_model_distribution.py
git commit -m "feat(model): real-percentile helper for data-derived metric tiers"
```

---

## Task 4: Triage pass — assign every Engine package an outcome

**Files:**
- Modify: `docs/PACKAGE_VALIDATION_STATUS.md`
- Test: none (judgment deliverable; the outcome table is the artifact)

**Interfaces:**
- Consumes: the rubric (spec), `docs/THEORY_AND_METHODOLOGY.md` §75–141, `docs/DECISIONS.md` ADR-089–258, `docs/reference/agy/`.
- Produces: a complete outcome table — every ADR-089–258 package assigned `WIRE` / `RELABEL` / `RETIRE` with a one-line reason and, for WIRE, the named real metric + its `raw.*` input columns.

- [ ] **Step 1: Enumerate the packages**

`grep -n "^## ADR-0(89|9[0-9])\|^## ADR-[12][0-9][0-9]" docs/DECISIONS.md` — list every ADR 089–258 with its package name and `mlb_baseball/model/<file>.py`.

- [ ] **Step 2: For each package, record four facts**

Read its module + `tests/unit/test_<name>.py` + its ADR + its `THEORY_AND_METHODOLOGY.md` section. Record: (a) the named real metric(s) it's built on; (b) whether a governed feature already produces it (`grep` `FEATURE_REGISTRY.md` / `FEATURE_ADMISSION_QUEUE.md`); (c) whether its inputs exist in `raw.*` (cross-check `docs/DATA_SOURCES.md` + `mlb field-census`); (d) whether its premise is one this project's own docs flag as unreliable (`clutch`, `lineup_protect`, and search `RESEARCH.md` / `FEATURE_ADMISSION_QUEUE.md` for others).

- [ ] **Step 3: Assign the outcome using the rubric**

Default `WIRE`. `RELABEL` only for (d)-positive premises. `RETIRE` only for a genuine exact duplicate of a governed feature at the same grain, or a demonstrably wrong formula. Write each into a new `## Outcome table` section of `PACKAGE_VALIDATION_STATUS.md`: `| package | ADR | outcome | reason | real metric → raw inputs (WIRE only) |`.

- [ ] **Step 4: Produce the owner-confirmation list**

At the top of that section, list every `RELABEL` and `RETIRE` with its reason, as an explicit "owner confirm before acting" checklist.

- [ ] **Step 5: Commit**

```bash
git add docs/PACKAGE_VALIDATION_STATUS.md
git commit -m "docs: Bucket B triage — per-package WIRE/RELABEL/RETIRE outcomes"
```

- [ ] **Step 6: Stop for owner review**

Do not start any conversion until the owner has reviewed the outcome table and confirmed the RELABEL/RETIRE list.

---

## Task 5: Reference implementation — `poptime` (WIRE, metric + calibrated tiers)

**Files:**
- Modify: `mlb_baseball/model/poptime.py`
- Create: `mlb_baseball/sql/poptime_update.sql`, `mlb_baseball/sql/poptime_health_check.sql`
- Create: `migrations/00NN_poptime.sql`
- Modify: `mlb_baseball/model/__init__.py` (`enrich_feature_stage`), `mlb_baseball/model/__init__.py::health_check`
- Modify: `docs/FEATURE_ADMISSION_QUEUE.md`, `docs/FEATURE_REGISTRY.md`, `docs/THEORY_AND_METHODOLOGY.md` (§ for pop time), `docs/DECISIONS.md`
- Test: `tests/integration/test_model_poptime.py`

**Interfaces:**
- Consumes: `_distribution.percentiles` (Task 3); `raw.statcast_poptime` (per-catcher-season `pop_time_2b_sba_count`, `pop_time_2b_avg`, `arm_strength` — verify exact column names against the table).
- Produces: `poptime.compute(conn) -> int` (rows updated); `gold.game_feature` columns `home_catcher_pop_time_s`, `away_catcher_pop_time_s`, `home_catcher_pop_time_tier`, `away_catcher_pop_time_tier` (raw seconds + a data-derived tier). The catcher for a game is the team's primary catcher entering that game (most starts in prior completed games of that season).

- [ ] **Step 1: Confirm the real distribution**

Against `mlb_test` (or `mlb`, read-only): `SELECT percentile_cont(ARRAY[0.1,0.5,0.9]) WITHIN GROUP (ORDER BY pop_time_2b_avg) FROM raw.statcast_poptime WHERE pop_time_2b_sba_count >= 20;`. Record the three values — these become the `ELITE` / `AVERAGE` / `SLOW` tier cutoffs (replacing `poptime.py`'s current hand-typed `1.89` / `2.06`). Put them in the ADR with the query.

- [ ] **Step 2: Write the failing integration test**

```python
# tests/integration/test_model_poptime.py
from mlb_baseball.model import poptime

def test_compute_populates_pop_time_from_prior_season_leaderboard(db_conn):
    # Fixture: 1 catcher-season in raw.statcast_poptime (pop 1.90, elite),
    # a core.player + core.game where that catcher started the prior game,
    # a gold.game_feature row for the current game.
    ...  # build the fixture the same way tests/integration/test_model_framing.py does
    updated = poptime.compute(db_conn)
    db_conn.commit()
    assert updated >= 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT home_catcher_pop_time_s, home_catcher_pop_time_tier "
                    "FROM gold.game_feature WHERE game_id = %s", (current_game_id,))
        pop, tier = cur.fetchone()
    assert pop == 1.90
    assert tier == "ELITE"

def test_compute_is_idempotent(db_conn):
    ...  # run compute twice, assert identical values and same updated count on the 2nd pass being 0 or equal

def test_compute_no_ops_when_leaderboard_missing(db_conn):
    ...  # drop/rename raw.statcast_poptime, assert compute returns 0, not a crash
```

- [ ] **Step 3: Run it, verify it fails**

Run: `uv run pytest tests/integration/test_model_poptime.py -v` → FAIL (`poptime.compute` missing).

- [ ] **Step 4: Write `migrations/00NN_poptime.sql`**

`ALTER TABLE gold.game_feature ADD COLUMN home_catcher_pop_time_s double precision, ADD COLUMN away_catcher_pop_time_s double precision, ADD COLUMN home_catcher_pop_time_tier text, ADD COLUMN away_catcher_pop_time_tier text;` — with a header comment matching the newest existing migration.

- [ ] **Step 5: Write `mlb_baseball/sql/poptime_update.sql`**

Point-in-time UPDATE against `gold.game_feature`: resolve each game's home/away primary catcher from prior completed games that season (same "prior completed events, ordered by date/game_number/id" pattern as `mlb_baseball/sql/pitcher_command_update.sql`), join `raw.statcast_poptime` on the **prior** season (one-season lag, same treatment as `war.py` / `oaa.py`), set the raw seconds. The tier is set from the constants recorded in Step 1 as a CASE expression (values inlined by the migration/ADR, not recomputed per run).

- [ ] **Step 6: Write `poptime.compute(conn)` + `poptime_health_check.sql`**

`compute` = `to_regclass` gate on `raw.statcast_poptime` (return 0 if absent) → `cur.execute(read_sql("poptime_update.sql"))` → `return cur.rowcount`. Same shape as `mlb_baseball/model/command.py`. Keep the existing `CatcherPopTimeEngine` CLI class but have `evaluate_pop_time` use the Step-1 constants; delete the invented `csaa_runs` composite and its tier logic that isn't backed by the real distribution, or mark it display-only per the rubric.

- [ ] **Step 7: Wire into `enrich_feature_stage` + `health_check`**

Add `"gold.game_feature (poptime)": poptime.compute(conn),` after `framing` (same data family) in `mlb_baseball/model/__init__.py`. Add `poptime.health_check()` to `model.health_check()`'s list.

- [ ] **Step 8: Run the tests, verify they pass**

Run: `uv run pytest tests/integration/test_model_poptime.py tests/integration/test_model_enrich_stage.py -v` → PASS.

- [ ] **Step 9: Docs**

- `FEATURE_ADMISSION_QUEUE.md`: new row `DEF-04 catcher pop time` — grain, formula (raw Savant value + lagged), null policy (NULL below `pop_time_2b_sba_count` minimum / no prior catcher), tests, source profile `local_research`.
- `FEATURE_REGISTRY.md`: new `catcher_poptime_v1` row with lineage.
- `THEORY_AND_METHODOLOGY.md`: update the pop-time section — cite Baseball Savant's definition; state the tier cutoffs are "our data p10/p50/p90, computed <date>, query in ADR".
- `DECISIONS.md`: new ADR — decision, the Step-1 query + values, what changed from the invented version.

- [ ] **Step 10: Lint + full check + commit**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run sqlfluff lint mlb_baseball/sql/poptime_update.sql`. Then:

```bash
git add -A
git commit -m "feat(poptime): wire catcher pop time to real Savant data + data-derived tiers (WIRE reference)"
```

---

## Task 6: Reference implementation — `vaa` (WIRE, expose the real metric, retire the invented index)

**Files:**
- Modify: `mlb_baseball/model/vaa.py`
- Create: `mlb_baseball/sql/vaa_update.sql`, `mlb_baseball/sql/vaa_health_check.sql`
- Create: `migrations/00NN_vaa.sql`
- Modify: `mlb_baseball/model/__init__.py`
- Modify: `docs/FEATURE_ADMISSION_QUEUE.md`, `docs/FEATURE_REGISTRY.md`, `docs/THEORY_AND_METHODOLOGY.md`, `docs/DECISIONS.md`
- Test: `tests/integration/test_model_vaa.py`

**Interfaces:**
- Consumes: `raw.statcast_pitch` (`vy0`, `vz0`, `ay`, `az`, `plate_z`, `release_pos_y`, `pitch_type` — verify names). VAA at the plate = `-atan( (vz0 + az * t_plate) / (vy0 + ay * t_plate) ) * 180/pi` where `t_plate` solves the y-equation to the front of the plate (17/12 ft from the tip). Cite `docs/reference/statcast_glossary.md` + Alan Nathan (THEORY §141 entry 6).
- Produces: `vaa.compute(conn) -> int`; `gold.game_feature` columns `home_starter_ff_vaa`, `away_starter_ff_vaa` (four-seam VAA, rolling prior-appearances mean at pitcher grain — the flat-fastball concept). No invented composite; the raw degrees are the feature.

- [ ] **Step 1: Verify the geometry against one known pitch**

Pick a real 2024 four-seam fastball from `raw.statcast_pitch` with a Savant-published VAA (spot-check via the Savant pitch page). Compute VAA with the formula above in a scratch query; confirm it matches to ~0.1°. Put the check in the ADR.

- [ ] **Step 2: Write the failing integration test**

```python
# tests/integration/test_model_vaa.py
from mlb_baseball.model import vaa

def test_compute_populates_starter_four_seam_vaa(db_conn):
    # Fixture: raw.statcast_pitch rows for one pitcher across 2 prior games
    # (known vy0/vz0/ay/az), a gold.game_feature row for a 3rd game.
    ...
    updated = vaa.compute(db_conn); db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute("SELECT home_starter_ff_vaa FROM gold.game_feature WHERE game_id = %s", (g3,))
        (v,) = cur.fetchone()
    assert -6.5 < v < -3.5   # realistic four-seam VAA range
```

Plus idempotency + missing-table no-op tests (same shape as Task 5).

- [ ] **Step 3: Run it → FAIL. Steps 4–8 mirror Task 5** (migration → `vaa_update.sql` with the geometry as a subquery computing `t_plate` then VAA, prior-appearances rolling mean → `vaa.compute` gate+exec+rowcount → wire after `pitch_movement` in `enrich_feature_stage` → run tests).

- [ ] **Step 9: Retire the invented index**

Delete `vaa.py`'s `ApproachAngleEngine` composite/tier scoring (the part with no published basis). Keep a thin `mlb vaa` CLI that reports the raw computed VAA for given inputs, or delete the subcommand + its dispatch test if it adds nothing. Mark the old ADR section **Superseded by** the new one.

- [ ] **Step 10: Docs + lint + commit** (same as Task 5 Steps 9–10; ADR notes the retired composite).

---

## Task 7: Reference implementation — `lineup_protect` (RELABEL) — CONDITIONAL

**Only if** the owner confirmed in Task 4 that `lineup_protect`'s premise is RELABEL.

**Files:**
- Modify: `mlb_baseball/model/lineup_protect.py` (docstring only), `docs/DECISIONS.md` (ADR-255 rewrite), `tests/unit/test_lineup_protect.py` (assert internal consistency only, with a comment)
- Test: `tests/unit/test_lineup_protect.py`

- [ ] **Step 1: Rewrite the module docstring**

Replace with: `"""Lineup protection exploratory calculator (LINEUP-PROTECT-01, ADR-255). PREMISE UNVALIDATED: Tango/Lichtman/Dolphin, *The Book*, find no reliably measurable "protection" effect (see docs/FEATURE_ADMISSION_QUEUE.md CTX-06, docs/RESEARCH.md). This computes an invented index from hand-entered inputs. NOT a model feature, NOT a gold column, NOT fit for the public site as fact — kept as a documented exploratory tool only."""`

- [ ] **Step 2: Rewrite ADR-255**

Add a `**Status: Relabeled exploratory (2026-08-28)**` block: why (cited research), what that means (no gold column, no FEATURE_COLUMNS), owner confirmed on `<date>`.

- [ ] **Step 3: Update the unit test**

Keep the tests, add a module docstring: `"""Internal-consistency tests only — lineup_protect is a relabeled exploratory calculator (ADR-255), not a validated metric. These assert the arithmetic is stable, not that the output means anything."""`

- [ ] **Step 4: Run + commit**

```bash
uv run pytest tests/unit/test_lineup_protect.py -q
git add -A && git commit -m "docs(lineup_protect): relabel as exploratory — premise contradicted by cited research (ADR-255)"
```

---

## Task 8: Fan-out kickoff — subagent prompt template + review protocol

**Files:**
- Create: `docs/superpowers/plans/2026-08-28-bucket-b-fanout-protocol.md`

**Interfaces:**
- Consumes: Tasks 1–7 (infra + the outcome table + the reference PRs).
- Produces: a reusable per-package subagent brief and the two-stage review checklist.

- [ ] **Step 1: Write the per-package brief template**

A fill-in-the-blanks prompt: package name, ADR, its outcome-table row, the matching reference PR number (Task 5 for metric+tier, Task 6 for metric-only, Task 7 for RELABEL), the named real metric + raw inputs, and the fixed instructions (quote the rubric, own worktree + own `mlb_test`, TDD, don't commit to main, return changed files + commands + limitations + next gate, don't start the next package).

- [ ] **Step 2: Write the review checklist**

Stage 1 (Claude, on the diff): admission-queue row present and complete; no invented constant survives uncited; raw component is the feature, not the composite; migration + registry + THEORY updated together; integration test has a hand-calculated fixture + idempotency + missing-table gate. Stage 2 (re-run): `uv run pytest tests/integration/test_model_<name>.py` + `uv run ruff check . && uv run mypy` from a clean checkout of the branch — a subagent's own green report is not accepted on its own (`CLAUDE.md`).

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/plans/2026-08-28-bucket-b-fanout-protocol.md
git commit -m "docs: Bucket B fan-out protocol — per-package subagent brief + review checklist"
```

---

## Self-Review

**Spec coverage:**
- Rubric's WIRE / RELABEL / RETIRE → Task 4 assigns them; Tasks 5–7 are one reference per outcome. ✓
- Tie-out reference infra (Tango tables, FanGraphs Guts, percentile helper) → Tasks 1–3. ✓
- Fan-out plan (triage → reference impls → delegated) → Tasks 4–8. ✓
- "RELABEL/RETIRE owner-confirmed per package" → Task 4 Step 4/6 + Task 7 gate. ✓
- GBM-v2 → out of scope for this plan (its own Plan 04 gate); noted in the spec, not a task here.

**Placeholder scan:** Task 5/6 test bodies use `...` for fixture construction with an explicit "build it the same way `tests/integration/test_model_<x>.py` does" pointer — acceptable because the fixture pattern is established and copying a 60-line fixture verbatim into the plan is the anti-pattern the skill's "repeat the code" rule is balanced against; the *behavioral assertions* are concrete. Data-derived constants (Task 5 Step 1, Task 6 Step 1) are "run this query, use the result" — a real instruction, not a TBD. Migration numbers are "next free number" because the free number changes as other PRs merge.

**Type consistency:** `percentiles(conn, *, table, expr, where, breaks) -> dict[float, float]` — defined Task 3, consumed Task 5. `compute(conn) -> int` — consistent across Tasks 5–6 and matches every existing `model/*.py::compute`. `raw.fangraphs_guts` column names consistent between Task 2 migration and test.

---

## Execution Handoff

Save location: `docs/superpowers/plans/2026-08-28-bucket-b-metrics-wiring.md` (this file).
