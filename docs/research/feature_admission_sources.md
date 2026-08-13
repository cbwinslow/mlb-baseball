# Feature-admission research sources (draft)

Status: research input for Plan 03G, not an approved feature contract.  Accessed
2026-08-12.  This note distinguishes a statistic's *definition* from proof that
the project has a lawful, complete, time-stamped input for it.  A value may enter
a pregame feature only when it is recomputed from events strictly before the
experiment's cutoff, or was captured from a provider with a retained publication
time no later than that cutoff.

## Cross-cutting rules

- **Pregame candidate:** season-to-date, expanding, or rolling calculation using
  only finished earlier games.  Record the source event cutoff, denominator,
  minimum sample, league/park constants, and whether the value is team, player,
  or matchup grain.
- **Not pregame by default:** end-of-season leaderboards, final game totals,
  postgame corrections, values without a publication timestamp, and every
  in-game value after the declared forecast cutoff.  They are useful descriptive
  or validation data, but are leakage until a historical as-of reconstruction
  proves otherwise.
- **Provider versions are separate features.**  FanGraphs WAR (fWAR),
  Baseball-Reference WAR (rWAR/bWAR), and Baseball Prospectus WARP are related
  frameworks, not interchangeable columns.  FanGraphs itself says the providers
  use different methods for offensive, defensive, and pitching value
  ([WAR explanation](https://library.fangraphs.com/misc/war/)).  Baseball-
  Reference likewise describes WAR as an approximation with many methodology
  choices and published revisions
  ([WAR explained](https://www.baseball-reference.com/about/war_explained.shtml)).
- **Weights/constants are versioned input.**  Store the season, league, provider
  and exact weights/constants alongside any reimplementation.  Do not apply a
  modern wOBA weight, FIP constant, park factor, or Statcast definition to an
  earlier era without a documented decision.

## Team offense and defense

| Candidate family | Formula / definition source | Valid pregame form | Important caveat |
| --- | --- | --- | --- |
| OBP, SLG, ISO, BB%, K%, BABIP | Use numerator and denominator counts from completed prior plate appearances; `ISO = SLG - AVG`; hitter/pitcher BABIP uses `(H-HR)/(AB-K-HR+SF)` in FanGraphs' glossary ([pitching list](https://library.fangraphs.com/pitching/complete-list-pitching/)). | Team aggregate, opponent-adjusted only after documenting the adjustment; season-to-date and rolling variants. | Denominator must be retained; early-season rates need shrinkage/minimum sample.  Historical play data has known count/pitch-detail gaps, so rate availability differs by era. |
| wOBA / wRAA | Weighted on-base average applies linear run weights to unintentional BB, HBP, 1B, 2B, 3B and HR over the appropriate wOBA denominator.  FanGraphs explains that linear weights are sample-dependent estimates ([Linear Weights](https://library.fangraphs.com/principles/linear-weights/)); Baseball-Reference publishes a provider-specific example with its own events/weights ([wRAA method](https://www.baseball-reference.com/about/war_explained_wraa.shtml)). | Recompute from prior completed PAs with season/league-specific published or project-derived weights frozen in a constants table. | Never call a project calculation “FanGraphs wOBA” unless its exact weights, exclusions and scale match the cited provider version.  Final leaderboard wOBA is descriptive only. |
| wRC+ / park-adjusted offense | FanGraphs defines wRC+ as weighted runs created plus; its position-player WAR method requires player wOBA, PA, home park factor, league wOBA, wOBA scale, and league runs per PA ([WAR for position players](https://library.fangraphs.com/war/war-position-players/)). | A project-owned entering-game estimate using only prior events and frozen league/park inputs. | Expensive and version-sensitive; park factors often use multi-year information and must not reach forward.  Keep a project ID distinct from provider wRC+. |
| Run differential and Pythagorean expectation | `W% = RS^x / (RS^x + RA^x)`; Baseball-Reference documents exponent 2 and the variable PythagenPat exponent `x=(runs/game)^.285` ([runs to wins](https://www.baseball-reference.com/about/war_explained_runs_to_wins.shtml)). | Prior completed team games only, with a stated season-to-date or rolling window. | FanGraphs cautions that Pythagorean expectation expresses a runs/wins relationship, not automatically a talent forecast ([Pythagorean Win-Loss](https://library.fangraphs.com/principles/expected-wins-and-losses/)).  Treat it as one feature/baseline, not a final answer. |
| Defensive quality | Team errors, double plays, runs allowed and play-derived defensive events can be calculated from finished games.  MLB notes that Statcast also supplies OAA, but its coverage/definition is era-specific ([Statcast glossary](https://www.mlb.com/glossary/statcast)). | Prior-game team defensive aggregates; only use player OAA after coverage and timing are proven. | Do not mistake team runs allowed for pure defense: pitching, park and sequencing confound it.  Provider defensive ratings are not interchangeable. |

## Pitching and bullpen

| Candidate family | Formula / definition source | Valid pregame form | Important caveat |
| --- | --- | --- | --- |
| FIP components and FIP | `FIP = (13*HR + 3*(BB+HBP) - 2*K) / IP + constant`; the constant is season-specific and aligns league FIP with league ERA ([FanGraphs FIP](https://library.fangraphs.com/pitching/fip/)). | Aggregate only completed appearances before cutoff; store HR, BB, HBP, K, IP and the season/league constant. | FIP is not a single-game talent estimate; FanGraphs explicitly says it needs more than a handful of innings.  Do not use a final-season FIP column as a historical pregame input. |
| xFIP / HR-FB | FanGraphs defines xFIP as FIP with HR replaced by expected HR based on fly balls and league-average HR/FB ([xFIP](https://library.fangraphs.com/pitching/xfip/)). | Project-owned prior-appearance estimate with frozen league HR/FB baseline. | HR/FB baseline/version and fly-ball classification must be explicit.  This is a later candidate until source coverage for fly balls is measured. |
| K-BB%, WHIP, ERA, BABIP allowed | Derive from prior event/box-score totals; FanGraphs defines WHIP as `(BB+H)/IP`, ERA as `(ER*9)/IP`, and pitcher BABIP as above ([pitching glossary](https://library.fangraphs.com/pitching/complete-list-pitching/)). | Starter and bullpen aggregates separated by role, with rate denominators and sample sizes. | ERA includes defense, sequencing and official scoring.  Do not silently substitute it for fielding-independent skill. |
| Starter rest, workload and bullpen fatigue | Transparent schedule/event features: days since last appearance/start, pitches/outs in preceding 1/3/7 days, consecutive-use flags, and active/known roster status. | Calculate from prior completed appearances and schedule timestamps; use only a starter identity known at cutoff. | A probable pitcher is explicitly “subject to change” on MLB's listing ([probable pitchers](https://www.mlb.com/probable-pitchers/)); it is valid only if the observation and retrieval time are retained.  Never backfill the eventual starter into an earlier forecast. |
| Pitch-mix, velocity, whiff/chase/contact, movement | MLB defines pitch velocity, movement and spin rate; Baseball Savant Search exposes pitch type/movement and whiff-rate fields ([Statcast glossary](https://www.mlb.com/glossary/statcast), [Search](https://baseballsavant.mlb.com/en/statcast_search)). | Rolling prior pitches by pitcher, batter handedness, pitch type and count bucket, subject to coverage tests. | Statcast began in every MLB park in 2015; retain a coverage flag and do not produce fake pre-2015 values ([MLB glossary](https://www.mlb.com/glossary/statcast)).  Do not use pitches from the forecast game. |

## Players, lineups and platoons

- **Confirmed lineup/player availability:** Retrosheet event files include the
  actual starters and batting order, but these are postgame records.  They prove
  identity and historical validation, not pregame availability.  Retrosheet says
  a game contains start/sub records and roster handedness
  ([event-file specification](https://www.retrosheet.org/eventfile.htm)).  A
  pregame lineup feature requires an independently retained lineup publication
  timestamp; without it, classify as blocked rather than joining actual starters
  backward into forecasts.
- **Probable starter:** admit only as an `as_of` observation.  MLB's probable
  pitcher page is useful as a current-source contract but says the listing is
  subject to change.  Version it with source URL, observation time, game key and
  confidence/status; use a distinct “confirmed starter” flag when supported.
- **Handedness/platoon:** Retrosheet roster/start records establish player and
  batting/throwing handedness.  Build batter-vs-opposing-starter and projected
  lineup handedness aggregates only when both identities are known before the
  cutoff.  Missing or unconfirmed lineups must produce explicit null/availability
  flags, never realized game lineups.
- **Age/experience:** birth date and service/appearance history may become a
  pregame input if identity crosswalk quality is measured.  Use age on game date
  and prior completed experience, not a retrospective career total.

## Context and schedule

- **Venue, home/away, game number, doubleheader, scheduled start:** Retrosheet
  documents game ID/date/home team/game number and notes the 0/1/2 doubleheader
  indicator ([event-file specification](https://www.retrosheet.org/eventfile.htm)).
  These are high-confidence schedule-context candidates once mapped to canonical
  game identity.  Preserve reschedules/suspensions as schedule history instead
  of overwriting it.
- **Weather, umpire, attendance, day/night, DH rule:** Retrosheet's `info`
  records may include weather/umpire fields, but it explicitly says not every
  type is present ([event-file specification](https://www.retrosheet.org/eventfile.htm)).
  Actual game-time weather and umpires are normally postgame evidence.  A
  pregame version requires an archived forecast/assignment plus timestamp; do
  not use realized weather or eventual umpire assignment without that evidence.
- **Travel, timezone, rest, series:** derive travel distance/timezone change from
  known prior finished schedule and a versioned venue reference.  It is a
  project-derived feature with clear definitions, not a provider metric.  Test
  doubleheaders, neutral/relocated games and postponed/resumed histories.

## Statcast batted-ball and expected metrics

- MLB defines a barrel as the ideal exit-velocity/launch-angle combination and a
  hard-hit ball as exit velocity of at least 95 mph.  It defines xBA as the
  likelihood a batted ball becomes a hit and xwOBA as a model using exit
  velocity, launch angle and, for some batted balls, sprint speed
  ([Statcast metrics context](https://baseballsavant.mlb.com/statcast-metrics-context)).
- Prior-event rolling player/team means and distributions for exit velocity,
  barrel rate, hard-hit rate, launch angle, xBA and xwOBA are plausible
  candidates after coverage tests.  Use BBE or PA denominators exactly as named;
  retain event counts and a minimum-sample/shrinkage policy.
- Coverage is a hard admission condition: barrels, hard-hit rate and launch-angle
  sweet-spot are listed from 2016 onward; newer bat-tracking measures begin in
  2023 and 2023 is partial ([Statcast metrics context](https://baseballsavant.mlb.com/statcast-metrics-context)).
  These features cannot support an all-era model without an explicit restricted
  profile and missingness policy.
- Statcast Gamefeed is real-time.  In-game values are valid only for a separately
  declared live cutoff, never for a first-pitch prediction.

## Ratings and approved interaction ideas

- **Ratings:** home-field-adjusted Elo/log5/team-strength estimates may be
  recalculated sequentially from strictly earlier final game results.  They are
  safe as long as ordering is stable for same-day/doubleheader games and no game
  updates its own pregame rating.  The project experiment lab's Elo ordering is
  the reference implementation contract.
- **Interactions:** propose only feature-family interactions with a baseball and
  timing rationale: home-minus-away prior rates; recent-minus-season-to-date
  deltas; guarded rates with denominator counts; starter handedness × opposing
  prior platoon split; park × prior batted-ball profile; rest/workload × role.
  Generate them inside an immutable feature snapshot, not from all possible
  columns.  Calendar/nested validation must choose them without touching the
  final holdout.
- **Do not admit:** actual game score/box score, final-season WAR/wRC+/xwOBA,
  realized starting lineup, realized weather, settled prices, game-event
  Statcast, WPA/RE24 accumulated after the forecast cutoff, or a provider metric
  with no reproducible historical availability time.

## Predictive-model research boundary

- A published two-stage Bayesian MLB model states that game win probability
  depends on team strength including past performance and starting pitchers
  ([JDS article PDF](https://jds-online.org/journal/JDS/article/1117/file/pdf)).
  This supports testing sequential team-strength and starter-context families;
  it does **not** validate retrospective use of the eventual starter, a final
  seasonal leaderboard, or a model selected on the final holdout.
- The source above is methodological evidence, not a feature recipe.  Each
  project feature still needs its own formula, raw-field lineage, as-of rule,
  missingness policy, and chronological out-of-sample test.

## Research-use and version notes

- FanGraphs and Baseball-Reference pages are formula/methodology references, not
  a license to mirror or redistribute their datasets.  The census must separately
  confirm source rights and local availability.
- Retrosheet's event records are particularly valuable for reproducible
  historical reconstruction, but its actual game fields should not be confused
  with pregame publications.
- The first implementation recommendation should favor project-computable,
  prior-game team offense/defense and starter/bullpen workload families.  Defer
  provider WAR/wRC+ reproduction, lineup-dependent features, weather/umpire
  features, and post-2015 Statcast families until the census proves coverage,
  identity linkage, rights, and as-of timing.
