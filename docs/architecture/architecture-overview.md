# Baseball Platform Architecture

Date: 2026-05-09
Version: 2.0.0
Updated: 2026-05-12

## Overview

This document describes the refactored architecture of the baseball analytics platform following the Phase 1 foundation and Phase 2 MLB migration.

The platform is a production-oriented Python CLI for downloading, ingesting, normalizing, and querying baseball data from all major public sources (MLB StatsAPI, Retrosheet, StatCast, FanGraphs, Lahman, ESPN, Weather).

---

## Core Principles

1. **Clear Separation of Concerns**
   - Sources: Fetch raw data from external APIs/files
   - Services: Orchestrate workflows
   - CLI: User interface via Typer commands
   - Database: SQL schema in `sql/` directory

2. **No Base Classes Unless Useful**
   - Protocol-based interfaces instead
   - Source-specific optimizations
   - Avoid forced inheritance hierarchies

3. **Reusable Building Blocks**
   - Common utilities in `sources/common/`
   - Shared result objects in `core/results.py`
   - Centralized logging and exceptions

4. **Type Safety**
   - Pydantic models for validation
   - Full type hints
   - Protocol-based contracts

5. **Source Registry**
   - All sources register a `downloader_class` and optional `ingestor_class` via `SourceRegistry`
   - Auto-registered on import from `baseball.sources`
   - Enables CLI and services to discover sources without hardcoding

---

## Directory Structure

```
mlb-baseball/
├── baseball/                    # Main Python package
│   ├── __init__.py
│   ├── __main__.py              # CLI entry point
│   ├── core/                    # Shared enums, exceptions, results, types
│   │   ├── enums.py             # SourceType, DataGranularity, OperationType
│   │   ├── exceptions.py        # Exception hierarchy
│   │   ├── logging.py           # Structlog setup
│   │   ├── results.py           # DownloadResult, IngestResult, ValidationResult
│   │   └── types.py             # Protocol definitions
│   ├── db/                      # Database layer
│   │   ├── bootstrap.py         # Recursive SQL file bootstrapper
│   │   ├── connection.py        # SQLAlchemy connection pool manager
│   │   ├── models.py            # ORM models (canonical + raw + bridge tables)
│   │   ├── schema.py            # Schema introspection and management
│   │   └── config.py           # Database URL and pool config
│   ├── sources/                 # All external data source adapters
│   │   ├── __init__.py          # Auto-registers all sources with SourceRegistry
│   │   ├── registry.py          # SourceRegistry: register/get downloader+ingestor
│   │   ├── contracts.py         # SourceContract abstract interface
│   │   ├── mlb/                 # MLB Stats API
│   │   ├── retrosheet/          # Retrosheet event files and game logs
│   │   ├── statcast/            # Baseball Savant / StatCast pitch data
│   │   ├── fangraphs/           # FanGraphs CSV exports
│   │   ├── lahman/              # Lahman historical database
│   │   ├── espn/                # ESPN scoreboard API
│   │   ├── weather/             # NOAA weather data
│   │   └── common/              # HTTP, file I/O, checksums, retries, time utils
│   ├── services/                # Workflow orchestration
│   │   ├── downloads.py         # download_mlb_season, etc.
│   │   ├── live_games.py        # Live polling orchestration
│   │   ├── validation.py        # Data quality validation orchestration
│   │   ├── normalization.py     # Cross-source normalization
│   │   └── bridging.py          # Cross-source identity resolution
│   └── cli/                     # Typer CLI application
│       ├── app.py               # Main app, version command
│       └── commands/            # download, ingest, validate, status, db
├── sql/                         # All SQL DDL files (versioned, layered)
    |   ├── 10_extensions/        # PostgreSQL extensions (uuid-ossp, pg_trgm, btree_gin)
    |   ├── 20_schemas/            # Schema CREATE statements (raw, staging, core, analytics, monitor)
    |   ├── 50_tables_core/        # Canonical dimension and fact tables (core schema)
    |   ├── 60_tables_xwalk/       # Cross-walk / player ID mapping tables
    |   ├── 70_tables_raw/         # Raw source tables (001–029, verbatim upstream fields)
    |   └── 80_tables_meta/        # Metadata and monitoring tables (run history, source health)
├── docs/                        # Project documentation
│   ├── README.md                # Documentation index
│   ├── architecture/            # Architecture guides
│   ├── sources/                 # Per-source schema and usage notes
│   ├── sql/                     # SQL design notes
│   └── reviews/                 # Code review logs
├── tests/                       # pytest test suite
├── pyproject.toml               # Dependencies and tool config
└── AGENTS.md                    # Contribution rules for humans and AI
```

---

## Data Flow

```
External Sources
  MLB StatsAPI · Retrosheet · StatCast · FanGraphs · Lahman · ESPN · Weather
        |
        v
  [ Downloaders ]  →  Raw files on disk  (DATA_DIR/<source>/)
        |
        v
  [ Ingestors ]    →  Raw tables in PostgreSQL  (schema: raw_<source>)
        |
        v
  [ Services ]     →  Canonical / staging tables  (schema: public)
        |
        v
  [ CLI / Services ] →  baseball <command>
```

---

## Source Registry

All sources implement the `SourceContract` protocol and register with `SourceRegistry` via `baseball/sources/__init__.py`:

```python
from baseball.sources import SourceRegistry

entry = SourceRegistry.get(SourceType.MLB)
downloader = entry.downloader_class(config)
ingestor = entry.ingestor_class(db)
```

`SourceRegistry.summary()` prints a table of all registered sources, their downloader/ingestor classes, and descriptions.

---

## Database Schema Layers

| Layer | Prefix | Purpose |
|-------|--------|----------|
| Extensions    | `10_` | PostgreSQL extensions (uuid-ossp, pg_trgm, btree_gin) |
| Schemas       | `20_` | Schema namespaces (raw, staging, core, analytics, monitor) |
| Core tables   | `50_` | Canonical dimension and fact tables (core schema) |
| Cross-walk    | `60_` | Player ID mapping tables |
| Raw tables    | `70_` | Source tables (001–029, verbatim upstream fields) |
| Meta/Monitor  | `80_` | Metadata, run history, and source health tables |
The bootstrap process is handled by `baseball/db/bootstrap.py`, which recursively discovers and executes all `.sql` files in the `sql/` directory in numeric prefix order.

---

## Related Docs

- [Architecture README](README.md)
- [Source Adapters](source-adapters.md)
- [Download Architecture (Detailed)](download-architecture-detailed.md)
- [Implementation Summary](implementation-summary.md)
- [Architecture Evaluation Summary](architecture-evaluation-summary.md)
- [Sources Documentation](../sources/README.md)
- [SQL Notes](../sql/README.md)
- [Code Reviews](../reviews/README.md)
