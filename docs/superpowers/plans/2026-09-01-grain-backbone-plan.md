# Grain-complete statistic backbone — plan

Executes `docs/superpowers/specs/2026-09-01-grain-complete-stat-backbone-design.md`.

## Stage 1 — classical counting/rate backbone

| # | Relation | Source | Status |
|---|---|---|---|
| 1 | `gold.batting_game` | `raw.retrosheet_event` | **in review** — migration 0094, `sql/batting_game_build.sql`, wired into `mlb report` + doctor, integration tests with hand-math + idempotency. PR for this. |
| 2 | `gold.pitching_game` | `raw.retrosheet_event` | next — earned-run attribution (inherited runners) is the hard part; use Retrosheet's `er` where the game data carries it, otherwise document the gap |
| 3 | `gold.batting_season` / `gold.batting_team` | roll up `gold.batting_game` + `core.game` for team/season keys | + AVG/OBP/SLG/OPS/ISO/BABIP/BB%/K%. **Tie-out test vs a real Baseball-Reference player-season.** |
| 4 | `gold.pitching_season` / `gold.pitching_team` | roll up `gold.pitching_game` | + ERA/RA9/WHIP/K9/BB9/HR9/K:BB |
| 5 | `gold.batting_career` / `gold.pitching_career` | roll up the season tables | simple sum + career rates |
| 6 | `gold.batting_live` / `gold.pitching_live` (2026+) | `raw.mlb_playbyplay` | mirrors `offense.py::compute_live`; a separate builder, unioned into the season tables via a `source` column |
| 7 | ADR + docs | — | decide: does `gold.player_season` (BRef, 2008+) become a view over the new tables, or stay as the "official-source" alternative? One choice, recorded. |

Relations 2–6 are delegatable to Agy against relation 1 as the worked
example, once its column contract is merged.

## Stage 2 — advanced layer at the new grains

| # | Relation | Reuses |
|---|---|---|
| 1 | `gold.linear_weights` (season) | derived from `gold.run_expectancy_24` — the one genuinely new build |
| 2 | wOBA / wRC+ / wRAA on `gold.batting_season` / `_team` | `model/offense.py` constants |
| 3 | FIP / xFIP / SIERA on `gold.pitching_game` / `_season` | `model/starter.py`, `model/pitcher_estimators.py` |
| 4 | RE24 / WPA per PA | `model/run_expectancy.py` + `gold.run_expectancy_24` + `gold.win_expectancy` |
| 5 | BsR / wSB / UBR / wGDP on season/team | `model/bsr.py` |

Each still gets its own fixture + tie-out at the new grain.

## Stages 3–5 — roadmap

Historical-completeness honesty; parameterized rolling windows; export bundle
+ machine-readable stat catalog. Detailed once Stages 1–2 land.

## Definition of done per relation

Migration + named `.sql` builder + `mlb report` wiring + `mlb doctor` check +
integration tests (hand math, idempotency, and — for the season/career
relations — a real published-figure tie-out) + `DATA_DICTIONARY.md` /
`TABLE_CONTRACTS.md` rows + `mlb export` allow-list entry (after PR #123).
