## Context

See `proposal.md` - Why for the full background. Key facts that shape this
design, confirmed directly against production `mlb`:

- `raw.statcast_pitch.arm_angle` (Statcast's own published per-pitch arm
  angle, Hawk-Eye biomechanic tracking): populated 2020-2026, ~97% filled
  2021 onward, 0% before 2020. It does not exist before Statcast started
  publishing it — there is no way to backfill a real value for older
  seasons.
- `raw.statcast_pitch.estimated_ba_using_speedangle` (Statcast's own xBA
  model) and `.babip_value`: populated 2015-2026 on batted-ball rows only
  (both are ~0 on non-batted-ball pitches, by design — not a data gap).
- `raw.statcast_pitch` also carries full release/trajectory kinematics
  (`release_pos_x/y/z`, `vx0/vy0/vz0`, `ax/ay/az`, `pfx_x/pfx_z`,
  `plate_x/plate_z`) back to 2008.
- `core.game.home_score`/`away_score` exist for computing real per-team
  runs-scored/runs-allowed (already used elsewhere in the codebase; the
  exact query pattern needs a `season`/`game_date`/`game_type` filter
  matching `season.py`'s existing `load_schedule_from_db`).
- `mlb_baseball/model/vaa.py` (already fixed in PR #240) sets the pattern
  this design follows for `pitch_tunneling_engine`: derive an exact
  trajectory position from the pitch's own measured `vy0`/`ay`/`vz0`/`az`
  kinematics via closed-form projectile-motion equations, not an
  approximation.
- `mlb season-sim` (`cli.py`) currently has no point-in-time cutoff
  argument; it only takes `--season`/`--sims`/`--seed`/`--json`.

## Goals / Non-Goals

**Goals:**
- Each of the four engines has at least one real, cited, data-driven code
  path in addition to (not replacing) any existing hand-typed what-if mode.
- No claim in a catalog `citation` field covers more than what the code
  actually reproduces.
- `season-sim`'s default behavior differentiates teams by real performance
  as of a real point-in-time cutoff, with no lookahead.

**Non-Goals:**
- Backfilling or approximating `arm_angle` for pre-2020 seasons — those
  pitchers/seasons get an honest "no real measurement available" result,
  not a synthetic estimate.
- Building a tuned/regressed team-strength model (Marcel-style shrinkage,
  park adjustment, strength-of-schedule). The fix is the direct,
  already-cited Pythagorean-from-real-runs swap the triage flagged; a
  better team-strength model is future work, not this change.
- Pinning down every historical BP pitch-tunnels threshold if the specific
  published numbers cannot be found during implementation. See Decisions
  below for the fallback.
- Any change to `gold`/`feat` output, SQLMesh models, or CI catalog
  enforcement itself.

## Decisions

### 1. `arm_slot_engine`: read `arm_angle` directly; keep dispersion as a separately-labeled sub-score

Use `AVG(arm_angle)` (or the catalog's existing tier boundaries applied to
that average) over a caller-specified pitcher + date range as the real,
cited angle and tier. Drop the uncited "shoulder = 82% of height"
trigonometry entirely — it is now dead code once a real measurement exists
and has no reason to survive as a fallback (a wrong estimate is worse than
an honest "no data").

The release-consistency / "elite release tunnel" sub-score has no
citable published source found. Rather than delete it or leave it
uncited-but-implied-real, recompute it from `STDDEV(arm_angle)` (a real
statistical property of real per-pitch data) instead of a caller-typed
dispersion number, and keep its `citation` as `project-derived` in the
catalog — same as several already-accepted `complexity: arithmetic`
entries elsewhere in the catalog. This satisfies "citation covers only
what it supports": the angle is now real+cited, the consistency score is
real-data-driven but its 0-100 scaling and tier cutoffs remain an honest
project-derived heuristic, not attributed to the arm-angle citation.

**Alternative considered**: derive dispersion from real release-point
(`release_pos_x`/`release_pos_z`) spread instead of arm-angle spread.
Rejected for this pass — `arm_angle` is already the metric being read, and
using the same column avoids a second, independent data-quality
investigation; release-point-based dispersion can be a later enhancement
if a real citation for it turns up.

### 2. `babip_luck_scanner`: xBABIP from `estimated_ba_using_speedangle`, actual BABIP computed the same way BABIP is actually defined

Compute, for a caller-specified batter + date range, over the batter's own
non-home-run balls in play:
- actual BABIP = hits / (balls in play), computed directly from `events`/
  `bb_type`/`description` in `raw.statcast_pitch` (the standard BABIP
  definition: `(H - HR) / (AB - K - HR + SF)`), not from the `babip_value`
  column until its exact per-row semantics are confirmed against real rows
  (see Open Questions).
- expected BABIP = `AVG(estimated_ba_using_speedangle)` over the same
  balls-in-play population, per Statcast's own Expected Statistics
  methodology (already cited by `model/statcast_expected.py` — reuse that
  citation).

This replaces the uncited linear formula entirely rather than keeping it
as a fallback — an uncited formula presented as an estimate is exactly the
finding being fixed, so it should not survive as a silent default.

**Alternative considered**: keep the linear formula as a fast, no-DB-read
approximation for a "quick estimate" CLI flag. Rejected: the proposal's
CLI-surface change already keeps a hand-typed what-if mode for scouting
inputs; adding a second uncited approximation path reintroduces the same
problem the triage flagged.

### 3. `pitch_tunneling_engine`: real kinematics for the tunnel-point position, honest labeling for unsourced thresholds

Replace the `poc_factor = 0.30` linear approximation with the exact
closed-form trajectory position at the tunnel point, using the same
projectile-motion approach `vaa.py`'s `pitch_vaa_degrees()` already uses
for VAA: integrate each pitch's own `vx0/vy0/vz0`/`ax/ay/az` to get real
x/z position at the tunnel-point distance (Baseball Prospectus's own
"~175ms before plate crossing" definition — consistent with the `23.8 ft`
already in the existing docstring), instead of assuming movement scales
uniformly as `t^2` of total break. This is exact physics from real
per-pitch data, not an approximation, and mirrors an already-accepted
project pattern.

The `tunneling_quality_score`/`whiff_boost_pct` formulas and the specific
elite-tunnel thresholds (`POC <= 8.5in`, `plate split >= 16.0in`) have no
confirmed published source. Implementation must do a real literature check
(BP's original 2017 article and any follow-ups) before deciding: if real
published thresholds are found, cite them; if not, keep the ratio-based
score (which does resemble the published "tunnel ratio" concept per PR
#240's own audit) but label its specific thresholds `project-derived` in
the catalog, same treatment as arm-slot's dispersion score above. Either
outcome is compliant with the new capability spec; which one applies is
resolved during implementation, not decided here (see Open Questions).

### 4. `season_monte_carlo_simulation`: point-in-time Pythagorean from real runs, explicit zero-games fallback

Add a `team_strength_asof(season: int, as_of: date, conn) -> dict[str,
float]` helper that, for each team, aggregates `core.game.home_score`/
`away_score` for `game_type = 'regular'` games with `game_date < as_of`
(strict inequality — the cutoff game itself must not leak in) within the
given season, and feeds the resulting runs-scored/allowed-per-game into
the already-cited `pythagorean_team_win_pct()`. A team with zero qualifying
games gets exactly `0.500` (the existing default), explicitly documented
in the function's docstring and in a returned/loggable flag as "no prior
games — league-average fallback," not silently indistinguishable from a
team that was computed and happens to be exactly average.

Add `--as-of DATE` to `mlb season-sim` (default: today, i.e. simulate the
rest of the season using everything known so far — the CLI's normal use
case), and wire its handler to call `team_strength_asof()` instead of the
hardcoded `{t: 0.500 for t in ALL_MLB_TEAMS}`.

**Alternative considered**: blend the Pythagorean estimate with
`marcel_project_rate()` (already in the same module, already flagged as
uncited) for early-season shrinkage. Rejected as out of scope — that adds
a second uncited-formula surface to fix inside what should be a bounded
placeholder swap; tracked as a future enhancement, not blocking this
change.

## Risks / Trade-offs

- [Small-sample noise] Early in a season, a handful of games' Pythagorean
  win% is a noisy team-strength estimate → Mitigated by the explicit
  zero-games-only fallback (not a small-sample fallback) — this design
  intentionally does not try to fix statistical noise, only the
  categorically worse problem of every team being identical. A better
  small-sample treatment is future work (see Decision 4 alternative).
- [`arm_angle`/`estimated_ba_using_speedangle` coverage gaps] Pre-2020 (arm
  angle) or pre-2015 (xBA) pitchers/seasons have no real value → Mitigated
  by the explicit "no data" scenario in the spec; the engines must not
  silently substitute a default.
- [BP tunnel-methodology thresholds may not be findable] → Mitigated by
  Decision 3's honest-labeling fallback; either outcome keeps the catalog
  entry truthful.
- [Query performance] Ad hoc aggregation over `raw.statcast_pitch` (13.6M
  rows) or `core.game` per CLI invocation could be slow → Existing indexes
  cover `pitcher`, `batter`, `game_date`, `game_pk` on `statcast_pitch`;
  scope each new query to a specific player/date range (never an unfiltered
  full-table scan) and confirm with `EXPLAIN` during implementation.

## Migration Plan

No schema migration. Rollout is a normal PR: land the four module changes,
catalog YAML updates, and tests together; no phased rollout or feature flag
needed since these are internal/CLI-invoked calculators with no external
callers or `gold`/`feat` dependents to break. Rollback is a normal revert.

## Open Questions

- Exact per-row semantics of `raw.statcast_pitch.babip_value` (does it need
  a separate denominator column, or is it already a 0/1 "counts as a BABIP
  hit" flag on qualifying rows only?) — resolve by inspecting real rows
  during implementation; does not change the spec (actual BABIP is
  defined the standard way regardless of which column computes it) or the
  task breakdown, only which SQL expression task 2 writes.
- Whether Baseball Prospectus's original 2017 article (or a follow-up)
  publishes the specific `tunneling_quality_score`/elite-tunnel threshold
  constants — resolve via literature check in task 3; Decision 3 already
  specifies the fallback if no source is found, so this does not change
  the approach, only whether those specific numbers get a citation or an
  honest `project-derived` label.
