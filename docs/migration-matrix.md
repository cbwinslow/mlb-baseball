# Migration Matrix - Old to New Code Structure

> **Date:** 2026-05-09

## Files Created (Phase 1 & 2)

### Core Layer
- `baseball/core/__init__.py`
- `baseball/core/enums.py` - SourceType, DataGranularity, OperationType
- `baseball/core/exceptions.py` - Exception hierarchy
- `baseball/core/logging.py` - Centralized logging setup
- `baseball/core/results.py` - DownloadResult, IngestResult, ValidationResult, LiveUpdate
- `baseball/core/types.py` - Protocol definitions

### Sources Layer - Common
- `baseball/sources/__init__.py`
- `baseball/sources/contracts.py` - Abstract base contracts
- `baseball/sources/registry.py` - SourceRegistry
- `baseball/sources/common/__init__.py`
- `baseball/sources/common/http.py` - HTTP client utilities
- `baseball/sources/common/files.py` - File I/O utilities
- `baseball/sources/common/checksums.py` - Checksum utilities
- `baseball/sources/common/time.py` - Time utilities
- `baseball/sources/common/retries.py` - Retry decorators

### Sources Layer - MLB
- `baseball/sources/mlb/__init__.py`
- `baseball/sources/mlb/models.py` - Pydantic models (MLBScheduleRequest, MLBGame, etc.)
- `baseball/sources/mlb/params.py` - Parameter transformation
- `baseball/sources/mlb/endpoints.py` - Endpoint URLs and builders
- `baseball/sources/mlb/client.py` - MLB HTTP client
- `baseball/sources/mlb/downloader.py` - Download orchestration
- `baseball/sources/mlb/ingestor.py` - Database ingestion
- `baseball/sources/mlb/validator.py` - Data validation
- `baseball/sources/mlb/live.py` - Live game polling
- `baseball/sources/mlb/schedule.py` - Schedule discovery and planning

### Services Layer
- `baseball/services/__init__.py`
- `baseball/services/downloads.py` - Download orchestration
- `baseball/services/live_games.py` - Live polling orchestration
- `baseball/services/validation.py` - Validation orchestration

### CLI Layer
- `baseball/cli/__init__.py`
- `baseball/cli/app.py` - Typer main app
- `baseball/cli/commands/__init__.py`
- `baseball/cli/commands/download.py`
- `baseball/cli/commands/ingest.py`
- `baseball/cli/commands/validate.py`
- `baseball/cli/commands/status.py`

### Documentation
- `docs/architecture/architecture-evaluation-summary.md`
- `docs/architecture/download-architecture-detailed.md`
- `docs/architecture/implementation-summary.md`
- `docs/migration-matrix.md` - This file

---

## Files Migrated From (Preserved Logic)

### Old `baseball/sources/mlb.py`
- Schedule download logic → `baseball/sources/mlb/downloader.py`
- Game fetch logic → `baseball/sources/mlb/client.py`
- API endpoints → `baseball/sources/mlb/endpoints.py`

### Old `baseball/sources/live_mlb.py`
- Live polling logic → `baseball/sources/mlb/live.py`
- Game state extraction → `baseball/sources/mlb/models.py`

### Old `baseball/cli.py`
- CLI app structure → `baseball/cli/app.py`
- Command registration → Individual command modules

---

## Files NOT YET Migrated (Phase 3+)

| Source | Old Location | Future Location |
|--------|-------------|------------------|
| Retrosheet | `scripts/data_ingestion/retrosheet_*.py` | `baseball/sources/retrosheet/` |
| StatCast | pybaseball wrapper | `baseball/sources/statcast/` |
| FanGraphs | HTML scraping logic | `baseball/sources/fangraphs/` |
| Lahman | Bulk file download/load | `baseball/sources/lahman/` |
| ESPN | Basic scraping | `baseball/sources/espn/` |
| Weather | NOAA integration | `baseball/sources/weather/` |
| Park Factors | Manual file handling | `baseball/sources/park_factors/` |

---

## Breaking Changes

1. **Import paths changed**
   - Old: `from baseball.sources import MLBDownloader`
   - New: `from baseball.sources.mlb import MLBDownloader`

2. **Result objects**
   - Old: Random dicts or plain objects
   - New: Structured result dataclasses

3. **CLI structure**
   - Old: Source-specific sub-apps
   - New: Operation-specific sub-apps (`download`, `ingest`, `validate`, `status`)

## Compatibility Layer (Temporary)

To support gradual migration, add in `baseball/sources/__init__.py`:

```python
# Backwards compatibility (temporary)
from baseball.sources.mlb.downloader import MLBDownloader
from baseball.sources.mlb.client import MLBClient
```
