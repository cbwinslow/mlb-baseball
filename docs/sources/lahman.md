# Lahman Baseball Database

Same layout and ownership rules as [`mlb_api.md`](mlb_api.md).

| Question | Owner |
|---|---|
| Tables, rows, seasons, columns | [`RAW_INVENTORY.md`](../RAW_INVENTORY.md) (section `lahman`) |
| Offered vs. held vs. missing | `mlb coverage --source lahman` |
| Connector | `mlb_baseball/connectors/lahman.py` (module docstring; no sidecar yet) |
| Manual download steps | [`DATA_SOURCES.md`](../DATA_SOURCES.md), section "Manual step required: Lahman Database" |
| Rights | [`SOURCE_RIGHTS.md`](../SOURCE_RIGHTS.md) (row "Lahman") |

Facts checked 2026-10-06 (SABR's Lahman page, database).

## Access

- **Distribution:** SABR publishes the current release only through a Box.com folder with no scriptable download URL, so the zip is a **manual download** into `downloads/` (gitignored). The connector picks the newest `downloads/lahman*.zip`.
- **Fallback:** with no local zip, it loads `pybaseball.lahman`'s network copy, repointed to our preserved fork of `baseballdatabank` and **frozen at the 2021 season**, and prints a warning. A fresh clone therefore works but holds old data.
- **Current release:** SABR lists the **2025** release (published 2026-01-02). The database holds seasons up to 2025, so it is current.
- **Update shape:** frozen annual release, so `bootstrap()` and `update()` are the same full reload.
- **Rate limit:** not applicable (single zip).

## Rights

SABR's page names no license and gives the credit "created by SABR member Sean Lahman", with **Negro Leagues data "licensed from Seamheads.com"**. `SOURCE_RIGHTS.md` records CC BY-SA from project documentation and marks public use as pending an attribution and share-alike review. Open item: the Seamheads-licensed portion may carry terms of its own; confirm before any public derivative, and check the documentation file in the release or ask `lahmandb@sabr.org`.

## Products

27 tables named as Lahman names them (people, batting, pitching, fielding, teams, awards, salaries, Hall of Fame, postseason batting and pitching, and more). Row counts and column lists are in `RAW_INVENTORY.md`. Coverage runs from 1871 to the release year.

## Known gaps

- It is a release, not a feed: the current season is absent until SABR publishes the next one. Use other sources for in-season data.
- The 2021-frozen fallback is silent unless the warning is read; a coverage check on the max season would catch it (`mlb coverage` expects the release year only if the registry records it).
