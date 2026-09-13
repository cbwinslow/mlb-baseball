# Metric catalog

Every publicly-visible statistic this project implements, generated from `meta.metric` (`mlb catalog docs`) -- see `openspec/changes/metric-catalog/` for how this catalog is built and maintained. An internal (non-public) entry never appears here.

## batting_rate_stats_bref_tieout

A player's core batting rate statistics for a season -- batting average (AVG), on-base percentage (OBP), slugging percentage (SLG), and their sum (OPS) -- computed from this project's own event-level data and checked directly against Baseball-Reference's own published numbers for real players and seasons.

- **Status:** validated
- **Citation:** Standard sabermetric/official formulas for AVG, OBP, SLG, OPS (MLB glossary / FanGraphs definitions)
- **Data source:** gold.batting_game (raw.retrosheet_event 1910-2025, raw.mlb_boxscore_batting 2026+)
- **Grain:** player-season
- **Layer:** gold
- **Source:** [https://github.com/cbwinslow/mlb-baseball/blob/3a4e2c18df98c5b9df04535981b6b6368876ee02/mlb_baseball/sql/batting_season_build.sql](https://github.com/cbwinslow/mlb-baseball/blob/3a4e2c18df98c5b9df04535981b6b6368876ee02/mlb_baseball/sql/batting_season_build.sql)
- **Notes:** The strongest evidence in this batch, and confirmed by directly reading what the gate compares (not assumed from its name). AVG = H/AB, OBP = (H+BB+HBP)/(AB+BB+HBP+SF), SLG = TB/AB, OPS = OBP+SLG, all computed as season-grain sums-of-components (never an average of already-aggregated game rates) -- confirmed correct per direct code read of batting_season_build.sql, with every rate correctly NULL on a zero denominator.
scripts/verify_baseball_reference_tie_out.py is a real, independent, currently-passing gate, not a self-derived test: (1) two CITED CASES read directly from Baseball-Reference's own player pages -- Aaron Judge's 2022 season (g/ab/r/h/hr/rbi/bb exact, avg/obp/slg/ ops matched to Baseball-Reference's own 3-decimal display precision) and Gerrit Cole's 2023 season (17 fields including whip, exact) -- with `source_url` naming the exact page each expected value was read from; (2) a BULK CROSS-CHECK comparing this project's event-derived gold.batting_season against gold.player_season (Baseball-Reference lineage, via pybaseball) field-by-field for every qualified player-season 2008-2025 (2020 excluded, COVID-shortened), passing if each field is within a documented tolerance on at least 98% of player-seasons. Per this project's own record (docs/DECISIONS.md, openspec/project.md NOW/NEXT, 2026-09-07/2026-09-11), this gate currently passes: both cited cases match exactly/to display precision, and the bulk cross-check is clean within tolerance across the full 2008-2025 window. This session did not re-run the gate against production (it requires a fully-built database with real ingested data, out of scope for this batch's scratch-DB verification) -- status "validated" rests on reading the gate's own logic plus this project's own dated, recorded passing runs, not a fresh run performed here.
Coverage/known limits, per the gate's own docstring and docs/DATA_DICTIONARY.md: exact tie-out is not achievable at the career grain or for seasons much before ~2000 (independent decades of scoring corrections on both the Retrosheet and Baseball-Reference sides) -- this entry's `validated` status is scoped to the season grain the gate actually covers, not every grain gold.batting_season/career exposes.

## catcher_framing_prior_season

A team's catcher pitch-framing value (extra strikes earned by good glove positioning, converted to runs) from the season before the game being predicted. This project does not calculate framing itself -- it takes Statcast's own published per-catcher framing runs value, adds up each team's catchers, and lags it by one full season so no game is scored using data that only exists because of games played after it.

- **Status:** published
- **Citation:** Statcast catcher framing runs (rv_tot), via Baseball Savant's catcher framing leaderboard
- **Data source:** raw.statcast_framing (via core.player_war's bref/Retrosheet team crosswalk)
- **Grain:** team-season (lagged one season, joined onto a per-game feature row)
- **Layer:** gold
- **Source:** [https://github.com/cbwinslow/mlb-baseball/blob/3a4e2c18df98c5b9df04535981b6b6368876ee02/mlb_baseball/model/framing.py](https://github.com/cbwinslow/mlb-baseball/blob/3a4e2c18df98c5b9df04535981b6b6368876ee02/mlb_baseball/model/framing.py)
- **Notes:** Same posture as team_war_prior: sums and lags an externally-published, per-catcher Statcast value (rv_tot) rather than reimplementing Statcast's own framing model. Team identity resolved by reusing war.py's _BREF_TO_RETRO crosswalk directly (framing.py imports it rather than maintaining a second copy). ADR-045 documents a real, understood coverage gap checked against real 2024 data: only ~52% of catcher rows resolve to a team, traced to rookies/prospects below core.player_war's own minimum-playing-time threshold, not a join bug (confirmed by name against four specific 2024 players).
No dedicated automated test compares this project's summed/lagged value against an independently published team-level framing total, so this is "published" (correctly implemented per direct code read, cited source) rather than "validated".
This is a distinct metric, computed in the same module, from catcher_framing_csae (this project's own in-season, project-derived approximation of framing -- see that entry).

## comprehensive_baserunning

A team's baserunning value beyond stolen bases: how often runners take an extra base on a hit (XBT%), Ultimate Base Running (UBR, a run-value score for taking extra bases), weighted stolen-base runs (wSB), weighted ground-into-double-play avoidance (wGDP), and a single combined total (BsR). Computed point-in-time, entering each game, from games already played.

- **Status:** published
- **Citation:** Tom Tango / FanGraphs Sabermetrics Library -- wSB (https://library.fangraphs.com/offense/wsb/), UBR (https://library.fangraphs.com/offense/ubr/), wGDP (https://library.fangraphs.com/offense/wgdp/), and BsR (https://library.fangraphs.com/offense/bsr/) methodology.

- **Data source:** raw.retrosheet_event, raw.retrosheet_gameinfo
- **Grain:** team, point-in-time entering each game
- **Layer:** gold
- **Source:** [https://github.com/cbwinslow/mlb-baseball/blob/3a4e2c18df98c5b9df04535981b6b6368876ee02/mlb_baseball/model/bsr.py](https://github.com/cbwinslow/mlb-baseball/blob/3a4e2c18df98c5b9df04535981b6b6368876ee02/mlb_baseball/model/bsr.py)
- **Notes:** wSB = SB*0.20 + CS*(-0.42) - lgwSB*(1B+uBB+HBP): the fixed run values 0.20 (steal) / -0.42 (caught stealing) are Tom Tango's widely-cited constants (FanGraphs' own year-by-year weights aren't published in closed form, per ADR-081). Correctly implements the FanGraphs-cited formula per direct code read, including a real, checked algebraic simplification (`1B+BB+HBP-IBB` = `1B+uBB+HBP` since `BB=uBB+IBB`, so IBB is never separately counted -- confirmed correct, not a shortcut that changes the answer, per ADR-081).
UBR and wGDP follow FanGraphs' published "actual vs. league-average opportunity rate" structure, but with ONE project-derived constant FanGraphs does not publish: wGDP's run-value-per-erased-runner (0.4153) is derived from this project's own empirically-built 24-state run expectancy matrix (gold.run_expectancy_24, ADR-260), not from a FanGraphs-published number (FanGraphs' library page for wGDP does not publish its own exact constant). UBR's per-extra-base run value (0.20) is a commonly-used estimate, not separately re-derived. Flagged here so this specific constant isn't mistaken for a value FanGraphs itself publishes.
tests/integration/test_model_bsr.py hand-derives its own expected wSB value using the same arithmetic the SQL performs (self-consistency, not an independent tie-out), so status is "published" rather than "validated". MIN_ATTEMPTS/opportunity-count sample-size gates (5, 10) are chosen floors, not derived or cited numbers.

## era_earned_runs

Earned Run Average (ERA): the traditional measure of a pitcher's runs allowed per 9 innings, counting only "earned" runs (excluding runs that scored because of a fielding error). This project's own event-derived data (1910-2025) cannot identify earned runs at all, so ERA is NULL for every pitcher-season through 2025 and only populated from 2026 onward, once MLB's own scorer-assigned earned-run figure became available as a source.

- **Status:** published
- **Citation:** Official MLB statistic (traditional baseball statistic; no single formula author)
- **Data source:** raw.mlb_boxscore_pitching (2026+ only; er is NULL for 1910-2025, sourced from raw.retrosheet_event which carries no earned-run data)
- **Grain:** pitcher-game, pitcher-season, pitcher-career
- **Layer:** gold
- **Source:** [https://github.com/cbwinslow/mlb-baseball/blob/3a4e2c18df98c5b9df04535981b6b6368876ee02/mlb_baseball/sql/pitching_season_build.sql](https://github.com/cbwinslow/mlb-baseball/blob/3a4e2c18df98c5b9df04535981b6b6368876ee02/mlb_baseball/sql/pitching_season_build.sql)
- **Notes:** era = er * 27 / outs (equivalent to the standard er * 9 / IP). er is a plain SUM of game-level earned runs, nulled for the whole season total if any contributing game lacks it (the `CASE WHEN count(*) = count(er) THEN sum(er) END` guard in pitching_season_build.sql) rather than silently treating a missing game as zero earned runs. Added in migration 0102_pitching_er_era.sql (backbone-2026-source change). ra9 (runs allowed per 9, using total runs, not just earned) is the honest cross-era rate populated for every year -- docs/DATA_DICTIONARY.md documents this "era coverage cliff" explicitly, and warns a naive average of era across the 2025/2026 boundary is meaningless.
NOT independently tie-out tested by either of this project's real tie-out gates: scripts/verify_baseball_reference_tie_out.py's cited Judge/Cole cases and bulk cross-check do not include er/era among their compared fields, and scripts/verify_mlb_boxscore_tie_out.py's play-by-play reconstruction (the 2026-onward gate) only covers batting counting stats (PA/AB/H/BB/SO/HBP/SF/SH/HR) -- neither covers pitching earned runs at all. tests/integration/test_report_pitching_season.py's test_pitching_season_era_populated_for_2026_null_for_retrosheet_era seeds synthetic pitcher-game fixtures and hand-derives the expected era using the same arithmetic the SQL performs -- self-consistency, not an independent tie-out. "published" (correctly implemented, well-documented, standard formula) rather than "validated".

## fangraphs_guts

FanGraphs' "Guts!" per-season linear-weight constants used to compute wOBA and FIP correctly for a given season's actual run environment, rather than a single fixed weight set applied to every year.

- **Status:** published
- **Citation:** FanGraphs, Guts! constants (https://www.fangraphs.com/guts.aspx)
- **Data source:** raw.fangraphs_guts
- **Grain:** season
- **Layer:** gold
- **Source:** [https://github.com/cbwinslow/mlb-baseball/blob/3a4e2c18df98c5b9df04535981b6b6368876ee02/mlb_baseball/sql/gold_fangraphs_guts.sql](https://github.com/cbwinslow/mlb-baseball/blob/3a4e2c18df98c5b9df04535981b6b6368876ee02/mlb_baseball/sql/gold_fangraphs_guts.sql)
- **Notes:** Verbatim numeric conform of FanGraphs' own published constants -- no re-derivation. Not yet independently tie-out tested against a second source, hence "published" rather than "validated" (ADR-290). This is a cross-check/reference relation: a publishable wOBA/FIP for this project's own data is computed from core.play, not from here (see gold.fangraphs_guts' table comment).

## fangraphs_park_factors

FanGraphs' own published park factors -- one row per team-season showing how much a ballpark inflates or deflates offense (overall, and broken out by hit type: home runs, doubles, triples, walks, strikeouts, batted-ball type). This project stores FanGraphs' numbers as-is; it does not recompute them.

- **Status:** published
- **Citation:** FanGraphs, park factors (https://www.fangraphs.com/guts.aspx?type=pf)
- **Data source:** raw.fangraphs_park_factors
- **Grain:** team-season
- **Layer:** gold
- **Source:** [https://github.com/cbwinslow/mlb-baseball/blob/3a4e2c18df98c5b9df04535981b6b6368876ee02/mlb_baseball/sql/gold_fangraphs_park_factors.sql](https://github.com/cbwinslow/mlb-baseball/blob/3a4e2c18df98c5b9df04535981b6b6368876ee02/mlb_baseball/sql/gold_fangraphs_park_factors.sql)
- **Notes:** Verbatim numeric conform of FanGraphs' own published park factors -- no re-derivation, component factors kept exactly as FanGraphs publishes them. Scoped to season >= 2003 (pre-2003 FanGraphs park factors are low value and the franchise set is unstable, so those rows are deliberately left unconformed in raw). Not yet independently tie-out tested against a second source, hence "published" rather than "validated" (ADR-290).
Reference/cross-check only, same posture as gold.fangraphs_guts: no gold.fangraphs_* relation may be public_safe or appear in the published research dataset (docs/SOURCE_RIGHTS.md records no Baseball-Reference/ FanGraphs redistribution permission). This catalog entry's `visibility: public` describes the formula/citation only -- it does NOT mean the underlying data may be redistributed; see mlb_baseball/export.py.
This is a distinct thing from mlb_baseball/model/park.py's own park factor (see the park_factor_project entry in this catalog) -- that one is computed from this project's own core.game data using Pete Palmer's classical home-vs-road run-ratio method and IS usable as a model feature / in publishable output. ADR-290: "a publishable park factor is computed from core.play [or core.game], not from here."

## leverage_index_empirical

How much a single moment in a game matters to the final result, on a scale where 1.0 is an average moment (a bases-loaded, bottom-of-the-9th, tied game is a very high-leverage moment; a lopsided blowout in the 7th is a very low one). Built from this project's own real, historical win-expectancy swings (win_expectancy_empirical), not a hand-typed table.

- **Status:** published
- **Citation:** Tom Tango, Leverage Index (general concept, described in Tango, Lichtman & Dolphin, "The Book: Playing the Percentages in Baseball," 2006).

- **Data source:** gold.win_expectancy (itself built from raw.retrosheet_event, raw.retrosheet_gameinfo)
- **Grain:** (inning, half, outs, base state, score-margin bucket)
- **Layer:** gold
- **Source:** [https://github.com/cbwinslow/mlb-baseball/blob/3a4e2c18df98c5b9df04535981b6b6368876ee02/mlb_baseball/model/leverage_index.py](https://github.com/cbwinslow/mlb-baseball/blob/3a4e2c18df98c5b9df04535981b6b6368876ee02/mlb_baseball/model/leverage_index.py)
- **Notes:** Replaces the previously hand-typed, unvalidated leverage table used directly inside run_expectancy.py (ADR-262). Normalized so the sample- weighted average across every state is exactly 1.0, the standard Leverage Index convention. health_check() checks that this normalization holds (weighted average within 0.85-1.15 of 1.0) and that a well-known maximum-leverage situation (bottom 9th, bases loaded, 0 outs, tied) scores well above 1.0 -- both currently pass, and are real sanity checks against known baseball facts, but are plausibility bounds rather than a tie-out against one specific externally-published number, so "published" rather than "validated".
tests/integration/test_model_leverage_index.py's test_compute_matches_hand_calculation hand-derives its own expected value using the same arithmetic the SQL performs -- self-consistency, not an independent tie-out.
Distinct from mlb_baseball/model/leverage.py's BullpenLeverageEngine (see that module's own catalog entry, bullpen_leverage_volatility_engine) -- that is a separate, NOT-database-integrated CLI calculator with uncited constants; this is the real, production-integrated Leverage Index gold table used elsewhere in the pipeline (e.g. run_expectancy.py).

## park_factor_project

How much a ballpark inflates or deflates scoring and specific outcomes (home runs, doubles, triples, and home runs split by batter handedness), computed from this project's own game data (not FanGraphs'), using trailing 1/3/5-year windows so a park's rating is based on real games already played, never future ones. Also includes air-density and effective wind-speed features for the same park/date.

- **Status:** published
- **Citation:** Pete Palmer & John Thorn, "The Hidden Game of Baseball" (1984) -- classical home-vs-road run-ratio park factor method.

- **Data source:** core.game (home/away runs, venue, weather)
- **Grain:** (venue, season), 1/3/5-year trailing windows, joined onto a per-game feature row
- **Layer:** gold
- **Source:** [https://github.com/cbwinslow/mlb-baseball/blob/3a4e2c18df98c5b9df04535981b6b6368876ee02/mlb_baseball/model/park.py](https://github.com/cbwinslow/mlb-baseball/blob/3a4e2c18df98c5b9df04535981b6b6368876ee02/mlb_baseball/model/park.py)
- **Notes:** DISTINCT from gold.fangraphs_park_factors (see that entry) -- FanGraphs' relation is an external, verbatim-conformed reference/cross-check-only relation that may never be public_safe or used as a model input (ADR-290: "a publishable park factor is computed from core.play [or core.game], not from here"). This module IS that publishable park factor: computed from this project's own core.game runs data using Palmer's classical home-run-rate-vs-road-run-rate ratio, regressed to the league scoring environment, extended with component (HR/2B/3B/handedness-split) factors and environmental air-density/wind features (ADR-094). Correctly implements the cited home-vs-road ratio method per direct code read.
tests/integration/test_model_park.py's test_compute_matches_hand_calculation_and_stays_out_of_its_own_trailing_window hand-derives its own expected value using the same arithmetic the SQL performs -- self-consistency, not an independent tie-out against a real externally-published park-factor number, so "published" rather than "validated".

## starter_fip

Fielding Independent Pitching (FIP): a starting pitcher's performance measured only from the outcomes a pitcher most directly controls -- strikeouts, walks, hit-by-pitches, and home runs -- put on the same scale as ERA. This project computes it point-in-time, entering each game, from games the pitcher has already started that season (ERA itself is not available from this project's own event data before 2026, so FIP stands in for it as a starting-pitcher-quality feature).

- **Status:** published
- **Citation:** Tango, Lichtman & Dolphin, "The Book: Playing the Percentages in Baseball" (2006) -- Fielding Independent Pitching (FIP) formula.

- **Data source:** raw.retrosheet_event, raw.retrosheet_gameinfo (1910-2025); raw.mlb_playbyplay (2026+); health_check reconciles against raw.bref_pitching
- **Grain:** team (starting pitcher), point-in-time entering each game
- **Layer:** gold
- **Source:** [https://github.com/cbwinslow/mlb-baseball/blob/3a4e2c18df98c5b9df04535981b6b6368876ee02/mlb_baseball/model/starter.py](https://github.com/cbwinslow/mlb-baseball/blob/3a4e2c18df98c5b9df04535981b6b6368876ee02/mlb_baseball/model/starter.py)
- **Notes:** FIP = (13*HR + 3*(BB+HBP) - 2*K) / IP + FIP_constant. Correctly implements the cited formula per direct code read (event_cd-based K/BB/HR counts, event_outs_ct-based innings, resp_pit_id for correctly attributing plays to the pitcher actually charged, confirmed against Chadwick's own field documentation).
SAME fixed-vs-real-weights issue as team_woba: FIP_CONSTANT is a single fixed 3.10 (a commonly-cited modern value) applied to every season, not a year-specific constant -- the module's own docstring says so directly ("early-20th-century FIP values sit on a slightly different implied run environment than their true era"). This is the same class of gap as team_woba's fixed weights: gold.fangraphs_guts (ADR-290) now carries a real, era-accurate FIP constant per season that this module does not use. Flagged as a known inconsistency worth a follow-up, not fixed here.
STRONGER evidence than most entries in this batch, but short of "validated": health_check() runs a REAL, currently-passing, automated reconciliation of this module's summed strikeout and outs totals against raw.bref_pitching (Baseball-Reference, an independent source) via `mlb doctor` -- 98.3% of 13,613 real pitcher-seasons match within a small tolerance (documented, calibrated against real production data, the residual traced to Retrosheet's own ~1.7% published-event-file coverage gap, not a bug). This is a real, independent, currently-passing check -- but it only reconciles two of FIP's four inputs (strikeouts and outs), not walks, HBP, or home runs, and it never compares the final FIP number itself against any independently published FIP value. "validated" per this catalog's spec requires the metric's own output be tied out, not just a fraction of its inputs, so this stays "published" -- worth a second look given how close this partial evidence comes.
tests/integration/test_model_starter.py's test_compute_rolling_fip_and_rates_match_hand_calculation hand-derives its own expected FIP value using the same arithmetic the SQL performs -- self-consistency, not an independent tie-out; consistent with the self-referential test pattern found across this whole batch.

## team_war_prior

A team's total Wins Above Replacement (WAR) from the season before the game being predicted, used as a model feature. This project does not calculate WAR itself -- it takes Baseball-Reference's own published player WAR values, adds up each team's players, and lags it by one full season so a game is never scored using WAR data that only exists because of games played after it (which would let the model "see the future").

- **Status:** published
- **Citation:** Baseball-Reference, WAR Explained (https://www.baseball-reference.com/about/war_explained.shtml)
- **Data source:** core.player_war (loaded from raw.bref_war_batting, raw.bref_war_pitching)
- **Grain:** team-season (lagged one season, joined onto a per-game feature row)
- **Layer:** gold
- **Source:** [https://github.com/cbwinslow/mlb-baseball/blob/3a4e2c18df98c5b9df04535981b6b6368876ee02/mlb_baseball/model/war.py](https://github.com/cbwinslow/mlb-baseball/blob/3a4e2c18df98c5b9df04535981b6b6368876ee02/mlb_baseball/model/war.py)
- **Notes:** This module sums and lags an externally-published metric; it does not reimplement Baseball-Reference's own WAR formula (that formula is complex and involves choices Baseball-Reference makes internally). Correctly implemented per direct code read: SUM(war) per team-season, joined through a hand-built bref-to-Retrosheet team-code crosswalk (_BREF_TO_RETRO, current 30 teams only -- older, relocated/renamed franchises correctly get NULL rather than a guessed mapping), lagged via `season - 1` so a game always uses the prior season's total, never the current, still-accumulating one. tests/integration/test_model_war.py verifies the lag and the crosswalk with a hand-built fixture (self-consistency, not an external tie-out), so this is "published" (correctly implemented, cited formula) rather than "validated" -- no automated test compares team_war_prior against an independently published team-level WAR total.
Rights note, not a visibility question: docs/SOURCE_RIGHTS.md / export.py record core.player_war (Baseball-Reference WAR) as local_research only -- no redistribution permission. This catalog entry's `visibility: public` describes the formula/citation only (Baseball-Reference's WAR methodology is publicly documented), separate from the data-redistribution rights question tracked in mlb_baseball/export.py's BACKBONE_EXCLUDED.

## team_woba

Weighted On-Base Average (wOBA): a team's offense measured in one number that weighs each way of reaching base (walk, hit-by-pitch, single, double, triple, home run) by how much it actually tends to help score runs, instead of counting every one the same way batting average does. This project computes a rolling, point-in-time team wOBA entering each game, built from games strictly before it (never leaking games not yet played).

- **Status:** published
- **Citation:** FanGraphs, wOBA methodology (Sabermetrics Library, https://www.fangraphs.com/library/offense/woba/); Tango, Lichtman & Dolphin, "The Book: Playing the Percentages in Baseball" (2006), for the underlying linear-weights concept.

- **Data source:** raw.retrosheet_event, raw.retrosheet_gameinfo (1910-2025); raw.mlb_playbyplay (2026+)
- **Grain:** team, point-in-time entering each game
- **Layer:** gold
- **Source:** [https://github.com/cbwinslow/mlb-baseball/blob/3a4e2c18df98c5b9df04535981b6b6368876ee02/mlb_baseball/model/offense.py](https://github.com/cbwinslow/mlb-baseball/blob/3a4e2c18df98c5b9df04535981b6b6368876ee02/mlb_baseball/model/offense.py)
- **Notes:** KNOWN LIMITATION, flagged for a follow-up (not fixed here per this batch's scope): the weights used (W_UBB=0.690, W_HBP=0.722, W_1B=0.878, W_2B=1.242, W_3B=1.569, W_HR=2.015 -- defined in offense.py) are a SINGLE FIXED set applied to every season, not FanGraphs' real per-season weights (which genuinely shift year to year, published on FanGraphs' "Guts!" page). The module's own docstring is explicit about this tradeoff and says so directly: "these aren't mistaken for a year-precise reproduction." Since ADR-290, gold.fangraphs_guts now holds exactly the real, era-accurate per-season weights this module would need -- but team_woba has not been updated to join against it. This is a real, live inconsistency worth a follow-up (era-accurate reference data exists but isn't used by the production formula), not something this catalog change fixes.
Correctly implements the cited formula per direct code read (numerator = weighted sum of unintentional walks/HBP/1B/2B/3B/HR; denominator = AB + uBB + SF + HBP). tests/integration/test_model_offense.py's test_compute_rolling_woba_matches_hand_calculation hand-derives its own expected value using the same arithmetic the code uses -- this is a self-consistency test, not an independent tie-out, so status is "published" rather than "validated". The module docstring separately describes a one-off MANUAL check (computed the real 2023 MLB league-average wOBA directly from raw.retrosheet_event with these weights, got .317, close to the real 2023 league figure) -- good supporting evidence, but not an automated test, so it doesn't change the status call either.

## team_wrc_plus

Weighted Runs Created Plus (wRC+): a team's offense compared to the league average, adjusted for the ballpark it plays in, where 100 is exactly average (110 means 10% better than average, 90 means 10% worse). Built on top of this project's own team wOBA and park-factor features, computed point-in-time entering each game.

- **Status:** published
- **Citation:** FanGraphs, wRC+ methodology (Sabermetrics Library, https://www.fangraphs.com/library/offense/wrc/)
- **Data source:** raw.retrosheet_event, raw.retrosheet_gameinfo (1910-2025); raw.mlb_playbyplay (2026+); depends on gold.game_feature's own home_woba/park_factor columns
- **Grain:** team, point-in-time entering each game
- **Layer:** gold
- **Source:** [https://github.com/cbwinslow/mlb-baseball/blob/3a4e2c18df98c5b9df04535981b6b6368876ee02/mlb_baseball/model/offense.py](https://github.com/cbwinslow/mlb-baseball/blob/3a4e2c18df98c5b9df04535981b6b6368876ee02/mlb_baseball/model/offense.py)
- **Notes:** wRC+ = (((team_wOBA - league_wOBA) / WOBA_SCALE) + 1) / (park_factor/100) * 100. Correctly implements the standard, cited wRC+ formula per direct code read; the module docstring shows the required sanity property algebraically (a league-average team wOBA in a neutral park reduces to exactly 100, which wRC+ requires by definition). WOBA_SCALE is a single fixed value (1.20, the commonly-cited modern-era figure) rather than year-specific, the same fixed-vs-real-weights tradeoff as team_woba (see that entry's notes) -- flagged here for the same reason.
Unlike team_woba, there is no dedicated automated test asserting a specific numeric wRC+ value against any calculation (hand-derived or otherwise) -- only a coverage/health-check test (test_health_check_flags_a_wrc_plus_coverage_gap) that a value is present, not that it is correct. "published" here reflects a correctly-implemented, cited formula read directly from source, not any test evidence -- weaker evidence than team_woba's self-consistency test, worth a second look.
Inherits team_woba's known fixed-weight limitation (this metric is computed from team_woba, which uses a single fixed weight set rather than gold.fangraphs_guts' now-available era-accurate weights -- see team_woba's notes).

## win_expectancy_empirical

For every real game situation (inning, which team is batting, outs, which bases are occupied, and score margin) that has actually happened in this project's historical play-by-play data, the real observed percentage of time the home team went on to win. This is an average of what actually happened, not a fitted formula or a hand-typed lookup table.

- **Status:** published
- **Citation:** Tango, Lichtman & Dolphin, "The Book: Playing the Percentages in Baseball" (2006) -- empirical win-expectancy tables are a standard sabermetric reference method described in this book.

- **Data source:** raw.retrosheet_event, raw.retrosheet_gameinfo
- **Grain:** (season, inning, half, outs, base state, score-margin bucket)
- **Layer:** gold
- **Source:** [https://github.com/cbwinslow/mlb-baseball/blob/3a4e2c18df98c5b9df04535981b6b6368876ee02/mlb_baseball/model/win_expectancy.py](https://github.com/cbwinslow/mlb-baseball/blob/3a4e2c18df98c5b9df04535981b6b6368876ee02/mlb_baseball/model/win_expectancy.py)
- **Notes:** Replaces a previously hand-typed, unvalidated leverage lookup table (ADR-262) with a real average over every historical observation of each state. health_check() checks two real sanity bounds against known baseball facts (a tied game in the top of the 1st should show home-field advantage of roughly 0.50-0.58; a near-certain-loss state should be near 0.00) -- both currently pass, but these are broad plausibility ranges, not a tight tolerance against one specific externally-published figure, so this counts as supporting evidence for "published," not a "validated" tie-out.
tests/integration/test_model_win_expectancy.py's test_compute_populates_real_observed_win_rate seeds two synthetic games and asserts the exact resulting average (1 win / 2 observations = 0.5) -- proves the aggregation logic is correct, but is a self-built fixture, not an independent published value.
