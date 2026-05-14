# Source Adapter Documentation

Each source adapter lives in `baseball/sources/<source>/` and implements two classes:
- **Downloader** — fetches raw data from the external source and writes to `DATA_DIR`
- **Ingestor** — parses raw files and inserts/upserts into the database

All sources auto-register with `SourceRegistry` when `baseball.sources` is imported.
See [architecture-overview.md](architecture-overview.md) for the full data flow.

---

## MLB StatsAPI (`baseball/sources/mlb/`)

| File | Purpose |
|---|---|
| `client.py` | Low-level HTTP client for StatsAPI |
| `downloader.py` | Fetch schedules, box scores, rosters, play-by-play |
| `endpoints.py` | Endpoint URL builders |
| `ingestor.py` | Database ingestion for MLB raw payloads |
| `live.py` | Live game polling via StatsAPI push |
| `models.py` | Pydantic response models |
| `params.py` | Query parameter builders |
| `schedule.py` | Season schedule downloader |
| `validator.py` | Response validation |

Registry: `SourceType.MLB` → `MLBDownloader` + `MLBIngestor`

---

## Retrosheet (`baseball/sources/retrosheet/`)

| File | Purpose |
|---|---|
| `downloader.py` | Download event/roster/schedule ZIP files |
| `ingestor.py` | Parse and insert retrosheet events into DB |
| `models.py` | Pydantic models for retrosheet record types |
| `parser.py` | Parse `.EVA`/`.EVN` event files |
| `validator.py` | Event record validation |

Registry: `SourceType.RETROSHEET` → `RetroEventFileDownloader` + `RetroEventFileIngestor`

---

## StatCast (`baseball/sources/statcast/`)

| File | Purpose |
|---|---|
| `downloader.py` | Fetch pitch data via pybaseball |
| `ingestor.py` | Parse and insert pitch records into DB |
| `models.py` | Pydantic pitch models |

Registry: `SourceType.STATCAST` → `StatcastDownloader` + `StatcastIngestor`

---

## FanGraphs (`baseball/sources/fangraphs/`)

| File | Purpose |
|---|---|
| `downloader.py` | Fetch CSV exports from FanGraphs |

Registry: `SourceType.FANGRAPHS` → `FanGraphsDownloader` (ingestor: TBD Phase 3)

---

## Lahman (`baseball/sources/lahman/`)

| File | Purpose |
|---|---|
| `downloader.py` | Download Lahman database ZIP |

Registry: `SourceType.LAHMAN` → `LahmanDownloader` (ingestor: TBD Phase 3)

---

## ESPN (`baseball/sources/espn/`)

| File | Purpose |
|---|---|
| `downloader.py` | Fetch scores and standings from ESPN API |

Registry: `SourceType.ESPN` → `ESPNDownloader` (ingestor: TBD Phase 3)

---

## Weather (`baseball/sources/weather/`)

| File | Purpose |
|---|---|
| `downloader.py` | Fetch game-time weather data |

Registry: `SourceType.WEATHER` → `WeatherDownloader` (ingestor: TBD Phase 3)

---

## Common Utilities (`baseball/sources/common/`)

| File | Purpose |
|---|---|
| `checksums.py` | File integrity verification |
| `files.py` | File I/O helpers (requires `pandas`) |
| `http.py` | Shared httpx client with retry logic (requires `tenacity`) |
| `retries.py` | Retry decorator utilities (requires `tenacity`) |
| `time.py` | Date/time helpers |

---

## Adding a New Source

1. Create `baseball/sources/<name>/` with `downloader.py` (and optionally `ingestor.py`)
2. Export the class(es) from `baseball/sources/<name>/__init__.py`
3. Add a `SourceType.<NAME>` entry to `baseball/core/enums.py`
4. Register in `baseball/sources/__init__.py`:
   ```python
   SourceRegistry.register(
       SourceType.NAME,
       downloader_class=MyDownloader,
       ingestor_class=MyIngestor,  # or None
       description="Short description",
   )
   ```

---

## Related Docs

- [Architecture Overview](architecture-overview.md)
- [Sources Documentation Index](../sources/README.md)
- [SQL Raw Schema Notes](../sql/README.md)
