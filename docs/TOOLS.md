# Tools & Libraries

Principle: reuse well-established, actively-used libraries for talking to each source rather than writing custom scrapers/parsers. Each connector's job is landing that library's output into our raw schema — not reimplementing what already exists.

## Per-source libraries (production dependencies)

| Source | Library | Notes |
|---|---|---|
| Chadwick Register | none — direct CSV | Flat file published at [chadwickbureau/register](https://github.com/chadwickbureau/register); just download it. |
| Lahman | manual download + `pandas.read_csv` direct from the zip | `pybaseball`'s `lahman` module and `chadwickbureau/baseballdatabank` are both dead ends — the repo was deleted, and SABR's current release is Box.com-only with no scriptable download (confirmed: Box API 401s without an app-registered token). See `docs/DATA_SOURCES.md` for the manual step. Network fallback (frozen at 2021) still uses `pybaseball.lahman`, repointed at a preserved fork. |
| Retrosheet | direct `requests` + `pandas.read_csv` against retrosheet.org's own pre-parsed CSV product | No parsing tool needed — retrosheet.org distributes already-parsed, properly-headered CSVs directly (`downloads/{year}/{year}csvs.zip`), superseding an earlier approach that cloned the raw event files and shelled out to the Chadwick `cwevent` CLI tool (see `docs/DECISIONS.md` ADR-004). That earlier approach worked and is preserved in git history if this source ever goes away; the `pychadwick` Python binding was tried and rejected before that — its C-extension build fails against current CMake (an unfixed upstream packaging bug). |
| MLB Stats API | [MLB-StatsAPI](https://github.com/toddrob99/MLB-StatsAPI) (toddrob99) | Mature (738+ stars), single dependency (`requests`). |
| Statcast | `pybaseball` (`statcast`, `statcast_pitcher`, `statcast_batter`) | Ships built-in local caching (`pybaseball.cache.enable()`) — useful for idempotent re-runs. |
| Polymarket | direct `requests` against the public Gamma REST API | Skip the official `py-clob-client` — it's built for order placement/trading (out of scope, see `NORTH_STAR.md`). No auth needed for reads. |
| Kalshi | direct `requests` against public market-data REST endpoints | Skip trading-oriented SDKs for the same reason. Requires a free account for an API key, but no trading integration. |

## Dev-time tool (not a production dependency)

**`prediction-markets-mcp`** ([JamesANZ/prediction-markets-mcp](https://github.com/JamesANZ/prediction-markets-mcp)) — registered as a local MCP server (`claude mcp add prediction-markets-mcp -s local -- npx -y prediction-markets-mcp`) so Claude can query live Polymarket/Kalshi/PredictIt data interactively while building those connectors. Zero-config, no API keys. This is a development convenience only — the actual Polymarket/Kalshi connectors talk to the REST APIs directly, independent of this MCP server.

Several MCP servers exist that wrap MLB data (`mlb-api-mcp`, `mlb-mcp`, `mcp_mlb_statsapi`) — not adopted, because they're thin wrappers around the same libraries listed above (e.g. `mlb-mcp` literally uses `pybaseball` + `MLB-StatsAPI` under the hood). No reason to add an MCP layer between our code and a library we're already depending on directly.

## Orchestration

None yet. Airflow/Dagster/Prefect all require real hosting/maintenance overhead not justified for one pipeline with a handful of connectors — confirmed by research, matches the existing call in `ARCHITECTURE.md`. Revisit only when there's an actual scheduling/coordination need across many connectors.

## License note

Chadwick's underlying C tools (used via `pychadwick`) are GPL-licensed but invoked as an external process, not linked into our code — no licensing conflict with our AGPL-3.0 code license. `pybaseball` and `MLB-StatsAPI` are permissively licensed.
