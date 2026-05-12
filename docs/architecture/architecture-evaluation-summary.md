# Baseball Data Download System - Architecture Evaluation Summary

**Date:** 2026-05-09
**System:** retrosheet - Baseball Data Warehouse
**Component:** baseball.data (Data Download Layer)
**Target Reviewer:** Perplexity AI / Code Architecture Evaluation

---

## Executive Summary

This document provides a comprehensive architecture evaluation for the baseball data download system. The design solves the problem of integrating 8+ baseball data sources (MLB Stats API, Retrosheet, StatCast, FanGraphs, Lahman, ESPN, Baseball-Reference, Weather) with:

- **Different API patterns** (RESTful, file-based, web scraping, CSV export)
- **Multiple granularity levels** (league, team, game, play, player, pitcher/batter)
- **Real-time live data** polling capability
- **Clean separation** between download and ingestion
- **Reusable functions** across scripts, Jupyter, CLI, and live applications
- **Type-safe configuration** via Pydantic
- **CLI integration** via Typer

**Key Design Decision:** Strategy Pattern (NO base class inheritance) + Protocol-based polymorphism + Endpoint Registry + Query Builder

---

## Problem Statement

### Current Issues (Before This Design)

1. **30+ scattered download scripts** in `scripts/data_ingestion/` with no unified structure
2. **Inconsistent naming conventions** (download_*, fetch_*, ingest_*)
3. **Mixed concerns** (download + ingestion in same scripts)
4. **No reusability** (functions tightly coupled to scripts)
5. **API endpoint knowledge scattered** (hardcoded URLs in multiple places)
6. **No live data support** (only bulk historical downloads)
7. **Missing granularity levels** (can't download just pitcher stats, batter stats, etc.)
8. **Poor error handling** (no validation, retries, or structured results)
9. **No type safety** (missing Pydantic configs)
10. **Difficult CLI integration** (scattered argparse instead of unified Typer)

### New Requirements

1. ✅ **Unified namespace** (`baseball.data.*`)
2. ✅ **All data sources** mapped with all granularities
3. ✅ **Separation of concerns** (download ≠ ingestion)
4. ✅ **Reusable functions** (work in Jupyter, scripts, CLI, live)
5. ✅ **Type safety** (Pydantic configs + type hints)
6. ✅ **Live data support** (real-time polling)
7. ✅ **Comprehensive endpoint mapping** (all API endpoints)
8. ✅ **Clean polymorphism** (no awkward inheritance)
9. ✅ **Typer CLI** with auto-generated help
10. ✅ **Structured results** with metadata

---

## Architecture Overview

### Design Pattern: Strategy + Adapter + Registry
