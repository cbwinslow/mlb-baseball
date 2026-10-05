# Design — `retrosheetpy` (the "pybaseball for Retrosheet files"), 2026-10-05

Companion to `RETROSHEETPY-PLAN.md` (what and why). This file is how it is built. Facts below were
checked against the installed `pybaseball` and the `chadwickpy` 0.1.1 source, not recalled.

## What we copy from pybaseball, and what we don't
Checked: `pybaseball.retrosheet` has `events(season, type, export_dir)`, `rosters`, `park_codes`,
`schedules`, `season_game_logs`, `world_series_logs`, `all_star_game_logs`, `wild_card_logs`,
`division_series_logs`, `lcs_logs`. Its `events` clones a GitHub mirror and needs the Chadwick C tools
installed. Ours uses `chadwickpy` (pure Python) and Retrosheet's own site, so it works with `pip install`.
- Copy: "ask for a season, get a table"; a switchable on-disk cache; short verb-like function names.
- Don't copy: hard pandas dependency (ours is optional), plotting, other data sources (Statcast, Lahman).
  This package is Retrosheet only.

## Layers (dependencies point down only)
```
cli.py           argparse commands; no logic, calls api
api.py           public functions: get, events, games, ... (the only module users import from)
tables.py        the ONE adapter to chadwickpy; turns each tool into a Table (columns + rows)
export.py        Table -> CSV / list of dicts / (extras) pandas, Parquet
season.py        a cached season on disk: unpack, find TEAMyyyy / .ROS / event files
cache.py         where the cache lives, list, clear, verify
client.py        download + SHA-256 + safe zip reading        (moved in PR #1)
catalog.py       the official Retrosheet URLs, one file       (moved in PR #1)
artifact.py      record of one download                       (moved in PR #1)
errors.py        RetrosheetError and subclasses
_meta.py         version
```
Why a single adapter (`tables.py`): chadwickpy's Python API is documented as "may change before 1.0",
and its tools differ (`event_rows` yields dicts; the others return text lines). Only `tables.py` may
import `chadwickpy`; if its API moves, one file changes. Pin `chadwickpy>=0.1.1,<0.2` until 1.0.

## Core types (small, typed, no framework)
- `Table` (frozen dataclass): `name`, `columns: tuple[str, ...]`, `rows: Iterable[Mapping[str, str]]`.
  Rows are lazy (iterators) so a season never has to sit in memory. Values stay strings like Chadwick's CSV;
  no silent type guessing (missing is not zero).
- `Tool` (a `Protocol`, structural typing): `name`, `columns`, `run(data, league) -> Iterator[row]`. One small
  adapter class per Chadwick tool (events, games, daily, subs, comments). Polymorphism is used here, where
  five tools share one calling shape; the exporter and CLI treat them identically. No other inheritance.
- `Season` (class): owns one unpacked season folder; methods `teams()`, `event_files()`, `league()`.
  Encapsulates "tools need TEAMyyyy and .ROS beside the event files" so callers never touch paths.
- `Cache` (class): `home` dir (env `RETROSHEETPY_HOME`, default `~/.retrosheetpy`), `list()`, `clear()`,
  `verify()`. Wraps `Client`.
- Errors: `RetrosheetError` -> `IntegrityError`, `InvalidArchiveError`, `UnsafeArchiveMemberError`,
  plus `SeasonNotFoundError`, `DownloadError` (network). Every `except` names a specific type, re-raises
  as ours with `from exc`, never `except: pass`.

## Public API (0.1.0, deliberately small)
```python
import retrosheetpy as rs
rs.get(2010)                    # download + cache + unpack; returns Season
rs.events(2010)                 # Table (play-by-play, all cwevent columns)
rs.games(2010)  rs.daily(2010)  rs.subs(2010)  rs.comments(2010)
rs.boxscores(2010)              # text box scores
rs.seasons()                    # what is cached / what can be fetched
rs.to_csv(table, "out.csv")     # export; table.to_dicts(); table.to_pandas() needs the [pandas] extra
```
Options are keyword-only (`team="NYA"`, `out=...`, `refresh=False`). No global mutable state; the cache
location comes from an argument or the environment, read at call time.

## Naming
Short verbs and nouns, one or two words: `get`, `events`, `games`, `Cache`, `Season`, `Table`. Modules are
single words. Keep Chadwick's column names exactly (`GAME_ID`, `EVENT_CD`) because users search for them.

## Code standards (enforced in CI, not just stated)
- Python >= 3.11; `mypy --strict`; `ruff` rules E,F,I,UP,B (add `S` security, `SIM`, `PTH`, `RUF` in the
  scaffold-hardening PR); line length 100; docstring on every public name explaining what and why;
  comments on every non-obvious step (why, not what).
- Standard library plus `chadwickpy` only at runtime. Optional extras: `pandas`, `parquet`.
- Network only in `client.py`, behind an injectable `fetch`. Tests never touch the live site (fake fetch +
  a tiny captured fixture season). Retrosheet data is never committed.
- Safety: unsafe zip names rejected (done); add an uncompressed-size and member-count cap when unpacking
  (the moved client checks names and integrity but has no size limit; this is the one real gap found).
  Polite downloading: honest User-Agent, one file at a time, cached so each file is fetched once.
- Conventional Commit PR titles; squash merge; release-please; PyPI trusted publishing with owner approval.

## Redistribution (PyPI-ready)
hatch-vcs versions from tags; wheel + sdist built and `twine check`ed in CI; clean-venv install test runs the
`retrosheetpy` command; `py.typed`; GPL-3.0-or-later with `NOTICE` carrying Retrosheet's credit; README and
site both show the data-use notice; `get` prints it once on first use.

## Website
Same MkDocs Material setup and theme as chadwickpy (docs workflow, `llms.txt`, sitemap, social card):
Home, Getting started, Guides (seasons and cache, events, games and boxes, Python API, export to a database,
recipes), Reference (CLI help generated from `argparse`, library via mkdocstrings), About (who it is for,
vs pybaseball, vs chadwickpy, Retrosheet data use, FAQ), Changelog.

## Review additions (2026-10-05, after the survey)
- **Retrosheet's own parsed CSVs** (`{year}csvs.zip`: plays, gameinfo, batting, pitching ...) are already in the
  catalog. Offer them too (`retrosheetpy csv 2010`), next to our Chadwick-column tables. Users get both.
- **More than play-by-play**, because pybaseball users expect it: game logs, schedules, rosters, park codes and
  people (biodata) as `Table`s. These are plain files; cheap to add. Target 0.2 (events/games/daily/subs/
  comments/boxscores stay 0.1).
- **Output formats:** rows, CSV, SQLite (stdlib) and pandas in 0.1; Parquet and a generic DB-API loader (Postgres
  etc.) in 0.2. All fed by the one `Table` type.
- **Speed:** chadwickpy is ~25x slower than C. Measure, then add per-team-file parallelism (`jobs=` option);
  do it before 0.1.0 if a full season exceeds about a minute.
- **End-to-end parity test in CI:** a tiny season fixture run through `retrosheetpy` equals the real
  `cwevent` output (CI already builds Chadwick for chadwickpy).
- **Before release, verify** Retrosheet's current data-use and automated-download terms (not yet checked here).
- **Claims:** the docs state only measured, checkable claims (matches Chadwick on N seasons, install without a
  compiler, seconds per season). No "best" or "most complete" wording.

## Revised build order
1. (done) scaffold, protections.  2. (PR #1) downloader moved.
3. Hardening: add ruff `S`/`SIM`/`PTH`/`RUF`, size cap on unpack, `errors` additions.
4. `cache.py` + `season.py` + `get`/`seasons`/`cache` commands (fake-season tests).
5. `tables.py` + the five tool adapters + `events`/`games`/... (test: equals `chadwickpy` run directly).
6. `export.py`, `schema`, CLI wiring, optional pandas extra.
7. Docs site, README, Pages.  8. Independent review pass, then 0.1.0 (owner approves `pypi`).
