# `statcast_leaderboard.py` DOX

## Purpose

Own Baseball Savant's **season-level tracking and official aggregate leaderboard products** that either require source inputs absent from `raw.statcast_pitch` or provide valuable official cross-validation of statistics derivable from pitch-level data.

This connector complements `statcast.py`; it is not a duplicate pitch feed.

## Ownership

Implementation: `statcast_leaderboard.py`.

Major raw outputs currently include:

- `raw.statcast_sprint_speed`
- `raw.statcast_poptime`
- `raw.statcast_framing`
- `raw.statcast_jump`
- `raw.statcast_oaa`
- `raw.statcast_catch_prob`
- `raw.statcast_oaa_direction`
- `raw.statcast_running_split`
- `raw.statcast_batter_exitvelo`
- `raw.statcast_batter_expected`
- `raw.statcast_batter_percentile`
- `raw.statcast_batter_arsenal`
- `raw.statcast_pitcher_exitvelo`
- `raw.statcast_pitcher_expected`
- `raw.statcast_pitcher_percentile`
- `raw.statcast_pitcher_arsenal`
- `raw.statcast_pitcher_arsenal_stat`
- `raw.statcast_spin_dir`

Public connector capabilities:

- `bootstrap()`
- `update()`
- `health_check()`

## Source Contract

- Source: Baseball Savant, primarily through pybaseball leaderboard functions.
- First supported year is 2015, based on direct endpoint/library testing and the league-wide Statcast era boundary.
- Several products use tracking inputs **not present in raw pitch rows**, such as fielder positioning, hang time, throw timing, baserunning, or catcher framing context.
- Other products are official Baseball Savant aggregates that can overlap statistics derivable from pitch-level source data; those are intentionally retained as independent cross-validation evidence rather than treated as wasteful duplication.
- Repository source-rights/profile metadata remains authoritative for permitted use/redistribution.

## Product Contracts

### Simple one-call-per-season leaderboards

`SIMPLE_LEADERBOARDS` is the explicit registry of raw table -> fetch callable. This is the source of truth for products that can be fetched once per season.

When adding a product:

- verify it is genuinely MLB/Statcast data and works for the intended years;
- determine whether it is unique tracking input or an official aggregate used for cross-validation;
- add its table to health checks and historical-completeness logic;
- document source grain/important null semantics if non-obvious.

Do not add a leaderboard merely because pybaseball exports a function; first confirm research value and source behavior.

### OAA

- Outs Above Average is fetched separately by fielding position because the pybaseball API requires a position-specific call.
- Current position codes cover non-catcher fielding positions; catcher is intentionally excluded because this leaderboard does not support it.
- `_scope` is `<season>_<position>` so each position-season load is independently replaceable/idempotent.
- Do not collapse position calls into one guessed aggregate without verifying source semantics.

### Catcher framing exception

- Current installed pybaseball framing helper points at an obsolete Baseball Savant route that returns HTML rather than CSV.
- `_fetch_framing()` therefore calls the verified current `/leaderboard/catcher-framing` endpoint directly and parses CSV.
- This is a targeted compatibility repair, not a license to bypass pybaseball for every leaderboard.
- Re-check upstream pybaseball behavior before removing or expanding this workaround.

## Runtime Contracts

### Season scoping

- Each simple leaderboard adds `_season` and uses season-scoped replacement.
- Past seasons are treated as immutable/published and skipped only when **every currently registered leaderboard table** is loaded for that season.
- Do not revert to checking one proxy table. That approach previously caused newly added leaderboard tables to remain permanently empty for historical seasons because old seasons appeared "complete" from the proxy alone.
- Current season always refreshes.

### Failure isolation

- Each leaderboard table/season commits independently.
- A failed leaderboard rolls back/logs/continues so one broken upstream product does not discard every other table in that season.
- OAA is similarly isolated as its own multi-position unit.

### Rate/concurrency behavior

- Calls use shared retry/backoff.
- This connector shares Baseball Savant infrastructure with `statcast.py` and is grouped with it by the CLI's same-server concurrency rules.
- Do not run both connector request storms concurrently by bypassing that grouping without measured upstream evidence.

## Data / Grain Semantics

- Most tables are season-level player leaderboards, but exact source grain differs by product (player, pitch type, position, directional bucket, etc.).
- Raw source columns remain source-faithful; downstream typed/statistical contracts should state exact grain before using a leaderboard in gold/research relations.
- Missing seasons/players/fields can represent eligibility/minimum-opportunity/source-era absence rather than a numerical zero.
- Similar names do not imply identical meaning: pitcher arsenal usage/velocity and pitcher arsenal results are distinct products and remain separate tables.

## Cross-Validation Role

Official aggregate tables may overlap formulas computable from `raw.statcast_pitch`. When both are used:

- identify the project-owned formula/definition being validated;
- compare like grain/eligibility/window definitions;
- preserve unexplained discrepancies as evidence rather than overwriting one source to match the other;
- use the Stat Registry/tie-out documentation as the eventual canonical place for reusable statistic validation metadata.

## Point-in-Time / Research Semantics

Season leaderboard values describe accumulated/post-event outcomes. They are not automatically valid pregame features for every game in that season.

For predictive use:

- use only a snapshot/aggregate whose underlying observation window ends before the target game;
- do not join final full-season leaderboard values into earlier games;
- if only final-season data is available from a source product, treat it as descriptive/validation data rather than PIT training input unless a historical-as-of reconstruction is built separately.

## Dependencies

- `pybaseball`
- direct `requests` + pandas CSV parsing for the framing compatibility path
- pandas / psycopg
- `load_dataframe` / `season_already_loaded`
- `call_with_retry`
- run tracking, DB, health helpers

## Downstream Consumers

- Research/stat validation and official-source tie-outs.
- Player defensive, baserunning, catcher, contact-quality, expected-stat, arsenal, percentile, and other descriptive research.
- Future feature pipelines only when PIT availability is explicitly correct.

## Known Quirks / Decisions

- Products do not exist before 2015 in the same sense as full Statcast tracking.
- Catcher framing currently requires a direct endpoint because the installed pybaseball route is stale.
- Newly registered tables must participate in `_season_fully_loaded()`; otherwise historical bootstrap can silently skip them.
- Some official aggregate tables intentionally duplicate derivable information for cross-validation value.

## Work Guidance

- Verify pybaseball function behavior and direct endpoint responses before changing URLs/arguments/year boundaries.
- Add a table only with an explicit grain/research purpose.
- Keep table registration, historical-completeness checks, health checks, docs/DOX, and tests synchronized.
- Do not infer predictive availability from "season = X" alone.
- Coordinate request/concurrency changes with `statcast.py` and CLI same-server grouping.

## Verification

For changes, verify:

- 2015 boundary and empty pre-2015 behavior where relevant;
- simple leaderboard season-scoped idempotency;
- OAA position-loop scopes and catcher exclusion;
- framing direct-endpoint parsing and protection against HTML-as-CSV regression;
- `_season_fully_loaded()` checks **all** registered tables and detects a newly added missing historical table;
- per-table rollback/failure isolation;
- health coverage updated for new/removed tables;
- any official-aggregate tie-out uses matching grain/eligibility definitions;
- predictive consumers do not leak full-season final values into earlier games.

Use bounded live source probes only for material source-contract verification; routine tests should use deterministic fixtures/mocks.

## Child DOX Index

No child DOX files. This is a leaf connector contract.
