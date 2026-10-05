# Plan — `retrosheetpy` (the second package), 2026-10-05

Status: DRAFT for owner review. Nothing is built yet. Repo `cbwinslow/retrosheetpy` exists, empty, public.
PyPI name `retrosheetpy` was free on 2026-10-05. Owner decision: keep the name (another unrelated
`retrosheetpy` exists on Codeberg; it is not on PyPI). Keep it as long as the name is fine on GitHub.

## What it is, in plain words

`chadwickpy` (published, 0.1.1) turns Retrosheet event files into tables, but you must download and
unzip the files yourself. `retrosheetpy` does the rest: **download a season, keep it in a hidden cache
folder, run the Chadwick tools on it, and hand you data ready for a database.** Like pybaseball: you
ask for a season and it works.

## Who uses it

Researchers, students and data people who want "give me the 2010 season as tables" in one command,
without knowing Retrosheet's file layout. Not a replacement for chadwickpy: it depends on it.

## Commands (proposed)

```
retrosheetpy get 2010                 # download + unpack + cache the 2010 season
retrosheetpy events 2010 [--out DIR]  # cwevent over every team file -> CSV (also: games, daily, subs, comments)
retrosheetpy boxscores 2010           # cwbox text/XML
retrosheetpy list                     # what is cached, what is available
retrosheetpy cache path|clear|verify  # where the cache is, remove it, re-check checksums
```

Python: `import retrosheetpy; retrosheetpy.get(2010); retrosheetpy.events(2010)` returning plain Python
rows (list of dicts) or writing CSV files. pandas is an optional extra, never required.

## Cache

Default `~/.retrosheetpy/` (overridable with `RETROSHEETPY_HOME` or `--cache-dir`). Holds the downloaded
zips with a small JSON record each (URL, download time, SHA-256) and the unpacked season folders.
The tools must run from the folder holding `TEAMyyyy` and the `.ROS` files (Chadwick reads them from the
current folder), so `retrosheetpy` runs each tool with that folder as the working directory.

## Reuse (from `mlb-baseball`, `packages/retrosheetpy/` — ~200 lines, already tested, 835-test suite)

Keep, move into the new repo with history if practical:
- `client.py` (`Client`, `http_fetch`, atomic writes, zip-bomb/path-traversal guards, `iter_zip_members`)
- `catalog.py` (`Product`, `resolve`: yearly CSV, decade event zips, postseason, all-star, Negro Leagues,
  box archive, rosters, biodata, team abbreviations)
- `artifact.py`, `errors.py`
Decide per module (legacy, not part of the Chadwick port): `records.py`, `play.py`, `validation.py`,
`report.py`, `crosswalk.py`, `coverage.py` (a second, independent parser + comparison tooling). Recommendation:
**leave them in `mlb-baseball`** (they serve that project's validation), do not ship them in the new package.
New package = download + cache + run tools + export. Smaller, easier to trust.

## Rights and credit (required, not optional)

- Retrosheet's data-use notice goes in the README, in the docs, and is printed once by `get` on first use.
- Ship no Retrosheet data. Download from Retrosheet's own site with an honest User-Agent, one season at a time,
  never in a tight loop (a polite delay and the cache mean each file is fetched once).
- Say plainly the package is independent and not endorsed by Retrosheet or Chadwick.
- Licence: GPL-3.0-or-later to match chadwickpy (it depends on a GPL derivative). Confirm.

## Build order (each step is a small PR; CI green + review threads resolved before merge)

1. Repo scaffold: pyproject (hatch-vcs, depends on `chadwickpy>=0.1.1`), LICENSE, NOTICE, README, SECURITY,
   CONTRIBUTING, issue templates, CODEOWNERS, ruleset (same as chadwickpy), Dependabot, CodeQL, release-please,
   trusted-publishing workflow (owner adds the PyPI pending publisher), docs workflow. Copy the chadwickpy setup.
2. Move/adapt `client.py`, `catalog.py`, `artifact.py`, `errors.py` + their tests (offline: a fake `fetch`).
3. `get` + cache layout + `list` + `cache` commands. Tests use a tiny fake season zip, no network.
4. `events`/`games`/`daily`/`subs`/`comments`/`boxscores` commands that call chadwickpy per team file.
   Test: output equals running `chadwickpy` by hand on the same files.
5. Export for databases: CSV with a header (default), a `schema` command printing column names/types,
   optional Parquet/SQLite extras later (not in 0.1).
6. Docs site (MkDocs Material, same theme, llms.txt, sitemap), README, GitHub Pages, Search Console later.
7. Review pass (independent agent that also runs the code), TestPyPI is optional, then 0.1.0 to PyPI
   (owner approves the `pypi` environment).

## Decisions I need from the owner

1. Licence GPL-3.0-or-later for retrosheetpy too? (Recommended: yes.)
2. Leave the legacy parser/validation modules in `mlb-baseball`? (Recommended: yes.)
3. Cache folder name `~/.retrosheetpy`? (Recommended: yes, overridable.)
4. Version 0.1.0 scope: seasons 1910+ (decade event zips) first; postseason/all-star/Negro Leagues in 0.2.
   (Recommended: yes.)
5. Docs: separate site per repo (`cbwinslow.github.io/retrosheetpy`)? (Recommended: yes.)

## Risks

- Retrosheet site layout or file names change: pin the catalog in one file, test with a fake server, and
  have `verify` report changed checksums rather than silently re-using bad data.
- Speed: chadwickpy is ~25x slower than C; a full season is ~20-60 s. Say so; add optional per-file
  parallelism later (measure first).
- Name overlap with the Codeberg `retrosheetpy`: say "not affiliated" in the README; revisit only if a real
  conflict appears.
