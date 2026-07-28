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
mlb bootstrap            # runs every registered connector's bootstrap() — see "Bootstrap procedure" below
mlb conform              # builds core.player/team/game from the raw tables above
```

`mlb bootstrap` is slow (realistically days, not minutes) once `mlb_api`'s and Statcast's full historical ranges are involved, and it's resumable — see `docs/ARCHITECTURE.md` "Bootstrap procedure" before running it for real. To bootstrap one source at a time instead (useful while developing, or to retry just the source that failed), use `mlb ingest <source> --mode bootstrap`; every registered source is in `mlb_baseball/registry.py`. `lahman` prefers a manually-downloaded zip (see `docs/DATA_SOURCES.md`) but falls back to a network mirror automatically if you skip that step.

`mlb doctor` reports on every source in one pass, and `mlb inventory` shows live row counts and last-run status per source — both are the way to check on a bootstrap's progress, not by assuming a long-running command has hung.

## Scheduling

Two cron jobs, two different cadences — see `docs/ARCHITECTURE.md` "Scheduling" and `docs/DECISIONS.md` ADR-016/ADR-023:

```cron
*/5 * * * * /path/to/mlb-baseball/scripts/mlb_api_update.sh
0 6 * * *   /path/to/mlb-baseball/scripts/mlb_daily_update.sh
```

Replace `/path/to/mlb-baseball` with this repo's actual path. `mlb_api_update.sh` keeps the current season's schedule/standings and live-game state fresh every 5 minutes (`logs/mlb_api_update.log`). `mlb_daily_update.sh` runs `mlb update` — every connector's `update()`, all of them deliberately cheap (current season or a small full-catalog check, never a full historical re-fetch) — once a day to keep Statcast leaderboards, Baseball-Reference season stats, and similar season-in-progress data fresh (`logs/mlb_daily_update.log`). Both guard against overlapping runs with `flock`. `mlb doctor` reports `mlb_api freshness` as unhealthy if the 5-minute job stops running (no successful run in the last 15 minutes), not just if the last run failed.

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
