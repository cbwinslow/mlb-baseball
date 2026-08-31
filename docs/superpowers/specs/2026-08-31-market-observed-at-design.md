# `core.market.observed_at` — truthful pre-game timestamp for market comparison lines

**Status:** Owner-reviewed 2026-08-31 (two decisions recorded below). Next
step: `superpowers:writing-plans` → implementation plan.

**Issue:** [#107](https://github.com/cbwinslow/mlb-baseball/issues/107) —
"Holdout eval can't compare against Kalshi/Polymarket — market predictions
stamped `generated_at=now()`".

**Relation to existing work:** unblocks Layer 4 (market comparison) of the
prediction ladder in `docs/PRODUCT_DIRECTION.md`. ADR-052 (`core.market`
resolves to the last pre-game snapshot *price*) and ADR-053 / ADR-267
(`market.py` writes `kalshi-v1` / `polymarket-v1` as comparison lines in
`gold.prediction`) are the direct predecessors. This spec adds the missing
piece: the *time* that pre-game price was observed.

---

## Why this spec exists

`scripts/eval_markov_holdout.py` — and any future model-vs-market comparison
— selects one prediction per game through
`mlb_baseball/model/evaluation.py::_selected_predictions`, which requires
`p.generated_at < s.game_start` (a prediction must predate first pitch).

The market comparison lines fail that filter:

- `market._record_decided()` runs
  `market_kalshi_prediction_insert.sql` /
  `market_polymarket_prediction_insert.sql`. Those INSERTs set only
  `(mlb_game_pk, game_instance_key, model_version, home_win_prob)`, so
  `gold.prediction.generated_at` defaults to `now()`.
- `_record_decided` runs inside `mlb predict`, i.e. **after** the game
  finished.
- Every decided-game market row therefore has
  `generated_at > game_start` and is filtered out of every evaluation.

Verified on production `mlb`, 2026-08-31:

| model_version | rows | resolved | valid pre-game |
|---|---|---|---|
| `elo-v1` | 17,621 | 7,923 | 7,575 |
| `kalshi-v1` | 393 | 312 | 28 |
| `polymarket-v1` | 447 | 278 | 24 |

The 28 / 24 valid rows come entirely from the *other* market path,
`_record_upcoming` (added in ADR-267), which inserts pre-game rows while a
game is still upcoming — those get a truthful `now()` timestamp. That path
only started producing rows when the daily job stabilised (2026-08-29), so
it has accumulated ~1 day of sample. Left alone it grows ~25 games/day; a
sample comparable to `elo-v1`'s is ~10 weeks away, and the decided-game
path stays permanently broken.

`core.market` already stores the *value* of the last pre-game snapshot
(`implied_probability`, ADR-052) but discards its `captured_at` — the
helper `conform._latest_before` returns only the price. This spec persists
that timestamp.

---

## Goals

1. `market._record_decided()` writes `gold.prediction` rows with a truthful
   pre-game `generated_at` — the `captured_at` of the market snapshot the
   `implied_probability` was resolved from.
2. Every model-vs-market holdout comparison for a game played on or after
   2026-08-02 (when `raw.*_snapshot` capture began) works immediately,
   without waiting for `_record_upcoming` to accumulate.
3. No change to the *value* semantics of `core.market.implied_probability`
   or to the `_record_upcoming` (live) path.

## Non-goals

- The mild lookahead in `_record_upcoming` — it resolves the last snapshot
  before *first pitch*, not before *now*. Harmless on the 06:00 UTC cron
  because only ~06:00 snapshots exist by then. Noted here, not fixed; a
  separate issue if the cron ever moves.
- Historical `markov-v1` / `gbm-v1` prediction backfill. The holdout
  harness computes `markov-v1` live; `gbm-v1` is issue #108.
- Full `raw.polymarket_price` / `raw.kalshi_candle` line-movement backfill
  (owner-triggered, real API-cost decision). This fix uses only the
  already-captured snapshot stream.
- `gold.total_prediction` market lines — no market total-runs data is
  conformed today (ADR-056).

---

## Owner decisions (2026-08-31)

1. **Backfill from 2026-08-02, not forward-only.** Plumb the snapshot
   `captured_at` through conform into a new `core.market.observed_at`
   column and use it as `generated_at`. Unlocks a few hundred decided
   games of model-vs-market comparison immediately (every completed game
   since snapshot capture began that has a resolved home-moneyline price),
   instead of waiting ~10 weeks for `_record_upcoming` to accumulate a
   comparable sample.
2. **Delete the invalid production rows** (post-first-pitch `kalshi-v1` /
   `polymarket-v1` snapshots — ~540 rows on 2026-08-31, exact `SELECT`
   count shown to the owner first) rather than keep them and loosen the
   idempotency guard. They are provably useless (0 pass the eval filter);
   the next `mlb predict` re-inserts them correctly.

---

## Data flow

```
raw.{kalshi,polymarket}_snapshot  (captured_at, price — ingested every run since 2026-08-02)
      │  conform._latest_entry_before(entries, first_pitch)
      │     picks the last snapshot strictly before game start
      ▼
core.market.implied_probability   +   core.market.observed_at   ← NEW
      │  (both from the same selected snapshot; NULL together when none qualifies)
      │
      │  market._record_decided()  →  market_{kalshi,polymarket}_prediction_insert.sql
      ▼
gold.prediction  (generated_at = m.observed_at)     ← was: now(), post-game
      │  evaluation._selected_predictions:  WHERE p.generated_at < s.game_start
      ▼
model-vs-market holdout comparison works
```

---

## Design

### 1. Schema — `migrations/0093_market_observed_at.sql`

```sql
-- core.market.observed_at: the captured_at of the raw snapshot that
-- implied_probability was resolved from (issue #107). Lets
-- market_*_prediction_insert.sql stamp a truthful pre-game generated_at
-- instead of now(). NULL exactly when implied_probability is NULL.
ALTER TABLE core.market ADD COLUMN IF NOT EXISTS observed_at timestamptz;
```

Nullable, no default. Instant on PostgreSQL 16 (no table rewrite).
`conform.run()` already `TRUNCATE`s and rebuilds `core.market` every run,
so the next nightly `mlb conform` fully populates the column — no separate
backfill for this table.

### 2. `mlb_baseball/conform.py`

**New helper**, beside `_latest_before`:

```python
def _latest_entry_before(
    entries: list[tuple[datetime, Decimal]], cutoff: datetime
) -> tuple[datetime, Decimal] | None:
    """The whole (captured_at, value) entry strictly before cutoff, or None.
    entries must be sorted ascending by timestamp (both snapshot lookups
    build them via ORDER BY captured_at)."""
    idx = bisect_left(entries, (cutoff, Decimal(0))) if entries else 0
    if idx == 0:
        return None
    return entries[idx - 1]


def _latest_before(
    entries: list[tuple[datetime, Decimal]], cutoff: datetime
) -> Decimal | None:
    entry = _latest_entry_before(entries, cutoff)
    return entry[1] if entry is not None else None
```

`_latest_before`'s two callers in `mlb_baseball/model/market.py` (the
`_record_upcoming` path) and its existing unit tests are unchanged.

**`_polymarket_market_rows` / `_kalshi_market_rows`:** replace the
`_latest_before(...)` call with

```python
entry = _latest_entry_before(snapshots.get(key, []), start_time) if start_time else None
implied_probability, observed_at = (entry[1], entry[0]) if entry else (None, None)
```

and append `observed_at` to the row tuple (after `implied_probability`,
before `volume`, to match the INSERT column order below).

**`_build_market` INSERT:** add `observed_at` to the column list and one
more `%s`:

```sql
INSERT INTO core.market
    (game_id, source, market_ref, team_id, implied_probability, observed_at, volume, status)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
```

### 3. Prediction SQL — `market_kalshi_prediction_insert.sql` and `market_polymarket_prediction_insert.sql`

Both change identically:

```sql
INSERT INTO gold.prediction
    (mlb_game_pk, game_instance_key, model_version, home_win_prob, generated_at)
SELECT g.game_pk, f.game_instance_key, %(model_version)s, m.implied_probability, m.observed_at
FROM core.market m
JOIN core.game g   ON g.id = m.game_id AND g.home_team_id = m.team_id
JOIN gold.game_feature f ON f.game_id = g.id
-- (polymarket keeps its raw.polymarket_market moneyline join)
WHERE m.source = '<kalshi|polymarket>'
    AND m.implied_probability IS NOT NULL
    AND m.observed_at IS NOT NULL
    AND g.game_pk IS NOT NULL
    AND NOT EXISTS (
        SELECT 1 FROM gold.prediction p
        WHERE p.game_instance_key = f.game_instance_key
          AND p.model_version = %(model_version)s
    )
```

- `m.observed_at IS NOT NULL` is redundant with `implied_probability IS NOT
  NULL` (they are always both-or-neither) but is stated explicitly: the
  column feeds `generated_at`, which is `NOT NULL` in `gold.prediction`.
- The `NOT EXISTS` guard is unchanged. `observed_at` for a finished game is
  deterministic (its snapshot history is immutable), so first-write-wins is
  correct — the evaluation wants one immutable snapshot per game.
- The two grains compose: if `_record_upcoming` already wrote a pre-game
  row for a game, `_record_decided` skips it (`NOT EXISTS` fails); the
  decided path only fills games the live path missed.

### 4. One-time data repair — `scripts/repair_market_prediction_times.sql`

Run once by the owner **against production `mlb`**, after the migration and
code are deployed, before the next `mlb predict`. Only touches regenerable
prediction rows — never `raw`/`core` data.

```sql
-- PROD mlb.gold.prediction. Deletes kalshi-v1 / polymarket-v1 rows stamped
-- at or after first pitch (~590 rows; 0 currently pass the eval pre-game
-- filter). The next `mlb predict` re-inserts them correctly from
-- core.market.observed_at. A SELECT count(*) with the same predicate is
-- run and shown first.
DELETE FROM gold.prediction p
USING (
    SELECT game_id,
           min(NULLIF(game_datetime, '')::timestamptz) AS game_start
    FROM raw.mlb_schedule
    WHERE game_id IS NOT NULL AND NULLIF(game_datetime, '') IS NOT NULL
    GROUP BY game_id
    HAVING count(DISTINCT NULLIF(game_datetime, '')) = 1
) s
WHERE p.model_version IN ('kalshi-v1', 'polymarket-v1')
  AND p.mlb_game_pk = s.game_id
  AND p.generated_at >= s.game_start;
```

The doubleheader `HAVING count(DISTINCT …) = 1` guard matches
`evaluation.py::_selected_predictions`' own `schedule` CTE — a game whose
schedule rows disagree on first-pitch time is left untouched (its market
rows would be filtered by the eval anyway).

### 5. Testing

**Unit (`tests/unit/`):**
- `_latest_entry_before` returns the correct `(captured_at, value)` tuple
  for a cutoff between entries.
- `_latest_entry_before` with `cutoff` exactly equal to an entry's
  timestamp excludes that entry (same boundary as `_latest_before` —
  `bisect_left`).
- `_latest_entry_before` returns `None` for an empty list and for a cutoff
  before the first entry.
- Existing `_latest_before` tests still pass (wrapper behaviour identical).

**Integration (`tests/integration/`) — mock the network, real Postgres:**
- **conform:** given fixture `raw.*_snapshot` rows with known `captured_at`
  and a fixture `raw.mlb_schedule` first-pitch time, after `_build_market`:
  `core.market.observed_at` is non-NULL for exactly the rows where
  `implied_probability` is non-NULL, and every non-NULL `observed_at` is
  strictly less than that game's first pitch.
- **market (`_record_decided`):** after conform + `market.record()`, the
  `kalshi-v1` / `polymarket-v1` rows in `gold.prediction` have
  `generated_at = core.market.observed_at`, and a decided-game row passes
  `evaluation._selected_predictions([...], season, "close")`. This is the
  regression test for issue #107.
- **idempotency:** `market.record()` run twice produces the same row count
  (existing test extended, not replaced).

**Existing checks:** `mlb doctor` market checks (`_polymarket_coverage_check`
/ `_kalshi_coverage_check`) unchanged and still green.

### 6. Documentation (same change)

- `docs/DECISIONS.md`: new ADR, newest first (number assigned in the
  implementation PR — the next free ADR-NNN) — "`core.market.observed_at`
  — truthful pre-game timestamp for market comparison lines".
- `docs/DATA_DICTIONARY.md` and `docs/TABLE_CONTRACTS.md`: `core.market`
  gains `observed_at timestamptz` (nullable; snapshot `captured_at`).
- `docs/ROADMAP.md` Phase 2: the ADR-053 market-comparison paragraph's
  "Next: revisit once market coverage grows past a few dozen games"
  becomes "unblocked by the new ADR / issue #107".
- `plans/PROGRESS.md`: dated evidence entry after the production deploy and
  repair (row counts before/after, first successful holdout comparison).
- Close issue #107.

---

## Files touched

| File | Change |
|---|---|
| `migrations/0093_market_observed_at.sql` | **new** — `ALTER TABLE core.market ADD COLUMN observed_at` |
| `mlb_baseball/conform.py` | `_latest_entry_before` helper; `_latest_before` → wrapper; `_polymarket_market_rows` / `_kalshi_market_rows` return `observed_at`; `_build_market` INSERT |
| `mlb_baseball/sql/market_kalshi_prediction_insert.sql` | `generated_at` column + `m.observed_at` + `observed_at IS NOT NULL` |
| `mlb_baseball/sql/market_polymarket_prediction_insert.sql` | same |
| `scripts/repair_market_prediction_times.sql` | **new** — one-time owner-run prod cleanup |
| `tests/unit/test_conform*.py` | `_latest_entry_before` cases |
| `tests/integration/test_*market*.py` | `observed_at` populated + pre-game; `_record_decided` `generated_at`; regression test |
| `docs/DECISIONS.md`, `docs/DATA_DICTIONARY.md`, `docs/TABLE_CONTRACTS.md`, `docs/ROADMAP.md` | column + ADR |

## Deploy sequence

1. Merge the PR (migration + code + tests + docs).
2. `DATABASE_URL=postgresql:///mlb uv run mlb migrate` — applies 0093.
3. `DATABASE_URL=postgresql:///mlb uv run mlb conform` — repopulates
   `core.market` with `observed_at` (nightly cron does this anyway; can
   wait for it).
4. Owner runs the `SELECT` count, then the `DELETE` in
   `scripts/repair_market_prediction_times.sql` against `mlb`.
5. Next `mlb predict` re-inserts the decided-game market rows with truthful
   `generated_at`.
6. `scripts/eval_markov_holdout.py --season 2026` — confirm non-zero shared
   games vs `kalshi-v1` / `polymarket-v1`; record in `plans/PROGRESS.md`.

## Risks

- **`observed_at` in the far past for a stale market.** If a market's only
  snapshots predate the game by days (a market listed early, then not
  re-polled), `observed_at` is that early time — still a truthful pre-game
  observation, just not a close-to-first-pitch one. The `"close"` cutoff in
  evaluation already takes the latest qualifying snapshot; nothing to fix.
- **Doubleheaders.** Both the repair SQL and `_selected_predictions` skip
  games whose schedule rows disagree on first pitch. A doubleheader market
  row stays in `gold.prediction` but is never selected by the eval —
  consistent with today's behaviour for every model.
- **Migration number collision.** If another branch claims `0093` first,
  renumber to the next free integer before merge (standard for this repo).
