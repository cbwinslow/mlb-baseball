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

For pitch, play, or identity research, join the explicit `core` relations by
their documented keys. Do not union Retrosheet and MLB play-by-play rows until
their source-specific grains have been selected and documented.
