## Why

`gold.player_season` / `gold.team_season` silently include **postseason** games
in a player's or team's stated season line, for playoff teams, from 2021 onward.
ADR-282 has the full finding; the short version:

- `mlb_baseball/connectors/bref.py` loads `raw.bref_batting` / `raw.bref_pitching`
  from `pybaseball.batting_stats_bref(year)` / `pitching_stats_bref(year)`, which
  query a **March 1 – November 30** Baseball-Reference range. That window spans
  October/November, and Baseball-Reference's daily tool now returns postseason
  game-logs inside it (a behaviour change around 2020–21 — which is why
  2008–2019 are clean and 2021+ are not).
- Example: Marcus Semien 2023 = 179 G / 835 PA in `raw.bref_batting`; his real
  regular season is 162 G / 753 PA (the Rangers played 17 postseason games).
- A prior session already noticed this (`mlb_baseball/model/starter.py`
  docstring, Blake Snell 2025 example) and treated it as "a real property of
  the ground-truth source" rather than fixing it, widening a reconciliation
  tolerance to absorb it.

Every serious source keeps the two apart — Retrosheet ships postseason in a
separate archive (`allpost.zip`; our `raw.retrosheet_event._group = 'postseason'`
tags it, and `core.game.game_type` labels each game); Lahman has `Batting` vs
`BattingPost`; Baseball-Reference and FanGraphs keep the standard line
regular-season-only with a distinct postseason section. This change makes our
data follow suit.

The owner's direction: **separate the data** (own tables, not a flag), and
**audit the whole pipeline — bootstrap, ingestion, views, SQL, Python — so
postseason never lands in a regular-season table again.**

## What Changes

- **`raw.bref_batting` / `raw.bref_pitching` become regular-season only.** Fix
  `mlb_baseball/connectors/bref.py` so its Baseball-Reference pull ends at the
  regular-season boundary, not November 30. Re-ingest every affected season
  (2021+; the whole 2008+ range for consistency). `gold.player_season` /
  `gold.team_season` then rebuild clean with no builder change.
- **New separate postseason relations** in `gold`, built from the same
  Retrosheet-event pipeline as the regular-season backbone, filtered to the
  postseason `game_type`s: `gold.batting_postseason` / `gold.pitching_postseason`
  at the player-season and team-season grains (career optional). One row per
  `(player, season)` covering that player's whole postseason run;
  `game_type` / round retained so a researcher can slice by series.
- **Pipeline audit + guards.** Review every `gold` builder, SQLMesh model,
  materialised view, and Python aggregation that touches game-level data;
  confirm each explicitly scopes `game_type` (regular vs postseason) rather
  than relying on a source being "clean". Add an `mlb doctor` check that fails
  if any `gold.player_season` / `gold.team_season` row exceeds a 162-game / plausible-PA
  envelope, and a check that the postseason relations only contain postseason
  games.
- **Bootstrap + `mlb daily`**: verify the ingestion order and the connectors'
  own scoping so a fresh `mlb bootstrap` produces separated data with no manual
  step.
- **Reconciliation + docs**: tighten `starter.py` / `bullpen.py` reconciliation
  tolerances now that `raw.bref_*` is clean; update `docs/RESEARCH.md`, the
  `starter.py` docstring, `docs/DATA_DICTIONARY.md`, `docs/TABLE_CONTRACTS.md`,
  and ADR-282 (mark the fix landed).

## Capabilities

### New Capabilities

- `postseason-stats`: separate, Retrosheet-event-derived postseason batting and
  pitching relations at the player-season and team-season grains, and the rule
  that regular-season relations never contain postseason games.

### Modified Capabilities

- `statistic-backbone`: add the requirement that the grain ladder scopes
  `game_type` explicitly, and that a `mlb doctor` envelope check guards against
  postseason contamination in any regular-season relation.
- `delivery`: `gold.player_season` / `gold.team_season` are regular-season only;
  the postseason relations are a separate part of the distribution with their
  own `local_research` profile.

## Impact

- `mlb_baseball/connectors/bref.py` — regular-season date boundary; re-ingest.
- `mlb_baseball/report.py` — the `_build_player_season` / `_build_team_season`
  SQL is unchanged in shape but rebuilds against clean raw; a new
  postseason-relation builder is added (or a new `mlb_baseball/sql/*_postseason_build.sql`).
- New migration(s) for `gold.batting_postseason` / `gold.pitching_postseason`.
- `mlb_baseball/model/starter.py`, `mlb_baseball/model/bullpen.py` — reconciliation
  tolerance + docstrings.
- `mlb_baseball/export.py` — allow-list entries for the new relations.
- `mlb_baseball/health.py` / `mlb doctor` — new envelope + scope checks.
- `docs/DECISIONS.md` (ADR-282 update), `docs/RESEARCH.md`,
  `docs/DATA_DICTIONARY.md`, `docs/TABLE_CONTRACTS.md`, `openspec/project.md`
  NOW block.
- `transforms/models/park_factor*.sql` — audited (they use CTE aliases named
  `team_season_*`, not the gold table; confirm).
- No model-feature or `gold.game_feature` change — those already scope
  `game_type = 'regular'` everywhere (verified: `gold.game_feature` is 100%
  regular, ~20 build files carry the filter).
- Data rebuild: re-ingest `raw.bref_*`, re-run `mlb report`.
