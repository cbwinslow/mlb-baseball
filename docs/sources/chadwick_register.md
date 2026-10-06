# Chadwick Bureau Register

Same layout and ownership rules as [`mlb_api.md`](mlb_api.md).

| Question | Owner |
|---|---|
| Tables, rows, columns | [`RAW_INVENTORY.md`](../RAW_INVENTORY.md) (section `register`) |
| Offered vs. held vs. missing | `mlb coverage --source register` |
| Connector contract | [`chadwick_register.py.dox.md`](../../mlb_baseball/connectors/chadwick_register.py.dox.md) |
| ID resolution command | `mlb player-id` |
| Rights | [`SOURCE_RIGHTS.md`](../SOURCE_RIGHTS.md) (row "Chadwick Register") |

Facts checked 2026-10-06 (the register's GitHub page, database).

## Access

- **Source:** CSV files under `raw.githubusercontent.com/chadwickbureau/register/master/data`: 16 sharded people files (`people-0.csv` to `people-f.csv`) plus single files for names, links and countries.
- **Auth and rate limit:** none needed; ordinary GitHub raw-file etiquette.
- **Freshness:** the public repository is updated roughly weekly and runs behind the full register that Chadwick's clients receive. Treat it as a point-in-time snapshot, not a feed.

## Rights

The data is published under the Open Data Commons Attribution License (ODC-By 1.0), which requires attribution. `SOURCE_RIGHTS.md` still says "needs a pinned-release review"; that row should be updated to cite the license named here once the release is pinned. Not `public_safe` until then.

## Products

| Table | Content |
|---|---|
| `raw.register_people` | one row per person, with Retrosheet, MLBAM, Baseball-Reference, FanGraphs and other IDs (about 527k rows today) |
| `raw.register_names` | name variants |
| `raw.register_links` | external links |
| `raw.register_countries` | country reference |

This is the crosswalk every cross-source join depends on; a missing ID is a missing identity, never a guess (root `AGENTS.md`).

## Known gaps

- Pre-event availability: a person new to the league may appear in the register later than in other sources. Joins must treat an unresolved ID as NULL.
