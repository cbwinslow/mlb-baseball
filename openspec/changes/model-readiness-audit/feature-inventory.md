# Feature inventory — task 1.1

Observed from `mlb_baseball/sql/duckdb/feat_game.sql`,
`feat_player_form.sql`, `feat_pitcher_form.sql`, `docs/FEATURE_STORE.md`,
and the feature-store integration tests on 2026-09-26. This is an evidence
inventory, not the `game-win-v1` declaration; task 1.2 will make the final
allow-list only after task 2.3 measures real coverage.

## Canonical model surface

`mlb build` writes three DuckDB relations: `feat.player_form`,
`feat.pitcher_form`, and `feat.game`. All source rows filter to
`core.game.game_type = 'regular'`; their rolling frames exclude the entering
game's entire calendar day. Tests cover clock ordering, same-day doubleheader
non-leakage, retrieval equivalence for starter columns, rate/null invariants,
and the absence of `gold.game_feature` reads. `gold.game_feature` is not an
admissible training surface for this change.

The current `feat.game` builder requires `core.game.retro_game_id`, so its
documented usable historical coverage is 1910–2025. It does not create a
fabricated current-season row merely to fill this gap.

## `feat.game` field disposition

| Fields | Disposition | Evidence / reason |
| --- | --- | --- |
| `game_pk`, `season`, `game_date`, `event_ts`, `available_ts`, `created_ts`, `visible_ts`, `feature_version` | excluded | Entity, partition, clock, and reproducibility metadata; not predictive inputs. |
| `home_team_id`, `away_team_id` | excluded | Entity identifiers; retain for joins and chronological evaluation only, not the first portable feature set. |
| `home_k_pct_30d`, `away_k_pct_30d`, `home_bb_pct_30d`, `away_bb_pct_30d`, `home_obp_30d`, `away_obp_30d`, `home_slg_30d`, `away_slg_30d` | admitted to `game-win-v1` | Team batting aggregates from prior completed regular-season `gold.batting_game` rows, recomputed from numerators/denominators. The builder now carries their denominator audit metadata; readiness profiles coverage/nulls per season and blocks unexplained in-window nulls. A full verification-build profile remains task 4.2. |
| `home_starter_k_minus_bb_pct_30d`, `away_starter_k_minus_bb_pct_30d`, `home_starter_fip_like_30d`, `away_starter_fip_like_30d`, `home_starter_bf_30d`, `away_starter_bf_30d` | excluded from `game-win-v1` | Their current assembly uses the *actual* starter (`starter_is_actual = TRUE`). Actual historical starters are valid descriptive data but not proven pre-game available inputs; a later version may admit probable-starter fields only with an availability contract. |
| `starter_is_actual` | excluded | Provenance flag, not a predictor; it also documents why the starter columns above are excluded. |
| `home_win` | excluded | Completed-game outcome label; never a training feature. |

## Form relations

`feat.player_form` and `feat.pitcher_form` expose point-in-time rates,
numerators, denominators, shrinkage inputs, and clocks at player grain. They
are admissible only through an explicit entity-level feature-set declaration.
The first game-win feature set will not silently join arbitrary player-form
fields: it either uses fields already assembled in `feat.game` or names the
retrieval key, decision timestamp, null policy, and coverage evidence.

## Existing evidence and open evidence

- **Existing:** deterministic hand fixtures, build idempotency/version
  coexistence, leakage checks, rate/null invariants, actual starter retrieval
  equivalence, and test-database integration coverage.
- **Still required before release/freeze:** a real-build per-season/per-feature
  coverage profile and current backbone tie-outs against the explicitly named
  verification target (task 4.2). The declaration, null-policy mapping, and
  generated report interface now exist and are fixture-tested.

## Organization findings to carry into task 3.1

1. `docs/FEATURE_STORE.md` is the authoritative public feature-store guide;
   `docs/FEATURE_REGISTRY.md` is explicitly the legacy `gold.game_feature`
   inventory. The readiness docs must link them without suggesting that the
   latter is a training contract.
2. `packages/mlb-research/mlb_research/features.py` describes `visible_ts` as
   including build time, while the full-rebuild SQL and feature-store guide set
   it to `event_ts`; incremental visibility behavior is future work. The
   public wording needs one precise, version-aware explanation.
