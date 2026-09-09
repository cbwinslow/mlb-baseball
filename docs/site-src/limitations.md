# Honest limitations

The backbone is built to be trustworthy, which means being explicit about what
it does **not** give you.

## Scope

- **Regular season only.** Every backbone relation excludes postseason games.
  Playoff batting and pitching live in separate `gold.batting_postseason` /
  `gold.pitching_postseason` relations (Lahman-sourced, player grain).
- **1910–2025.** The event-derived builder runs on Retrosheet play-by-play,
  which begins in 1910. A 2026-onward builder over MLB's play-by-play feed is
  planned follow-up work and is not shipped yet.
- **The 2020 season is real but short.** It is present in the data (60-game
  COVID season) but is excluded from the Baseball-Reference cross-check because
  it is not a useful reference point.

## Statistics that are deliberately missing

A measurement the source data cannot support is left **null with a stated
reason** — never imputed, never zeroed.

- **No earned-run average.** The Retrosheet event feed does not emit
  reconstructed-inning data, so the event-derived pitching relations carry
  `ra9` (runs allowed per 9), not `era`. Official ERA per player-season is in
  the Baseball-Reference-sourced `gold.player_season` line.
- **No stolen bases or caught stealing** in the batting relations — baserunning
  is deferred to a future `gold.baserunning_*` relation.
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
not `era`) are **parallel sources for different purposes**. Neither is a view
over, or a second writer into, the other. Each row is labelled with its source.

## Full write-up

The complete honest-limitations and negative-results record is in
[`docs/RESEARCH.md`](https://github.com/cbwinslow/mlb-baseball/blob/main/docs/RESEARCH.md).
