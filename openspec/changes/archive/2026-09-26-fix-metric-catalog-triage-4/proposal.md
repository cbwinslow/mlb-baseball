## Why

The metric-catalog triage (PR #240, merged) flagged four `mlb_baseball/model/`
calculators as `status: implemented-untested`, `visibility: internal`,
`citation: project-derived` — code that runs, but whose formulas are either
uncited approximations or, for one, wired to a hardcoded placeholder instead
of real data:

- `arm_slot_engine` (`model/arm_slot.py`) — classifies arm slot from an
  uncited "shoulder is 82% of height" geometric assumption, and scores
  release consistency from an uncited dispersion formula. Never reads real
  data; only takes caller-supplied coordinates.
- `babip_luck_scanner` (`model/babip.py`) — an uncited linear xBABIP formula
  (`0.220 + 0.380*LD% + ...`) with uncited regression-tier cutoffs. Only a
  standalone CLI calculator (`mlb babip`); never reads a real batter's actual
  data.
- `pitch_tunneling_engine` (`model/tunnel.py`) — uncited constants
  (`poc_factor = 0.30`, the tunneling-quality-score formula, the elite-tunnel
  thresholds). Only a standalone CLI calculator (`mlb tunnel`); never reads
  real pitch-tracking data.
- `season_monte_carlo_simulation` (`model/season.py`) — the Monte Carlo
  harness already uses two real cited formulas (Bill James Log5,
  Pythagorean win% with the Smyth-Patel exponent). But `mlb season-sim`
  (`cli.py:1661`) calls it with `talents = {t: 0.500 for t in ALL_MLB_TEAMS}`
  — every team is given identical, fabricated "talent," so the simulation's
  own default output cannot differentiate any team from any other.

Since the triage, direct inspection of `raw.statcast_pitch` (production
`mlb`) found that Baseball Savant already publishes, and this project already
ingests, the exact real metrics two of these calculators were trying to
approximate by hand:

- `arm_angle` — Statcast's own official per-pitch Arm Angle (Hawk-Eye
  biomechanic tracking), populated 2020-2026 (~97% filled from 2021 on;
  `arm_slot_engine`'s hand-derived 82%-of-height geometry is an unnecessary,
  uncited proxy for a number the project already has).
- `estimated_ba_using_speedangle` (Statcast's own xBA model) and
  `babip_value`, populated 2015-2026 on batted-ball rows — the real inputs
  for an actual-vs-expected BABIP comparison, in place of
  `babip_luck_scanner`'s uncited linear formula.

`pitch_tunneling_engine` has real release/trajectory columns available
(`release_pos_x/y/z`, `vx0/vy0/vz0`, `ax/ay/az`, `pfx_x/pfx_z`,
`plate_x/plate_z`) to implement the actual published methodology (Baseball
Prospectus, Long/Pavlidis/Judge, "Introducing Pitch Tunnels," 2017) instead
of the current uncited approximation. `season_monte_carlo_simulation` has
real per-team runs-scored/runs-allowed in `core.game` (`home_score`/
`away_score`) to feed its already-cited `pythagorean_team_win_pct()`.

Per `openspec/project.md`'s ADR-291 clarification, "a metric implementing a
published, citable formula is Phase A / public regardless of whether it
currently lives under `model/`" — so bringing these four to a real citation
and a real data source is Phase A work, not a Phase B/Engine expansion. This
proposal is scoped narrowly to that: swap uncited approximations for cited,
real-data-backed formulas. It does not build new predictive models, does not
touch the Phase B "model ladder," and does not add new data sources.

## What Changes

- **`arm_slot_engine`**: read real per-pitcher `arm_angle` from
  `raw.statcast_pitch` (aggregated per pitcher over a season/date range)
  instead of deriving an angle from an uncited shoulder-height assumption.
  Cite Baseball Savant's Arm Angle leaderboard methodology. Keep (and
  re-cite, or drop if no citable source is found) the release-point
  dispersion/tunneling-consistency piece separately from the angle itself —
  these are two different claims and must not share one citation.
- **`babip_luck_scanner`**: compute real actual BABIP and a real xBABIP
  proxy (mean `estimated_ba_using_speedangle` over the same non-HR
  balls-in-play population BABIP itself covers) from `raw.statcast_pitch`
  for a real batter over a real date range, replacing the uncited linear
  formula. Cite Statcast's Expected Statistics methodology (the same source
  already cited by `model/statcast_expected.py`).
- **`pitch_tunneling_engine`**: reimplement against the real Baseball
  Prospectus pitch-tunnels methodology (Long/Pavlidis/Judge, 2017) using
  real release/trajectory columns from `raw.statcast_pitch` for a real
  pitcher's two real pitch types, replacing the uncited constants.
- **`season_monte_carlo_simulation`**: add a real team-strength estimator
  that computes each team's runs-scored/runs-allowed per game from
  `core.game` up to a caller-supplied point-in-time cutoff, and feeds that
  through the already-cited `pythagorean_team_win_pct()`. Wire `mlb
  season-sim` (`cli.py`) to use it instead of the hardcoded `0.500` for
  every team. Preserve a documented fallback (e.g. early season / no prior
  games) rather than silently defaulting to 0.500 forever.
- **CLI surfaces change**: `mlb babip` and `mlb tunnel` currently take only
  hand-typed numbers; each gets a new real-data mode (e.g. `--player`/
  `--season` or similar, following this project's existing CLI flag
  conventions) that looks the player/pitch-pair up in the database, while
  keeping the existing hand-typed mode as an explicit what-if/scouting path
  (documented as such, not implied to be the real one). `mlb season-sim`'s
  default team-talent behavior changes; a flag to force the old flat-0.500
  behavior is out of scope unless an existing test depends on it.
- **Catalog YAML updates**: `mlb_baseball/metrics/{arm_slot_engine,
  babip_luck_scanner, pitch_tunneling_engine, season_monte_carlo_simulation}.yaml`
  get real `citation`/`data_source` fields and a `status` promotion
  (`published`, or `validated` where a tie-out test against an independent
  published value is added) per the `metric-catalog` capability's existing
  status rules — no status is set without the evidence those rules require.
- **New/updated tests**: real-data-backed tests for each module (deterministic
  hand fixtures for the formulas themselves, plus a real-Postgres integration
  test where a module now queries `raw.statcast_pitch`/`core.game`).

**Out of scope / non-goals**: the 101 already-removed metrics and the 3
Engine-serving-layer metrics noted in PR #240; any new data source; the
Phase B "model ladder" (elastic-net/CatBoost/Bayes); building a full
walk-forward-backtested team-strength model (the Pythagorean-from-real-runs
estimator here is a direct, already-cited-formula swap, not a new predictive
model); changing `gold`/`feat` materialized output (none of these four are
currently wired into `gold.game_feature`, and this change does not wire them
in).

## Capabilities

### New Capabilities

- `sabermetric-calculator-engines`: standalone (non-`gold`-materialized)
  sabermetric calculator engines under `mlb_baseball/model/` — the ones a
  researcher or the CLI can invoke directly for a specific player/pitcher/
  team/season — must use a real, cited, published formula, and must compute
  from this project's own ingested data when the citable formula has a real
  data-driven form, rather than only accepting hand-typed inputs. This is
  new because no existing capability spec currently governs these
  standalone/CLI-invoked calculators as a class (`statistic-backbone`
  governs `gold`-layer relations tied out against Baseball-Reference, which
  is a different surface).

### Modified Capabilities

_None._ (`metric-catalog`'s status/citation/visibility rules already exist
and already apply to these four entries; this change brings the entries
into compliance with those existing rules rather than changing the rules
themselves.)

## Impact

- **Code**: `mlb_baseball/model/arm_slot.py`, `mlb_baseball/model/babip.py`,
  `mlb_baseball/model/tunnel.py`, `mlb_baseball/model/season.py`,
  `mlb_baseball/cli.py` (the `arm-slot`, `babip`, `tunnel`, `season-sim`
  command handlers).
- **Catalog**: the four corresponding
  `mlb_baseball/metrics/<name>.yaml` entries.
- **Tests**: `tests/unit/test_arm_slot.py`, `tests/unit/test_babip.py`,
  `tests/unit/test_tunnel.py`, plus `model/season.py`'s existing test
  coverage; new real-Postgres integration test(s) for the
  `raw.statcast_pitch`/`core.game`-reading paths.
- **Data**: read-only against existing `raw.statcast_pitch` and `core.game`
  in production `mlb` / the disposable test database. No new ingestion, no
  new source, no schema migration.
- **No impact** to `gold`/`feat` materialized tables, SQLMesh models, or any
  currently-published catalog entry outside these four.
