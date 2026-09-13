# Re-ingest `raw.bref_batting` / `raw.bref_pitching` (task 2.2) — owner-run

## What this is (and isn't)

- **Only two tables** are re-pulled: `raw.bref_batting` / `raw.bref_pitching`
  — the Baseball-Reference season stat lines from `pybaseball`, **one row per
  player per season**. A few thousand rows a season.
- **Nothing else.** Lahman / baseball databank, Retrosheet, Statcast, MLB API —
  all untouched. `raw.bref_war_batting` / `_war_pitching` are already clean.
- **Why re-pull instead of filter:** these rows are pre-summed season totals
  from Baseball-Reference (Semien 2023 = one "179 G / 835 PA" row). There is no
  per-game breakdown inside them to filter — the only fix is to ask
  Baseball-Reference again with the right date window (regular season only).

## Scope: 2021–2026 only

2008–2019 are already regular-season-only (Baseball-Reference didn't backfill
postseason game-logs into its daily tool for those years — ADR-282). 2020 is
the COVID season. Only **2021 onward** is contaminated, so only those seasons
are re-pulled.

## Commands (against the production `mlb` database)

```bash
# 1. Clear the pybaseball on-disk cache so the range calls re-fetch fresh.
uv run python -c "import pybaseball.cache as c; c.purge()"

# 2. Delete the contaminated seasons. WAR tables and 2008-2020 are NOT touched.
psql "$DATABASE_URL" -c "DELETE FROM raw.bref_batting  WHERE _season::int >= 2021;"
psql "$DATABASE_URL" -c "DELETE FROM raw.bref_pitching WHERE _season::int >= 2021;"

# 3. Re-ingest. bootstrap() re-pulls the now-missing 2021-2025 plus the current
#    season, and skips 2008-2020 (still loaded). ~12 HTTP requests, ~2 min.
uv run mlb ingest bref --mode bootstrap

# 4. Apply pending migrations. This change ships 0100 (gold.batting_postseason /
#    gold.pitching_postseason) + 0101 (ros_team_standings view) -- `mlb report`
#    TRUNCATEs the postseason tables and errors if they don't exist yet.
uv run mlb migrate

# 5. Rebuild the gold reporting surface off the clean raw (task 3.1).
#    Takes ~15-20 min (full retrosheet-event rebuild, 1910+). Run detached.
uv run mlb report
```

If you would rather re-pull the whole 2008-2026 range for one consistent
methodology, `TRUNCATE raw.bref_batting, raw.bref_pitching` before step 3
instead of the two DELETEs — ~40 requests, ~5 min. Functionally identical
result; the scoped version is just faster.

## Verification (task 2.2 acceptance)

Columns in `raw.bref_batting` / `raw.bref_pitching` are lowercase and stored as
`text` (source-faithful), so cast to `int` for numeric comparisons.

```sql
-- Marcus Semien 2023: must be 162 G / 753 PA (was 179 / 835).
SELECT name, g, pa FROM raw.bref_batting
WHERE name = 'Marcus Semien' AND _season = '2023';

-- Spot check 3 more deep-playoff-team players:
--   Corey Seager 2023 (TEX)     -> 119 G
--   Freddie Freeman 2021 (ATL)  -> 159 G
--   Jose Altuve 2022 (HOU)      -> 141 G
SELECT name, _season, g FROM raw.bref_batting
WHERE (name, _season) IN
  (('Corey Seager','2023'), ('Freddie Freeman','2021'), ('Jose Altuve','2022'));

-- No season line over the regular-season envelope (cast — column is text):
SELECT max(g::int) FROM raw.bref_batting;   -- <= 163
SELECT max(g::int) FROM raw.bref_pitching;  -- <= 163
```

Then task 3.1: `SELECT max(games) FROM gold.player_season;` must be ≤ 163, and
`mlb doctor` passes its new "regular-season envelope" check.
