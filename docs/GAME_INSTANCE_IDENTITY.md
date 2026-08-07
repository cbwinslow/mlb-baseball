# Durable game-instance identity

`core.game.game_pk` and `gold.game_feature.mlb_game_pk` are MLB lookup
identifiers, not primary identities. A real suspended/resumed pair can share a
`game_pk`; migration `0015_game_feature_pk_not_unique.sql` records the
production example. Using that value alone for feature, prediction, outcome,
market, or evaluation joins can duplicate, collapse, or misattribute rows.

Migration 0034 adds `gold.game_feature.game_instance_key` and
`gold.prediction.game_instance_key`. New normal-flow keys use the stable,
human-inspectable form:

`mlb:<season>:<local game date>:<game number>:<home MLB team id>:<away MLB team id>:<game_pk>`

Completed games use the matching retained schedule row when available, so a
scheduled prediction and its later completed outcome retain the same key. A
Retrosheet identifier is used when no MLB identity exists. Existing rows are
preserved with deterministic `legacy-*` keys where their old `game_pk` cannot
be resolved unambiguously; this keeps history intact and makes repair visible
instead of silently guessing.

## Audited grains and legacy ambiguity

This is the Plan 01F read-only code/schema audit.  It distinguishes an
acceptable provider lookup from a relational identity join; the latter must
use `game_instance_key` at the feature/prediction boundary.

| Location / relation | Actual grain | `game_pk` use and ambiguity | Contract after 0034/0035 |
|---|---|---|---|
| `core.game` | One completed conformed game; `id` is its database key | `game_pk` is an optional MLB lookup and is non-unique for a suspended/resumed pair | Do not join downstream model records directly to it on `game_pk` |
| `raw.mlb_playbyplay` → `core.play` | Provider play/at-bat record | Existing conformance joins its provider `game_pk` to `core.game`; raw play-by-play has no separate cross-source instance key, so this remains an explicitly source-scoped ambiguity | Kept inside conformance; no model, market, or evaluation consumer may inherit this as prediction identity |
| `raw.statcast_pitch` → `core.pitch` | Provider pitch record | Same source-scoped `game_pk` lookup ambiguity as play-by-play | Kept inside conformance; pitch consumers must join through `core.pitch.game_id` |
| `gold.game_feature` | One scheduled or completed regular-season game instance | `game_id` is absent before completion; `mlb_game_pk` can repeat | Required unique `game_instance_key`; lookup columns are not unique identity |
| `gold.prediction` | One immutable model snapshot for one game instance | Former primary key used `mlb_game_pk`, so same-time predictions for two instances could not coexist | Primary key is `(game_instance_key, model_version, generated_at)` |
| Outcome backfill | Prediction-to-current-feature-to-completed-core-game | Former direct `prediction.game_pk = core.game.game_pk` could update both instances | Joins `prediction → game_feature → core.game` by declared instance key |
| Market recording / health | Market's matched `core.game` and its feature | A direct prediction-to-game `game_pk` join could multiply market coverage | Inserts and health checks pass through the matching feature key |
| Evaluation / provenance | One selected pre-game snapshot per model and instance | Partitioning or matching by MLB ID conflates repeated IDs | Schedule-derived instance key, feature-key join, and key partitioning are required |
| Serving plans | A future read-only projection of gold outputs | `mlb_game_pk` alone is insufficient for a game URL or cache key | Serve the durable key (or an explicit opaque alias of it) alongside the human MLB lookup ID |

Migration 0035 changes the prediction primary key to
`(game_instance_key, model_version, generated_at)`. `mlb_game_pk` remains
indexed for API lookup but cannot prevent two valid instances from coexisting.

Migration 0036 adds `meta.game_instance`, an append/preserve registry. It is
the historical owner of an instance key because `gold.game_feature` is rebuilt
in place. Feature builds upsert current instances but never delete registry
entries referenced by older predictions. Evaluation uses the registry for
Retrosheet rows when no MLB schedule record remains; its game-date fallback is
not a precise first-pitch timestamp.

## Join rules

- Features, predictions, outcome backfill, market recording, and evaluation
  join through `game_instance_key`.
- Join a prediction to `core.game` through its feature row (`prediction` →
  `game_feature` → `core.game`), never directly on `game_pk`.
- Source connectors may use `game_pk` to request MLB API records; that is a
  lookup, not a relational uniqueness assertion.
- `gold.game_feature` is still a transactional full rebuild. Prediction
  history therefore has no foreign key to the rebuilt feature table.
- `raw.mlb_probable` currently exposes only `game_pk`; it cannot safely choose
  between reused lookup IDs without richer provider fields.

## Operational serialization

Each connector run holds a shared PostgreSQL advisory workflow lock. Conform,
feature build, and prediction runs hold the exclusive form. Existing
per-source locks still prevent duplicate runs of one connector. `mlb doctor`
is read-only; use `mlb repair-runs` to explicitly mark dead-process run rows
failed.

`mlb migrate` additionally takes `mlb-migrate`. Migration 0035 is explicitly
nontransactional so PostgreSQL can build the replacement prediction identity
index concurrently and record its ledger row only after all statements work.
Run the 0034/0035 cutover in an approved maintenance window: 0034 backfills
existing rows and can generate significant WAL. Preflight free disk/WAL
headroom and validate row counts, null keys, and duplicate durable keys. Stop
on failure; retries are idempotent, but schema migration has no automatic
rollback.
