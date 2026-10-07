# FanGraphs

Same layout and ownership rules as [`mlb_api.md`](mlb_api.md).

| Question | Owner |
|---|---|
| Tables, rows, seasons, columns | [`RAW_INVENTORY.md`](../RAW_INVENTORY.md) (section `fangraphs`) |
| Offered vs. held vs. missing | `mlb coverage --source fangraphs` |
| Connector contract (grains, append rule for projections) | [`fangraphs.py.dox.md`](../../mlb_baseball/connectors/fangraphs.py.dox.md) |
| Rights | [`SOURCE_RIGHTS.md`](../SOURCE_RIGHTS.md) (row "FanGraphs via fungo"); `gold.fangraphs_*` inherits `local_research` |
| Why not `pybaseball` | ADR-288 in [`DECISIONS.md`](../DECISIONS.md) |

Facts checked 2026-10-06 (database, connector code, one web search).

## Access

- **Client:** `fungo` (>=2.0, <3, MIT, single maintainer). It calls FanGraphs' mobile-app JSON API with `User-Agent: okhttp/4.12.0`, the one client Cloudflare does not block. `pybaseball`'s FanGraphs functions return HTTP 403 and are not used.
- **Auth:** none. **Documentation:** none; the mobile API is unofficial and can change without notice. Single-maintainer dependency risk (see the audit).
- **Rate limit:** none published. About one request per season per board on a full load; `update()` is roughly 60 requests.
- **Saved before load:** no (fetched into memory).

## Rights

The terms-of-use page could not be retrieved on 2026-10-06 (the URL tried returned 404), so there is **no first-hand wording in this repo**. A web search reports that FanGraphs does not permit redistribution of its bulk leaderboard data and discourages automated access; that is second-hand. Treat as `local_research` only (never `public_safe`, never in published datasets, never a reference-model input). Next step: find the live terms page, record its exact wording in `SOURCE_RIGHTS.md`, and correct this section.

## Products

| Product | Table(s) | Grain | Held now | Rule |
|---|---|---|---|---|
| Season leaderboards | `raw.fangraphs_batting`, `_pitching`, `_fielding` | player-season | 1871 to 2026 | per-season scoped replace; advanced columns are genuine NULLs in early years; pitching board is about 540 columns incl. Stuff+ (`sp_*`) and PitchingBot (`pb_*`) |
| Guts constants | `raw.fangraphs_guts` | season | all years in one call | whole-table replace; all-string values |
| Park factors | `raw.fangraphs_park_factors`, `_park_factors_handedness` | park-season | per season | scoped replace |
| Prospects (THE BOARD) | `raw.fangraphs_prospects` | player-season | per season | scoped replace |
| Split leaderboards | `raw.fangraphs_split_batting`, `_split_pitching` | league-wide split per season | curated set only | the full 292-code split table is out of scope (ADR-020/024) |
| Projections | `raw.fangraphs_projection` | system, stat group, player, capture date | snapshots since first capture | append-only; a new row only when the projected values change (`_row_hash`) |

Seasons held were read from the database (min 1871, max 2026 on the batting and pitching boards).

## Verified 2026-10-07 (live probe and database)

- **Park factors:** the basic board serves every year from 1871 (9 rows in 1871, 30 from 2001); the handedness board serves only from 2002 (2001 and earlier raise "No Guts table found"). Held: basic 1871-2026, handedness 2002-2026.
- **Fielding 2019:** served (2,269 rows) and now held; it had been missing, along with 1871-1900 park factors, until the 2026-10-07 repair (`data-completeness` task 2.3).
- **Prospects:** held 2010-2026 (`PROSPECT_FIRST_YEAR`).
- **Re-runs:** `mlb ingest fangraphs` now fetches only the past seasons, park-factor boards and split boards that hold no rows, plus the current season.

## Known gaps and open questions

- Which seasons each board really offers (the sidecar says the observed earliest season per board is to be recorded after a bootstrap; the database shows 1871 for batting and pitching). Record the per-board first year here once probed, and register it in `mlb_baseball/coverage/registry.py`.
- Boards not built: see `SOURCE_COVERAGE_AUDIT.md` and `full-source-ingestion` task 4.2.
