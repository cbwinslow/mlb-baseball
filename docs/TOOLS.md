# Tools & Libraries

Principle: reuse well-established, actively-used libraries for talking to each source rather than writing custom scrapers/parsers. Each connector's job is landing that library's output into our raw schema — not reimplementing what already exists.

## Per-source libraries (production dependencies)

| Source | Library | Notes |
|---|---|---|
| Chadwick Register | none — direct CSV | Flat file published at [chadwickbureau/register](https://github.com/chadwickbureau/register); just download it. |
| Lahman | `pybaseball` (`lahman` module) | Or pull CSVs directly from [chadwickbureau/baseballdatabank](https://github.com/chadwickbureau/baseballdatabank), which now maintains Lahman's successor. |
| Retrosheet play-by-play | Chadwick CLI tools (`cwevent`, `cwgame`, `cwbox`), invoked via `subprocess` | The standard Retrosheet parser for 20+ years. `pybaseball` does **not** parse Retrosheet itself; confirmed by reading its docs. Don't write a custom parser. The `pychadwick` Python binding was tried and rejected — its C-extension build fails against current CMake (an unfixed upstream packaging bug: its `CMakeLists.txt` requires a `cmake_minimum_required` version modern CMake refuses to process). Calling the CLI tools directly as external processes is more robust and avoids depending on a package that doesn't reliably build. Requires `cwevent`/`cwgame`/`cwbox` on `PATH` — see README for how to get them. |
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
