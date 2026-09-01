# SQL ownership inventory

Plan 02A inventory, 2026-08-06. This document is the ownership boundary for
new SQL; it prevents a second embedded-SQL monolith from growing in Python.

## SQLMesh models

| Relation / family | Current Python owner | Grain | Initial disposition |
|---|---|---|---|
| `core.venue` | `conform._build_venues` | one row per Retrosheet park | production SQL is named `sql/conform_venue_*.sql`; deterministic duplicate-name tie-break aligned; promote only after writer/environment parity gate |
| `gold.park_factor` | `model.park.compute` | venue-season | production SQL is a named `sql/park_factor_update.sql` resource; SQLMesh port promotes only after demand-shape parity gate |
| `gold.team_woba` | `model.offense.compute` | game-team | already ported; promote after parity gate |
| `gold.game_feature` base | `model.features.build` | game / scheduled game | named `sql/game_feature_rebuild.sql`; Python retains optional-source selection and rebuild sequencing pending candidate-model parity |
| `gold.prediction` market baseline | `model.market.record` | decided game-model version | named `sql/market_*_prediction_insert.sql`; Python retains source/model-version orchestration |
| wOBA/wRC+, starters, bullpen, WAR, framing, OAA, speed | feature-family update modules | game-team or game-player inputs | historical/live wOBA/wRC+; historical/live/upcoming starter and bullpen; plus park/venue/speed/OAA/framing/WAR use named SQL resources; feature writes retain Python orchestration only |
| `core.team` | `conform._build_teams` | one Retrosheet team-era | stable insert is named `sql/conform_team_insert.sql`; Python retains the surrounding identity/sequencing flow |
| `core.player`, `core.game`, `core.play`, `core.pitch`, `core.player_war`, `core.standing` | `conform.py` | canonical documented grain | migrate individually only after deterministic parity tests |

## Retain in Python

- Network ingestion, download/archive parsing, manifests, retries, COPY, and
  ingestion run tracking.
- Multi-pass game/team identity reconciliation and market snapshot matching.
- Sequential Elo, GBM training/inference, simulations, and evaluation control
  flow. The experiment lab's two stable bulk writes -- the snapshot feature
  matrix selection and the immutable `gold.game_feature_snapshot` insert it
  feeds -- are named resources (`experiment_selection.sql`,
  `experiment_snapshot_insert.sql`); Python keeps only the content-addressing
  and idempotency check around them.
- Parameterized operational statements and doctor/inventory diagnostics.
- Small source-selection fragments whose composition is procedural (for
  example `features.py` choosing whether the optional schedule branch is
  present) remain inline. The complete business mutation they feed is still
  owned by a named SQL resource.

## Remaining extraction queue

1. `conform.py`: only stable set-based writes after identity and dependent
   surrogate-ID contracts have dedicated parity gates. The ambiguous-game
   diagnostic remains an inline operational query.

## Migrations only

Schema/extension/role DDL and fixed raw indexes belong in numbered migrations.
`load.py`'s dynamic raw text landing-table expansion remains justified while
the source schemas are genuinely variable; any stabilized raw schema is moved
to a migration when its contract is known.

## Canonical-formula risks

- wOBA/wRC+ constants currently exist in Python and the SQLMesh spike.
- FIP and live out-count logic are duplicated between starter and bullpen
  modules.
- Pythagenpat currently lives in `features.py`.

New SQLMesh models become the canonical formula owner when promoted; Python is
then reduced to orchestration and the old mutating SQL is deleted only after
an exact full-table and sampled point-in-time tie-out.

## Identity-preservation gate

SQLMesh candidates may not silently replace a relation whose existing
surrogate IDs are referenced elsewhere. In particular, the spike's declarative
`core.venue` output has the natural `retro_park_id` but no stable replacement
for PostgreSQL's `core.venue.id`, which existing `core.game` and
`gold.game_feature` rows reference. Keep such a model in a candidate namespace
or treat the current core relation as external until a dedicated migration maps
and preserves every referenced identity. A natural-key tie-out alone is not a
writer-cutover proof.
