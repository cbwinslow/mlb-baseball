# Honest limitations

The backbone is built to be trustworthy, which means being explicit about what
it does **not** give you.

## Scope

- **Regular season only.** Every backbone relation excludes postseason games.
  Playoff batting and pitching live in separate `gold.batting_postseason` /
  `gold.pitching_postseason` relations (Lahman-sourced, player grain).
- **1910 onward, two pipelines.** Game-grain rows for **1910–2025** are built
  from Retrosheet play-by-play events. **2026 onward** is built from MLB's own
  official per-game box score (`raw.mlb_boxscore_batting` /
  `raw.mlb_boxscore_pitching`) — Retrosheet publishes no event file for the
  in-progress season. Each game row carries a `source` marker
  (`retrosheet_event` / `mlb_boxscore`); the season / team / career roll-ups
  aggregate both and are source-agnostic. The 2026 rows are MLB's
  scorer-assigned line, not event-derived — so a season-to-season comparison
  across the 2025/2026 boundary is comparing two different pipelines.
- **~200 recent 2026 games have no box score yet.** The MLB box-score feed
  lags a few days behind the schedule; `mlb report` re-run as ingest catches
  up fills them, and an `mlb doctor` join-coverage check makes the gap
  visible. Not a builder defect.
- **The 2020 season is real but short.** It is present in the data (60-game
  COVID season) but is excluded from the Baseball-Reference cross-check because
  it is not a useful reference point.

## Statistics that are deliberately missing

A measurement the source data cannot support is left **null with a stated
reason** — never imputed, never zeroed.

- **Earned-run average has a coverage cliff.** The Retrosheet event feed does
  not emit reconstructed-inning data, so `er` and `era` are **null for
  1910–2025**; `ra9` (runs allowed per 9) is the honest event-derived rate.
  From **2026** the MLB box score carries scorer-assigned earned runs, so `er`
  and `era` are populated. A naive average of `era` across the 2025/2026
  boundary is meaningless — use `ra9`, which is populated for every year.
  Official ERA per player-season for earlier years is in the
  Baseball-Reference-sourced `gold.player_season` line. Career `era` exists
  only for a pitcher whose entire career is 2026 or later. `era` is not
  carried at the team-season grain at all.
- **No stolen bases or caught stealing** in the batting relations — baserunning
  is deferred to a future `gold.baserunning_*` relation, even though the 2026
  box score carries steals.
- **Grounded-into-double-play undercounts before 1988** — upstream batted-ball
  coding is sparse in earlier years.
- **A rate statistic is null when its denominator is zero** (a pitcher with no
  walks has a null `k_bb`, a position player with no at-bats has null `avg` /
  `obp` / `slg`).

## Tie-out is close, not exact

Each relation has hand-calculated unit fixtures and an `mlb doctor` check, and a
two-part Baseball-Reference tie-out gate: documented **cited cases** (every
expected value read from a named Baseball-Reference page — Aaron Judge 2022,
Gerrit Cole 2023 — matching counting stats exactly and rates to displayed
precision) and a **bulk cross-check** of the event-derived season tables against
the Baseball-Reference-lineage `gold.player_season` for every qualified
player-season, gated on a small documented tolerance.

**Exact tie-out is not achievable at the career grain, nor for seasons much
before 2000.** Retrosheet's event record and Baseball-Reference's official
record have each absorbed decades of independent scoring corrections, so they
differ by small amounts. This is a source-of-record divergence, not a builder
error.

**2026 is checked against play-by-play, not Baseball-Reference.** There is no
Baseball-Reference page for the in-progress season, so the 2026 box-score-built
game lines are cross-checked field-by-field against an independent
reconstruction from `raw.mlb_playbyplay` events
(`scripts/verify_mlb_boxscore_tie_out.py`), gated on a small documented
tolerance over a sample of complete games. This stands in for the
Baseball-Reference tie-out.

## Distribution

- **The backbone relations are `local_research`, not `public_safe`.** Their
  builders join the conformed `core` dimensions (which mix non-Retrosheet
  sources) for surrogate keys. A `public_safe` variant keyed by Retrosheet
  identifiers is permitted future work and should not be assumed to exist.
- **`player_season` and `team_season` are built but not published** on
  source-rights grounds; the browser [query page](query/index.html) exposes the
  eight Retrosheet-derived relations only.

## Two season lines, on purpose

`gold.player_season` / `gold.team_season` (Baseball-Reference / Lahman sourced,
2008 onward, carrying `era` and other official fields) and the event-derived
`gold.batting_season` / `gold.pitching_season` (1910 onward, team-aware, `ra9`
for every year and `era` only from 2026) are **parallel sources for different
purposes**. Neither is a view
over, or a second writer into, the other. Each row is labelled with its source.

## Full write-up

The complete honest-limitations and negative-results record is in
[`docs/RESEARCH.md`](https://github.com/cbwinslow/mlb-baseball/blob/main/docs/RESEARCH.md).
