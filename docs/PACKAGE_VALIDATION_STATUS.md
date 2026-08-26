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

## Bugs found in the 2026-08-26 Bucket B triage — all 16 fixed same day

**Status: all 16 items below (plus the 2 cosmetic-only notes) were fixed
later the same session, each with a real regression test.** See the session
log entry at the bottom of this file for the fix summary and real
lint/type/test output. Left in place below as the original findings record.

The 92 previously-unclassified Bucket B packages were triaged this session
(6 parallel read-only passes). None were reclassified out of Bucket B and no
files were edited during the triage pass itself — the bugs below were found
read-only and fixed in a separate, later pass. Real, behavior-changing bugs
found (same "formula doesn't match its own documented benchmark" root cause
as the `bullpen_bridge.py` precedent above), ranked by real impact:

1. **`poptime.py` (POPTIME-01, ADR-173) — a league-average catcher is scored
   "elite."** The CS% sigmoid's neutral point (`delta_t = 0`) evaluates to
   50%, but the file's own comment states real league-average CS% is ~21%.
   Feeding the file's own default (`pop_time_s=1.95`, already verified real
   against Baseball Savant) computes `exp_cs=58.9%` (not ~21%) and
   `csaa_runs=5.42`, which trips the elite-tier gate and labels an average
   catcher `ELITE_POP_TIME`. Needs the sigmoid's slope/intercept
   recalibrated so `delta_t=0` maps near 21%, not 50%.
2. **`nrfi.py` (NRFI-01, ADR-156) — implemented constant contradicts the
   code's own comment, and it changes the betting recommendation.** Line 81
   comments "Baseline Inning 1 average ~ 0.52 runs" but the code uses `0.40`.
   Recomputed with the documented 0.52 instead of 0.40, NRFI probability for
   the default matchup moves from 46.5% to 37.0% — enough to flip the
   engine's own recommended side from `NEUTRAL` to `YRFI`.
3. **`bunt.py` (BUNT-01, ADR-185) — tier logic contradicts its own ADR.**
   ADR-185 defines `ELITE_BUNT_ERASER` as a single condition
   (`BuntRuns >= +1.60`); the code adds an undocumented
   `or lead_runner_outs >= 3`. The file's own literal defaults compute
   `runs=1.25` (below the elite threshold) but still tag
   `ELITE_BUNT_ERASER`; an input with `bunt_hits_allowed=10` computes
   `runs=-3.36` and *still* tags elite via the same OR branch.
4. **`arm.py` (ARM-01, ADR-168) — same OR-bypass pattern.** Raw
   `arm_velocity_mph >= 96.0 or arm_runs >= 4.5` (and `>=91.0 or >=1.5` for
   the tier below) means a hard-throwing arm with a slow exchange
   (99 mph / 1.5s exchange, computed `arm_runs_saved_season ~= -11.6`, which
   alone would qualify for the `WEAK_ARM_TARGET <= -3.0` tier) still tags
   `CANNON_ELITE` purely off velocity.
5. **`pull_gb.py` (PULL-GB-01, ADR-203) — a near-max score still reads
   "moderate."** The file's own defaults compute `gbti=145.9` (91% of the
   stated 0-160 scale) but `is_extreme` also gates on
   `pull_groundball_pct >= 64.0`, and the default (`62.0`) narrowly misses
   it, so the tier falls through to `MODERATE_PULL_SHADING`.

Smaller anchor/benchmark-constant mismatches (same bug class, lower
real-world impact — a one- or two-line constant fix each):

6. `catcher_pop.py` (ADR-193): formula anchors at 2.30s, comment says
   benchmark is 2.50s (an 18-point deterrence-% swing at the file's own
   sample input).
7. `extension.py` (ADR-153): formula anchors at 6.0ft, field comment says
   "MLB avg ~6.2 ft."
8. `rel_drift.py` (ADR-207): formula anchors at 2.6in; the file's own
   defaults compute 2.408in.
9. `ssw_latent.py` (ADR-232): formula anchors at 30min/2.5in; the file's own
   defaults compute 35min/3.5in (a 12.5-point miss from "neutral").
10. `foul_attrition.py` (ADR-216): three anchors (10.0%/3.90/40.0%) vs. the
    fields' own documented benchmarks (11.0%/3.95/42.0%).
11. `wall_crash.py` (ADR-221): defaults (65.0%/4.6ft) vs. the fields' own
    comment benchmarks (~64.0%/~4.8ft) — minor.
12. `slash_oppo.py` (ADR-219): anchor 65.0% vs. field default 64.0% — minor,
    1-point score drift.
13. `route_burst.py` (ADR-213): anchors (0.45s/26.5ft/92.0%) vs. defaults
    (0.44s/27.0ft/93.0%) — minor.
14. `tto.py` (ADR-164): three numbers disagree — comment says 0.035, the
    formula's normalizer is 0.040, the field defaults imply 0.065.
15. `pivot_dp.py` (ADR-197): default 0.72s vs. the field's own comment
    "benchmark ~0.78s" — documentation-only, does not change output (the
    formula itself correctly uses 0.78).

Dead/misleading code (not a wrong-number bug, but a real quality issue):

16. **`fstrike.py` (FSTRIKE-01, ADR-172)**: `PitcherFStrikeMetrics` declares
    `woba_after_0_1`/`woba_after_1_0` fields, and the docstring claims the
    run value comes from "Count Delta Leverage" using them — but
    `evaluate_fstrike()` never references either field; the real formula is
    a flat, unrelated `0.068` runs/PA constant. Real first-pitch-strike% is
    already computed correctly from real data elsewhere, in the Bucket A
    `pitch_discipline.py` (ADR-263) — no need to refit this file, just
    remove the dead/misleading fields or wire them in honestly.

Cosmetic, no behavior change: `blocking.py`'s comment ("-5.0 runs -> 89.0%")
doesn't match its own symmetric formula's actual output (90.5%);
`velo_delta.py`'s docstring says "~10.0 in" vs. the default-implied 10.5.

### Structural findings (not a formula bug — a codebase-shape issue)

- **`splits.py` (PLATOON-01, ADR-155) is an orphaned shadow duplicate of the
  real, already-wired `platoon.py` (PLT-01, ADR-101, Bucket A, feeds
  `gbm.py`'s `FEATURE_COLUMNS`).** Different mechanism (hand-typed Empirical
  Bayes shrinkage vs. real SQL), confusingly similar ADR short-codes
  (`PLATOON-01` vs `PLT-01`), never referenced outside its own `mlb splits`
  CLI command. Recommend removing it or merging its shrinkage technique into
  the real `platoon.py`, not validating it standalone.
- `vaa.py`/`vaa_toz.py` (and Bucket A's `pitch_movement.py`) look like
  near-duplicate implementations of the same VAA physics — a consolidation
  candidate.
- `fatigue.py`/`fatigue_drop.py` both track pitcher fatigue via
  velocity/release-point decay under different names/acronyms.
- The wall-catch family (`wall.py`, `wall_crash.py`, `wall_leap.py`,
  `wall_block.py`) covers a narrower slice of defensive value that the real,
  already-validated `oaa.py` (Bucket A) should already handle more
  rigorously — future refit effort is better spent extending `oaa.py` than
  rebuilding a parallel wall-specific track.
- `bullpen_opt.py` hand-types inputs that duplicate real functionality this
  project already computes from real data (`platoon.py`, `bullpen.py`,
  `run_expectancy.py`'s leverage) — a real refit could wire it directly to
  those instead.
- `leverage.py` (Bucket B, ADR-154) and the real `re24_leverage_v1`
  (Bucket A, ADR-091) both use the short-code `LEV-01` — a doc-hygiene
  collision worth a rename, not a runtime issue.

### Data-availability finding that changes the refit-cost calculus

`raw.statcast_pitch` already ingests pybaseball's full ~119-column Statcast
schema (release position, movement/`pfx_x`/`pfx_z`, plate location, zone,
swing/contact codes, launch speed/angle — confirmed directly from the
connector) — but the conformed `core.pitch` only exposes a narrower subset
(no release position, no IVB, no `plate_z`, no zone). For the
pitch-trajectory-based packages below (VAA/HAA family, tunneling, velocity
delta/drift, expected stats, zone swing/whiff, gyro spin), the real input
data is already sitting in this project's own raw layer — a future refit is
a concrete, scoped task, not a hypothetical needing a new source.

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

- `run_expectancy`'s `home_bullpen_re24`/`away_bullpen_re24`/
  `home_batting_re24`/`away_batting_re24` — **fixed (ADR-264).** They used
  the same pre-existing crude "runs vs. flat 0.12/PA league average" proxy
  as the LI columns did before ADR-262. Replaced with real RE24
  (`RE(after) - RE(before) + runs scored`, Tom Tango/FanGraphs, cumulative
  not per-PA, pitcher RE24 = -batter RE24) against the now-fixed
  `gold.run_expectancy_24` matrix, using the same `LEAD()`-based
  before/after-state technique `gold.leverage_index` was built with.
  Hand-verified against a hand-computed 3-play half-inning fixture
  (single -> strikeout -> GIDP), repeated 17 times: `batting_re24 =
  -8.5000`, `bullpen_re24 = +8.5000`, both matching the SQL's real output
  exactly. See `tests/integration/test_model_run_expectancy.py::
  test_compute_real_bullpen_and_batting_re24`.

**Still open:** `wpa.py`'s own `WinExpectancyEngine` (backing the separate
`mlb wpa` CLI command, not `gold.game_feature`) still uses its unvalidated
hand-typed formula — not touched this session; see
`docs/THEORY_AND_METHODOLOGY.md` §10.3 for the full note on these two
now-diverged implementations.

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

### 2026-08-26: remaining 92 packages triaged, 06C decision recorded for each

All 92 packages below were read in full (module + unit test + ADR entry)
this session. Real correctness bugs found are in the "Bugs found" section
near the top of this file, not repeated here. None of these 92 rest on a
classically debunked premise like `lineup_protect.py`/`clutch.py`, except
the one marked premise-check below. "Relabel" = 06C option 3 (unvalidated
exploratory calculator, the default when neither of the other two applies
right now); "Refit" = 06C option 1, flagged as future Plan-04-scale work,
**not attempted this session**; "Premise-check" = 06C option 2. A "B-sub"
note means at least one real input benchmark constant was spot-checked
against a real published number and found in the right range — the
composite score itself is still invented either way.

| Package | Code / ADR | 06C verdict | Note |
| --- | --- | --- | --- |
| `active_spin` | ACTIVE-SPIN-01 / 224 | Relabel | Real Statcast concept (spin efficiency); mild anchor drift (85.0% vs default-implied 87.0%), not self-contradictory. |
| `aging` | AGE-02 / 145 | Relabel | Projection engine, not a tier score; coefficients invented/uncited. |
| `air_trap` | AIR-TRAP-01 / 227 | Relabel | Anchors match field defaults exactly; clean 100.0 neutral. |
| `ambush` | AMBUSH-01 / 205 | Relabel | Comment benchmarks match; default score 107.9, not self-contradictory. |
| `arm` | ARM-01 / 168 | Relabel, **bug** | See bug #4 (OR-bypass: velocity alone can override negative arm-run value). |
| `arm_accuracy` | ARM-ACCURACY-01 / 201 | Relabel | Missing intermediate tier — a near-elite 117.6 score falls to "average"; design gap, not a code bug. |
| `arm_align` | ARM-ALIGN-01 / 220 | Relabel | Anchors don't exactly match defaults but no contradiction produced. |
| `arm_slot` | ARM-SLOT-01 / 192 | Relabel | Pure trig, two independent axes, no scoring-anchor pattern to break. |
| `babip` | BABIP-LUCK-01 / 179 | **Refit candidate** | Real DIPS premise; formula's own xBABIP (~.355 for a plausible avg profile) overshoots real MLB BABIP (~.290–.300) — calibration concern, real `batted_ball` data path exists. |
| `baserunning` | SB-01 / 143 | Relabel | Kinematic sim, not a scored index; default 16% steal-success plausible given real success rates are selection-biased. |
| `blast_angle` | BLAST-ANGLE-01 / 199 | Relabel | B-sub: 8°-32° sweet-spot window matches real Statcast definition. Missing intermediate tier baked into ADR-199 itself (126.8 score still lands "average"). |
| `blocking` | BLOCK-01 / 148 | Relabel | Cosmetic-only comment error (89.0% vs actual 90.5%); formula itself well-calibrated (0.0 runs to 0.0 delta exactly). |
| `block_suppress` | BLOCK-SUPPRESS-01 / 217 | Relabel | Anchors match field comments exactly; no contradiction. |
| `bullpen_opt` | BULLPEN-OPT-01 / 160 | **Refit candidate** | Duplicates real `platoon`/`bullpen`/`run_expectancy` leverage functionality with hand-typed inputs instead — real refit path is wiring to those. |
| `bunt` | BUNT-01 / 185 | Relabel, **bug** | See bug #3 (OR-bypass contradicts ADR-185's own elite-tier definition). |
| `bunt_charge` | BUNT-CHARGE-01 / 233 | Relabel | Anchors match defaults exactly; clean 100.0 neutral. |
| `bvp` | BVP-01 / 135 | Relabel | Legitimate EB-shrinkage approach to a real small-sample problem; `M=350` plausible but not pinned to a citation. |
| `carry` | CARRY-01 / 165 | Relabel | B-sub: Yankee Stadium/Fenway/Coors dimensions all checked and correct; altitude-boost constant (16.0ft) uncited. |
| `catcher_pop` | CATCHER-POP-01 / 193 | Relabel, **bug** | See bug #6 (2.30s anchor vs. 2.50s documented benchmark). |
| `catch_prob` | CATCH-PROB-01 / 189 | Relabel | B-sub: star-rating cutoffs (5-star ≤25% ... ROUTINE) match Baseball Savant's real published buckets exactly. |
| `catch_xchg` | CATCH-XCHG-01 / 209 | Relabel | Anchors internally consistent; 0.70s exchange-time benchmark unverifiable (Savant doesn't publish it separately). |
| `chase_recog` | CHASE-RECOG-01 / 247 | Relabel | Anchors match defaults exactly; clean 100.0 neutral. |
| `contact_depth` | CONTACT-DEPTH-01 / 191 | Relabel | No benchmark-mismatch term exists; "5.0in optimal" uncited. |
| `count` | COUNT-01 / 139 | **Refit candidate** | Simulator, not an index; pitches/PA health check (3.0-5.0) matches real MLB average (~3.9-4.0); count-mix shift by count state is well-established pitcher behavior. |
| `damage` | DAMAGE-01 / 159 | Relabel, **bug** | See bugs section: Barrel LA window claimed "dynamic," implemented static/mis-centered vs. real Statcast definition. |
| `decision` | DECISION-01 / 151 | **Refit candidate** | Zone framework (Heart/Shadow/Chase/Waste) directly mirrors Baseball Savant's real published Swing/Take metric with real per-zone run values already public — best refit candidate in its batch. |
| `diversity` | ARSENAL-01 / 169 | Relabel | Gini-Simpson/Shannon entropy legitimate; minor dead-code nit (`hasattr` fallback references a non-existent field, harmless). |
| `dp_footwork` | DP-FOOTWORK-01 / 241 | Relabel | Anchors match defaults exactly; 0.74s pivot uncited. |
| `entropy` | ENTROPY-01 / 144 | Relabel | No fixed anchor to break (computes directly from input mix); real info-theory concept, real data path plausible later. |
| `exp_resist` | EXP-RESIST-01 / 208 | Relabel | Anchors match "league average" comments exactly; minor tier-granularity gap (111.0 score still "average"). |
| `extension` | EXT-01 / 153 | Relabel, **bug** | See bug #7 (6.0ft anchor vs. field's own "MLB avg ~6.2ft"). |
| `ext_perceive` | EXT-PERCEIVE-01 / 215 | Relabel | Real "effective velocity" concept (Husband/Driveline); minor anchor drift (16.5 default vs 16.0 anchor), not tier-breaking. |
| `fatigue` | FATIGUE-01 / 161 | **Premise-check** | ACWR itself is a genuinely contested sports-science metric (mathematical-coupling critiques exist in the literature) — flag the controversy, don't present FRI as validated. |
| `fatigue_drop` | FATIGUE-DROP-01 / 236 | Relabel | Overlaps conceptually with `fatigue.py` (duplication note, not a bug); anchors match defaults exactly. |
| `first_pitch_ambush` | FIRST-PITCH-AMBUSH-01 / 248 | Relabel | Anchors match defaults exactly; 60.0% first-pitch-strike benchmark directionally plausible. |
| `first_step` | FIRST-STEP-01 / 237 | Relabel | Anchors match defaults exactly; premise mirrors Statcast's own OAA jump component. |
| `foul_attrition` | FOUL-ATTRITION-01 / 216 | Relabel, **bug** | See bug #10 (three anchors drift from documented benchmarks). |
| `fstrike` | FSTRIKE-01 / 172 | Relabel, **bug** | See bug #16 (dead `woba_after_0_1`/`woba_after_1_0` fields; real F-Strike% already correct in `pitch_discipline.py`). |
| `gyro_spin` | GYRO-SPIN-01 / 195 | **Refit candidate** | `gyro_angle = arccos(spin_efficiency)` is the actual correct Statcast/Trackman identity, no invented composite at all — smallest-lift refit in the whole batch. |
| `haa` | HAA-01 / 184 | **Refit candidate** (partial) | HAA physics approximation is legitimate; relabel the bolted-on "deception score," refit the HAA computation itself. |
| `heat_check` | HEAT-CHECK-01 / 243 | Relabel | Anchors match defaults exactly; clean 100.0 neutral. |
| `high_heat` | HIGH-HEAT-01 / 231 | Relabel | Anchors match defaults exactly; clean 100.0 neutral. |
| `iffb` | IFFB-01 / 181 | **Refit candidate** | Real established FanGraphs stat, no invented acronym score at all; 9.5% league-baseline plausible; strongest refit candidate in its batch — real data path is `core.play`/`raw.retrosheet_event`. |
| `intent_leak` | INTENT-LEAK-01 / 228 | Relabel | Anchors match defaults exactly; clean 100.0 neutral. |
| `lead_snap` | LEAD-SNAP-01 / 229 | Relabel | Anchors match field benchmarks exactly; 20.5ft secondary-lead figure unverified. |
| `leverage` | LEV-01 / 154 | Relabel | Ratio-based, not anchor-subtraction; internally consistent; ADR short-code collides with the real `LEV-01`/ADR-091 (`re24_leverage_v1`) — rename recommended. |
| `low_scoop` | LOW-SCOOP-01 / 225 | Relabel | Anchors match defaults exactly; clean 100.0 neutral. |
| `nrfi` | NRFI-01 / 156 | Relabel, **bug** | See bug #2 (0.40 implemented vs. 0.52 documented baseline — flips the betting recommendation). |
| `oppo_gap` | OPPO-GAP-01 / 239 | Relabel | Anchors match defaults exactly; clean 100.0 neutral. |
| `oppo_liner` | OPPO-LINER-01 / 251 | Relabel | Anchors match defaults exactly; clean 100.0 neutral. |
| `outfield_target` | OUTFIELD-TARGET-01 / 245 | Relabel | Anchors match defaults exactly; clean 100.0 neutral. |
| `pivot_dp` | PIVOT-DP-01 / 197 | Relabel, **bug** | See bug #15 (doc-only mismatch, formula itself correct). |
| `poptime` | POPTIME-01 / 173 | Relabel, **bug** | See bug #1 (CS% sigmoid mislabels a league-average catcher "elite"). |
| `pull_air` | PULL-AIR-01 / 183 | Relabel | No field-level benchmark comments to check; default scores borderline-consistent (31.8%/1.57 vs. 38%/1.60 elite cutoff). |
| `pull_barrel` | PULL-BARREL-01 / 211 | Relabel | Constants match "league average" comment; defaults deliberately set above average (documented, not a bug); minor tier-granularity gap. |
| `pull_gb` | PULL-GB-01 / 203 | Relabel, **bug** | See bug #5 (91%-of-max score still tagged "moderate"). |
| `pull_slice` | PULL-SLICE-01 / 235 | Relabel | Anchors match defaults exactly; clean 100.0 neutral; no real benchmark exists for "fair-pole conversion%" to check. |
| `putaway` | PUTAWAY-01 / 176 | Relabel | Real FanGraphs Put-Away% concept; 19.5% baseline plausible but unverified this session. |
| `putaway_depth` | PUTAWAY-DEPTH-01 / 244 | Relabel | Cleanest-constructed file checked — all constants including a derived delta match exactly; clean 100.0 neutral. |
| `putaway_exec` | PUTAWAY-EXEC-01 / 212 | Relabel | Anchors match defaults exactly; clean 100.0 neutral; 2-strike zone targeting is real pitch-calling behavior. |
| `rel_drift` | REL-DRIFT-01 / 207 | Relabel, **bug** | See bug #8 (2.6in anchor vs. own defaults' 2.408in). |
| `reliever` | BULLPEN-01 / 138 | Relabel | Threshold model, not anchor-scored; workload-degrades-effectiveness premise broadly accepted; decay weights invented; real team pitch-count data exists for a later refit. |
| `route_burst` | ROUTE-BURST-01 / 213 | Relabel, **bug** | See bug #13; also B-sub: reaction/burst/route decomposition structurally matches Savant's real published "Outfielder Jump" methodology exactly. |
| `shift` | SHIFT-01 / 140 | Relabel | B-sub: league BABIP (.295) and sprint speed (27.0 ft/s) both real and correct. Caveat: `SHADED_PULL`-style alignments are illegal under MLB's 2023 shift-ban rule — outdated if ever wired to post-2023 data. |
| `slash_oppo` | SLASH-OPPO-01 / 219 | Relabel, **bug** | See bug #12 (minor 1-point anchor drift). |
| `slot_sag` | SLOT-SAG-01 / 252 | Relabel | Anchors match defaults exactly; tier-boundary quirk only (exact-benchmark input isn't labeled "average"), not a numeric bug. |
| `spin` | SPIN-01 / 157 | Relabel | Correct physics identity, no invented scoring term at all; closest of its batch to Bucket A′; only the archetype cutoffs (88%/45%) are invented. |
| `spin_align` | SPIN-ALIGN-01 / 240 | **Premise-check** | "Tunneling improves whiff rate" is mixed/contested evidence in more recent replication, not flatly debunked — softer flag than `lineup_protect`/`clutch`, same treatment. |
| `splits` | PLATOON-01 / 155 | **Structural — see "Structural findings" above** | Confirmed orphaned duplicate of the real `platoon.py`; not independently bucketed. |
| `spray` | SPRAY-01 / 163 | Relabel | Pull%/Center%/Oppo% are real Statcast categories; Spray Neutrality Index's 2.2 scale factor is invented. |
| `ssw` | SSW-01 / 147 | Relabel | Seam-shifted wake is a real, actively-researched phenomenon; per-pitch-type Magnus baseline constants are hand-picked, not derived from the real velocity²/drag equation — methodology gap, not a bug. |
| `ssw_latent` | SSW-LATENT-01 / 232 | Relabel, **bug** | See bug #9 (30min/2.5in anchors vs. own defaults' 35min/3.5in). |
| `stuff` | STUFF-01 / 126 | **Refit candidate** | Strongest refit candidate overall — Stuff+/Location+/Pitching+ are real published metric families (FanGraphs, PitchingBot); this implementation hand-picks weights instead of regression-fitting them; baseline velo/IVB constants plausible against real Statcast four-seam averages. |
| `sub` | SUB-01 / 141 | Relabel | Threshold decision-tree on wOBA-vs-handedness, a real accepted platoon heuristic; specific thresholds invented. |
| `sweetspot` | SWEETSPOT-01 / 175 | Relabel | B-sub: 8°-32° sweet-spot window is Statcast's real official definition; ICR composite weighting (0.70/0.30) invented. |
| `travel` | TRAVEL-01 / 149 | **Refit candidate** | Jet-lag/travel-fatigue effects are real and published (Roy & Forest, PNAS 2017, recalled not freshly fetched); real data path is unusually cheap (schedule + static venue-timezone lookup, no new source needed). |
| `tto` | TTO-01 / 164 | Relabel, **bug** | See bug #14 (three disagreeing numbers). Otherwise: Times-Through-the-Order Penalty is one of the most replicated findings in modern sabermetrics (drove the "opener" strategy) — **refit candidate** once the constant is fixed; real data path is `core.play`. |
| `tunnel` | TUNNEL-01 / 152 | **Refit candidate** | Geometry (release/POC/plate-break math) is legitimate physics; only the 0-100 quality-score weighting is invented; tunneling's predictive power for whiffs is more mixed in follow-up research than TTOP, not debunked. |
| `two_strike` | TWO-STRIKE-01 / 196 | Relabel | Real behavior (2-strike swing shortening), but its key input (bat-tracking swing length) is a 2024+ Statcast release not confirmed ingested anywhere in this project yet — data path uncertain, unlike most of this batch. |
| `umpire` | UMP-01 / 136 | **Refit candidate** | Umpire zone bias/run impact is real and documented (BU umpire-scorecard research); umpire ID presence in Retrosheet not yet confirmed conformed into `core`. |
| `vaa` | VAA-01 / 180 | **Refit candidate** | Legitimate physics-derived Statcast concept, increasingly validated publicly (Chamberlain/FanGraphs); real inputs already in `raw.statcast_pitch`. |
| `vaa_toz` | VAA-TOZ-01 / 204 | **Refit candidate** | Same premise/data path as `vaa.py`; near-duplicate implementation — see "Structural findings." |
| `velo_delta` | VELO-DELTA-01 / 200 | Relabel, **bug** | Cosmetic-only doc mismatch (10.0 vs 10.5); well-designed otherwise. Real data path exists — **refit candidate**. |
| `velo_drift` | VELO-DRIFT-01 / 188 | **Refit candidate** | Intra-game velocity fade as a fatigue signal is real and widely discussed; thresholds applied consistently; real data path via `raw.statcast_pitch` pitch sequencing. |
| `wall` | WALL-01 / 177 | Relabel | Real premise but redundant with the already-validated `oaa.py` (Bucket A) — extend `oaa.py` instead of refitting this in parallel. Run-value constants (1.65/0.75) plausible in magnitude, uncited. |
| `wall_block` | WALL-BLOCK-01 / 249 | Relabel | Anchors match defaults exactly; clean 100.0 neutral; same `oaa.py`-redundancy note as `wall.py`. |
| `wall_crash` | WALL-CRASH-01 / 221 | Relabel, **bug** | See bug #11 (minor anchor drift); same `oaa.py`-redundancy note. |
| `wall_leap` | WALL-LEAP-01 / 253 | Relabel | Anchors match defaults exactly; clean 100.0 neutral; same `oaa.py`-redundancy note. |
| `weather` | WEATHER-01 / 137 | Relabel (top future refit candidate) | B-sub: ADI reference point (59°F/29.92inHg) matches the real International Standard Atmosphere exactly; altitude scale-height constant matches real physics (~27-28k ft); Coors Field example checks out. Distance-to-run-multiplier conversion is invented. **Refit blocked** until a real weather source is added to `docs/DATA_SOURCES.md` per CLAUDE.md. |
| `xslg` | XSLG-01 / 187 | **Refit candidate** | Real official Statcast metric family; barrel coefficient (2.500) close to the real published 2.386 SLG-on-Barrels figure (recalled, ~5% off); real data path via `raw.statcast_pitch`. |
| `zone_swing` | ZONE-SWING-01 / 171 | **Refit candidate** | Standard uncontested Statcast plate-discipline metric; league Z-Contact% benchmark (82.0%) plausible vs. real ~83-86%; real data path exists. |
| `zone_whiff` | ZONE-WHIFF-01 / 223 | **Refit candidate** | Standard uncontested Statcast metric; benchmarks plausible vs. real Savant averages; anchors match defaults exactly, clean 100.0 neutral. |

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
- 2026-08-25 (continued, separate worktree): `run_expectancy`'s
  `bullpen_re24`/`batting_re24` columns fixed against real RE24 (ADR-264,
  `tests/integration/test_model_run_expectancy.py`) — replaced the
  "~0.12 runs/PA league average" proxy with `RE(after) - RE(before) +
  runs scored` (Tom Tango/FanGraphs, fetched directly this session)
  against the now-fixed `gold.run_expectancy_24` matrix.
- 2026-08-26: all 92 remaining unclassified Bucket B packages triaged (6
  parallel read-only passes, ~15 packages each, cross-referenced against
  `plans/06-package-validation-and-tieout.md`, this file's own worked
  examples, and `docs/FEATURE_ADMISSION_QUEUE.md`). Full per-package 06C
  verdicts recorded in the new table above. Found 16 real, previously
  unknown correctness bugs of the same class as `bullpen_bridge.py`
  (documented benchmark != implemented constant, or a raw-input OR-branch
  that can override a computed run value) — none fixed yet in this pass,
  recorded in "Bugs found" near the top of this file, ranked by real impact.
  Two are meaningful enough to prioritize: `poptime.py` labels an average
  catcher "elite," and `nrfi.py`'s constant mismatch flips its own betting
  recommendation. Also found: `splits.py` is an orphaned duplicate of the
  real `platoon.py` (recommend removal/merge); several other duplication/
  redundancy pairs noted (`vaa`/`vaa_toz`, `fatigue`/`fatigue_drop`, the
  wall-catch family vs. `oaa.py`); and `raw.statcast_pitch` already carries
  real trajectory/movement data that isn't yet conformed into `core.pitch`,
  which materially lowers the cost of a future refit for the VAA/HAA/
  tunneling/velocity-delta/expected-stats family. 14 packages flagged as
  real future Plan-04-scale refit candidates (not attempted this session);
  2 flagged premise-check (`fatigue`'s ACWR methodology, `spin_align`'s
  mixed tunneling-whiff evidence); the remaining ~75 get the default
  relabel-as-unvalidated-exploratory-calculator recommendation. Nothing
  moved, renamed, or refit in this pass — recommendations only, pending
  owner review, matching the `lineup_protect`/`clutch` precedent above.
  Next: owner reviews the relabel/refit/premise-check recommendations, and
  the 16 flagged bugs get real code fixes with regression tests (same
  pattern as the `bullpen_bridge.py` fix).
- 2026-08-26 (continued, same session): all 16 bugs above fixed, each with
  a new or updated regression test in `tests/unit/`, using the same
  before/after-numbers discipline as the `bullpen_bridge.py` precedent.
  Highlights: `poptime.py`'s CS% sigmoid gained a missing intercept so a
  league-average catcher (`pop_time_s=1.95`) now scores `ABOVE_AVERAGE`
  (27.6% expected CS%) instead of `ELITE_POP_TIME` (was 58.9%); `nrfi.py`'s
  0.40-vs-0.52 baseline was fixed to the documented 0.52, which flips the
  default matchup's recommended side from `NEUTRAL` to `YRFI` exactly as
  predicted (its own `health_check()` example matchup needed retuning to
  genuinely elite pitchers to stay a meaningful demonstration under the
  corrected constant); `bunt.py`'s tier logic now matches ADR-185 exactly
  (removed an undocumented raw-outs override); `arm.py` had all three tiers
  fixed from `or` to `and` (the fixing agent found the same OR-bypass bug
  in `WEAK_ARM_TARGET` too, not just the two originally flagged, and
  verified no tier became unreachable); `pull_gb.py` gained a new
  intermediate tier (`AGGRESSIVE_PULL_SHADING`) rather than loosening the
  two-factor `is_extreme` gate, preserving its original strict semantics;
  `fstrike.py` had its two dead, never-referenced fields removed and its
  docstring corrected to describe the flat constant it actually uses,
  instead of methodology it doesn't implement. The remaining 11 were
  one-line-per-constant reconciliations (formula anchor vs. documented
  benchmark) plus 2 cosmetic-only comment fixes. Where a fix decision was
  ambiguous (e.g. `wall_crash.py`/`slash_oppo.py`/`route_burst.py`: fix the
  formula or the field default?), the fixing agent deferred to whichever
  side `cli.py`'s own hardcoded argparse defaults already matched, to avoid
  introducing a new silent inconsistency there — noted per-file so this can
  be revisited. Full repo-wide verification after merging all three fix
  passes: `ruff check`/`ruff format --check` clean on
  `mlb_baseball/model/`+`tests/unit/`, `mypy` clean on 151 source files,
  `pytest tests/unit` — 1051 passed. Diffs read directly (not just the
  fixing agents' self-reports) before this log entry was written, per
  `CLAUDE.md`'s "re-run tests and read the diff yourself" rule. Not yet
  done: none of the 16 fixes touch real ingested data (all remain Bucket B
  exploratory calculators) — the separate relabel/refit/premise-check
  recommendations in the table above are still open, pending owner review.
