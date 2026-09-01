# Table contracts

Plan 02E contract baseline, 2026-08-06. A table's contract is its grain,
identity, event/cutoff time, lineage, and replacement behavior. Consumers may
not infer any of these from a convenient current row count or a Python query.

## Layer rules

| Layer | Purpose | Mutation rule | Consumer rule |
|---|---|---|---|
| `raw` | Source-faithful landed records | Connector-owned; retain source fields and landing metadata | No public/site query and no business-rule cleanup |
| `core` | Canonical resolved baseball entities/facts | Conformance-owned; deterministic reconciliation with documented exceptions | Stable analytical joins, but not model outputs |
| `gold` | Derived statistics, point-in-time feature families, and predictions | SQLMesh models or explicitly documented procedural model code | Research and model inputs; only approved narrow outputs later feed `serve` |
| `meta` | Operational lineage, runs, artifacts, evaluations | Application/migration-owned append/update records | Audit and reproducibility only |

`serve` is intentionally absent. It is introduced only in Plan 05 with a
read-only role, source-profile eligibility, and an explicit public contract.

**Terminology note (2026-08-13, independent research review):** what this doc
calls a "feature cutoff" is the same concept dedicated feature-store products
(Feast, Tecton, Hopsworks) call **point-in-time correctness**, implemented via
an **as-of join** — for each entity row, retrieve the latest feature value
timestamped at or before that row's own event timestamp, never after. This
project's `feature_cutoff_at` is the event timestamp; the `ROWS BETWEEN
UNBOUNDED PRECEDING AND 1 PRECEDING` window frame used throughout `gold`'s
rolling-stat SQL is a hand-written as-of join. Noted here so a reader coming
from the feature-store/MLOps literature recognizes this project's own
vocabulary as the same thing under a different name, not a different design.
Hand-rolling this in SQL rather than adopting a feature-store product is the
right call at this project's current scale (single model consumer, no
online/offline serving-skew problem to solve) — revisit only if that changes.

## Raw landing contracts

Raw tables are grouped by source product because a connector, not a generic
ORM, owns their parsing and refresh semantics. Dynamic raw tables use text
columns until a source schema has remained stable enough to deserve a numbered
migration. New columns are an alert/review event, never a reason to silently
reinterpret an existing conformed field.

| Family | Grain / identity | Time and lineage | Update contract |
|---|---|---|---|
| `raw.retrosheet_*` CSV/event/box products | Source-record row; event and box loads include `_scope`, CSV/game-log loads include `_season` or `_type` | Retrosheet archive filename/hash and parser are the source identity | Replace exactly the loaded scope; no cross-scope truncate |
| `raw.mlb_*` API product tables | API object/snapshot row, as defined by the endpoint | MLB API ID plus fetched/season fields; live/probable products retain capture time | Reference entities replace as a whole; game/season scopes replace; live/probable snapshots append |
| `raw.statcast_*`, `raw.bref_*`, `raw.lahman_*` | Provider row at the provider's published grain | Source profile and season/snapshot identify the extract | Replace a declared season/scope or the whole small reference table |
| `raw.polymarket_*`, `raw.kalshi_*` | Market/catalog object or observed price snapshot | Provider market ID and observed timestamp | Catalog tables replace; price snapshots append and must preserve observed time |

Append-only loaders must declare their observation identity and reject a
duplicate identity within one batch. Current identities are Polymarket
`(market_id, outcome, captured_at)`, Kalshi `(ticker, captured_at)`, live MLB
game state `(game_pk, captured_at)`, and announced probable pitchers
`(game_pk, side, captured_at)`. `captured_at` is an immutable per-run snapshot
time, not a later-updated freshness field.

## Core contracts

| Relation | Grain / key | Time semantics | Lineage and update contract |
|---|---|---|---|
| `core.player` | One resolved person (`id`); provider IDs are alternate anchors | Biography/current identity, not a player-season fact | Multi-pass source reconciliation in `conform.py`; never treat display name as an identity key |
| `core.team` | Franchise/team identity interval (`id`, `first_year`, `last_year`) | Team names/locations are valid only over their interval | Conformance uses Retrosheet's primary team reference plus its official date-bounded supplemental team records for otherwise absent historical/Negro League codes; it never merges teams by display-name similarity |
| `core.venue` | Retrosheet park identity (`id` / `retro_park_id`) | Venue lifecycle fields are descriptive | Raw park plus best-effort MLB enrichment; SQLMesh candidate after deterministic duplicate-match parity gate |
| `core.game` | One completed canonical game (`id`, source game keys); `game_pk` is the unique natural key when an MLB source supplies it, while nullable `retro_game_id` is populated only by Retrosheet | `game_date`, game number, season, final score; excludes scheduled/live data | Conformance-owned resolution from raw products; completed MLB-only current-season and Spring Training rows are admitted only for `Final`, `Completed Early`, or `Forfeit` status. Retrosheet's `game_number = 0` means an ordinary single game. Schedule revisions are retained in `raw`, not duplicated as canonical games |
| `core.play` | One canonical play within a game | Ordered game event; win-probability fields are play-time values | Conformance merges source events; partitioned fact, never a wide feature table. Terminal source counts of five balls/four strikes are retained rather than rewritten |
| `core.pitch` | One landed Statcast pitch (`id`, `season`); `source_game_pk` preserves the provider game key while `game_id` is the nullable resolved core FK | Pitch sequence/event time where supplied | Conformance maps Statcast and play context. An unresolved `game_id` retains `source_game_pk` for exact audit/reconciliation rather than dropping the pitch or guessing a match |
| `core.market` | One matched market/game/side observation or derived pregame selection | A selected value must be from before game start; `observed_at` is the `captured_at` of the `raw.{polymarket,kalshi}_snapshot` row `implied_probability` was resolved from, and is NULL exactly when `implied_probability` is NULL (issue #107) | Python-owned multi-pass market matching; no settled/current value may masquerade as pregame |
| `core.player_war`, `core.standing` | Provider player-season / team-season fact | Season aggregate | Conformance-owned derived source facts; refresh replaces their declared season/source scope |

## Gold contracts

| Relation / family | Grain / key | Cutoff semantics | Lineage and update contract |
|---|---|---|---|
| `gold.game_feature` | One completed or scheduled **regular-season MLB** game; populated `mlb_game_pk` is the business identity and `game_id` is populated for completed canonical games | `feature_cutoff_at` is the provider's scheduled first-pitch time. The base family uses only completed regular games ordered strictly before that cutoff; doubleheaders order by cutoff, game number, then MLB key. Retrosheet-only, Spring, postseason, live, and cancelled rows are excluded. | Full rebuild in one transaction. The first audited base family is team entering wins/losses, win rate, runs for/against, rest, home field, and an outcome label. Null records/runs are expected for first games; source schedule history stays raw and is collapsed to one feature row per key. Later enrichment columns are compatibility fields, not part of this base contract. |
| `gold.park_factor` (target narrow family) | Venue-season needed by a `gold.game_feature` row | Trailing seasons only, never target-season games | SQLMesh candidate; its demand relation must include scheduled games before it replaces `model.park.compute` |
| `gold.team_woba` (target narrow family) | Game-team entering value | Prior events only within the applicable game/season window | SQLMesh candidate; a wide `gold.game_feature` projection is derived only after parity |
| Starter, starter workload (PIT-03), bullpen, framing, OAA, speed, WAR, team-rate/run-environment families | Game-team or game-player feature family | Must be point-in-time/no-leakage as documented by the individual feature | Remain Python-owned until a narrow named SQL model has exact full/sampled tie-out |
| `DEF-01` Run Prevention distinction | Derived team run-prevention composite (`runs_allowed`) vs component metrics | Point-in-time prior games | `runs_allowed` is a combined team run-prevention composite reflecting pitching, fielding, baserunning suppression, and park context. It is explicitly distinguished from defense-independent pitching talent (FIP/xFIP in starter/bullpen families) and pure fielding metrics (OAA in `raw.statcast_oaa`). |
| `gold.prediction` | Immutable `(mlb_game_pk, model version, generated_at)` snapshot; compatibility `game_instance_key` is `mlb:<game_pk>` or a Retrosheet/legacy provenance key | `generated_at` and `data_cutoff` precede outcome; outcome is filled later | Append immutable prediction; never overwrite a historical forecast with a current rerun |
| `gold.game_feature_snapshot` | One frozen resolved game-win input per `(snapshot_id, game_instance_key)` | Retains the feature cutoff, declared doubleheader order, target, and approved base fields exactly as copied | Created only by `mlb experiment snapshot`; never rebuilt or updated from mutable `gold.game_feature`. A new source state creates a different content-addressed snapshot. |
| `gold.player_season` | One provider final-season line per `(player_id, season, is_pitcher)` | Final-season aggregate; never a pregame feature | Explicit `mlb report` rebuild from Baseball-Reference season rows plus conformed WAR. Current source coverage begins in 2008; unresolved provider player IDs are excluded and reported by health checks. |
| `gold.team_season` | One final-season line per `(team_id, season)` | Final-season aggregate; never a pregame feature | Explicit `mlb report` rebuild from Lahman, core games, Retrosheet event aggregates, and conformed WAR. Historical team coverage differs from player coverage and known unresolvable teams remain documented gaps. |
| `gold.division_standing` | One team-season standing row `(team_id, season)` | Final standings/snapshot values; never a pregame feature | Explicit `mlb report` rebuild from `core.standing` with retained MLB elimination markers. Source coverage starts in 1969. |
| `gold.batting_game` | One batting box-score line per `(game_id, player_id, team_id)`, regular season only | Actual game result, not a pregame feature — this is the *what happened* grain, the complement to `gold.game_feature`'s *what was knowable before* | Explicit `mlb report` rebuild (truncate-and-replace, idempotent) from `raw.retrosheet_event` (1910–2025), using the same `bat_event_fl` / `ab_fl` / `sf_fl` / `sh_fl` / `event_cd` handling as `sql/team_woba_retrosheet_update.sql` (ADR-034). Counting stats only; rate stats belong in the season/career roll-ups. First relation of the grain-complete statistic backbone (Plan 03B). Degrades gracefully when `raw.retrosheet_event` is absent. 2026+ (MLB Stats API) and postseason are separate follow-up builders. `gidp` undercounts pre-1988 (sparse `battedball_cd`). |
| `gold.pitching_game` | One pitching box-score line per `(game_id, player_id, team_id)`, regular season only | Actual game result, not a pregame feature | Explicit `mlb report` rebuild (truncate-and-replace, idempotent) from `raw.retrosheet_event` (1910–2025). Every play charged to `re.resp_pit_id`; runs charged per responsible pitcher (`resp_pit_id` for the batter-runner, `re.run{1,2,3}_resp_pit_id` for inherited runners). Counting stats only. **`er` / `era` not produced** — earned runs need reconstructed-inning logic cwevent does not emit; `r` and season RA9 are the honest figures, ERA is per-player-season from Baseball-Reference. Same graceful-degrade, follow-up-builder, and `battedball_cd` caveats as `gold.batting_game`. Part of the grain-complete statistic backbone (Plan 03B, ADR-278). |

## Audit contract

`mlb audit` is the read-only evidence gate for these contracts. Its bounded
default validates exact required-key null counts, duplicate business keys,
foreign-key orphans, source/decade coverage for optional MLB keys, stable game
and play value domains, and feature/prediction identity. The optional
`database` scope reports row/dead-row estimates, analyze freshness, index-use
signals, and raw landing freshness; `statcast` deliberately performs the
separate pitch-level source-to-schedule scan. See [`AUDIT_RUNBOOK.md`](AUDIT_RUNBOOK.md)
for interpretation and the safe production sequence.

The audit is intentionally not a substitute for unproven uniqueness. In
particular, `core.pitch` retains the source game key and surrogate primary key,
but does not assert a compound Statcast pitch key until a full-source duplicate
study proves one. A plausible-looking combination of game, plate appearance,
and pitch number is not enough to make a permanent constraint.

## Meta contracts

| Relation | Grain / key | Contract |
|---|---|---|
| `meta.ingestion_run` | One connector invocation | Starts `running`, ends `success` or `failed`; source advisory lock prevents overlap; rows/error/pid are operational lineage |
| `meta.experiment_target` | Declared experiment target (`name`) | Seeded with `home_win` (classification) and `run_differential` (regression); defines task type and target description |
| `meta.feature_selection` | One feature-selection stability run (`selection_id`) | Records deterministic selection identity, target, fold plan, method configuration, status, result JSON, and artifact URI/hash for filter + embedded stability reports across calendar folds |
| `meta.feature_selection_stepwise` | One forward-stepwise feature selection run (`selection_id`) | Records deterministic selection identity, target, fold plan, method configuration (survival threshold, probe model), status, result JSON (including per-fold trace), and artifact URI/hash for nested forward-stepwise validation |
| Model/artifact/run/snapshot/evaluation relations | Immutable model/version/run/snapshot/evaluation identity | Records must make a prediction and evaluation reproducible without claiming old in-place feature rows still exist |
| Experiment snapshot/run/fold relations | Content-addressed game-win input, declared config/folds, and one result artifact per model/fold | Calendar folds train only on preceding seasons; 2025 is reserved holdout and 2026 forward-monitoring under the default plan | `meta.experiment_snapshot`, `meta.experiment`, and `meta.experiment_fold` retain input hash, selection, lock/environment identity, scores, errors, and artifact hashes. No experiment automatically promotes a production model. |

## Change rules

- Keep `raw`, `core`, `gold`, and `meta` names. Add narrow `gold` statistic or
  feature families rather than more sparse columns to `gold.game_feature`.
- `mlb field-census` is the read-only evidence path for raw-to-core-to-gold
  field flow. It classifies fields, but it never promotes a raw field; a new
  canonical or gold destination needs its own documented contract and tests.
- A misleading metric rename (including FIP presented as ERA) requires a
  numbered migration, compatibility period, consumer migration, and removal
  decision. It is never an unannounced column rename.
- Add constraints and indexes only with an explicit key/contract and measured
  query or integrity evidence. Dynamic raw landing tables are the exception
  while their source schema is still variable.
- A model/output contract change needs full-table plus sampled point-in-time
  comparison, an owner decision on every difference, and a recorded rollback
  path before the previous writer is removed.
