# Tools & Libraries

Principle: reuse well-established, actively-used libraries for talking to each source rather than writing custom scrapers/parsers. Each connector's job is landing that library's output into our raw schema — not reimplementing what already exists.

## Per-source libraries (production dependencies)

| Source | Library | Notes |
|---|---|---|
| Chadwick Register | none — direct CSV | Flat file published at [chadwickbureau/register](https://github.com/chadwickbureau/register); just download it. |
| Lahman | manual download + `pandas.read_csv` direct from the zip | `pybaseball`'s `lahman` module and `chadwickbureau/baseballdatabank` are both dead ends — the repo was deleted, and SABR's current release is Box.com-only with no scriptable download (confirmed: Box API 401s without an app-registered token). See `docs/DATA_SOURCES.md` for the manual step. Network fallback (frozen at 2021) still uses `pybaseball.lahman`, repointed at a preserved fork. |
| Retrosheet (CSV product) | direct `requests` + `pandas.read_csv` against retrosheet.org's own pre-parsed CSV product | retrosheet.org distributes already-parsed, properly-headered CSVs directly (`downloads/{year}/{year}csvs.zip`) — no parsing tool needed for this product specifically. |
| Retrosheet (raw event files) | the Chadwick Baseball Bureau's `cwevent`/`cwgame` CLI tools, installed as system binaries (build from source: [chadwickbureau/chadwick](https://github.com/chadwickbureau/chadwick)) | Returned as a *second*, additional Retrosheet product (`retrosheet_event.py`) alongside the CSV product above, not instead of it — see `docs/DECISIONS.md` ADR-009. The `pychadwick` Python binding was tried and rejected — its C-extension build fails against current CMake (an unfixed upstream packaging bug) — so the CLI tools are invoked directly via `subprocess` (`mlb_baseball/chadwick_tools.py`). `mlb doctor` checks all three tools are on `PATH`. |
| Retrosheet (box-score-only files) | the same Chadwick toolchain's `cwbox` CLI tool | Covers games that only ever exist as box scores (pre-1910, Negro League) — `retrosheet_box.py`, see ADR-012. Needs real `TEAM{year}`/roster files unlike `cwevent`/`cwgame` (constructed from Retrosheet's own `TEAMABR.TXT`/`biodata.zip` registries and `rosters.zip`, not invented). `cwbox`'s `-X` XML output needed a couple of real-data fixes (unescaped `&` in historical names, one genuine data-integrity error in Retrosheet's own 1921 Negro League file) — see ADR-012 for both. |
| MLB Stats API | [MLB-StatsAPI](https://github.com/toddrob99/MLB-StatsAPI) (toddrob99) | Mature (738+ stars), single dependency (`requests`). |
| Statcast | `pybaseball` (`statcast`, `statcast_pitcher`, `statcast_batter`) | Ships built-in local caching (`pybaseball.cache.enable()`) — useful for idempotent re-runs. |
| Polymarket | direct `requests` against the public Gamma REST API | Skip the official `py-clob-client` — it's built for order placement/trading (out of scope, see `NORTH_STAR.md`). No auth needed for reads. |
| Kalshi | direct `requests` against public market-data REST endpoints | Skip trading-oriented SDKs for the same reason. Requires a free account for an API key, but no trading integration. |

## Dev-time tool (not a production dependency)

**`prediction-markets-mcp`** ([JamesANZ/prediction-markets-mcp](https://github.com/JamesANZ/prediction-markets-mcp)) — registered as a local MCP server (`claude mcp add prediction-markets-mcp -s local -- npx -y prediction-markets-mcp`) so Claude can query live Polymarket/Kalshi/PredictIt data interactively while building those connectors. Zero-config, no API keys. This is a development convenience only — the actual Polymarket/Kalshi connectors talk to the REST APIs directly, independent of this MCP server.

Several MCP servers exist that wrap MLB data (`mlb-api-mcp`, `mlb-mcp`, `mcp_mlb_statsapi`) — not adopted, because they're thin wrappers around the same libraries listed above (e.g. `mlb-mcp` literally uses `pybaseball` + `MLB-StatsAPI` under the hood). No reason to add an MCP layer between our code and a library we're already depending on directly.

## Database contract tests

[`pgTAP`](https://pgtap.org/) provides a small database-native complement to
pytest's real-Postgres integration suite. The first contract,
`tests/pgtap/log5.pg`, checks the canonical Log5 identities and required
`gold.prediction` columns. Every pgTAP script begins a transaction and rolls it
back, so it never changes test data. Run it with:

```sh
pg_prove --dbname=mlb_test --verbose tests/pgtap/*.pg
```

Install the extension package matching the active PostgreSQL major version
(currently `postgresql-16-pgtap`) on the database host, plus the pgTAP Perl
runner where `pg_prove` runs. GitHub Actions installs the extension in its
disposable PostgreSQL service container and installs only the runner on the
worker.

## Database backup/restore

`mlb backup`/`mlb restore` (`mlb_baseball/backup.py`) wrap PostgreSQL's own
`pg_dump`/`psql` CLI tools — the tools every real Postgres deployment already
trusts for this, not a reimplemented dump format. Same posture as the Chadwick
tools above: invoked directly via `subprocess`, `mlb doctor` checks both are
on `PATH` before a backup/restore is attempted. Install via your OS's
PostgreSQL client package (e.g. `apt install postgresql-client` on
Debian/Ubuntu, `brew install libpq` on macOS) if `mlb doctor` reports them
missing. `restore` is destructive (overwrites objects in the target
database) and requires an explicit `--yes` flag.

## Orchestration

None yet. Airflow/Dagster/Prefect all require real hosting/maintenance overhead not justified for one pipeline with a handful of connectors — confirmed by research, matches the existing call in `ARCHITECTURE.md`. Revisit only when there's an actual scheduling/coordination need across many connectors.

## License note

Chadwick's `cwevent`/`cwgame`/`cwbox` CLI tools are GPL-licensed but invoked as external processes via `subprocess` (`mlb_baseball/chadwick_tools.py`), not linked into our code — no licensing conflict with our AGPL-3.0 code license. (The `pychadwick` Python binding, which would have linked the GPL C library directly into the process, was rejected anyway for the unrelated build-failure reason above.) `pybaseball` and `MLB-StatsAPI` are permissively licensed.
