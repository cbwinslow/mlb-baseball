## 1. Rights lock and decision record

- [ ] 1.1 `docs/DECISIONS.md` — one ADR: public-safe mart is the
  Retrosheet-id-keyed query surface for issue #89; `gold.player_season` /
  `gold.team_season` / `gold.division_standing` stay local-research;
  `--preset backbone` is unchanged; mart FIP uses an RA9-centering
  constant; wOBA uses the existing fixed `offense.py` weights applied to
  events, never `gold.fangraphs_guts`. Verify: next unused ADR number;
  cross-linked from this change's proposal.
- [ ] 1.2 Standing registry test (same idea as
  `tests/unit/test_fangraphs_conform_rights.py`): `gold.mart_*` entries in
  the export allow-list are `public_safe`; `gold.player_season`,
  `gold.team_season`, `gold.division_standing`, `gold.game_export`,
  `gold.game_feature`, `gold.fangraphs_*`, `gold.batting_postseason`,
  `gold.pitching_postseason` are not `public_safe`; `BACKBONE_TABLES` /
  `BACKBONE_EXCLUDED` are bit-for-bit unchanged. Verify: test fails if
  someone adds `player_season` to `public_safe` or the mart to
  `BACKBONE_CANDIDATES`.
- [ ] 1.3 `openspec/project.md` NOW/NEXT — one line that issue #89's
  public-safe mart is v1 finishing work complementing delivery-surface,
  not a Phase B item. Verify: it does not pull paused model/website work
  forward.

## 2. Schema and SQL ownership

- [ ] 2.1 Migration creating `gold.mart_player`, `gold.mart_team`,
  `gold.mart_game`, `gold.mart_player_game`, `gold.mart_player_season`,
  `gold.mart_team_season` with the keys and columns in `design.md` D1/D3
  (including additive advanced-stat components, `role`, `is_combined`,
  `source`, `_built_at`). PKs / unique keys / types reviewed. Additive
  only. Verify: `mlb migrate` on a scratch DB; `\d gold.mart_*` matches
  the contract.
- [ ] 2.2 Named SQL resources under `mlb_baseball/sql/mart_*.sql` (no SQL
  strings in Python). Builders read only Retrosheet raw tables (+
  `gold.run_expectancy_24` for RE24). Explicit regular-season filter on
  `raw.retrosheet_gameinfo`. Verify: `scripts/lint_sql_ownership.py`
  clean; grep of the new SQL shows no `core.` / `raw.bref_` /
  `raw.lahman_` / `raw.statcast` / `raw.mlb_` / `raw.fangraphs_`
  references.
- [ ] 2.3 `docs/SQL_OWNERSHIP.md` — one inventory row for the mart family
  (`mlb report`, grain, named SQL). Verify: the row names the files from
  2.2.

## 3. Identity tables

- [ ] 3.1 `gold.mart_player` from the already-ingested Retrosheet bio
  product (not Chadwick). Verify: a known Retrosheet id (e.g. a cited
  backbone tie-out player) has a name row; no `mlbam_id` / Chadwick
  key required on the public table.
- [ ] 3.2 `gold.mart_team` from Retrosheet team reference. Verify: a
  modern franchise and a historical franchise both resolve; no MLB Stats
  API team id on the public table.
- [ ] 3.3 `gold.mart_game` from `raw.retrosheet_gameinfo`, regular season
  only. Verify: a known regular-season `retro_game_id` is present; a
  postseason / All-Star gameinfo row is absent.

## 4. Player-game mart (counting + advanced)

- [ ] 4.1 Counting-stat insert for `role = 'batting'` and
  `role = 'pitching'` from `raw.retrosheet_event`, same event
  classification as `sql/batting_game_build.sql` /
  `sql/pitching_game_build.sql` (`bat_event_fl`, `ab_fl`, `event_cd`,
  `resp_pit_id`). Verify: sampled `(retro_game_id, retro_id)` counting
  stats match `gold.batting_game` / `gold.pitching_game` rows with
  `source = 'retrosheet_event'` for the same game (join via
  `core.game.retro_game_id` **only in the test**, not in the builder).
- [ ] 4.2 wOBA components + rate using `offense.py` weights inlined in
  named SQL (or bound as existing constants without reading
  `gold.fangraphs_guts`). Verify: hand-calculated fixture; a 2023
  league-average check in the same spirit as `offense.py`'s .317 note,
  documented as approximate.
- [ ] 4.3 FIP on pitching rows with seasonal RA9-centering constant
  computed from the same Retrosheet events. Verify: for a season with
  events, league FIP equals league RA9 within a documented rounding
  tolerance; `er` / `era` columns are absent from the mart.
- [ ] 4.4 RE24 from `gold.run_expectancy_24` changes on charged events.
  Verify: unit fixture on a tiny event sequence; NULL when the season
  matrix is missing.
- [ ] 4.5 wSB from event SB/CS; GB%/FB%/LD% from `battedball_cd`; K%/BB%
  as `so/pa` and `bb/pa`. Verify: NULL on zero denominator; a pre-1988
  game with empty `battedball_cd` does not store 0% as if it were
  measured.
- [ ] 4.6 Two-way player in one game produces two rows (`batting` and
  `pitching`). A player appearing for both clubs in one `retro_game_id`
  produces two team keys. Verify: fixtures for both.

## 5. Season and team roll-ups

- [ ] 5.1 `gold.mart_player_season` aggregated from `gold.mart_player_game`:
  stint rows + one `is_combined` row per `(retro_id, season, role)`;
  rates recomputed from sums. Verify: combined counting stats equal the
  sum of stints; AVG/wOBA/FIP are not the mean of game rates; a one-team
  player's combined row equals the stint.
- [ ] 5.2 `gold.mart_team_season` from the game grain (or from stint rows
  with `is_combined = false` so traded players are not double-counted).
  Verify: team HR equals sum of that team's batting-role game HR for the
  season.
- [ ] 5.3 Wire builders into `mlb report` in dependency order (identity
  → player-game → player-season / team-season) inside the existing
  reporting transaction. Verify: running `mlb report` twice on a fixture
  DB is idempotent (same row counts and values).

## 6. Export, doctor, profile

- [ ] 6.1 Register the six mart tables on `mlb_baseball/export.py`
  `RELATIONS` with `profile="public_safe"`. Verify: `mlb export --profile
  public_safe` on a scratch DB with mart rows writes one Parquet (or CSV)
  per mart table plus the existing five public_safe relations; manifest
  lists them; Retrosheet attribution is present.
- [ ] 6.2 Confirm `mlb export --preset backbone` file set is still exactly
  the eight counting-stat tables (plus exclusions for
  `player_season` / `team_season`). Verify: existing backbone export
  tests still pass; no new file named `mart_*` in the backbone out dir.
- [ ] 6.3 Doctor checks from `design.md` D5 (non-empty mart, Statcast
  column denylist, source = Retrosheet, public_safe denylist of
  local-research gold tables). Verify: a fixture that adds `hc_x` to a
  mart table fails doctor; a zero-row mart on a DB that has events fails
  doctor.

## 7. Docs

- [ ] 7.1 `docs/RESEARCH_QUERY_RUNBOOK.md` — public examples query
  `gold.mart_*` (player-season wOBA, team-season FIP, a single game line).
  BRef/Lahman/`game_export` snippets move under a **local-research (do
  not redistribute)** heading. Verify: no remaining unlabelled
  `gold.player_season` example in the public section.
- [ ] 7.2 `docs/DATA_DICTIONARY.md` and `docs/TABLE_CONTRACTS.md` — grain,
  keys, columns, formula citations, null policy, coverage 1910–last
  Retrosheet event season, 2026 exclusion. Verify: each mart table has a
  row; wOBA/FIP/RE24/wSB/GBFB caveats are stated.
- [ ] 7.3 `docs/SOURCE_RIGHTS.md` — one sentence that `gold.mart_*` is
  the public-safe player/team/game surface and inherits Retrosheet's
  "yes, with attribution" row. Verify: it does not claim Lahman or BRef
  became public-safe.
- [ ] 7.4 `docs/PUBLIC_API.md` — note that the Hugging Face backbone
  preset is unchanged; strangers who want the rights-strict dump use
  `mlb export --profile public_safe` after building the mart. Verify: no
  implication that `mlb_research.load("player_season")` started working.

## 8. Verification

- [ ] 8.1 `ruff` / `mypy` / `sqlfluff` clean on new/changed files.
- [ ] 8.2 Unit tests for rate formulas and rights registry; integration
  tests for report idempotency and public_safe export contents (real
  PostgreSQL where the test depends on SQL semantics, per
  `tests/AGENTS.md`).
- [ ] 8.3 `openspec validate public-safe-research-mart --strict` (or the
  repo's equivalent) passes.
- [ ] 8.4 EXPLAIN/ANALYZE of the new gold mart queries before ship
  (`openspec/project.md` gold definition of done) on a representative DB
  if available; otherwise record that production `mlb` was not reachable
  and leave it as an owner apply step.
