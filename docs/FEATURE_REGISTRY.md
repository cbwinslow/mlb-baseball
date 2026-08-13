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

`game_base_v1` is the only approved input family for the first game-win
experiment lab. The experiment snapshot copies its resolved completed rows
immutably. Final-season reporting tables, postgame scores (except for the
sequential Elo update after a prediction), markets, and legacy enrichment
columns are not experiment features.

`home_win` is a completed-game label, never a training feature. The base family
does not include pitchers, lineups, weather, markets, or pitch-level metrics.

`team_prior_offense_defense_v1` (`mlb_baseball/model/team_rate.py`, ADR-061)
adds prior rolling OBP/SLG/ISO/BB%/K% (admission queue OFF-01/02/03) and
prior runs-for/allowed averages (OFF-08/DEF-01) as compatibility enrichment
columns on `gold.game_feature`, the same status as the existing starter/
bullpen/park/oaa/speed/framing/war/woba columns: not part of `game_base_v1`,
not wired into the live pipeline yet, tested and health-checked in isolation.
