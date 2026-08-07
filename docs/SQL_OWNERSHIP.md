# SQL ownership inventory

Plan 02A inventory, 2026-08-06. This document is the ownership boundary for
new SQL; it prevents a second embedded-SQL monolith from growing in Python.

## SQLMesh models

| Relation / family | Current Python owner | Grain | Initial disposition |
|---|---|---|---|
| `core.venue` | `conform._build_venues` | one row per Retrosheet park | already ported; deterministic duplicate-name tie-break aligned; promote only after writer/environment parity gate |
| `gold.park_factor` | `model.park.compute` | venue-season | already ported; promote after parity gate |
| `gold.team_woba` | `model.offense.compute` | game-team | already ported; promote after parity gate |
| `gold.game_feature` base | `model.features.build` | game / scheduled game | next assembly model |
| wOBA/wRC+, starters, bullpen, WAR, framing, OAA, speed | feature-family update modules | game-team or game-player inputs | split into narrow upstream models before replacing wide assembly |
| `core.team`, `core.player`, `core.game`, `core.play`, `core.pitch`, `core.player_war`, `core.standing` | `conform.py` | canonical documented grain | migrate individually only after deterministic parity tests |

## Retain in Python

- Network ingestion, download/archive parsing, manifests, retries, COPY, and
  ingestion run tracking.
- Multi-pass game/team identity reconciliation and market snapshot matching.
- Sequential Elo, GBM training/inference, simulations, and evaluation control
  flow.
- Parameterized operational statements and doctor/inventory diagnostics.

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
