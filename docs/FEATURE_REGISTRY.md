# Feature registry

This registry records the first reusable feature family. It is intentionally
narrow: later feature families must be registered separately rather than being
silently added to `gold.game_feature`.

The read-only [`mlb field-census`](RAW_CORE_GOLD_FIELD_CENSUS.md) and
[feature-admission queue](FEATURE_ADMISSION_QUEUE.md) are the gate before a
new family enters this registry. A landed raw value is not a feature merely
because it is populated; it needs an explicit point-in-time contract.

| Family / version | Grain and key | Availability and formula | Null policy | Tests / source lineage |
| --- | --- | --- | --- | --- |
| `game_base_v1` | One completed or scheduled regular-season MLB game; `mlb_game_pk` is unique, with `core.game.id` populated for completed games | `feature_cutoff_at` is `raw.mlb_schedule.game_datetime`. Team record, win rate, runs for/against, and rest use only completed regular games ordered before cutoff, then game number, then key. `home_field` is true by definition for the home-side columns. | First tracked game has NULL record/runs/rest; scheduled games have NULL label; unavailable venue remains NULL. Missing MLB key or cutoff excludes a row. | `tests/integration/test_game_feature_contract.py`; official MLB schedule payload retained in `raw.mlb_schedule`; contract in `TABLE_CONTRACTS.md`. |
| `bsr_v1` | Per (game, team) prior stolen-base run value; `home_sb`/`away_sb`/`home_cs`/`away_cs`/`home_wsb`/`away_wsb` on `gold.game_feature` | Rolling within-season entering value from `raw.retrosheet_event`'s `run1/2/3_sb_fl`/`_cs_fl` (Chadwick cwevent's per-runner advance flags, not primary `event_cd` -- catches steals/caught-stealings embedded as a secondary event on a compound play). `wSB = SB*0.2 + CS*(-0.42) - lgwSB*(1B+UBB+HBP)`, Tom Tango linear weights (ADR-081, admission queue BSR-01). Covers 1910-2025 (Retrosheet range); no 2026+ live equivalent built yet. | `home_sb`/`home_cs` ungated (always populated once a team has one prior game with real Retrosheet coverage); `home_wsb` NULL below `MIN_ATTEMPTS=5` (SB+CS) or before enough season-to-date league data exists for `lgwSB`. | `tests/integration/test_model_bsr.py` (hand-calculated fixture, two missing-table gate tests, plausible-range/min-sample-gate/coverage health-check tests); `mlb_baseball/model/bsr.py`, ADR-081. |
| `diff_v1` | Per game; `win_pct_diff`/`win_pct_10_diff`/`pyth_wpct_diff`/`elo_diff`/`woba_diff`/`wrc_plus_diff` on `gold.game_feature` | Pure algebra (`home_X - away_X`) over six already-approved paired team features -- no new raw dependency, no join. Computed in `run()`, after `elo.compute_ratings()` (not inside `enrich_feature_stage()` -- `elo_diff` needs real `home_elo`/`away_elo`, which only `elo.compute_ratings()` populates; a real bug from an earlier attempt, see ADR-082) (ADR-082, admission queue INT-01). | NULL whenever either the home or away side of a pair is itself NULL (subtracting a NULL is NULL in SQL). | `tests/integration/test_model_diff.py` (hand-calculated fixture across all six columns, NULL-propagation test, idempotency, health-check parity violation and clean-pass tests); `tests/integration/test_model_enrich_stage.py::test_diff_compute_after_elo_ratings_produces_a_real_elo_diff`; `mlb_baseball/model/diff.py`, ADR-082. |
| `trend_v1` | Per side; `home_win_pct_trend`/`away_win_pct_trend` on `gold.game_feature` | Pure algebra per side (`home_win_pct_trend = home_win_pct_10 - home_win_pct`; `away_win_pct_trend = away_win_pct_10 - away_win_pct`) over two already-approved base-family column pairs -- no new raw dependency, no join. Positive means playing better recently than season rate; negative means worse (ADR-083, admission queue INT-02). | NULL whenever either `home_win_pct`/`away_win_pct` or `home_win_pct_10`/`away_win_pct_10` is itself NULL (e.g. a team's first game of the season). | `tests/integration/test_model_trend.py` (hand-calculated fixture for both directions, NULL-propagation test, idempotency, health-check parity violation and clean-pass tests); `mlb_baseball/model/trend.py`, ADR-083. |
| `experience_v1` | Per starter, per game; `home_starter_career_bf`/`away_starter_career_bf`/`home_starter_career_ip`/`away_starter_career_ip` on `gold.game_feature` | Career (not season-scoped) batters-faced/innings-pitched from `raw.retrosheet_event`, entering value only -- same event-code counting as `starter.py`'s own season window, but with no season partition (ADR-085, admission queue PLN-04's "prior MLB PA/IP" half). | NULL for a pitcher's first-ever Retrosheet-covered appearance (no career prior at all). | `tests/integration/test_model_experience.py` (cross-season-boundary fixture, doubleheader-ordering regression, idempotency, two missing-table gate tests, health-check test); `mlb_baseball/model/experience.py`, ADR-085. |
| `starter_prior_v1` (`starter.py`, ADR-034) | game-player/game-team; true FIP (not ERA) + K%/BB%/HR% from a starter's prior completed appearances | Historical Retrosheet path (1910-2025) + `compute_live()` for 2026 (`raw.mlb_playbyplay`) + `compute_probable()` for still-upcoming games (`raw.mlb_probable`, ADR-048) | NULL unresolved/debut starter | `tests/integration/test_model_starter.py`; reconciled at full scale (13,613 pitcher-seasons) against `raw.bref_pitching`, permanent `mlb doctor` check. Wired into `gbm.py`'s `FEATURE_COLUMNS`. |
| `starter_workload_v1` (`starter_workload.py`, PIT-03, ADR-068/069) | game-player; days since prior start, prior 7-day outs | Historical + live 2026 + probable-starter paths, day-collapse RANGE-frame window | NULL unknown starter/debut start | `tests/integration/test_model_starter_workload.py`. **Not currently in `gbm.py`'s `FEATURE_COLUMNS`** -- corrected 2026-08-20 (PR review, Kilo): this was tried, not "never tried" -- it was added to `OPTIONAL_COLUMNS` alongside `team_prior_offense_defense_v1` in the same 2026-08-20 retrain and reverted together when the combined attempt didn't beat both baselines (see `docs/DECISIONS.md`'s entry for that change). |
| `bullpen_v1` (`bullpen.py`, ADR-039) | game-team; rolling relief FIP/K%/BB% + trailing-3-day relief-outs fatigue | Team-level by design (which reliever pitches today is an in-game decision, per-pitcher composition would leak); historical + `compute_live()`/`compute_upcoming()` for 2026 (ADR-051) | NULL for a team with no qualifying prior relief history; uncovered games excluded from the backbone entirely, not zero-filled (issue #29) | `tests/integration/test_model_bullpen.py`; 406,516-row outs reconciliation. Wired into `gbm.py`'s `FEATURE_COLUMNS`. |
| `park_factor_v1` (`park.py`, ADR-035) | game/venue; trailing 3-year ratio of a park's runs-per-game to league average, scaled around 100 | Derived purely from `core.game`'s own historical scores, zero external dependency | NULL unavailable venue/insufficient trailing window | Verified: Coors Field ranks highest (135.4), matching sabermetric consensus. Wired into `gbm.py`'s `FEATURE_COLUMNS` as `park_factor`. |
| `team_offense_v1` (`offense.py`, ADR-036/037; admission queue OFF-05/06) | game-team; rolling within-season team wOBA (FanGraphs' own published linear weights, recreated not scraped) + park/league-adjusted wRC+ | Prior completed events, `raw.retrosheet_event` + `compute_live()` for 2026 | NULL below min-PA | Verified: real 2023 league-average wOBA = .317 (known real value); wRC+ algebraically must equal exactly 100 for a neutral-park average hitter, tested directly. Wired into `gbm.py`'s `FEATURE_COLUMNS`. |
| `war_prior_v1` (`war.py`, ADR-038) | game-team; prior-season team WAR | `core.player_war`, one full season lag (same treatment as every other season-aggregate source here) | NULL first tracked season | Verified: 2023's Braves/Rangers (real, well-known strong teams) rank highest entering 2024. Wired into `gbm.py`'s `FEATURE_COLUMNS`. |
| `oaa_prior_v1` (`oaa.py`, ADR-040; admission queue DEF-03) | game-team; prior-season Statcast Outs Above Average | `raw.statcast_oaa.fielding_runs_prevented` (2016-2026), one season lag | NULL before 2016 or first tracked season | Wired into `gbm.py`'s `FEATURE_COLUMNS` as `home_oaa_prior`/`away_oaa_prior`. |
| `speed_prior_v1` (`speed.py`, ADR-041) | game-team; prior-season `competitive_runs`-weighted average Statcast Sprint Speed | `raw.statcast_sprint_speed` (2015+), one season lag | NULL before 2015 or first tracked season | Wired into `gbm.py`'s `FEATURE_COLUMNS` as `home_speed_prior`/`away_speed_prior`. |
| `framing_prior_v1` (`framing.py`, ADR-045) | game-team (resolved from player via `war.py`'s `_BREF_TO_RETRO` crosswalk through `core.player_war`) | `raw.statcast_framing.rv_tot`, one season lag | NULL for ~48% of rows -- traced to `core.player_war`'s own min-playing-time threshold excluding rookies/prospects, not a join bug | Verified against real 2024 data. **Deliberately not in `gbm.py`'s `FEATURE_COLUMNS`**: a retrain that added it didn't beat both baselines (documented negative result, see `gbm.py`'s own comment). |

`game_base_v1` is the only approved input family for the first game-win
experiment lab. The experiment snapshot copies its resolved completed rows
immutably. Final-season reporting tables, postgame scores (except for the
sequential Elo update after a prediction), markets, and legacy enrichment
columns are not experiment features.

`home_win` is a completed-game label, never a training feature. The base family
does not include pitchers, lineups, weather, markets, or pitch-level metrics.

`team_prior_offense_defense_v1` (`mlb_baseball/model/team_rate.py`, ADR-061)
adds prior rolling OBP/SLG/ISO/BB%/K%/BABIP (admission queue OFF-01-04) and
prior runs-for/allowed averages (OFF-08/DEF-01) as compatibility enrichment
columns on `gold.game_feature` -- not part of `game_base_v1`, but (correction,
2026-08-20: this note was stale) wired into the live daily pipeline via
`enrich_feature_stage()` since ADR-061, and into `gbm.py`'s `FEATURE_COLUMNS`
as of 2026-08-20 (a real gap: it sat built, tested, and populated in
production for weeks before anyone tried it in the champion model -- see
`docs/DECISIONS.md`'s entry for that change for the retrain result).

All families above (`starter_prior_v1` through `framing_prior_v1`) share this
same "compatibility enrichment column" status relative to `game_base_v1` and
the experiment lab: none are approved experiment-snapshot inputs, all are
wired into the live `mlb predict` pipeline via `enrich_feature_stage()`, and
each is independently listed above (not "silently added," per this
document's own rule) once it lands. `starter_workload_v1` is the one
built-and-populated exception still missing from `gbm.py`'s own feature set,
same shape as `team_prior_offense_defense_v1` was until this correction.
