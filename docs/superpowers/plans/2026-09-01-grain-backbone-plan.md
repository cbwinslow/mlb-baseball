# Grain-complete statistic backbone — plan

Executes `docs/superpowers/specs/2026-09-01-grain-complete-stat-backbone-design.md`.

## Stage 1 — classical counting/rate backbone

| # | Relation | Source | Status |
|---|---|---|---|
| 1 | `gold.batting_game` | `raw.retrosheet_event` | **done — PR #126** (ADR-278). Migration 0094, `sql/batting_game_build.sql`, wired into `mlb report` + doctor, hand-math + idempotency tests. |
| 2 | `gold.pitching_game` | `raw.retrosheet_event` | **done — PR #126.** Migration 0095. Runs charged per responsible pitcher (`resp_pit_id` + `run{1,2,3}_resp_pit_id`). `er`/`era` deferred: reconstructed-inning logic cwevent does not emit — `r` + season RA9 are the honest figures. |
| 3 | `gold.batting_season` / `gold.batting_team` | roll up `gold.batting_game` | **in progress — WS-3a.** Migration 0096, `sql/batting_season_build.sql` + `sql/batting_team_build.sql`. AVG/OBP/SLG/OPS/ISO/BABIP/BB%/K% computed at grain. `batting_season` = per-team stint rows + one `is_combined` full-season row per player (`team_id` NULL); `batting_team` = one row per `(team, season)`. SB/CS/SB% omitted (not in `batting_game` yet). Rates NULL on zero denominator. Tie-out vs a real Baseball-Reference player-season still to add. |
| 4 | `gold.pitching_season` / `gold.pitching_team` | roll up `gold.pitching_game` | **in progress — WS-3b.** Migration 0097, `sql/pitching_season_build.sql` + `sql/pitching_team_build.sql`. Same combined-row shape as relation 3. RA9/WHIP/K9/BB9/HR9/K:BB computed at grain, NULL on zero `outs` (K:BB NULL on zero BB). **Not ERA** — no earned runs at this grain. |
| 5 | `gold.batting_career` / `gold.pitching_career` | roll up the season tables | **in progress — WS-3c.** Migration 0098. One row per player, summing each player's per-season `is_combined` rows; adds `seasons`/`first_season`/`last_season`; career rates recomputed from totals. `pitching_career` has `ra9` not ERA. |
| 6 | ADR + docs | — | decide: does `gold.player_season` (BRef, 2008+) become a view over the new tables, or stay as the "official-source" alternative? One choice, recorded. |

**Deferred out of Stage 1** (separate, later work item): `gold.batting_live` /
`gold.pitching_live` for 2026+ from `raw.mlb_playbyplay`, mirroring
`offense.py::compute_live`, unioned into the season tables via a `source`
column. Not needed for the 1910-2025 backbone.

Relations 2–6 are delegatable to Agy against relation 1 as the worked
example, once its column contract is merged.

**Tie-out contract for relation 3 onward (blocking, write before starting):**
Retrosheet-derived season lines will not match Baseball-Reference exactly —
different underlying data, corrections, and era-specific scoring judgment,
more so pre-1988. "Tie-out" here means: counting stats (H, BB, SO, ...) match
exactly or the delta is understood and documented (e.g. a known BRef
correction); rate stats (AVG/OBP/SLG) match within a few thousandths. A
documented, understood delta is a pass — it is not a blank check, so any
delta must be traced to a specific, named cause before the test is allowed to
pass with tolerance. An unexplained delta blocks the relation. Written down
here so whoever picks up relation 3 (Agy or otherwise) doesn't stall on the
first real BRef mismatch without a documented rule to apply.

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
`TABLE_CONTRACTS.md` rows + `mlb export` allow-list entry (the export/interop
layer PR #123 needed for that entry is merged) in the `public_safe` rights
profile — every relation here is Retrosheet-derived, so it stays
Retrosheet-only `public_safe` (which already emits the required Retrosheet
attribution + `MANIFEST.json` per bundle) and never `licensed_full` without a
recorded license (`docs/SOURCE_RIGHTS.md`).

All migrations, fixtures, tests, and database writes go through `mlb_test`
(the per-run isolated clone `tests/conftest.py` provisions), never production
`mlb` — `CLAUDE.md` golden rule. Chronological / no-lookahead correctness is
not a concern for these relations (they are final game results, not pregame
features), but idempotency and the tie-out are mandatory gates, and `ruff` /
`ruff format` / `mypy` / `sqlfluff` must pass clean.
