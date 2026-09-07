# Re-ingest `raw.bref_batting` / `raw.bref_pitching` (task 2.2) — owner-run

The `bref.py` fix (task 2.1) changed the Baseball-Reference query window to
regular-season only. The already-loaded rows for 2008–2025 still carry the old
regular + postseason numbers, and `bootstrap()` skips seasons it sees as
already loaded — so the rebuild is an explicit truncate + bootstrap.

Runs against the **production `mlb`** database. `raw.bref_war_batting` /
`raw.bref_war_pitching` are untouched (already clean) but `bootstrap()` reloads
them anyway (one HTTP call each, idempotent).

## Commands

```bash
# 1. Clear the pybaseball on-disk cache so the range calls re-fetch from
#    Baseball-Reference rather than serving any stale window.
uv run python -c "import pybaseball.cache as c; c.purge()"
#    (cache dir: ~/.pybaseball/cache — safe to delete wholesale instead)

# 2. Drop the contaminated season rows. WAR tables are NOT touched.
psql "$DATABASE_URL" -c "TRUNCATE raw.bref_batting, raw.bref_pitching;"

# 3. Re-ingest every season 2008–<current year> with the regular-season window.
uv run mlb ingest bref --mode bootstrap

# 4. Rebuild the gold reporting surface off the clean raw (task 3.1).
uv run mlb report
```

Expect ~40 HTTP requests (2 stat types × ~19 seasons + 2 WAR calls); a few
minutes with pybaseball's rate limiting.

## Verification (task 2.2 acceptance)

```sql
-- Marcus Semien 2023: must be 162 G / 753 PA (was 179 / 835).
SELECT name, "G", "PA" FROM raw.bref_batting
WHERE name = 'Marcus Semien' AND _season = '2023';

-- Spot check 3 more deep-playoff-team players, regular-season G:
--   Corey Seager 2023 (TEX)      -> 119 G
--   Freddie Freeman 2021 (ATL)   -> 159 G
--   Jose Altuve 2022 (HOU)       -> 141 G
SELECT name, _season, "G" FROM raw.bref_batting
WHERE (name, _season) IN
  (('Corey Seager','2023'), ('Freddie Freeman','2021'), ('Jose Altuve','2022'));

-- No season line should exceed the regular-season game envelope:
SELECT max("G") FROM raw.bref_batting;   -- <= 162
SELECT max("G") FROM raw.bref_pitching;  -- <= 162
```

Then task 3.1: `SELECT max(games) FROM gold.player_season;` must be ≤ 162.
