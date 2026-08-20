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

## Exporting to CSV

Every relation above can be piped straight to a CSV file with `psql`'s
`\copy` (client-side, so it works against a remote database without
server filesystem access). These three relations are unbounded and can be
tens of millions of rows for the full history, so filter to a season for
a one-off look:

```sh
psql "postgresql:///mlb" -c "\copy (SELECT * FROM gold.team_season WHERE season = 2024 ORDER BY team_id) TO 'team_season_2024.csv' WITH CSV HEADER"
psql "postgresql:///mlb" -c "\copy (SELECT * FROM gold.player_season WHERE season = 2024 ORDER BY player_id) TO 'player_season_2024.csv' WITH CSV HEADER"
psql "postgresql:///mlb" -c "\copy (SELECT * FROM gold.game_export WHERE season = 2024 ORDER BY game_date) TO 'game_export_2024.csv' WITH CSV HEADER"
```

An explicit full-history export (every season, no filter) is the same
shape without the `WHERE`:

```sh
psql "postgresql:///mlb" -c "\copy (SELECT * FROM gold.game_export ORDER BY season, game_date) TO 'game_export_full.csv' WITH CSV HEADER"
```
