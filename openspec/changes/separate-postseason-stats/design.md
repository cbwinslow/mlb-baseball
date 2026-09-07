## Context

See `proposal.md` — Why, and ADR-282 for the full finding. Current state:

- `raw.bref_batting` / `raw.bref_pitching` (from `pybaseball.batting_stats_bref`
  / `pitching_stats_bref`) are **regular + postseason** for playoff teams'
  players, 2021+. pybaseball queries a fixed `{season}-03-01` → `{season}-11-30`
  Baseball-Reference range; `batting_stats_range` has no season concept, it
  scrapes whatever games fall in the window.
- `gold.player_season` / `gold.team_season` (built by `mlb_baseball/report.py`
  from `raw.bref_*`) inherit the contamination. Nothing else does:
  `gold.game_feature` is 100% `game_type = 'regular'`, ~20 `mlb_baseball/sql/*`
  builders carry an explicit filter, and the event backbone
  (`gold.batting_season` etc.) filters `lower(g.game_type) = 'regular'`.
- `raw.retrosheet_event` already contains postseason events (`_group =
  'postseason'`, ~147k rows), and `core.game.game_type` labels every game:
  regular / spring / exhibition / allstar / **wildcard / divisionseries / lcs /
  worldseries / championship / playoff**.
- `raw.bref_war_batting` / `raw.bref_war_pitching` (from `bwar_bat` /
  `bwar_pitch`, Baseball-Reference's downloadable WAR CSV) are **clean** —
  regular season only — but carry only a thin column set (`g`, `pa`, `gs`,
  `ra`, `war`, `waa`, `era_plus`; no full box line, no `er`/`era`).
- A prior session documented the contamination in
  `mlb_baseball/model/starter.py`'s docstring and absorbed it into a
  reconciliation tolerance.

## Goals / Non-Goals

**Goals:**
- `raw.bref_*`, `gold.player_season`, `gold.team_season` become regular-season
  only.
- New separate postseason relations, event-derived, at player-season and
  team-season grains.
- Every game-aggregating `gold` relation has an explicit, documented
  `game_type` scope; a `mlb doctor` envelope check guards against regression.
- A fresh `mlb bootstrap` produces separated data with no manual step.

**Non-Goals:**
- No change to `gold.game_feature` or any model feature (already regular-only).
- No postseason *game*-grain relation in this change (season + team only;
  game-grain postseason box lines are a noted follow-up).
- No new external data source or dependency.
- Not reworking ADR-281's two-parallel-season-lines decision — this keeps them
  parallel, just both regular-season only.

## Decisions

### D1 — Fix `raw.bref_*` at the source: end the query at the regular-season boundary

`mlb_baseball/connectors/bref.py` stops calling `pybaseball.batting_stats_bref`
/ `pitching_stats_bref` and calls `pybaseball.batting_stats_range` /
`pitching_stats_range` directly with `f'{season}-03-15'` → a
**regular-season end date**. `gold.player_season`'s builder needs no change;
`era` / `whip` / every field stays clean.

End date: the regular season has ended by the first days of October in every
season (Game 162 is scheduled for late September / Oct 1; the Wild Card round
opens Oct 1–3). Use **`{season}-10-01`** as the default and allow an override
per season for the rare late finish (2021's Game 163 tiebreakers were Oct 4–5;
pre-2022 tiebreaker games — treat those as regular season and set the override).
The `mlb doctor` envelope check (D4) catches any residual leak; a small
under-count from a Game 162 played Oct 2 is caught the same way and the
override fixes it.

Alternative considered: leave `raw.bref_*` alone and re-source
`gold.player_season`'s counting stats from the event backbone, taking only
`war` from `raw.bref_war_*`. Rejected — it loses a clean `era` (neither the
event backbone nor `bref_war` has earned runs), blurs ADR-281's parallel-lines
line, and is more code than a date change.

### D2 — New relations: `gold.batting_postseason` / `gold.pitching_postseason`

Player-season and team-season grains. Same column shape as the regular-season
season tables (`gold.batting_season` / `gold.pitching_season`) so a researcher
can `UNION`/compare directly, plus:

- one **per-round** row per `(player, season, round)` where `round` is the
  `game_type` (`wildcard` / `divisionseries` / `lcs` / `worldseries`), and
- one **combined** all-rounds row per `(player, season)` — the same
  `is_combined` pattern the regular-season season tables already use.

Team grain: one combined row per `(team, season)` plus per-round rows.
Career grain: `gold.batting_postseason_career` / `gold.pitching_postseason_career`,
one row per player summing their postseason seasons — mirroring the
regular-season career tables so the ladder is symmetric.

Built by the same event pipeline as the backbone — a new
`mlb_baseball/sql/{batting,pitching}_postseason_build.sql` that is
`{batting,pitching}_game_build.sql` with the `game_type` filter inverted and a
`round` column added, rolled up. Migration(s) add the tables.

This mirrors Lahman's `BattingPost` / `PitchingPost` and Baseball-Reference's
separate postseason section — the universal convention.

### D3 — Pipeline audit produces a recorded game-type map

The audit task walks every `gold` builder (`mlb_baseball/sql/*.sql`,
`mlb_baseball/report.py`), every SQLMesh model in `transforms/`, every
materialised view, and every Python aggregation in `mlb_baseball/model/*.py`
and `mlb_baseball/*.py`, and records — in the change's `game-type-audit.md` —
for each relation: which `game_type`s it includes, where the filter is (or that
it is missing), and the fix if missing. `gold.game_feature` and the ~20 known
builders are expected to already be correct; the audit confirms and finds any
gap.

### D4 — `mlb doctor` guards

Two new checks in `mlb_baseball/health.py`:

- **Envelope:** fail if any `gold.player_season` row has `games > 162` or `pa`
  beyond a generous single-season ceiling (~780), or any `gold.team_season`
  row has `games > 162`. (162 is the hard regular-season max for one team.)
- **Postseason purity:** fail if any `gold.batting_postseason` /
  `gold.pitching_postseason` row traces to a game whose `game_type` is not a
  postseason type.

### D5 — Reconciliation + docs cleanup

`raw.bref_*` being clean means `mlb_baseball/model/starter.py` and
`mlb_baseball/model/bullpen.py`'s reconciliation health checks no longer need
the postseason-absorbing tolerance — tighten them and update the docstrings
(the Blake Snell example becomes "was a source-scope issue, fixed in
<this change>"). Update `docs/RESEARCH.md`, `docs/DATA_DICTIONARY.md`,
`docs/TABLE_CONTRACTS.md`, `openspec/project.md`'s NOW block, and mark ADR-282
resolved.

### D6 — Data rebuild

Clear the pybaseball on-disk `df_cache` for the affected `batting_stats_bref` /
`pitching_stats_bref` entries, re-ingest `raw.bref_*` for 2008–2026 (whole
range, one methodology), then `mlb report`. This is owner-run, like the
`v0.1.0` backbone build.

## Risks / Trade-offs

- **The Oct 1 cutoff is a heuristic** → Mitigation: the doctor envelope check
  catches both over- (postseason leaked in) and gross under-counts; a per-season
  override list handles the handful of tiebreaker/late-Game-162 cases; the
  cross-check against the event backbone (`verify_baseball_reference_tie_out.py`)
  re-enables its 2020+ comparison once this lands and would surface any residual.
- **Retrosheet postseason event completeness** varies for older years →
  Mitigation: the postseason relations inherit the same "deduced-era" caveat as
  the backbone; scope the tie-out-style validation to the modern era.
- **A rebuild of `gold.player_season` shifts numbers researchers may have
  already used** → Mitigation: it is a correction, documented in ADR-282 and
  the changelog; the pre-fix values were wrong.

## Open Questions

None. The per-season regular-season end-date list and the career-grain
postseason relations are both in scope (owner's direction: complete, no
shortcuts).
