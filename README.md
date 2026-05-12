# ⚾ MLB Baseball Analytics Platform

[![CI](https://github.com/cbwinslow/mlb-baseball/actions/workflows/ci.yml/badge.svg)](https://github.com/cbwinslow/mlb-baseball/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A canonical baseball data engineering, modeling, simulation, and prediction platform. It aggregates data from MLB StatsAPI, Retrosheet, StatCast, FanGraphs, Lahman, ESPN, and Weather sources into a unified PostgreSQL database and exposes a rich CLI for downloading, ingesting, validating, and analyzing baseball data.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [CLI Usage](#cli-usage)
- [Data Sources](#data-sources)
- [Database Schema](#database-schema)
- [Development](#development)
- [Roadmap](#roadmap)
- [Contributing](#contributing)

---

## Features

- **Multi-source ingestion** — MLB StatsAPI, Retrosheet, StatCast/Baseball Savant, FanGraphs, Lahman, ESPN, Weather
- **Unified PostgreSQL schema** — canonical player/team/park/game/pitch tables with cross-source ID crosswalks
- **CLI-first** — `baseball` CLI with `db`, `download`, `ingest`, `validate`, and `status` command groups
- **Data quality framework** — pluggable validators for completeness, integrity, and referential checks
- **Live game support** — poll MLB StatsAPI for live play-by-play with StatCast delay awareness
- **ID bridging** — reconcile MLBAM, Retrosheet, Lahman, FanGraphs, and Baseball-Reference IDs
- **Structured logging** — `structlog`-backed JSON logs for every pipeline stage

---


## Documentation

See the documentation index for organized project docs:

- [Documentation index](docs/README.md)
- [Architecture overview](docs/architecture/architecture-overview.md)
- [Source adapters](docs/architecture/source-adapters.md)
- [Migration matrix](docs/migration-matrix.md)

## Architecture

See [`docs/architecture/architecture-overview.md`](docs/architecture/architecture-overview.md) for the full system design.

```
External Sources
  MLB StatsAPI · Retrosheet · StatCast · FanGraphs · Lahman · ESPN · Weather
          |
   [ Downloaders ]  →  Raw files on disk
          |
   [ Ingestors ]   →  Parse + normalize
          |
   [ DB Layer ]    →  PostgreSQL (SQLAlchemy + versioned SQL scripts)
          |
   [ Validators ]  →  Data quality checks
          |
   [ CLI / Services ] →  baseball <command>
```

---

## Prerequisites

- Python 3.12+
- PostgreSQL 15+
- [uv](https://github.com/astral-sh/uv) (recommended) or `pip`

---

## Installation

```bash
# Clone the repo
git clone https://github.com/cbwinslow/mlb-baseball.git
cd mlb-baseball

# Install with uv (recommended)
uv sync

# Or with pip
pip install -e .

# Install dev extras
pip install -e ".[dev]"
```

---

## Configuration

The platform is configured via environment variables. Copy and edit the example:

```bash
cp .env.example .env
```

| Variable | Description | Example |
|---|---|---|
| `DATABASE_URL` | PostgreSQL DSN | `postgresql+psycopg://user:pass@localhost:5432/baseball` |
| `DATA_DIR` | Root directory for downloaded raw files | `/data/baseball` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `MLB_API_BASE_URL` | MLB StatsAPI base URL | `https://statsapi.mlb.com/api/v1` |

> ⚠️ `DATABASE_URL` is **required** for all `db`, `ingest`, and `validate` commands.

---

## CLI Usage

```
baseball --help

Usage: baseball [OPTIONS] COMMAND [ARGS]...

  Baseball analytics platform CLI

Commands:
  db        Database initialization and management
  download  Download raw data from external sources
  ingest    Ingest downloaded data into database
  status    Report system and data status
  validate  Validate data integrity and quality
```

### Database

```bash
# Initialize schema (creates all tables)
baseball db init

# Drop and recreate (DESTRUCTIVE)
baseball db init --drop-existing

# Show connection status and row counts
baseball db status

# Validate schema
baseball db validate
```

### Download

```bash
# Download MLB StatsAPI data for a season
baseball download mlbstatsapi --season 2024

# Download Retrosheet event files
baseball download retrosheet --season 2024 --type events

# Download StatCast pitches for a date range
baseball download statcast --start-date 2024-04-01 --end-date 2024-10-01
```

### Ingest

```bash
# Ingest Retrosheet data into database
baseball ingest retrosheet --season 2024

# Ingest MLB StatsAPI data
baseball ingest mlbstatsapi --season 2024
```

### Validate

```bash
# Run all data quality checks
baseball validate all-checks

# Check completeness for a season
baseball validate completeness --season 2024
```

### Status

```bash
# System health
baseball status system

# Data coverage
baseball status data --season 2024
```

---

## Data Sources

| Source | Type | Coverage | Status |
|---|---|---|---|
| MLB StatsAPI | REST API | Schedules, box scores, play-by-play, rosters | ✅ Downloader implemented |
| Retrosheet | File download | Event files, rosters, schedules 1920–present | ✅ Downloader + parser implemented |
| StatCast | pybaseball | Pitch-level data 2015–present | ✅ Downloader implemented |
| FanGraphs | CSV export | Advanced batting/pitching stats | ✅ Downloader implemented |
| Lahman | File download | Historical stats 1871–present | ✅ Downloader implemented |
| ESPN | REST API | Scores, standings | ✅ Downloader implemented |
| Weather | REST API | Game-time weather | ✅ Downloader implemented |

---

## Database Schema

All schema is managed via versioned SQL scripts in `sql/`. The bootstrap order is:

```
sql/
  10_extensions/     PostgreSQL extensions (uuid-ossp, pg_trgm, etc.)
  20_schemas/        Schema creation
  30_tables_raw/     Raw staging tables per source
  40_tables_staging/ Normalized staging tables
  50_tables_core/    Core canonical tables (player, team, park, game, pitch, ...)
  60_tables_analytics/ Derived/analytics tables
  70_constraints_indexes/ FK constraints and performance indexes
  80_views_mviews/   Views and materialized views
  90_functions_triggers/ Stored procedures and triggers
  100_validation/    Data quality assertion queries
  110_monitoring/    Monitoring and alerting queries
  120_metadata/      Schema metadata and documentation tables
```

> ⚠️ **SQL schema files are pending** — tracked as [Phase 2 work](https://github.com/cbwinslow/mlb-baseball/milestones). The ORM models in `baseball/db/models.py` define the canonical schema and are used by `baseball db init` to bootstrap the database via SQLAlchemy.

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Lint and format
ruff check baseball/
ruff format baseball/

# Type check
pyright baseball/

# Security scan
bandit -r baseball/ -ll

# Pre-commit hooks
pre-commit install
pre-commit run --all-files
```

### Project Structure

```
mlb-baseball/
├── baseball/
│   ├── cli/           CLI entry point and command groups
│   ├── core/          Enums, exceptions, logging, types
│   ├── data/          Query and data source contracts
│   ├── db/            Database layer (connection, models, schema, migrations)
│   ├── services/      Orchestration services (downloads, bridging, live games)
│   └── sources/       Source-specific downloaders and ingestors
│       ├── common/    Shared HTTP, retry, checksum, file utilities
│       ├── espn/
│       ├── fangraphs/
│       ├── lahman/
│       ├── mlb/
│       ├── retrosheet/
│       ├── statcast/
│       └── weather/
├── docs/
│   └── architecture/  Architecture documentation
├── sql/               Versioned SQL schema scripts (Phase 2)
├── tests/             Test suite
├── AGENTS.md          AI agent coding guidelines
├── pyproject.toml
└── README.md
```

---

## Roadmap

See [GitHub Milestones](https://github.com/cbwinslow/mlb-baseball/milestones) for the current roadmap.

| Phase | Focus | Status |
|---|---|---|
| Phase 1 | Core architecture, downloaders, CLI, DB layer | ✅ Complete |
| Phase 2 | SQL schema files, ingestor wiring, test coverage | 🔄 In Progress |
| Phase 3 | Analytics models, predictions, simulations | 📋 Planned |
| Phase 4 | Live game engine, real-time features, API server | 📋 Planned |

---

## Contributing

1. Read [`AGENTS.md`](AGENTS.md) before making changes — it contains coding standards and architecture guidelines.
2. Open an issue or pick up an existing one from the [backlog](https://github.com/cbwinslow/mlb-baseball/issues).
3. Create a feature branch: `git checkout -b feat/your-feature`
4. Write tests for any new functionality.
5. Run `pre-commit run --all-files` before submitting a PR.
6. Submit a pull request against `main`.
