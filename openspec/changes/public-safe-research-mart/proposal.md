## Why

Issue #89 asks for a **public-safe research mart**: player, team, and game
tables a stranger can query. The two-product test in `openspec/project.md`
is the same question: *does this help a stranger build their own research
database?* If yes, it ships in `mlb-research`. This is Phase A / v1
finishing work (`research-db`), not Phase B.

The counting-stat backbone already exists and already leaves the building
through `mlb export --preset backbone` (`openspec/changes/archive/2026-09-06-delivery-surface/`,
published as Hugging Face `cbwinslow/mlb-research` `v0.1.0`). That preset
ships **8 of 10** candidate tables. `gold.player_season` and
`gold.team_season` were excluded on rights grounds
(`rights-review.md`): Baseball-Reference and Lahman are not
redistributable. The eight that ship (`gold.batting_*` /
`gold.pitching_*` at game / season / team / career) are still registered
`local_research` in `mlb export`, because they are keyed by mixed-source
`core.*` surrogate IDs. `mlb export --profile public_safe` therefore still
does **not** include any player/team/game box-score table — only raw
Retrosheet events plus the RE24 / WE / LI matrices.

So a stranger today can download counting stats from Hugging Face, but
cannot:

- get a **rights-clean player/team/game mart** from `--profile public_safe`
  (the dump path issue #89 names);
- query **wOBA, FIP, RE24, wSB, GB/FB/LD** at player-game and player-season
  on a public-safe grain (K%/BB% already live on `gold.batting_season`;
  they are not a new invention);
- follow `docs/RESEARCH_QUERY_RUNBOOK.md`, which still points at
  `gold.player_season` / `gold.team_season` / `gold.division_standing` /
  `gold.game_export` — tables this repo's own rights docs say must not be
  redistributed.

This change is the missing public query surface. It does not rebuild the
backbone, does not republish the Hugging Face `backbone` preset, and does
not expose any table `docs/SOURCE_RIGHTS.md` marks non-redistributable.

## What Changes

- **A Retrosheet-id-keyed mart** (`gold.mart_player`, `gold.mart_team`,
  `gold.mart_game`, `gold.mart_player_game`, `gold.mart_player_season`,
  `gold.mart_team_season`) built only from Retrosheet products
  (`raw.retrosheet_event`, `raw.retrosheet_gameinfo`, Retrosheet bio /
  team reference). Keys are Retrosheet identifiers (`retro_id`,
  `retro_team_id`, `retro_game_id`), never `core.player` / `core.team` /
  `core.game` surrogates. That is the "public_safe variant keyed by
  Retrosheet identifiers" already named as permitted future work in
  `openspec/specs/statistic-backbone/spec.md`.
- **Advanced stats on the player-game and player-season grains**, computed
  from Retrosheet events with published formulas: wOBA, FIP, RE24, wSB,
  K%/BB%, GB%/FB%/LD%. Missing measurements stay NULL (no Statcast fill,
  no FanGraphs Guts! table, no Baseball-Reference WAR).
- **`--profile public_safe` includes the mart.** `mlb export --preset
  backbone` is unchanged (still the eight counting-stat tables, still the
  Hugging Face v0.1.0 contract). This change extends the *rights-filtered
  dump*, not the backbone publish preset.
- **Doctor checks** that the mart has rows and that the public dump
  contains no Statcast-derived columns (`hc_x` / `hc_y` and kin), no
  Baseball-Reference / Lahman / FanGraphs / MLB-boxscore content, and no
  `gold.player_season` / `gold.team_season` / `gold.division_standing` /
  `gold.game_export` / `gold.fangraphs_*`.
- **`docs/RESEARCH_QUERY_RUNBOOK.md`** is rewritten to query the mart for
  any public/redistributable example, and to label the BRef/Lahman tables
  as local-research only.

**Explicitly not in this change:** no Hugging Face republish, no new
`--preset` that replaces `backbone`, no SQLMesh cutover, no career-grain
mart (strangers sum seasons), no `gold.baserunning_game` as a new
backbone relation (steal counts land as mart columns), no 2026
`mlb_boxscore` rows (MLB Stats API is not public-safe), no Engine
tables (`gold.game_feature`, predictions, `feat.*`).

## Capabilities

### New Capabilities

- `public-safe-mart`: a Retrosheet-keyed player / team / game query
  surface a stranger can dump under `MLB_DATA_PROFILE=public_safe` /
  `mlb export --profile public_safe`, with cited advanced stats and
  doctor/export guards that keep non-redistributable sources out.

### Modified Capabilities

- `statistic-backbone`: the deferred "public_safe variant keyed by
  Retrosheet identifiers" is this mart. The eight `gold.batting_*` /
  `gold.pitching_*` relations stay `local_research` (core-keyed). They
  are not reclassified.
- `delivery`: the public-safe export bundle gains the mart tables. The
  `backbone` preset, Hugging Face layout, and `mlb-research.load()`
  table list are unchanged.

## Impact

- **New:** `gold.mart_*` tables (migration), named `mlb_baseball/sql/mart_*.sql`
  builders wired into `mlb report`, export-allow-list rows with
  `profile=public_safe`, doctor checks, runbook + data-dictionary +
  table-contract entries, one ADR for the mart/rights split.
- **Changed:** `mlb_baseball/export.py` allow-list / `--profile public_safe`
  contents; `docs/RESEARCH_QUERY_RUNBOOK.md`; `docs/DATA_DICTIONARY.md`;
  `docs/TABLE_CONTRACTS.md`; `docs/SQL_OWNERSHIP.md` (mart SQL ownership);
  `openspec/project.md` NOW/NEXT one line that this is the public query
  surface for issue #89.
- **Unchanged:** `BACKBONE_TABLES` / `BACKBONE_EXCLUDED`, Hugging Face
  `v0.1.0`, `packages/mlb-research` loader, `gold.player_season` /
  `gold.team_season` (local-research official lines, ADR-281), FanGraphs
  guts/park-factor tables, `feat.*`.
- **No production overwrite of existing gold backbone rows.** Mart tables
  are additive.
