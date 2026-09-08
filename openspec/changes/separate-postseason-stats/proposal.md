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

**Reference implementation: baseball.computer.** Its `seed_game_types` marks
`RegularSeason` and `TiebreakerPlayoff` as `is_regular_season = true` and every
postseason series (`WildCardSeries`, `DivisionSeries`,
`LeagueChampionshipSeries`, `WorldSeries`, `OtherChampionship`) as
`is_postseason = true`; every one of its season / career / team-season metric
tables filters to the regular-season game types and is documented "Regular
season only". It publishes **no** separate postseason aggregate table —
postseason stays at the game/event grain behind the `is_postseason` flag. We
adopt the same rule for our aggregates and go one step further only where
Lahman already leads: a player-grain postseason total table, the direct
parallel to Lahman's `BattingPost` / `PitchingPost`.

The owner's direction: **regular-season aggregates are regular-season only —
tables, views, `mlb doctor` metrics, and every math / ML model feature** — and
**audit the whole pipeline (bootstrap, ingestion, views, SQL, Python, model
features) so postseason never lands in a regular-season number again.**
Postseason performance stays available in the raw Lahman / Retrosheet
postseason data and gets one player-grain gold total table.

## What Changes

- **`raw.bref_batting` / `raw.bref_pitching` become regular-season only.** Fix
  `mlb_baseball/connectors/bref.py` so its Baseball-Reference pull ends at the
  regular-season boundary, not November 30. Re-ingest every affected season
  (2021+; the whole 2008+ range for consistency). `gold.player_season` /
  `gold.team_season` then rebuild clean with no builder change.
- **New postseason relations** in `gold`, built from the postseason data
  **already ingested**: `raw.lahman_batting_post` / `raw.lahman_pitching_post`
  (Lahman's own `BattingPost` / `PitchingPost`, 1884–2025).
  `gold.batting_postseason` / `gold.pitching_postseason` at the **player-season
  and career** grains, with Lahman's `round` retained (per-round rows + a
  combined all-rounds row per player-season). Cross-checked against
  `raw.retrosheet_event` postseason plays. No new event-parsing — the direct
  parallel to Lahman's own `BattingPost` / `PitchingPost` (which are
  player-grain; Lahman ships no team postseason table, and neither does
  baseball.computer). A postseason **team** total is a trivial query off the
  player table and is left as a follow-up.
- **Pipeline audit + guards.** Review every `gold` builder, SQLMesh model,
  materialised view, Python aggregation, and **model / ML feature** that
  touches game-level data; confirm each explicitly scopes `game_type` (regular
  vs postseason) rather than relying on a source being "clean". Add an
  `mlb doctor` check that fails if any `gold.player_season` / `gold.team_season`
  row exceeds a 162-game / plausible-PA envelope, and a check that the
  postseason relations only contain postseason games.
- **Bootstrap + `mlb daily`**: verify the ingestion order and the connectors'
  own scoping so a fresh `mlb bootstrap` produces separated data with no manual
  step.
- **Reconciliation + docs**: tighten `starter.py` / `bullpen.py` reconciliation
  tolerances now that `raw.bref_*` is clean; update `docs/RESEARCH.md`, the
  `starter.py` docstring, `docs/DATA_DICTIONARY.md`, `docs/TABLE_CONTRACTS.md`,
  and ADR-282 (mark the fix landed).

## Capabilities

### New Capabilities

- `postseason-stats`: separate postseason batting and pitching relations at the
  player-season and career grains (built from Lahman's `BattingPost` /
  `PitchingPost`), and the rule that regular-season relations — including views,
  `mlb doctor` metrics, and model / ML features — never contain postseason
  games.

### Modified Capabilities

- `statistic-backbone`: add the requirement that the grain ladder — and every
  other `gold` relation, view, and model / ML feature — scopes `game_type`
  explicitly (baseball.computer's rule: aggregates are regular-season only,
  tiebreaker Game 163 counts as regular season), and that a `mlb doctor`
  envelope check guards against postseason contamination in any regular-season
  relation.
- `delivery`: `gold.player_season` / `gold.team_season` are regular-season only;
  the postseason relations are a separate part of the distribution with their
  own `local_research` profile.

## Impact

- `mlb_baseball/connectors/bref.py` — regular-season date boundary; re-ingest.
- `mlb_baseball/report.py` — the `_build_player_season` / `_build_team_season`
  SQL is unchanged in shape but rebuilds against clean raw; a new
  postseason-relation builder is added (`mlb_baseball/sql/*_postseason_build.sql`).
- New migration for `gold.batting_postseason` / `gold.pitching_postseason`
  (player-season + career grains).
- `mlb_baseball/model/starter.py`, `mlb_baseball/model/bullpen.py` — reconciliation
  tolerance + docstrings.
- `mlb_baseball/export.py` — allow-list entries for the new relations.
- `mlb_baseball/health.py` / `mlb doctor` — new envelope + scope checks.
- `docs/DECISIONS.md` (ADR-282 update), `docs/RESEARCH.md`,
  `docs/DATA_DICTIONARY.md`, `docs/TABLE_CONTRACTS.md`, `openspec/project.md`
  NOW block.
- `transforms/models/park_factor*.sql` — audited (they use CTE aliases named
  `team_season_*`, not the gold table; confirm).
- `mlb_baseball/model/*.py` + ML feature builders — audited for explicit
  `game_type` scope (the audit extends to model / ML code, not just `gold`
  builders). `gold.game_feature` already scopes `game_type = 'regular'`
  everywhere (verified: 100% regular, ~20 build files carry the filter);
  the audit confirms the model layer is the same and fixes any gap.
- Data rebuild: re-ingest `raw.bref_*`, re-run `mlb report`.
