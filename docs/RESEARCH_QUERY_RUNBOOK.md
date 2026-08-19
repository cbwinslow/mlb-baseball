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
is already computed and stored elsewhere, so it needs no separate refresh
and is always as fresh as `gold.game_feature`. Upcoming (not yet played)
games still appear in it, with score/venue/starter columns `NULL` until
`core.game`/features resolve them.

For pitch, play, or identity research, join the explicit `core` relations by
their documented keys. Do not union Retrosheet and MLB play-by-play rows until
their source-specific grains have been selected and documented.

## Exporting to CSV

Every relation above can be piped straight to a CSV file with `psql`'s
`\copy` (client-side, so it works against a remote database without
server filesystem access):

```sh
psql "postgresql:///mlb" -c "\copy (SELECT * FROM gold.team_season ORDER BY season, team_id) TO 'team_season.csv' WITH CSV HEADER"
psql "postgresql:///mlb" -c "\copy (SELECT * FROM gold.player_season ORDER BY season, player_id) TO 'player_season.csv' WITH CSV HEADER"
psql "postgresql:///mlb" -c "\copy (SELECT * FROM gold.game_export ORDER BY season, game_date) TO 'game_export.csv' WITH CSV HEADER"
```

Always filter or `LIMIT` first for a one-off look — these three relations
are unbounded and can be tens of millions of rows for the full history.
