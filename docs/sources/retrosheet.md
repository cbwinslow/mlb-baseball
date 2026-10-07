# Retrosheet

Source page for the whole Retrosheet family (eight connectors). Same layout and ownership rules as [`mlb_api.md`](mlb_api.md).

| Question | Owner |
|---|---|
| Tables, rows, seasons, columns | [`RAW_INVENTORY.md`](../RAW_INVENTORY.md) (section `retrosheet`) |
| Offered vs. held vs. missing, with the fix command | `mlb coverage --source retrosheet` (and `retrosheet_box`, `retrosheet_event`, `retrosheet_gamelog`, `retrosheet_reference`, `retrosheet_roster`, `retrosheet_schedule`, `retrosheet_transaction`) |
| Connector contracts | `mlb_baseball/connectors/retrosheet*.py.dox.md` (one per connector) |
| Rights | [`SOURCE_RIGHTS.md`](../SOURCE_RIGHTS.md) (row "Retrosheet data products") |
| Is a downloaded file still current? | `mlb source-check` (HEAD requests only) |
| Tie-out against our own parse | `scripts/verify_retrosheet_tie_out.py` |

Facts checked 2026-10-06 (live response headers and the published notice).

## Access

- **Host:** `www.retrosheet.org`. Static files over HTTP; no API, no key, no published rate limit. Files are fetched whole and cached under `downloads/retrosheet*`.
- **Client:** project code (`requests` with shared retry), not `pybaseball`. Parsing of raw event files uses Chadwick tools (`cwevent`, `cwgame`, `cwbox`) where the connector says so.
- **Saved first:** the zips are kept on disk, so a load can be replayed (the strongest position of any source we have).
- **Republishing:** Retrosheet rewrites files in bulk. On 2026-08-09 every file we checked was re-stamped (`Last-Modified: Sun, 09 Aug 2026`), including old years, while `tranDB.zip` is unchanged since 2022-05-09. Procedure when a source changes: `mlb ingest <source> --refresh`, then `scripts/verify_retrosheet_tie_out.py`, then a core/gold rebuild. `mlb source-check` is the cheap detector (HEAD requests only; exit 1 means something changed). Result on 2026-10-06 for the five zip-based families (yearly CSV 128 archives, game logs 160, rosters, schedule, transactions): 0 changed, so our saved files match what Retrosheet serves now. This compares saved files with the server, not the database with the files; whether raw tables were reloaded from the refreshed files is covered by the tie-out script, not by this check.

## Rights

Retrosheet's notice (`retrosheet.org/notice.txt`) lets recipients use the data freely, including selling it or building commercial products, on one condition: this statement must appear prominently: "The information used here was obtained free of charge from and is copyrighted by Retrosheet. Interested parties may contact Retrosheet at "www.retrosheet.org"." It makes no accuracy guarantee. This is the only source family allowed under the `public_safe` profile. Any public artifact must carry the statement; keep the notice that ships with each download in the ingestion manifest.

## Products

| Product | Connector | Source file | First year | Grain | Caveat |
|---|---|---|---|---|---|
| Yearly CSV bundle (`plays`, `gameinfo`, `teamstats`, `batting`, `pitching`, `fielding`, `allplayers`) | `retrosheet` | `downloads/{year}/{year}csvs.zip` | 1898 | per play / game / player-game | Retrosheet's pre-parsed product; narrower in time than the raw event files |
| Raw event files | `retrosheet_event` | `retrosheet.org/events` | about 1910 (regular season) | per play, parsed by Chadwick | some seasons are deduced (reconstructed) play-by-play; the raw table does not flag every deduced row; postseason, All-Star and Negro League have separate whole-history archives |
| Box-score-only games | `retrosheet_box` | box archives | 1871 | per game, per player line | covers games that never had event files (NA 1871/72/74, late 1890s-1909, Negro Leagues); a box score does not imply an event record |
| Game logs | `retrosheet_gamelog` | `gamelogs/gl{year}.zip` | 1871 | one row per game, 161 fields | headerless; postseason and All-Star are separate files (`glws`, `glas`, `glwc`, `gldv`, `gllc`), so regular-season logs are not a complete game list |
| Reference | `retrosheet_reference` | `parkcode.txt`, `TEAMABR.TXT`, `biofile.zip`, `biodata.zip` | n/a | parks, team history, people | whole-file replace each run, no per-year scope |
| Rosters | `retrosheet_roster` | `rosters.zip` | 1871 | player-team-season | team and season come from the filename; bundled umpire files are deliberately not loaded |
| Schedules | `retrosheet_schedule` | `schedule/schedule.zip` | 1877 | planned game | planned, not played: postponements and makeups differ from final facts |
| Transactions | `retrosheet_transaction` | `transactions/tranDB.zip` | historical | one row per transaction | **frozen 2021-11-26**; for anything later use the MLB API transactions |

Do not state one start year for Retrosheet; it varies by product. Event-level coverage is narrower than game-level coverage, which is why `mlb coverage` checks each product against its own unit.

## Known gaps and open questions

- Box-score coverage looks small next to the game list (about 18k box games against 211k games). Whether Retrosheet publishes box scores for the rest is open (`full-source-ingestion` task 4.1); do not assume it is a source gap until the published file list is compared.
- Raw tables versus the refreshed files: `source-check` cannot show this. Run the tie-out script and record the date and result here.

## Verified 2026-10-07 (database)

- Event (play-by-play) data: 208,693 games, 1900 to 2025. Box scores published directly: 1871 to 1961 (later box scores derive from the events). Game logs: 1871 to 2025.
- Nothing for 2026 yet; this is why the MLB Stats API loads play-by-play and box scores only from 2026 (`mlb_api.md`).
