# News / RSS (MLB.com, MLB Trade Rumors, ESPN)

Same layout and ownership rules as [`mlb_api.md`](mlb_api.md).

| Question | Owner |
|---|---|
| Table, rows, columns | [`RAW_INVENTORY.md`](../RAW_INVENTORY.md) (section `news`) |
| Offered vs. held | `mlb coverage --source news` |
| Connector | `mlb_baseball/connectors/news.py` (module docstring; no sidecar yet); ADR-047 in [`DECISIONS.md`](../DECISIONS.md) |
| Rights | [`SOURCE_RIGHTS.md`](../SOURCE_RIGHTS.md) (row "RSS/news feeds") |

## Access

| Feed | URL pattern | Scope |
|---|---|---|
| MLB.com | `mlb.com/{slug}/feeds/news/rss.xml` | league plus all 30 teams; a wrong slug returns 404 |
| MLB Trade Rumors | `mlbtraderumors.com/{slug}/feed` | league plus all 30 teams; a wrong slug returns 200 with an empty feed, so slugs were verified, not inferred |
| ESPN | `espn.com/espn/rss/mlb/news` | league-wide only; no working per-team feed found |

No auth. No archive and no pagination: each feed returns only its latest 15 to 25 items. **History exists only from the day polling started**, so a gap in polling is a permanent gap. `bootstrap()` and `update()` are the same.

## Rights

Feed access does not give the right to republish summaries or derived NLP features. The connector keeps headlines, links and summaries only, never article bodies. `local_research` only (record: `SOURCE_RIGHTS.md`).

## Products

One table, `raw.news`, for later text-signal work (injuries, trades, rumors). The extraction step is not built.

## Known gaps and open questions

- Because feeds have no archive, `mlb coverage` can only say the table has rows; it cannot say what was missed between polls. A freshness check (newest item age per feed) is the honest measure here.
