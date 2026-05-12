# Source Adapter Documentation

Each source adapter lives in `baseball/sources/<source>/` and implements two classes:
- **Downloader** — fetches raw data from the external source and writes to `DATA_DIR`
- **Ingestor** — parses raw files and inserts/upserts into the database

---

## MLB StatsAPI (`baseball/sources/mlb/`)

| File | Purpose |
|---|---|
| `client.py` | Low-level HTTP client for StatsAPI |
| `downloader.py` | Fetch schedules, box scores, rosters, play-by-play |
| `endpoints.py` | Endpoint URL builders |
| `live.py` | Live game polling via StatsAPI push |
| `models.py` | Pydantic response models |
| `params.py` | Query parameter builders |
| `schedule.py` | Season schedule downloader |
| `validator.py` | Response validation |

**Note:** `MLBIngestor` is imported by the CLI but does not yet exist — tracked as a Phase 2 issue.

---

## Retrosheet (`baseball/sources/retrosheet/`)

| File | Purpose |
|---|---|
| `downloader.py` | Download event/roster/schedule ZIP files |
| `ingestor.py` | Parse and insert retrosheet events — **DB wiring is TODO** |
| `models.py` | Pydantic models for retrosheet record types |
| `parser.py` | Parse `.EVA`/`.EVN` event files |
| `validator.py` | Event record validation |

---

## StatCast (`baseball/sources/statcast/`)

| File | Purpose |
|---|---|
| `downloader.py` | Fetch pitch data via pybaseball |
| `ingestor.py` | Parse and insert pitch records — **DB wiring is TODO** |
| `models.py` | Pydantic pitch models |

---

## FanGraphs (`baseball/sources/fangraphs/`)

| File | Purpose |
|---|---|
| `downloader.py` | Fetch CSV exports from FanGraphs |

---

## Lahman (`baseball/sources/lahman/`)

| File | Purpose |
|---|---|
| `downloader.py` | Download Lahman database ZIP |

---

## ESPN (`baseball/sources/espn/`)

| File | Purpose |
|---|---|
| `downloader.py` | Fetch scores and standings from ESPN API |

---

## Weather (`baseball/sources/weather/`)

| File | Purpose |
|---|---|
| `downloader.py` | Fetch game-time weather data |

---

## Common Utilities (`baseball/sources/common/`)

| File | Purpose |
|---|---|
| `checksums.py` | File integrity verification |
| `files.py` | File I/O helpers (requires `pandas`) |
| `http.py` | Shared httpx client with retry logic (requires `tenacity`) |
| `retries.py` | Retry decorator utilities (requires `tenacity`) |
| `time.py` | Date/time helpers |
