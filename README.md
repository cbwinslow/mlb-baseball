# MLB Baseball

A free, self-hosted MLB **research database** — historical and live baseball
data, ingested and conformed into a clean PostgreSQL warehouse you run
yourself, with analysis-ready views and CSV / Excel / Parquet export. It aims
to go further than [baseball.computer](https://baseball.computer) on source
coverage (Statcast pitch-level data, live MLB StatsAPI, prediction-market
data — not just Retrosheet/Lahman).

This is a ground-up rebuild; see [openspec/project.md](openspec/project.md) for
the current constitution, and [docs/archive/NORTH_STAR.md](docs/archive/NORTH_STAR.md)
for the original vision.

## Status

**The research database is the current focus** (see
[docs/superpowers/specs/2026-09-01-research-database-v1-design.md](docs/superpowers/specs/2026-09-01-research-database-v1-design.md)).
The warehouse and the daily ingestion path are in production. Work now is on
finishing the export / interop layer and outside-user docs.

Two related efforts are **paused until that ships**, and live in this repo but
are not being worked on:

- a play-then-simulate **prediction ladder** (Elo, GBM, Markov game sim) — the
  `mlb predict` / `train` / `simulate` command families;
- a public **Astro website** in the spirit of oddstrader.com.

Start at [openspec/project.md](openspec/project.md). Superseded navigation and
direction docs are kept in [docs/archive/](docs/archive/) —
[docs/archive/MAP.md](docs/archive/MAP.md),
[docs/archive/PRODUCT_DIRECTION.md](docs/archive/PRODUCT_DIRECTION.md),
[docs/archive/ROADMAP.md](docs/archive/ROADMAP.md).

## Docs

- [openspec/project.md](openspec/project.md) — the project constitution: product, audience, current phase, workflow. Start here.
- [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) — every source the pipeline pulls from, cost and license notes
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — schema layering, connector shape, configuration
- [docs/AUDIT_RUNBOOK.md](docs/AUDIT_RUNBOOK.md) — read-only integrity and coverage validation
- [docs/KNOWLEDGE_BASE.md](docs/KNOWLEDGE_BASE.md) — source-attributed research and data decisions
- [docs/DECISIONS.md](docs/DECISIONS.md) — architecture decision log
- [docs/archive/](docs/archive/) — frozen historical docs (NORTH_STAR, ROADMAP, MAP, plans, reviews)
- [CLAUDE.md](CLAUDE.md) — operating rules for making changes to this repo

## Contributing

Contributions are welcome from any GitHub account through fork-based pull
requests. Direct pushes to `main` are disabled: every change must pass the
required CI checks and be reviewed by the maintainer before it is merged.
`.github/workflows/ci.yml` (lint, type-check, the full test suite against a
real Postgres service, and a gitleaks secret scan) is the required gate;
CodeQL, a dependency-review check, an Actions-workflow linter (actionlint +
zizmor), OpenSSF Scorecard, and a Codecov coverage report also run and post
results without blocking a merge.

- Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.
- Report suspected vulnerabilities privately under [SECURITY.md](SECURITY.md);
  never include credentials in an issue, discussion, or pull request.
- Use the public [roadmap project](https://github.com/users/cbwinslow/projects/25)
  to find the current work, and GitHub Discussions for questions and ideas.

The project is in an early, data-pipeline-first stage. The public website is a
planned Astro deliverable; current progress and sequencing are tracked in
[docs/archive/plans/PROGRESS.md](docs/archive/plans/PROGRESS.md) and [docs/archive/ROADMAP.md](docs/archive/ROADMAP.md).

## License

AGPL-3.0 for the code (see [LICENSE](LICENSE)). Data retains whatever license its source requires — see [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).

## Setup

```bash
uv sync --extra dev
cp .env.example .env     # set DATABASE_URL to your own Postgres instance
cp mlb.toml.example mlb.toml  # optional: ordinary paths/API limits, no secrets
uv run mlb preflight --with-conform
uv run mlb migrate
uv run mlb bootstrap      # runs every registered connector's bootstrap()
uv run mlb doctor         # confirms the raw layer and dependencies are healthy
uv run mlb audit          # read-only game-identity/null/join readiness report
uv run mlb conform        # only after the raw-layer checks you need are healthy
uv run mlb report         # builds the gold.player_season / team_season / division_standing marts
uv run mlb inventory
```

That sequence gives you the warehouse: `raw` (source-faithful), `core`
(conformed, relational), and the research `gold` tables — `player_season`,
`team_season`, `division_standing`, and the per-game statistic backbone
(`batting_game`, …). `gold.game_feature` / `gold.game_export` (the *pregame*
prediction-feature matrix) are additionally populated by `mlb features`,
which is part of the paused prediction ladder — not needed for research use.
From there, query the database directly with `psql` or any Postgres client,
or dump tables to CSV with `psql \copy` (see "Exporting data" below).

The prediction ladder (`mlb predict` / `train` / `simulate`) is paused — see
**Status** above. It still runs, but it is not part of the research-database
workflow and is not being maintained right now.

`mlb preflight` does not download data or write to PostgreSQL. It validates the
resolved non-secret settings, Chadwick tools, database reachability/migration
state, writable download/log directories, free disk, and prints the commands it
would run. Use `mlb preflight --sources mlb_api retrosheet --with-conform` to
plan selected sources rather than the full registered set.

## Configuration

`.env` (or normal environment variables) holds secrets and always overrides
ordinary settings. `mlb.toml` is optional, local, and ignored by Git; copy
[`mlb.toml.example`](mlb.toml.example) to start. It supports only download/log
directories and the already-existing MLB API analytics limits. It does not hide
hardware choices behind presets.

| Setting | Default | Environment override |
| --- | --- | --- |
| Download directory | `downloads` | `MLB_DOWNLOAD_DIR` |
| Log directory | `logs` | `MLB_LOG_DIR` |
| Analytics workers | `8` | `MLB_ANALYTICS_WORKERS` |
| Analytics years | `1950` through current year | `MLB_ANALYTICS_START_YEAR`, `MLB_ANALYTICS_END_YEAR` |
| Retry attempts/backoff/timeout | `3` / `1.0s` / `5s` | `MLB_RETRY_ATTEMPTS`, `MLB_BACKOFF_SECONDS`, `MLB_REQUEST_TIMEOUT_SECONDS` |

`DATABASE_URL` and `TEST_DATABASE_URL` are intentionally environment-only.
That keeps connection credentials out of `mlb.toml`, command output, and Git.

`mlb bootstrap` is slow once `mlb_api`'s and Statcast's full historical ranges are involved, and it is resumable — see `docs/ARCHITECTURE.md` "Bootstrap procedure" before running it for real. To bootstrap one source at a time instead (useful while developing, or to retry just the source that failed), use `mlb ingest <source> --mode bootstrap`; every registered source is in `mlb_baseball/registry.py`. The largest MLB API backfill can also run on its own, without waiting through unrelated endpoint families:

```bash
mlb ingest mlb_api --stage analytics --start-year 1950 --end-year 2026 --workers 16
```

That command downloads bounded parallel batches, writes compressed replayable JSON under `downloads/mlb_api/`, bulk-loads only those games, and safely resumes after an interruption. `lahman` prefers a manually-downloaded zip (see `docs/DATA_SOURCES.md`) but falls back to a network mirror automatically if you skip that step.

To rebuild that analytics range from verified local artifacts without calling MLB again, use `mlb ingest mlb_api --stage analytics-replay --start-year 1950 --end-year 2026`.

For a complete MLB Stats API source rebuild (analytics plus every reference/catalog endpoint), run `scripts/mlb_api_backfill.sh`. It uses one lock, writes a log under `logs/`, resumes safely, refreshes PostgreSQL statistics/reclaimable space after the load, and ends with a database metrics snapshot. Run `mlb doctor` afterward, then `mlb conform` only once the raw-layer checks you need are healthy.

`mlb doctor` reports on every source in one pass, and `mlb inventory` shows live row-count estimates and last-run status per source — both are the way to check on a bootstrap's progress, not by assuming a long-running command has hung. Its default groups yearly play/pitch partitions under their parent; use `mlb inventory --exact` for exact counts and `--partitions` for every child table. `mlb audit` is the separate, read-only data-correctness gate: use it after raw ingestion and after `mlb conform`; `mlb audit --scope statcast` deliberately performs the heavier exact pitch-to-schedule coverage scan. `mlb status` gives the same live table-by-table state as a scannable progress-bar table (`--all` to include empty tables, `--run-status` to weight progress by each source's last ingestion-run outcome instead of just row count, `--watch SECONDS` to auto-refresh). Run `mlb metrics --source mlb_api --window-minutes 5` during a large load to see recent item throughput, database cache use, table size, dead-row estimates, and scan mix before changing performance settings.

For the complete clean-clone sequence, including how to interpret a failure or
resume a source, see [Bootstrap runbook](docs/BOOTSTRAP_RUNBOOK.md).

## Exporting data

The warehouse is a normal PostgreSQL database — point Excel, R, pandas, or any
SQL client straight at it. `gold.player_season`, `gold.team_season`,
`gold.division_standing`, and `gold.game_export` are wide, pre-joined,
analysis-ready relations; `docs/RESEARCH_QUERY_RUNBOOK.md` has copy-paste
`psql \copy ... WITH CSV HEADER` recipes for each.

An `mlb export` command — any allow-listed relation to CSV / Excel / Parquet,
plus a rights-filtered `public_safe` bundle for redistribution — is landing
in a separate change (see the
[v1 spec](docs/superpowers/specs/2026-09-01-research-database-v1-design.md)).
Until it merges, use the `psql \copy` recipes above.

## Scheduling

Two cron jobs, two different cadences — see `docs/ARCHITECTURE.md` "Scheduling" and `docs/DECISIONS.md` ADR-016/ADR-023:

```cron
*/5 * * * * /path/to/mlb-baseball/scripts/mlb_api_update.sh
0 6 * * *   /path/to/mlb-baseball/scripts/mlb_daily_update.sh
```

Replace `/path/to/mlb-baseball` with this repo's actual path. `mlb_api_update.sh` keeps the current season's schedule/standings and live-game state fresh every 5 minutes (`logs/mlb_api_update.log`). `mlb_daily_update.sh` runs `mlb update` — every connector's `update()`, all of them deliberately cheap (current season or a small full-catalog check, never a full historical re-fetch) — once a day to keep Statcast leaderboards, Baseball-Reference season stats, and similar season-in-progress data fresh (`logs/mlb_daily_update.log`). Both guard against overlapping runs with `flock`. `mlb doctor` reports `mlb_api freshness` as unhealthy if the 5-minute job stops running (no successful run in the last 15 minutes), not just if the last run failed.

## Requirements

- Postgres, reachable via a `DATABASE_URL` in `.env` (bare-metal Postgres is the default assumption — see ADR-002 in `docs/DECISIONS.md`).
- `cwevent`, `cwgame`, and `cwbox` (the Chadwick Baseball Bureau's CLI tools) on `PATH`, required by the `retrosheet_event` and `retrosheet_box` connectors to parse Retrosheet's raw event and box-score files. Build from source: <https://github.com/chadwickbureau/chadwick> (`./configure && make && sudo make install`). The `pychadwick` pip package does **not** work here — its C-extension build fails against modern CMake (see `docs/DECISIONS.md` ADR-004). `mlb doctor` checks for all three tools and tells you if any are missing. If setting this up with Claude Code, the `chadwick-tools` skill (portable install steps for Linux/macOS/Windows, plus real usage gotchas) covers this in more depth than this README does.

## Testing

```bash
pip install -e ".[dev]"
TEST_DATABASE_URL=postgresql://mlb:password@localhost:5432/mlb_test uv run pytest
```

Each `pytest` invocation automatically creates an isolated, uniquely-named database
(via `pytest-postgresql`) and tears it down after the run completes. `TEST_DATABASE_URL`
still names the base connection (host, port, user, password), but the actual database
used each run is a clone, not `mlb_test` itself. This isolation means concurrent runs —
including from multiple agent worktrees — no longer collide or interfere.

`tests/unit/` covers pure logic with no I/O; `tests/integration/` covers everything
that touches the database (network calls are mocked with fixture data so tests stay
fast and offline-capable). `mlb_test` is never used or modified during testing.

If a pytest process crashes and orphans its per-run database, run:
```bash
TEST_DATABASE_URL=postgresql:///mlb_test uv run python scripts/reap_test_databases.py --apply
```
(omit `--apply` for dry-run inspection mode).

## Python library usage

This project can bootstrap a researcher-owned local PostgreSQL database; it
does not provide a hosted database or public API. The supported programmatic
surface covers configuration, migrations, profile-checked source ingestion,
conformance, diagnostics, and a normal psycopg connection for SQL research.
See [Public Python API](docs/PUBLIC_API.md) for the local-bootstrap workflow
and data-rights guardrails.

### Test speed

See GitHub issue #2 for the original diagnosis. `core.play`/`core.pitch` are season-partitioned (migration 0011, ~158 partitions each) and every `TRUNCATE` that touches them — including `conform.run()`'s own consolidated one, called from most of `test_conform.py` — pays a synchronous per-relation fsync (`DataFileImmediateSync` in `pg_stat_activity`), independent of `synchronous_commit`: confirmed directly (`psql`, `\timing`) that a bare `TRUNCATE core.play, core.pitch` took ~79s with `synchronous_commit` on and ~84s with it off, no improvement.

`tests/conftest.py`'s session fixture now applies two test-only, automatic relaxations to whatever `TEST_DATABASE_URL` points at (never production — this code path only ever runs from the pytest fixture):

1. `ALTER DATABASE ... SET synchronous_commit = off` — a real, free win for the suite's many small per-test commits, even though it didn't fix the TRUNCATE cost above.
2. Every `core.play`/`core.pitch` partition is set `UNLOGGED`. Unlogged relations skip the fsync that made TRUNCATE slow (they're wiped on crash recovery instead, which is fine — test data is always rebuilt from fixtures). Measured: the same `TRUNCATE` above dropped from ~79s to ~20s. One-time cost (~55s to flip ~316 partitions the first time; ~0.2s on every run after, since it's idempotent) paid once per test session.

On top of that, `tests/integration/test_conform.py` had ~18 leftover per-test `TRUNCATE core.play, core.pitch, ...` cleanup calls that were fully redundant with its own autouse `_clean_tables` fixture (which already `DELETE`s the same tables after every test) — removed outright rather than sped up, since they did nothing but repeat work already done.

For a dedicated, disposable test Postgres *instance* (never one that also hosts a real database), the instance-level `fsync = off` setting eliminates this cost entirely rather than just reducing it — but it disables crash safety for every database on that instance, so only set it in `postgresql.conf` on a cluster you'd happily wipe and never on a shared instance that also runs production data.

Measured full-suite wall time on this machine (shared with other concurrent work at the time of both runs — expect better numbers on a quiet box): **before**, a full run against the unfixed code was deliberately stopped after 25 minutes having completed only 26 of roughly 400 tests (not a projection — an actual run, killed once the pace made a multi-hour completion time obvious); **after**, that then-current suite completed in **18m05s**. Test count changes as coverage is added, so do not treat the historical count as a performance claim.
