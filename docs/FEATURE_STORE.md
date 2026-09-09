# Feature store

The point-in-time feature layer for model building. It answers one question
honestly: **what did we know about a player, a pitcher, or a game *before* a
given moment?** Everything here is a reproducible artifact — run `mlb build`
and you get the same thing the project ships.

Related: [ADR-287](DECISIONS.md) (why features live in DuckDB, not PostgreSQL),
`openspec/changes/feature-store-v1/` (the design and its two reviews),
[FEATURE_REGISTRY.md](FEATURE_REGISTRY.md) (a *different* thing — the internal
Engine's ~178 game-feature families on `gold.game_feature`, which is **not** part
of this surface and is never published).

## The boundary is at `core`

| Layer | Engine | Owner | What it is |
| --- | --- | --- | --- |
| `raw`, `core` | PostgreSQL | `mlb bootstrap` / `mlb conform` | System of record. Ingestion, identity reconciliation, provenance, constraints. |
| `feat.*` | **DuckDB** | `mlb build` | Derived, reproducible, append-only. One local file. Delete it and lose nothing. |

`mlb build` reads PostgreSQL `core` / `gold` and writes the `feat.*` relations
into a single DuckDB file (default `~/.mlb/mlb.duckdb`; override with `--db` or
`$MLB_DUCKDB_PATH`). Models read only from that file. There is no `feat` schema
in PostgreSQL.

## The four clocks

Every feature row carries four timestamps. Point-in-time correctness is these
clocks, not a framework.

| Clock | Meaning |
| --- | --- |
| `event_ts` | End of the last game the row includes. `game_date` + `game_number × 3h` — a fictional absolute time that preserves same-day (doubleheader) ordering, because Retrosheet does not record first pitch. |
| `available_ts` | When a model may use the row. `event_ts + 6h` — the box score is available after the game. This lag is the documented per-source assumption; see *Honest limitations*. |
| `created_ts` | When `mlb build` wrote the row. Guards against a value that a *later* rebuild would change leaking into an *earlier* decision. |
| `visible_ts` | `GREATEST(available_ts, created_ts)`. Retrieval joins on this: a row is invisible both before the event was known and before the build produced it. |

## The relations

All in the `feat` schema of the DuckDB file. One row per
`(entity_id, event_ts, feature_version)` — **`window` is never a key**; each
window is its own set of columns.

### `feat.player_form`

Entering offensive form per batter. For each window `7d`, `30d`, `std`
(season-to-date):

- exposure: `pa_<w>`
- numerators: `so_num_<w>`, `bb_num_<w>`, `h_num_<w>`, `ab_num_<w>`, `tb_num_<w>`, `hbp_num_<w>`, `sf_num_<w>`, `hr_num_<w>`
- raw rates (NULL when the denominator is 0, recomputed from the summed
  numerators — never averaged from per-game rates): `k_pct_<w>`, `bb_pct_<w>`,
  `obp_<w>`, `slg_<w>`, `iso_<w>`, `babip_<w>`
- empirical-Bayes shrunk rates for K% and BB% only: `k_pct_shrunk_<w>`,
  `bb_pct_shrunk_<w>` = `(num + m·prior) / (denom + m)` with `m` in `shrink_m`
  and the as-of season-to-date league rate in `league_k_pct_prior_<w>` /
  `league_bb_pct_prior_<w>`. Shrinking the other rates is left to you — that
  is exactly why every numerator and exposure ships.

### `feat.pitcher_form`

Entering form per pitcher, same shape. Windows `7d` / `30d` / `std`:

- exposure `bf_<w>`; numerators `so_num_<w>`, `bb_num_<w>`, `r_num_<w>`,
  `hr_num_<w>`, `outs_num_<w>`, `hbp_num_<w>`
- rates: `k_pct_<w>`, `bb_pct_<w>`, `k_minus_bb_pct_<w>`, `ra9_<w>`
  (`r·27/outs`, NULL when `outs = 0`), `fip_like_<w>`
  (`(13·hr + 3·(bb+hbp) − 2·so)/(outs/3) + 3.1`, a fixed FIP constant)
- shrunk: `k_pct_shrunk_<w>`, `bb_pct_shrunk_<w>`

### `feat.game`

One row per regular-season game: game context, the four clocks, the home/away
team's entering offensive form (`home_k_pct_30d`, `away_obp_30d`, …), both
starters' entering form (`home_starter_k_minus_bb_pct_30d`, …), and the
`home_win` label. ~34 columns. Its form columns equal what
`get_historical_features` returns for the same entities at the game's
`event_ts` — a test enforces that so the assembly and the retrieval path cannot
drift.

Slice 1 uses the **actual** starting pitcher (`starter_is_actual = TRUE`).
Elo v2 (slice 3) swaps in the probable starter.

## Retrieval

```python
import mlb_research as mr

games = mr.load("...")   # or your own entity frame: entity id + a decision timestamp
X = mr.get_historical_features(
    games,
    ["player_form:obp_30d", "player_form:k_pct_shrunk_30d", "pitcher_form:k_minus_bb_pct_30d"],
    timestamp_col="event_timestamp",
)
```

`get_historical_features(entity_df, features, timestamp_col=, feature_version="v1", db=None)`
— Feast's signature and vocabulary (`"view:feature"` refs, one row out per row
in, missing stays missing). Under the hood it is **one DuckDB `ASOF LEFT JOIN`
per view** on `decision_time >= visible_ts` plus the entity-key match. `entity_df`
must carry `timestamp_col` and, per view, the entity-key column (`player_id`
for `player_form` / `pitcher_form`, `game_pk` for `game`).

There is no `merge_asof`, no per-row loop, and no database server — the DuckDB
file is read directly.

### No Feast

We copy Feast's call shape and vocabulary but not its framework. Feast's value
is online/offline serving consistency; this project has no serving path
(that is Phase C). Everything Feast would configure here (a registry, an offline
store, a provider) we would have to configure anyway, and everything it adds that
we would not (materialization, a feature server) is unused.

**Adoption trigger:** a real user asks for Feast. It is roughly a one-day add
then, because `feat.player_form` / `feat.pitcher_form` are already entity-keyed
with an availability timestamp — exactly what Feast's offline store expects.

## Leakage checks

`mlb verify` runs two checks against your own build. Both are pure — no model,
no labels, no scikit-learn.

| Check | What it proves |
| --- | --- |
| `check_clock_consistency` | Every row obeys `event_ts ≤ available_ts ≤ visible_ts` and `created_ts ≤ visible_ts`. A row that fails could be returned for a decision time before the event was known. |
| `check_doubleheader_ordering` | For two games of the same entity less than a day apart, the earlier game's `available_ts` lands at or after the later game's `event_ts` — game 2 cannot see game 1's box score. |

**What they do not cover:** whether a *model* trained on these features is
leaking. The "shuffle the labels" and "inject the outcome as a feature" tests
need a fitted model and belong in a notebook, not here. They ship as a recipe in
slice 3.

## Honest limitations

- **`available_ts` is an assumption, not a measurement.** Retrosheet has no
  ingest timestamp and no first-pitch time. `event_ts` is a fictional clock
  (`game_date + game_number × 3h`) that gets *ordering* right; `available_ts`
  adds a flat 6h. Real same-day timing (a rain-delayed game 1, a split
  doubleheader) is not modelled. The leakage checks test the mechanism, not the
  exact lag.
- **`std` denominators are tiny in April.** A season-to-date rate after two games
  is noise; use the shrunk column or a longer window early in a season.
- **wOBA is not in slice 1.** It needs the linear-weights machinery; K%, BB%,
  OBP, SLG, ISO, BABIP ship instead. Numerators ship so you can add wOBA
  yourself.
- **Coverage is the regular season, 1910–2025** — the Retrosheet event range.
