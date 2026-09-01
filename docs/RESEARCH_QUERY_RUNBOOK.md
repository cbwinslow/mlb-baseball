# Research query runbook

The project does not expose an arbitrary public SQL endpoint. Researchers use
PostgreSQL directly and start with documented `gold` relations whose grain is
clear. Rebuild the final-season reporting relations when needed:

```sh
DATABASE_URL=postgresql:///mlb uv run mlb report
DATABASE_URL=postgresql:///mlb uv run mlb doctor
```

`gold.game_feature` is for pregame research and modeling. Its team records and
rates were known before `feature_cutoff_at`; it is not a final standings table.
The three reporting relations below are final-season outputs and must not be
used as historical pregame inputs.

## Team seasons

```sql
SELECT season, wins, losses, win_pct, woba, wrc_plus, park_factor
FROM gold.team_season
WHERE team_id = :team_id
ORDER BY season DESC;
```

## Player seasons

```sql
SELECT season, player_name, pa, hr, ops, war
FROM gold.player_season
WHERE player_id = :player_id AND is_pitcher = false
ORDER BY season DESC;
```

## Division standings

```sql
SELECT season, division_name, division_rank, wins, losses, games_back
FROM gold.division_standing
WHERE team_id = :team_id
ORDER BY season DESC;
```

## Game exports

`gold.game_export` (migration 0058) is a wide, pre-joined view over
`gold.game_feature` for researchers who want one flat, CSV/Excel/R-ready
table per game instead of hand-joining team/player IDs themselves. It
resolves `core.team`/`core.player` IDs into readable names (`home_team`,
`home_starter`, ...) and adds the real final score from `core.game`
(`home_score`/`away_score` — `gold.game_feature` itself only carries the
boolean `home_win`). It is a view, not a materialized table: every column
is already computed and stored elsewhere (`gold.game_feature` plus the
`core.team`/`core.player`/`core.venue`/`core.game` rows it joins against),
so it needs no separate refresh and always reflects the current values of
every source relation, not just `gold.game_feature`. Upcoming (not yet
played) games still appear in it, with score/venue/starter columns `NULL`
until `core.game`/features resolve them.

`home_score`/`away_score`/`home_win` are reporting-only, postgame values —
never use them as a model input for the game they belong to. Every
pregame, model-eligible column is only ever known as of
`feature_cutoff_at`; that's the point-in-time cutoff to respect, the same
as `gold.game_feature` itself.

For pitch, play, or identity research, join the explicit `core` relations by
their documented keys. Do not union Retrosheet and MLB play-by-play rows until
their source-specific grains have been selected and documented.

## Exporting Research Data

The platform provides a first-class CLI export command (`mlb export`) that streams allow-listed relations directly to CSV, Apache Parquet, or Microsoft Excel (`.xlsx`), with server-side cursors and zero arbitrary SQL execution.

### Single Relation Export

Export any allow-listed `raw.*`, `core.*`, or `gold.*` relation:

```sh
# Export gold.game_export for 2024 to Parquet (default)
uv run mlb export gold.game_export --season 2024 --out game_export_2024.parquet

# Export player season metrics to CSV
uv run mlb export gold.player_season --season 2024 --format csv --out player_season_2024.csv

# Export team franchise directory to Excel (.xlsx with 1M-row safety check)
uv run mlb export core.team --format xlsx --out teams.xlsx

# Export full 24-state run expectancy matrix
uv run mlb export gold.run_expectancy_24 --format parquet
```

### Rights-Filtered Redistribution Bundles (`--profile public_safe`)

Generate a complete, rights-cleared research archive containing only Retrosheet-derived data, accompanied by an authoritative `MANIFEST.json` and Retrosheet attribution:

```sh
# Generate bundle directory
uv run mlb export --profile public_safe --out mlb_research_bundle/

# Generate compressed zip bundle directly
uv run mlb export --profile public_safe --out mlb_research_public_safe --zip
```

Relations included in the `public_safe` bundle:
- `raw.retrosheet_event`, `raw.retrosheet_gameinfo`
- `core.player`, `core.game`, `core.play`, `core.pitch`, `core.venue`, `core.team`, `core.team_alias`, `core.standing`
- `gold.game_export`, `gold.player_season`, `gold.team_season`, `gold.division_standing`, `gold.run_expectancy_24`, `gold.win_expectancy`, `gold.leverage_index`

(Excluded from `public_safe`: Statcast pitch tracking, MLB Stats API feeds, Baseball-Reference WAR, prediction markets, and model forecasts.)

### Alternative: Raw `psql \copy`

If querying directly from PostgreSQL without the Python CLI:

```sh
psql "postgresql:///mlb" -c "\copy (SELECT * FROM gold.team_season WHERE season = 2024 ORDER BY team_id) TO 'team_season_2024.csv' WITH CSV HEADER"
psql "postgresql:///mlb" -c "\copy (SELECT * FROM gold.player_season WHERE season = 2024 ORDER BY player_id) TO 'player_season_2024.csv' WITH CSV HEADER"
psql "postgresql:///mlb" -c "\copy (SELECT * FROM gold.game_export WHERE season = 2024 ORDER BY game_date) TO 'game_export_2024.csv' WITH CSV HEADER"
```
