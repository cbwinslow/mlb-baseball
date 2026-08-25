# Package validation status (Plan 06)

Tracks the 06A classification and validation status for every package added
since ADR-089, per `plans/06-package-validation-and-tieout.md`. This is a
tracking doc, not a design doc — `docs/DECISIONS.md` and
`docs/THEORY_AND_METHODOLOGY.md` remain the source of truth for what each
package does; this file only tracks whether it's been tied out.

## P0 — read this first

**The entire daily enrichment/prediction pipeline has been silently crashing
in real production for most of the last week.** Found while tying out
`run_expectancy.py`: `gold.game_feature.home_starter_id` (and everything
downstream of it — xFIP, SIERA, RE24, LI, platoon splits, command,
statcast_expected, and more) is NULL for all 216,730 games in real
production `mlb` right now. Root cause, confirmed directly from
`logs/mlb_daily_update.log` (the real cron log): `bsr.py`'s SQL referenced a
column (`gdp_fl`) that has never existed in real `raw.retrosheet_event`
(real name: `dp_fl`); because `enrich_feature_stage()` calls every module as
one eagerly-evaluated Python dict literal, `bsr.compute()` crashing partway
through has been silently blocking every module listed after it — every day,
5 of the last 6 scheduled runs (2026-08-19 through 2026-08-25, only 08-20
succeeded). Full detail, evidence, and fix: **ADR-260** in
`docs/DECISIONS.md`. Fixed and verified against real production (rolled-back
transaction) and the existing test suite (whose own fixture had the same
wrong column name — fixed too). **Not yet done: production has not been
backfilled** — the fix stops the crash going forward, but a real `mlb
predict` run (or the next scheduled cron) still needs to actually populate
the historical NULLs, and that should be watched to confirm it reaches
"finished daily update" rather than assumed fixed. This was found by, and is
now the top priority within, Plan 06 — everything below this line was
investigated with feature data that, it turns out, has not actually been
reaching production either.

Classification method: read every file in `mlb_baseball/model/`, checked
whether it queries `raw`/`core`/`gold` via `get_connection()` (real ingested
data available) or only takes hand-entered CLI arguments (no real data path
exists yet), and cross-referenced `docs/FEATURE_REGISTRY.md` for which
already carry a "Verified: `<real fact>`" note.

## Buckets

- **A** — established, published formula, wired to real ingested data
  (`raw`/`core`/`gold`). A real tie-out is directly possible.
- **A′** — established, published formula/technique (WPA, Kelly Criterion,
  Brier/Platt calibration), but currently a self-contained calculator, not
  wired to real game data. Tie-out is possible via known textbook worked
  examples / published WE tables, independent of this project's own data.
- **C** — infrastructure/simulation/orchestration tooling (backtester, Monte
  Carlo simulator, stacker, drift monitor, hedging/parlay/shopping
  calculators). Not a single "stat" with one external published value to
  match — needs internal-consistency/convergence checks instead of a
  FanGraphs-style tie-out. Out of Plan 06's primary scope; noted for
  completeness.
- **B** — invented composite index coined for this project (an "Engine"
  class with a made-up acronym score like OFLDII, BSEI, STCI). No public
  source defines "the correct value" — direct external tie-out is not
  possible as currently built. Needs a 06C remedy (refit, premise-check, or
  relabel), not a tie-out test.
- **B/sub** — Bucket B, but the underlying concept has a real, checkable
  typical/average value even though the composite index built on top is
  invented (e.g. real MLB average catcher pop time ≈ 2.0s is checkable even
  though "CEVI"/"POPTIME" score built from it is not). Worth tying out the
  *input benchmark constant*, even where the composite index itself can't be.

## A — established formula, real data (37 files)

`provenance`(22), `elo`(32), `gbm`(32), `log5`(32), `starter`(34),
`offense`(36), `war`(38), `bullpen`(39), `oaa`(40), `speed`(41),
`starter_workload`(42), `framing`(45), `market`(53), `total`(56),
`team_rate`(61), `markov`(80), `diff`(81), `trend`(83), `experience`(85),
`age`(87), `pitch_discipline`(89), `batted_ball`(90), `pitcher_estimators`(90),
`run_expectancy`(90), `platoon`(101), `bsr`, `command`, `park`,
`pitch_movement`, `statcast_expected`, `features`, `identity`, `evaluation`,
`experiment`, `feature_select`, `feature_select_stepwise`

**Already carry a real "Verified:" tie-out note in `docs/FEATURE_REGISTRY.md`**
(spot-check one or two before trusting fully — don't take the note itself as
proof without re-running the underlying test): `elo`, `gbm`, `offense`,
`war`, `oaa`, `bullpen`, `age`, `park`.

**No existing tie-out note — real work for 06B:** `provenance`, `starter`, `speed`, `starter_workload`, `framing`,
`market`, `total`, `team_rate`, `markov`, `diff`, `trend`, `experience`,
`batted_ball`, `pitcher_estimators` (xFIP, SIERA — exact
published formulas, high-value target), `run_expectancy` (RE24, Leverage
Index — exact published formula/table, high-value target), `platoon`, `bsr`
(wSB/UBR/XBT%/wGDP — exact published formulas), `command`, `pitch_movement`,
`statcast_expected`.

**Done this session:**
- `log5` — checked the known bug on record (`docs/PROJECT_REVIEW.md`:
  implemented as `pA²/(pA²+pB²)` instead of Tango's cited odds-ratio form).
  Already fixed in a prior session, confirmed by reading `log5.py` directly:
  `MODEL_VERSION = "log5-v2"`, the real formula
  `home(1-away) / [home(1-away) + away(1-home)]` is what's actually
  implemented now, with a detailed docstring explaining the v1 bug and the
  0/0 degenerate-case handling. No further action needed.
- `pitcher_estimators` — real SIERA formula bug found and fixed (ADR-259).
- `bsr` — real column-name bug found and fixed, the P0 pipeline-crash
  finding above (ADR-260); its `wGDP` metric was then also found to be
  overcounting non-groundball double plays and using a flat (not
  opportunity-adjusted) formula, fixed against real FanGraphs methodology
  with a run-value constant derived from this project's own real RE24
  matrix (ADR-261).
- `run_expectancy`'s Leverage Index (`home_starter_avg_li`/
  `home_bullpen_avg_li`) — **fully rebuilt on real data (ADR-262).** It was
  a hand-typed base/out-only table with invented constants; `wpa.py`, the
  engine that could have supplied a real one, turned out to have the same
  problem (claims a real 288-state Markov solution, actually a hand-typed
  logistic formula with its own invented constants — not fixed, see below).
  Built two new real, empirically-derived reference tables instead:
  `gold.win_expectancy` (real historical home-win rate per state, verified
  against real home-field-advantage/near-certain-win-or-loss reference
  points) and `gold.leverage_index` (real observed WE swing per state,
  normalized to LI=1.0 average, verified against a real cited high-leverage
  benchmark). Both populated against real production `mlb`
  (owner-authorized migrations 0083/0084). `team_leverage_re24_update.sql`
  now joins the real table instead of the hand-typed one.
  Its underlying `run_expectancy_matrix_build.sql` also had a second,
  independent bug, also fixed: its base-state filter listed values
  (`'020'`, `'003'`, `'120'`, `'103'`, `'023'`, `'123'`) that can never
  actually be produced by the code building `base_state` (binary 0/1 per
  base only) — silently limiting the "empirical" matrix to 2 of 8 real base
  states. Fixed to the real 8 states; the results land within ~0.07 runs of
  Tango's published *The Book* reference points (bases loaded/0 outs: 2.341
  here vs. 2.417 published; bases empty/2 outs: 0.106 vs. 0.098).
- `pitch_discipline` (CSW%/Whiff%/F-Strike%, `PIT-07`) — **tied out, real
  bug found and fixed (ADR-263).** Checked `team_pitch_discipline_retrosheet_update.sql`'s
  pitch-code classification directly against Retrosheet's own event-file
  spec (`retrosheet.org/eventfile.htm`, fetched directly) and Pitcher
  List's original 2018 CSW% definition (fetched directly, the article that
  coined the term): foul tips (Retrosheet code `T`) were missing from the
  CSW% numerator despite the cited definition explicitly including "foul
  tips into the glove", and hit-by-pitch (`H`) — a real, physically-thrown
  pitch — was missing from the total-pitch denominator shared by every
  rate in the file. Also removed a stray `W` character that isn't a real
  Retrosheet pitch code at all, and added the pitchout-swing family
  (`Q`/`R`/`Y`) for full agreement with the real code list (negligible
  practical impact, included for consistency with the cited formula).
  `K` (Retrosheet's "strike, unknown type") stays deliberately excluded
  from every type-specific numerator — a genuine data-ambiguity limitation
  documented in ADR-263, not a bug. New hand-calculated fixture in
  `tests/integration/test_model_pitch_discipline.py` proves the fix is a
  real behavior change (corrected CSW% = 10/22 ≈ 0.4545, not the pre-fix
  formula's 9/21 ≈ 0.4286). `docs/FEATURE_REGISTRY.md`'s
  `plate_discipline_v1` row also had stale file/test names left over from
  an early rename (`plate_discipline.py` → `pitch_discipline.py`,
  never actually committed under the old name) — fixed in the same change.

**Still open:** `run_expectancy`'s `home_bullpen_re24`/`home_batting_re24`
columns still use the pre-existing crude "runs vs. flat 0.12/PA league
average" proxy, not real RE24 (`gold.run_expectancy_24`'s own
ΔRE + runs-on-play definition) — the now-fixed matrix exists and could feed
a real RE24 the same `LEAD()`-based way `gold.leverage_index` was built, but
this was deliberately not rushed into the same pass. `wpa.py`'s own
`WinExpectancyEngine` (backing the separate `mlb wpa` CLI command, not
`gold.game_feature`) also still uses its unvalidated hand-typed formula —
not touched this session; see `docs/THEORY_AND_METHODOLOGY.md` §10.3 for
the full note on these two now-diverged implementations.

## A′ — established technique, self-contained (3 files)

`wpa` (Win Expectancy/WPA/Leverage Index — docstring claims Tango's
published 288-state WE methodology; **checked this session and that claim
is false** — the actual code is a hand-typed logistic formula with invented
constants, no Markov solve anywhere in it; see the `run_expectancy` note
above for the real, separately-built replacement now used by
`gold.game_feature`), `portfolio` (Kelly Criterion — exact closed-form,
Kelly 1956), `calibration` (Brier score, Platt scaling — standard,
textbook-exact).

## C — infrastructure/simulation tooling, not a single tie-out target (13 files)

`simulate`, `backtest`, `ros`, `stack`, `drift`, `props`, `season`, `parlay`,
`heatmap`, `neural`, `cluster`, `hedge`, `shop`. Recommendation: internal
consistency / convergence tests (e.g. does the Monte Carlo simulator
converge to the analytical answer for a simplified case with a known closed
form) rather than an external tie-out — flagged for a future pass, not
executed under this plan yet.

## B / B-sub — invented composite index, no real data path (~95 files)

The full list is every file with ADR ≥ 105 not already named above — see
`docs/FEATURE_REGISTRY.md` for the complete enumeration (each has its own
row). Representative work done this session:

- **`lineup_protect.py` (LINEUP-PROTECT-01, ADR-255) — premise check done,
  flagged.** "Lineup protection" (does the on-deck hitter change how a
  pitcher approaches the current batter) is a long-studied and largely
  debunked claim in sabermetrics — Tango/Lichtman/Dolphin's *The Book* (cited
  elsewhere in this project's own literature index) finds no reliably
  measurable protection effect. This package was built assuming the effect
  is real and gives it a specific, invented magnitude
  (`PII = 100 + (on_deck_woba - 0.320)*120.0 + ...`). **Recommendation:
  relabel as an unvalidated exploratory calculator (06C option 3), not
  refit** — refitting (06C option 1) would spend real modeling effort trying
  to find a signal the existing sabermetric literature already suggests
  probably isn't reliably there. Not yet acted on — this is a
  recommendation for the owner to confirm before moving it.
- **`clutch.py` (CLUTCH-01, ADR-167) — same premise-check flag, needs
  review.** "Clutch hitting" as a repeatable batter skill is the other
  classic largely-debunked sabermetric claim (Bill James onward; this
  project's own `docs/FEATURE_ADMISSION_QUEUE.md` CTX-06 row already says so
  explicitly: *"decades of sabermetric replication ... find batting 'clutch'
  performance is not a strongly repeatable skill year-over-year"*). `clutch.py`
  computes a `clutch_index` and labels batters `CLUTCH_PERFORMER` from
  invented weights, without engaging this project's own prior finding.
  Flagged for the same 06C treatment as `lineup_protect.py` — not yet acted
  on.
- **B-sub spot check done this session:** `poptime.py` (catcher pop time)
  and `vaa.py` (vertical approach angle) both use real, checkable Statcast
  concepts as their input benchmarks. Checked `poptime.py`'s
  `pop_time_s: float = 1.95  # elite < 1.85s, avg ~1.95s, poor > 2.05s`
  against Baseball Savant's published catcher pop-time leaderboard
  methodology (2B throws, avg ≈ 1.9-2.0s across recent seasons) — the
  benchmark is directionally correct and in the right range. The composite
  `ELITE_POP_TIME` tier score built on top of it is still an invented
  index, unchanged assessment. Full B-sub review of the remaining ~94
  packages not done — worth prioritizing packages whose docstring names a
  specific, real Statcast metric (VAA, HAA, spin efficiency, IFFB%, BABIP,
  xSLG) since those are the ones most likely to have a real, checkable
  input constant even though the composite score doesn't.

**Not yet classified individually / not yet given a 06C remedy decision:**
everything in Bucket B beyond the three above. This is the large remaining
body of work — plan 06's own text has the full three-option decision
process (refit / premise-check / relabel) to apply per package.

## Session log

- 2026-08-25: 06A classification completed (this document created).
  06B: `pitcher_estimators` tied out against the real SIERA formula, a real
  bug found and fixed (ADR-259, `tests/integration/test_model_pitcher_estimators.py`).
  While tying out `run_expectancy`, found and fixed a P0 bug that had been
  silently crashing the entire daily enrichment/prediction pipeline since
  2026-08-19 (ADR-260, `tests/integration/test_model_bsr.py`) — this
  redirected the rest of the session. `bsr`'s `wGDP` metric then also
  rebuilt properly against real FanGraphs methodology (ADR-261). Leverage
  Index then fully rebuilt on two new real, empirically-derived reference
  tables populated against real production data (ADR-262,
  `tests/integration/test_model_win_expectancy.py`,
  `tests/integration/test_model_leverage_index.py`,
  `tests/integration/test_model_run_expectancy.py`). `run_expectancy`'s
  RE24 columns and `wpa.py`'s own engine remain open (see the A/A′ sections
  above). 06C: 2 packages premise-checked and flagged (`lineup_protect`,
  `clutch`); 1 B-sub spot check done (`poptime`, `vaa`). Remaining ~90+
  Bucket B packages and ~30 Bucket A packages without a tie-out note are
  open work — this file is the worklist for continuing it.
- 2026-08-25 (continued, separate worktree): `pitch_discipline` (CSW%/
  Whiff%/F-Strike%, `PIT-07`) tied out against Retrosheet's own event-file
  spec and Pitcher List's original CSW% definition (both fetched directly
  this session), a real bug found and fixed (ADR-263,
  `tests/integration/test_model_pitch_discipline.py`): foul tips (`T`)
  missing from the CSW% numerator, hit-by-pitch (`H`) missing from the
  total-pitch denominator, and a stray non-real `W` character removed from
  the pitch-code whitelist. `docs/FEATURE_REGISTRY.md`'s
  `plate_discipline_v1` row now carries a real "Verified:" note and its
  stale file names (left over from an early, never-actually-committed
  rename) are corrected.
