# `core.market.observed_at` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Kalshi/Polymarket comparison lines in `gold.prediction` a
truthful pre-game `generated_at` so model-vs-market holdout evaluation works.

**Architecture:** A new nullable `core.market.observed_at` column records the
`captured_at` of the market snapshot that `implied_probability` was resolved
from. `conform.py` populates it (new `_latest_entry_before` helper returns the
whole `(timestamp, value)` entry instead of just the value). The two market
prediction-insert SQL files stamp `generated_at = m.observed_at` instead of
letting it default to `now()`. A one-time repair script deletes the ~540
already-broken production rows so the idempotency guard re-inserts them
correctly.

**Tech Stack:** Python 3.12, psycopg 3, PostgreSQL 16, pytest (real
`mlb_test` Postgres for integration), uv, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-08-31-market-observed-at-design.md`

## Global Constraints

- Numbered migrations in `migrations/` are **DDL only** — no INSERT/UPDATE/DELETE
  (`docs/PRODUCT_DIRECTION.md`). Data repair goes in `scripts/`.
- Names we choose ourselves are one word, two at most (`docs/CLAUDE.md` naming
  convention). `observed_at` is acceptable (two words, mirrors the existing
  `_conformed_at`).
- Any schema change is reflected in the docs **in the same change**, not a
  follow-up (`docs/CLAUDE.md` "Definition of done" item 5).
- Integration tests mock the **network** (fixture rows), never Postgres — run
  against the real dedicated `mlb_test` database (`docs/CLAUDE.md` "Testing").
- Every connector/pipeline change keeps re-runs **idempotent** — running it
  twice does not duplicate or corrupt data, proven by a test.
- `uv run ruff check .`, `uv run ruff format --check .`, and `uv run mypy` must
  all pass clean before a task is done.
- `_record_upcoming` (the live/upcoming market path in `market.py`) and the
  *value* semantics of `implied_probability` do **not** change.
- Work happens in worktree `.claude/worktrees/market-observed-at`, branch
  `fix/market-observed-at` (already created off `origin/main`).

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `mlb_baseball/conform.py` | Builds `core.*` from `raw.*`; owns the market snapshot-resolution helpers | Add `_latest_entry_before`; `_latest_before` becomes a wrapper; market-row builders + `_build_market` INSERT carry `observed_at` |
| `migrations/0093_market_observed_at.sql` | DDL for the new column | **new** |
| `mlb_baseball/sql/market_kalshi_prediction_insert.sql` | Decided-game Kalshi comparison line | Add `generated_at` column, select `m.observed_at`, require it non-NULL |
| `mlb_baseball/sql/market_polymarket_prediction_insert.sql` | Decided-game Polymarket comparison line | Same |
| `scripts/repair_market_prediction_times.sql` | One-time owner-run prod cleanup of the stale rows | **new** |
| `tests/unit/test_market_pregame_snapshot.py` | Pure bisect helper coverage | Add `_latest_entry_before` cases |
| `tests/integration/test_conform.py` | `_build_market` end-to-end coverage | Assert `observed_at` populated + pre-game + NULL when no snapshot |
| `tests/integration/test_model_market.py` | `market.record()` regression coverage | `_seed_market_row` seeds `observed_at`; assert `generated_at`; add `_selected_predictions` regression test |
| `tests/integration/test_repair_market_times.py` | Repair-script predicate coverage | **new** |
| `docs/DECISIONS.md` | ADR log | New ADR (next free number), newest first |
| `docs/DATA_DICTIONARY.md`, `docs/TABLE_CONTRACTS.md` | `core.market` column list | Add `observed_at` |
| `docs/ROADMAP.md` | Phase 2 market-comparison status | "blocked" → "unblocked" |

---

### Task 1: `_latest_entry_before` helper

**Files:**
- Modify: `mlb_baseball/conform.py` (the `_latest_before` function, currently at
  `mlb_baseball/conform.py:1238`)
- Test: `tests/unit/test_market_pregame_snapshot.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `conform._latest_entry_before(entries: list[tuple[datetime, Decimal]], cutoff: datetime) -> tuple[datetime, Decimal] | None`
    — the whole most-recent entry strictly before `cutoff`, else `None`.
  - `conform._latest_before(entries, cutoff) -> Decimal | None` — unchanged
    behaviour, now implemented as `_latest_entry_before(...)[1]`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_market_pregame_snapshot.py` (keep the existing
`_latest_before` tests untouched; add the import):

```python
from mlb_baseball.conform import _latest_before, _latest_entry_before


def test_latest_entry_before_returns_timestamp_and_value_of_the_qualifying_entry():
    entries = [
        (datetime(2026, 8, 1, 6, 0), Decimal("0.55")),
        (datetime(2026, 8, 2, 6, 0), Decimal("0.60")),
        (datetime(2026, 8, 3, 6, 0), Decimal("0.99")),
    ]
    assert _latest_entry_before(entries, datetime(2026, 8, 2, 19, 5)) == (
        datetime(2026, 8, 2, 6, 0),
        Decimal("0.60"),
    )


def test_latest_entry_before_excludes_a_snapshot_exactly_at_cutoff():
    entries = [(datetime(2026, 8, 2, 19, 5), Decimal("0.60"))]
    assert _latest_entry_before(entries, datetime(2026, 8, 2, 19, 5)) is None


def test_latest_entry_before_returns_none_for_empty_and_for_all_after_cutoff():
    assert _latest_entry_before([], datetime(2026, 8, 2, 19, 5)) is None
    later = [(datetime(2026, 8, 3, 6, 0), Decimal("0.99"))]
    assert _latest_entry_before(later, datetime(2026, 8, 2, 19, 5)) is None


def test_latest_before_still_returns_just_the_value():
    entries = [
        (datetime(2026, 8, 2, 6, 0), Decimal("0.55")),
        (datetime(2026, 8, 2, 12, 0), Decimal("0.58")),
    ]
    assert _latest_before(entries, datetime(2026, 8, 2, 19, 5)) == Decimal("0.58")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_market_pregame_snapshot.py -v`
Expected: the four new tests FAIL with `ImportError: cannot import name '_latest_entry_before'`; the five existing tests still PASS.

- [ ] **Step 3: Implement the helper**

In `mlb_baseball/conform.py`, replace the existing `_latest_before` function
(the one with the `bisect_left` body and the docstring beginning "entries must
be sorted ascending by timestamp") with:

```python
def _latest_entry_before(
    entries: list[tuple[datetime, Decimal]], cutoff: datetime
) -> tuple[datetime, Decimal] | None:
    """The whole (captured_at, value) entry strictly before ``cutoff``, or
    None. ``entries`` must be sorted ascending by timestamp (both snapshot
    lookups below build them via ORDER BY captured_at). bisect_left finds the
    first entry NOT strictly before cutoff; the qualifying entry, if any, is
    immediately before that index."""
    idx = bisect_left(entries, (cutoff, Decimal(0))) if entries else 0
    if idx == 0:
        return None
    return entries[idx - 1]


def _latest_before(
    entries: list[tuple[datetime, Decimal]], cutoff: datetime
) -> Decimal | None:
    """The value of the most recent snapshot strictly before ``cutoff``, or
    None. Thin wrapper over :func:`_latest_entry_before` for callers that only
    need the price (``market.py``'s ``_record_upcoming`` path)."""
    entry = _latest_entry_before(entries, cutoff)
    return entry[1] if entry is not None else None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_market_pregame_snapshot.py -v`
Expected: all nine tests PASS.

- [ ] **Step 5: Lint + type-check**

Run: `uv run ruff check mlb_baseball/conform.py tests/unit/test_market_pregame_snapshot.py && uv run ruff format --check mlb_baseball/conform.py tests/unit/test_market_pregame_snapshot.py && uv run mypy mlb_baseball/conform.py`
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add mlb_baseball/conform.py tests/unit/test_market_pregame_snapshot.py
git commit -m "refactor(conform): _latest_entry_before returns the whole snapshot entry

Pre-work for issue #107: the market prediction lines need the captured_at
of the resolved pre-game snapshot, not just its price. _latest_before is
now a thin wrapper; its behaviour and callers are unchanged."
```

---

### Task 2: migration + `conform` writes `observed_at`

**Files:**
- Create: `migrations/0093_market_observed_at.sql`
- Modify: `mlb_baseball/conform.py` — `_polymarket_market_rows`
  (`mlb_baseball/conform.py:1285`), `_kalshi_market_rows`
  (`mlb_baseball/conform.py:1365`), `_build_market`'s `INSERT INTO core.market`
  (near `mlb_baseball/conform.py:1460`)
- Modify: `docs/DATA_DICTIONARY.md`, `docs/TABLE_CONTRACTS.md`
- Test: `tests/integration/test_conform.py`

**Interfaces:**
- Consumes: `conform._latest_entry_before` from Task 1.
- Produces:
  - `core.market.observed_at timestamptz` — nullable; set iff
    `implied_probability` is set; equals the resolving snapshot's `captured_at`.
  - `_polymarket_market_rows` / `_kalshi_market_rows` now return 8-tuples:
    `(game_id, source, market_ref, team_id, implied_probability, observed_at, volume, status)`.

- [ ] **Step 1: Write the migration**

Create `migrations/0093_market_observed_at.sql`:

```sql
-- core.market.observed_at: the captured_at of the raw snapshot that
-- implied_probability was resolved from (issue #107). Lets
-- market_*_prediction_insert.sql stamp a truthful pre-game generated_at on
-- the kalshi-v1 / polymarket-v1 comparison lines instead of defaulting to
-- now() (which, running post-game, made every decided-game row fail the
-- evaluation's `generated_at < game_start` filter). NULL exactly when
-- implied_probability is NULL.
ALTER TABLE core.market ADD COLUMN IF NOT EXISTS observed_at timestamptz;
```

- [ ] **Step 2: Apply it to the test database and confirm the column exists**

Run:
```bash
TEST_DATABASE_URL=postgresql:///mlb_test uv run mlb migrate
psql "postgresql:///mlb_test" -c "\d core.market"
```
Expected: `observed_at | timestamp with time zone` appears in the column list.
Re-running `mlb migrate` is a no-op (`ADD COLUMN IF NOT EXISTS`).

Note: the integration suite's `tests/conftest.py` calls `migrate.run()` when it
builds each run's schema, so the later integration test steps pick the column
up automatically — this manual apply is just to eyeball the migration.

- [ ] **Step 3: Write the failing test**

In `tests/integration/test_conform.py`, add after
`test_build_market_matches_polymarket_and_kalshi_to_a_core_game`:

```python
def test_build_market_records_the_resolving_snapshot_capture_time(db_conn):
    _seed_market_game(db_conn)

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT m.source, t.retro_team_id, m.implied_probability, m.observed_at "
            "FROM core.market m JOIN core.team t ON t.id = m.team_id "
            "WHERE m.game_id IS NOT NULL ORDER BY m.source, t.retro_team_id"
        )
        rows = cur.fetchall()

    pre_game = datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc)
    first_pitch = datetime(2026, 5, 23, 23, 5, tzinfo=timezone.utc)
    for source, team, implied, observed in rows:
        assert implied is not None, (source, team)
        assert observed == pre_game, (source, team, observed)
        assert observed < first_pitch

    _drop_market_fixtures(db_conn)


def test_build_market_leaves_observed_at_null_when_no_pre_game_snapshot(db_conn):
    _seed_market_game(db_conn)
    with db_conn.cursor() as cur:
        # Push every snapshot to after first pitch — nothing qualifies.
        cur.execute(
            "UPDATE raw.polymarket_snapshot SET captured_at = '2026-05-24T06:00:00+00:00'"
        )
        cur.execute(
            "UPDATE raw.kalshi_snapshot SET captured_at = '2026-05-24T06:00:00+00:00'"
        )
    db_conn.commit()

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute("SELECT implied_probability, observed_at FROM core.market WHERE game_id IS NOT NULL")
        for implied, observed in cur.fetchall():
            assert implied is None
            assert observed is None

    _drop_market_fixtures(db_conn)
```

Check the imports at the top of `tests/integration/test_conform.py` — add
`from datetime import datetime, timezone` if not already imported.

- [ ] **Step 4: Run to verify it fails**

Run: `TEST_DATABASE_URL=postgresql:///mlb_test uv run pytest tests/integration/test_conform.py -k "observed_at" -v`
Expected: FAIL — either `column "observed_at" does not exist` (if migrate
didn't pick up) or `AssertionError` because `_build_market` doesn't write it
yet. (If it's the missing-column error, run `TEST_DATABASE_URL=postgresql:///mlb_test uv run mlb migrate` first.)

- [ ] **Step 5: Implement `observed_at` in `conform.py`**

In `_polymarket_market_rows`, replace:

```python
            start_time = game_starts.get(game_id) if game_id is not None else None
            implied_probability = (
                _latest_before(snapshots.get((market_id, outcome), []), start_time)
                if start_time is not None
                else None
            )
            rows.append(
                (game_id, "polymarket", market_ref, team_id, implied_probability, volume, status)
            )
```

with:

```python
            start_time = game_starts.get(game_id) if game_id is not None else None
            entry = (
                _latest_entry_before(snapshots.get((market_id, outcome), []), start_time)
                if start_time is not None
                else None
            )
            implied_probability, observed_at = (entry[1], entry[0]) if entry else (None, None)
            rows.append(
                (
                    game_id,
                    "polymarket",
                    market_ref,
                    team_id,
                    implied_probability,
                    observed_at,
                    volume,
                    status,
                )
            )
```

In `_kalshi_market_rows`, replace:

```python
            start_time = game_starts.get(game_id) if game_id is not None else None
            implied_probability = (
                _latest_before(snapshots.get(ticker, []), start_time)
                if start_time is not None
                else None
            )
            rows.append((game_id, "kalshi", ticker, team_id, implied_probability, volume, status))
```

with:

```python
            start_time = game_starts.get(game_id) if game_id is not None else None
            entry = (
                _latest_entry_before(snapshots.get(ticker, []), start_time)
                if start_time is not None
                else None
            )
            implied_probability, observed_at = (entry[1], entry[0]) if entry else (None, None)
            rows.append(
                (game_id, "kalshi", ticker, team_id, implied_probability, observed_at, volume, status)
            )
```

In `_build_market`, change the `INSERT INTO core.market` statement from:

```python
        cur.executemany(
            """
            INSERT INTO core.market
                (game_id, source, market_ref, team_id, implied_probability, volume, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
```

to:

```python
        cur.executemany(
            """
            INSERT INTO core.market
                (game_id, source, market_ref, team_id, implied_probability,
                 observed_at, volume, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
```

- [ ] **Step 6: Run to verify the new tests pass and nothing else broke**

Run: `TEST_DATABASE_URL=postgresql:///mlb_test uv run pytest tests/integration/test_conform.py -k "market" -v`
Expected: the two new tests PASS; every existing `*market*` test (matching,
uniqueness, midpoint fallback, idempotency/rerun) still PASSES.

- [ ] **Step 7: Update the docs**

In `docs/DATA_DICTIONARY.md` and `docs/TABLE_CONTRACTS.md`, find the
`core.market` column list and add a row/line for `observed_at` matching the
surrounding style, worded: *"`observed_at timestamptz` — nullable. The
`captured_at` of the `raw.{polymarket,kalshi}_snapshot` row that
`implied_probability` was resolved from; the pre-game moment that price was
observed. NULL exactly when `implied_probability` is NULL (issue #107)."*

- [ ] **Step 8: Lint + type-check**

Run: `uv run ruff check mlb_baseball/conform.py tests/integration/test_conform.py && uv run ruff format --check mlb_baseball/conform.py tests/integration/test_conform.py && uv run mypy mlb_baseball/conform.py`
Expected: clean.

- [ ] **Step 9: Commit**

```bash
git add migrations/0093_market_observed_at.sql mlb_baseball/conform.py \
        tests/integration/test_conform.py docs/DATA_DICTIONARY.md docs/TABLE_CONTRACTS.md
git commit -m "feat(conform): core.market.observed_at = resolving snapshot capture time

Issue #107. conform now persists the captured_at of the pre-game snapshot
that implied_probability came from. Nullable, set iff implied_probability
is set. Next task uses it as the prediction generated_at."
```

---

### Task 3: prediction SQL stamps `generated_at = observed_at`

**Files:**
- Modify: `mlb_baseball/sql/market_kalshi_prediction_insert.sql`
- Modify: `mlb_baseball/sql/market_polymarket_prediction_insert.sql`
- Modify: `tests/integration/test_model_market.py` — `_seed_market_row`
  (`tests/integration/test_model_market.py:50`) and
  `test_record_inserts_home_teams_moneyline_price_as_prediction`
  (`tests/integration/test_model_market.py:111`); add one regression test
- Modify: `docs/ROADMAP.md`

**Interfaces:**
- Consumes: `core.market.observed_at` from Task 2;
  `mlb_baseball.model.evaluation._selected_predictions(conn, model_versions, season, cutoff)`
  (existing).
- Produces: `market._record_decided()` writes `gold.prediction` rows whose
  `generated_at` equals `core.market.observed_at` — a real pre-game time.

- [ ] **Step 1: Update `_seed_market_row` and write the failing tests**

In `tests/integration/test_model_market.py`, change `_seed_market_row` to seed
`observed_at` (the decided game is `2024-04-01`, so a `2024-03-31` timestamp is
safely pre-game):

```python
def _seed_market_row(
    db_conn, game_id, source, team_id, implied_probability, market_ref,
    observed_at="2024-03-31 18:00:00+00",
):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.market "
            "(game_id, source, market_ref, team_id, implied_probability, "
            "observed_at, volume, status) "
            "VALUES (%s, %s, %s, %s, %s, %s, 1000, 'closed')",
            (game_id, source, market_ref, team_id, implied_probability, observed_at),
        )
```

Extend `test_record_inserts_home_teams_moneyline_price_as_prediction` — after
the existing assertions, add:

```python
    with db_conn.cursor() as cur:
        cur.execute("SELECT generated_at FROM gold.prediction")
        (generated_at,) = cur.fetchone()
    assert generated_at == datetime(2024, 3, 31, 18, 0, tzinfo=timezone.utc)
```

(add `from datetime import datetime, timezone` to the file's imports).

Add a new regression test at the end of the file:

```python
def test_decided_game_market_row_passes_the_evaluation_pre_game_filter(db_conn):
    """Issue #107: before the fix generated_at defaulted to now() (post-game),
    so _selected_predictions filtered every decided-game market row out."""
    from mlb_baseball.model import backfill_outcomes
    from mlb_baseball.model.evaluation import _selected_predictions

    _reset(db_conn)
    _ensure_polymarket_market_table(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    game_id = _seed_decided_game(db_conn, atl, nya)
    _seed_polymarket_market_type(db_conn, "m1", "moneyline")
    _seed_market_row(db_conn, game_id, "polymarket", atl, Decimal("0.62"), "m1:atl")
    db_conn.commit()

    market.record(db_conn)
    backfill_outcomes(db_conn)
    db_conn.commit()

    selected = _selected_predictions(db_conn, ["polymarket-v1"], 2024, "close")
    assert len(selected) == 1
    assert selected[0].model_version == "polymarket-v1"
    assert selected[0].actual is True  # ATL won 5-3, ATL is home

    _reset(db_conn)
```

- [ ] **Step 2: Run to verify failure**

Run: `TEST_DATABASE_URL=postgresql:///mlb_test uv run pytest tests/integration/test_model_market.py -v`
Expected: FAIL — the insert SQL doesn't select `observed_at`/`generated_at`
yet, so `test_record_inserts_...` fails its new `generated_at` assertion and
`test_decided_game_market_row_passes...` returns 0 rows.

- [ ] **Step 3: Update both prediction SQL files**

`mlb_baseball/sql/market_kalshi_prediction_insert.sql` — full new content:

```sql
INSERT INTO gold.prediction
    (mlb_game_pk, game_instance_key, model_version, home_win_prob, generated_at)
SELECT g.game_pk, f.game_instance_key, %(model_version)s, m.implied_probability, m.observed_at
FROM core.market m
JOIN core.game g ON g.id = m.game_id AND g.home_team_id = m.team_id
JOIN gold.game_feature f ON f.game_id = g.id
WHERE m.source = 'kalshi'
    AND m.implied_probability IS NOT NULL
    AND m.observed_at IS NOT NULL
    AND g.game_pk IS NOT NULL
    AND NOT EXISTS (
        SELECT 1 FROM gold.prediction p
        WHERE p.game_instance_key = f.game_instance_key AND p.model_version = %(model_version)s
    )
```

`mlb_baseball/sql/market_polymarket_prediction_insert.sql` — full new content
(keeps the existing comment header and the `raw.polymarket_market` join):

```sql
-- market_ref is "{market_id}:{team_id}".  The raw market join narrows an
-- otherwise ambiguous event to the actual moneyline contract.
INSERT INTO gold.prediction
    (mlb_game_pk, game_instance_key, model_version, home_win_prob, generated_at)
SELECT g.game_pk, f.game_instance_key, %(model_version)s, m.implied_probability, m.observed_at
FROM core.market m
JOIN core.game g ON g.id = m.game_id AND g.home_team_id = m.team_id
JOIN gold.game_feature f ON f.game_id = g.id
JOIN raw.polymarket_market pm ON pm.id = split_part(m.market_ref, ':', 1)
WHERE m.source = 'polymarket'
    AND pm.sportsmarkettype = 'moneyline'
    AND m.implied_probability IS NOT NULL
    AND m.observed_at IS NOT NULL
    AND g.game_pk IS NOT NULL
    AND NOT EXISTS (
        SELECT 1 FROM gold.prediction p
        WHERE p.game_instance_key = f.game_instance_key AND p.model_version = %(model_version)s
    )
```

- [ ] **Step 4: Run to verify the tests pass**

Run: `TEST_DATABASE_URL=postgresql:///mlb_test uv run pytest tests/integration/test_model_market.py -v`
Expected: every test PASSES, including the idempotency test
(`test_record_is_idempotent`) and the two new/changed ones.

- [ ] **Step 5: Update `docs/ROADMAP.md`**

Find the Phase 2 paragraph that ends "*Next: revisit once market coverage
grows past a few dozen games; a genuinely live version ... requires extending
`core.market`'s own matching to still-upcoming games first — real, separate
follow-up work.*" Append one sentence:

*"**Update (issue #107, 2026-08-31):** the decided-game comparison lines
previously carried `generated_at = now()` (post-game) and were silently
dropped by every holdout evaluation; `core.market.observed_at` now stamps a
truthful pre-game time, so any model can be scored against `kalshi-v1` /
`polymarket-v1` for every completed game since 2026-08-02."*

- [ ] **Step 6: Lint**

Run: `uv run ruff check tests/integration/test_model_market.py && uv run ruff format --check tests/integration/test_model_market.py`
Expected: clean. (`.sql` files are checked by the `sqlfluff-lint` pre-commit
hook — run `uv run pre-commit run sqlfluff-lint --files mlb_baseball/sql/market_kalshi_prediction_insert.sql mlb_baseball/sql/market_polymarket_prediction_insert.sql` and fix any complaint.)

- [ ] **Step 7: Commit**

```bash
git add mlb_baseball/sql/market_kalshi_prediction_insert.sql \
        mlb_baseball/sql/market_polymarket_prediction_insert.sql \
        tests/integration/test_model_market.py docs/ROADMAP.md
git commit -m "fix(market): stamp decided-game comparison lines with observed_at

Issue #107. market_{kalshi,polymarket}_prediction_insert.sql now set
generated_at = core.market.observed_at instead of letting it default to
now(). Regression test: a decided-game market row now passes
evaluation._selected_predictions' pre-game filter."
```

---

### Task 4: one-time production repair script

**Files:**
- Create: `scripts/repair_market_prediction_times.sql`
- Create: `tests/integration/test_repair_market_times.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (operates on existing
  `gold.prediction` + `raw.mlb_schedule`).
- Produces: an owner-run script; no importable interface.

- [ ] **Step 1: Write the script**

Create `scripts/repair_market_prediction_times.sql`:

```sql
-- One-time repair for issue #107. Run once against PRODUCTION `mlb` AFTER
-- migration 0093 and the conform + prediction-SQL changes are deployed, and
-- BEFORE the next `mlb predict`:
--
--   psql "postgresql:///mlb" -f scripts/repair_market_prediction_times.sql
--
-- Deletes kalshi-v1 / polymarket-v1 rows in gold.prediction whose
-- generated_at is at or after first pitch -- the stale rows _record_decided()
-- wrote with generated_at = now() while running post-game. They are
-- unrecoverable noise: 0 pass evaluation._selected_predictions' pre-game
-- filter. The next `mlb predict` re-inserts them correctly from
-- core.market.observed_at (via the NOT EXISTS idempotency guard).
-- gold.prediction holds regenerable model output, not raw/core source data.
--
-- DRY RUN FIRST -- run this SELECT by hand and eyeball the count before
-- running the file:
--
--   WITH schedule AS (
--       SELECT game_id, min(NULLIF(game_datetime,'')::timestamptz) AS game_start
--       FROM raw.mlb_schedule
--       WHERE game_id IS NOT NULL AND NULLIF(game_datetime,'') IS NOT NULL
--       GROUP BY game_id HAVING count(DISTINCT NULLIF(game_datetime,'')) = 1)
--   SELECT count(*) FROM gold.prediction p JOIN schedule s ON s.game_id = p.mlb_game_pk
--   WHERE p.model_version IN ('kalshi-v1','polymarket-v1') AND p.generated_at >= s.game_start;

\set ON_ERROR_STOP on

WITH schedule AS (
    SELECT game_id,
           min(NULLIF(game_datetime, '')::timestamptz) AS game_start
    FROM raw.mlb_schedule
    WHERE game_id IS NOT NULL AND NULLIF(game_datetime, '') IS NOT NULL
    GROUP BY game_id
    HAVING count(DISTINCT NULLIF(game_datetime, '')) = 1
)
DELETE FROM gold.prediction p
USING schedule s
WHERE s.game_id = p.mlb_game_pk
  AND p.model_version IN ('kalshi-v1', 'polymarket-v1')
  AND p.generated_at >= s.game_start;
```

`DELETE` prints its own row count (`DELETE <n>`) and, in psql autocommit mode,
each statement is its own transaction — the commented dry-run `SELECT` above is
the safety check. No `BEGIN`/`\if` control-flow (that pattern is fragile with
an unset psql variable).

- [ ] **Step 2: Write the failing test**

Create `tests/integration/test_repair_market_times.py`. The test runs the
script's real DELETE (with its `WITH schedule` CTE) against a fixture. Hold the
DELETE block as a module constant and assert it appears verbatim in the script
file, so the test breaks if the script's DELETE ever diverges:

```python
"""The one-time issue #107 repair (scripts/repair_market_prediction_times.sql)
must delete exactly the post-first-pitch market rows and nothing else."""

from datetime import datetime, timezone
from pathlib import Path

_REPAIR_SQL = (
    Path(__file__).resolve().parents[2] / "scripts" / "repair_market_prediction_times.sql"
)

# The DELETE block from the script, verbatim. Kept here so this test exercises
# the real statement and fails loudly if the script's DELETE is edited.
_DELETE_BLOCK = """WITH schedule AS (
    SELECT game_id,
           min(NULLIF(game_datetime, '')::timestamptz) AS game_start
    FROM raw.mlb_schedule
    WHERE game_id IS NOT NULL AND NULLIF(game_datetime, '') IS NOT NULL
    GROUP BY game_id
    HAVING count(DISTINCT NULLIF(game_datetime, '')) = 1
)
DELETE FROM gold.prediction p
USING schedule s
WHERE s.game_id = p.mlb_game_pk
  AND p.model_version IN ('kalshi-v1', 'polymarket-v1')
  AND p.generated_at >= s.game_start;"""


def test_script_file_contains_the_delete_block_verbatim():
    assert _DELETE_BLOCK in _REPAIR_SQL.read_text()


def _seed(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_schedule')")
        if cur.fetchone()[0] is None:
            cur.execute(
                "CREATE TABLE raw.mlb_schedule (game_id text, game_datetime text)"
            )
        cur.execute("DELETE FROM raw.mlb_schedule WHERE game_id IN ('700001', '700002')")
        cur.execute(
            "INSERT INTO raw.mlb_schedule (game_id, game_datetime) VALUES "
            "('700001', '2026-05-01T23:00:00Z'), ('700002', '2026-05-02T23:00:00Z')"
        )
        cur.execute("DELETE FROM gold.prediction WHERE mlb_game_pk IN ('700001', '700002')")
        cur.executemany(
            "INSERT INTO gold.prediction "
            "(mlb_game_pk, game_instance_key, model_version, home_win_prob, generated_at) "
            "VALUES (%s, %s, %s, 0.5, %s)",
            [
                # stale: generated after first pitch — must be deleted
                ("700001", "mlb:700001", "kalshi-v1",
                 datetime(2026, 5, 2, 6, 0, tzinfo=timezone.utc)),
                ("700001", "mlb:700001", "polymarket-v1",
                 datetime(2026, 5, 2, 6, 0, tzinfo=timezone.utc)),
                # good: generated before first pitch — must be kept
                ("700002", "mlb:700002", "kalshi-v1",
                 datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)),
                # not a market model — must be kept
                ("700001", "mlb:700001", "elo-v1",
                 datetime(2026, 5, 2, 6, 0, tzinfo=timezone.utc)),
            ],
        )
    db_conn.commit()


def _cleanup(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.prediction WHERE mlb_game_pk IN ('700001', '700002')")
        cur.execute("DELETE FROM raw.mlb_schedule WHERE game_id IN ('700001', '700002')")
    db_conn.commit()


def test_repair_deletes_only_post_first_pitch_market_rows(db_conn):
    _seed(db_conn)
    try:
        with db_conn.cursor() as cur:
            cur.execute(_DELETE_BLOCK)
        db_conn.commit()

        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT mlb_game_pk, model_version FROM gold.prediction "
                "WHERE mlb_game_pk IN ('700001', '700002') ORDER BY mlb_game_pk, model_version"
            )
            remaining = cur.fetchall()
        assert remaining == [
            ("700001", "elo-v1"),
            ("700002", "kalshi-v1"),
        ]
    finally:
        _cleanup(db_conn)
```

Keep `_delete_statement` simple — if the split logic is awkward, hard-code the
DELETE-with-CTE block as a string constant in the test and add a second
assertion that that constant is a substring of the script file (so the test
still fails if the script's DELETE changes). Prefer whichever the implementer
finds clearer; the intent is "run the script's real DELETE against a fixture."

- [ ] **Step 3: Run to verify it fails**

Run: `TEST_DATABASE_URL=postgresql:///mlb_test uv run pytest tests/integration/test_repair_market_times.py -v`
Expected: `test_script_file_contains_the_delete_block_verbatim` FAILS
(`FileNotFoundError` — script not written yet, or the block doesn't match).

- [ ] **Step 4: Write the script (Step 1) if not already, then run to green**

Ensure the `WITH schedule AS ( … );` DELETE block in
`scripts/repair_market_prediction_times.sql` is character-for-character equal
to `_DELETE_BLOCK` in the test (same indentation, same trailing `;`).
Run: `TEST_DATABASE_URL=postgresql:///mlb_test uv run pytest tests/integration/test_repair_market_times.py -v`
Expected: both tests PASS — `700001` keeps only its `elo-v1` row, `700002`
keeps its pre-game `kalshi-v1` row.

- [ ] **Step 5: Lint**

Run: `uv run ruff check tests/integration/test_repair_market_times.py && uv run ruff format --check tests/integration/test_repair_market_times.py`
Expected: clean. The `sqlfluff-lint` and `sql-ownership-lint` pre-commit hooks
are scoped to `^mlb_baseball/sql/` and `^mlb_baseball/.*\.py$` respectively, so
neither touches `scripts/repair_market_prediction_times.sql` — no SQL-lint step
needed for it. The `test_repair_deletes_only_post_first_pitch_market_rows`
integration test already executes the real DELETE block against `mlb_test`, so
its parse and behaviour are covered there.

- [ ] **Step 6: Commit**

```bash
git add scripts/repair_market_prediction_times.sql tests/integration/test_repair_market_times.py
git commit -m "chore(market): one-time repair script for stale issue #107 rows

Owner runs this once against prod mlb after deploy: deletes the ~540
kalshi-v1 / polymarket-v1 rows stamped after first pitch. Reports the
count first, wrapped in a transaction the owner commits or rolls back.
Test proves the DELETE predicate hits only post-first-pitch market rows."
```

---

### Task 5: ADR + close the issue

**Files:**
- Modify: `docs/DECISIONS.md`

**Interfaces:** none.

- [ ] **Step 1: Add the ADR**

At the top of `docs/DECISIONS.md`'s ADR list (newest first), directly under
the header, add a new ADR. Use the next free `ADR-NNN` number (read the current
top entry and add 1). Match the surrounding format
(**Decision** / **Context** / **Cost** / **Revisit if**):

```markdown
## ADR-NNN: core.market.observed_at — truthful pre-game timestamp for market comparison lines

**Decision:** `core.market` gains a nullable `observed_at timestamptz`
column holding the `captured_at` of the `raw.{polymarket,kalshi}_snapshot`
row that `implied_probability` was resolved from. `conform.py`'s
`_latest_entry_before` (a generalisation of `_latest_before` that returns
the whole `(timestamp, value)` entry) populates it. `market_kalshi_prediction_insert.sql`
and `market_polymarket_prediction_insert.sql` now `SELECT m.observed_at`
into `gold.prediction.generated_at` instead of letting it default to
`now()`.

**Context:** `market._record_decided()` runs inside `mlb predict`, i.e.
after a game has finished, so every decided-game `kalshi-v1` / `polymarket-v1`
row was stamped `generated_at = now() > game_start` and silently dropped by
`evaluation._selected_predictions`' `generated_at < s.game_start` filter
(issue #107). Verified on production 2026-08-31: 0 of ~590 decided-game
market rows passed. The `_record_upcoming` path (ADR-267) already records a
truthful pre-game time, but only accrues ~25 games/day and leaves the
decided path permanently broken. `core.market` already stored the pre-game
snapshot *value* (ADR-052) — this persists its *time*.

**Cost:** one nullable column (instant `ADD COLUMN` on PG16); `_latest_before`
becomes a one-line wrapper (behaviour and its `market.py` callers unchanged).
A one-time `scripts/repair_market_prediction_times.sql` deletes the stale
production rows so the idempotency guard re-inserts them; `gold.prediction`
is regenerable model output. `_record_upcoming` and `implied_probability`
value semantics are untouched.

**Revisit if:** the `mlb predict` cron moves off ~06:00 UTC — `_record_upcoming`
resolves the last snapshot before *first pitch*, not before *now*, a mild
lookahead that is currently harmless because only ~06:00 snapshots exist by
run time. A separate issue, not fixed here.
```

- [ ] **Step 2: Full test sweep**

Run: `uv run pytest tests/unit -q && TEST_DATABASE_URL=postgresql:///mlb_test uv run pytest tests/integration -q -k "market or conform or evaluation or repair"`
Expected: all green.

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy`
Expected: clean (pre-existing unrelated markdown-format complaints in
`docs/reference/agy/` and other plan docs are acceptable — do not fix them
here).

- [ ] **Step 3: Commit**

```bash
git add docs/DECISIONS.md
git commit -m "docs: ADR-NNN — core.market.observed_at for market comparison lines (#107)"
```

- [ ] **Step 4: Open the PR**

```bash
git push -u origin fix/market-observed-at
gh pr create --base main --title "fix: core.market.observed_at — truthful pre-game generated_at for market lines (#107)" \
  --body "$(cat <<'EOF'
Closes #107.

`market._record_decided()` runs post-game inside `mlb predict`, so every
`kalshi-v1` / `polymarket-v1` row in `gold.prediction` was stamped
`generated_at = now()` and dropped by the holdout evaluation's
`generated_at < game_start` filter (0 of ~590 passed on prod).

This persists the resolving pre-game snapshot's `captured_at` as a new
nullable `core.market.observed_at` and stamps `generated_at` from it.

- `migrations/0093_market_observed_at.sql` — `ADD COLUMN observed_at`
- `conform.py` — `_latest_entry_before` returns the whole entry;
  `_latest_before` is now a wrapper; market-row builders + `_build_market`
  carry `observed_at`
- `market_{kalshi,polymarket}_prediction_insert.sql` —
  `generated_at = m.observed_at`
- `scripts/repair_market_prediction_times.sql` — one-time owner-run prod
  cleanup of the ~540 stale rows (reports the count, transaction-wrapped)
- ADR, data dictionary, table contracts, roadmap updated

**Deploy:** merge → `mlb migrate` → `mlb conform` (or wait for the nightly
cron) → owner runs the repair script against `mlb` → next `mlb predict`
re-inserts the decided-game rows correctly → confirm
`scripts/eval_markov_holdout.py --season 2026` reports non-zero shared
games vs `kalshi-v1` / `polymarket-v1`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 5: Note the deploy steps for the owner**

The migration apply, the `mlb conform` run, and the `psql -f
scripts/repair_market_prediction_times.sql` against **production `mlb`** are
owner-run steps after merge — they are in the PR body and the spec's "Deploy
sequence". Do not run them as part of implementation.

---

## Self-Review

**1. Spec coverage:**

| Spec section | Task |
|---|---|
| Schema `migrations/0093_market_observed_at.sql` | Task 2 Step 1 |
| `conform.py` `_latest_entry_before` + wrapper | Task 1 |
| `conform.py` market-row builders + `_build_market` INSERT | Task 2 Steps 5 |
| Prediction SQL `generated_at = m.observed_at` + `observed_at IS NOT NULL` | Task 3 Step 3 |
| `NOT EXISTS` guard unchanged; two grains compose | Task 3 Step 3 (guard kept verbatim) |
| One-time data repair script | Task 4 Step 1 |
| Unit tests for `_latest_entry_before` (tuple, boundary, empty/after) | Task 1 Step 1 |
| Integration: conform `observed_at` populated + pre-game + NULL case | Task 2 Step 3 |
| Integration: `_record_decided` `generated_at` + passes `_selected_predictions` | Task 3 Step 1 |
| Integration: idempotency unchanged | Task 3 Step 4 (existing `test_record_is_idempotent`) |
| `mlb doctor` market checks unchanged | Task 5 Step 2 sweep (`-k "market"`) |
| Docs: ADR | Task 5 Step 1 |
| Docs: DATA_DICTIONARY + TABLE_CONTRACTS | Task 2 Step 7 |
| Docs: ROADMAP | Task 3 Step 5 |
| Docs: PROGRESS.md | deploy step (needs prod evidence — not a plan task) |
| Close #107 | Task 5 Step 4 (`Closes #107` in PR body) |
| Non-goal: `_record_upcoming` untouched | verified — no task modifies `market.py` |
| Non-goal: `implied_probability` value semantics unchanged | verified — Task 2 keeps the same value, adds the timestamp beside it |

No gaps.

**2. Placeholder scan:** `ADR-NNN` in Task 5 is a deliberate "read the current
top ADR and add 1" instruction, not a placeholder — the number genuinely
isn't knowable until implementation and the repo convention is to assign it
then. Migration `0093` is checked free as of 2026-08-31 (highest on any branch
is `0092`); Task 2 Step 1 says renumber if taken. No other placeholders.

**3. Type consistency:**
- `_latest_entry_before(entries: list[tuple[datetime, Decimal]], cutoff: datetime) -> tuple[datetime, Decimal] | None` — same name and signature in Task 1 (defined), Task 2 (consumed).
- Market-row tuple is 8 elements
  `(game_id, source, market_ref, team_id, implied_probability, observed_at, volume, status)`
  in Task 2 — the `_build_market` INSERT column list matches that order.
- `_seed_market_row(..., observed_at="2024-03-31 18:00:00+00")` in Task 3 —
  the new positional/keyword arg is added at the end, so the existing call
  sites in `test_model_market.py` that pass 6 positional args stay valid.
- `_selected_predictions(conn, model_versions, season, cutoff)` — used in
  Task 3 exactly as defined in `mlb_baseball/model/evaluation.py:57`.

No inconsistencies.
