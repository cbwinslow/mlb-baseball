# MLB Baseball

A free, self-hosted MLB data ingestion, modeling, and research platform — built to go further than [baseball.computer](https://baseball.computer) on data coverage, ship real predictive models, and present them on a public site in the spirit of oddstrader.com.

This is a ground-up rebuild; see [docs/NORTH_STAR.md](docs/NORTH_STAR.md) for the vision and current phase.

## Status

**Phase 1: data ingestion pipeline.** Nothing else is in scope yet — see [docs/ROADMAP.md](docs/ROADMAP.md).

## Docs

- [docs/NORTH_STAR.md](docs/NORTH_STAR.md) — vision, the three build phases, budget constraint
- [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) — every source the pipeline pulls from, cost and license notes
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — schema layering, connector shape, configuration
- [docs/DECISIONS.md](docs/DECISIONS.md) — architecture decision log
- [docs/ROADMAP.md](docs/ROADMAP.md) — build order
- [CLAUDE.md](CLAUDE.md) — operating rules for making changes to this repo

## License

AGPL-3.0 for the code (see [LICENSE](LICENSE)). Data retains whatever license its source requires — see [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).

## Setup

```bash
pip install -e .
cp .env.example .env   # then point DATABASE_URL at your own Postgres (bare-metal by default, see ADR-002)
mlb migrate
mlb doctor              # confirms the database and every dependency (see Requirements) is ready
mlb ingest register --mode bootstrap
mlb ingest lahman --mode bootstrap   # see docs/DATA_SOURCES.md for the manual download step first
mlb ingest retrosheet --mode bootstrap            # pre-parsed CSV product, 1898-present
mlb ingest retrosheet_gamelog --mode bootstrap    # game logs + postseason logs, 1871-present
mlb ingest retrosheet_reference --mode bootstrap  # parks, teams, biographical/coach/umpire/manager data
mlb ingest retrosheet_roster --mode bootstrap     # annual rosters, 1871-present
mlb ingest retrosheet_schedule --mode bootstrap   # planned schedules, 1877-2026
mlb ingest retrosheet_transaction --mode bootstrap
mlb ingest retrosheet_event --mode bootstrap      # raw play-by-play (needs cwevent/cwgame — see Requirements)
mlb ingest retrosheet_box --mode bootstrap        # box-score-only games (needs cwbox — see Requirements)
```

Every registered source is in `mlb_baseball/registry.py`; `mlb doctor` reports on all of them in one pass, and `mlb inventory` shows live row counts and last-run status per source.

## Requirements

- Postgres, reachable via a `DATABASE_URL` in `.env` (bare-metal Postgres is the default assumption — see ADR-002 in `docs/DECISIONS.md`).
- `cwevent`, `cwgame`, and `cwbox` (the Chadwick Baseball Bureau's CLI tools) on `PATH`, required by the `retrosheet_event` and `retrosheet_box` connectors to parse Retrosheet's raw event and box-score files. Build from source: <https://github.com/chadwickbureau/chadwick> (`./configure && make && sudo make install`). The `pychadwick` pip package does **not** work here — its C-extension build fails against modern CMake (see `docs/DECISIONS.md` ADR-004). `mlb doctor` checks for all three tools and tells you if any are missing.

## Testing

```bash
pip install -e ".[dev]"
createdb mlb_test   # one-time: a dedicated test database, separate from the real one
pytest
```

Integration tests run against `mlb_test` (override with `TEST_DATABASE_URL`) — real Postgres, not mocks, per `CLAUDE.md`. `tests/unit/` covers pure logic with no I/O; `tests/integration/` covers everything that touches the database (network calls are mocked with fixture data so tests stay fast and offline-capable).
