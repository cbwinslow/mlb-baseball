# Baseball-Reference

Same layout and ownership rules as [`mlb_api.md`](mlb_api.md).

| Question | Owner |
|---|---|
| Tables, rows, seasons, columns | [`RAW_INVENTORY.md`](../RAW_INVENTORY.md) (section `bref`) |
| Offered vs. held vs. missing | `mlb coverage --source bref` |
| Connector contract | [`bref.py.dox.md`](../../mlb_baseball/connectors/bref.py.dox.md) |
| Rights | [`SOURCE_RIGHTS.md`](../SOURCE_RIGHTS.md) (row "Baseball-Reference via pybaseball") |
| Postseason mix-up fix | ADR-282 (`separate-postseason-stats`) |

Facts checked 2026-10-06 (Sports-Reference's bot-traffic page, `pybaseball` 2.2.7 source, connector code).

## Access

- **Client:** `pybaseball` (`batting_stats_range`, `pitching_stats_range`, `bwar_bat`, `bwar_pitch`). Season lines are scraped from HTML; WAR comes from Baseball-Reference's WAR files.
- **Rate limit (published):** Sports-Reference says its sites (other than FBref/Stathead) will put a session "in jail for up to a day" if it makes more than twenty requests in a minute (ten for FBref and Stathead). `pybaseball` has a built-in throttle for exactly this site, the only one in the library. Do not run more than one Baseball-Reference loader at a time.
- **Data policy:** Sports-Reference says it cannot offer its data as a download because third parties license it to them, and offers no API.
- **Saved before load:** no.

## Rights

No permission for automated collection, model training or redistribution is on record, and Sports-Reference states third-party licensing limits. `local_research` only; the enforced record is `SOURCE_RIGHTS.md`.

## Products

| Product | Table(s) | Starts | Grain | Rule |
|---|---|---|---|---|
| Batting and pitching season lines | `raw.bref_batting`, `raw.bref_pitching` | 2008 (a limit inside `pybaseball`, not our choice) | player-season, regular season only | scoped replace per season; past seasons skipped once loaded |
| WAR | `raw.bref_war_batting`, `raw.bref_war_pitching` | 1871 | player-season | no season argument, so whole-table replace every run |

Postseason lines are not here: they come from Lahman (`raw.lahman_batting_post`, `raw.lahman_pitching_post`) into `gold.batting_postseason` and `gold.pitching_postseason`. Team aggregates through `pybaseball` are broken (`IndexError`) and not built; derive them from `core.play`/`core.pitch`.

## Known quirks

- Player names from `pybaseball` arrive with an encoding bug; a narrow repair is applied (ADR-071).
- Before ADR-282 the date window ran through November and Baseball-Reference started including postseason games around 2020 to 2021, which folded playoff games into season lines. Fixed and re-ingested 2008 to 2026.
- Season lines are source aggregates, not point-in-time game history.

## Open questions

- Pre-2008 season lines exist on the site but not through `pybaseball`; whether a lawful path exists is unexamined.
