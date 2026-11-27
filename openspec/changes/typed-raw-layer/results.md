# Results

## Rehearsal 1: Lahman and register on a copy of real production data (2026-10-13)
Fresh database `mlb_rehearsal` built with `mlb migrate` (all migrations incl. 0118), then production's 27 Lahman and 4 register tables copied in as text (`pg_dump` of the production tables, read-only), then the real operations:
- **Register, migration 0118 in place:** 526,894 people rows (+ names, links, countries) retyped in about 3.4 s; `key_mlbam` non-null count 135,208, equal to production.
- **Lahman, `mlb retype lahman`:** typed copies loaded from the 2025 release (github.com/cbwinslow/lahman-database-csv), 706,466 rows, compared cell by cell against the restored production tables: 27 of 27 identical once the old loader's `NA` -> NULL corruption (3,336 cells) is allowed for. `--apply` swapped all 27 in one transaction; `__old` tables kept (27), no `__new` left, `NA` preserved (50 rows in `lahman_teams`), `birthyear` is `integer`. A second `mlb ingest lahman` changed nothing (row counts the same, ledger rows `loaded`).
- The comparison gate caught a flaw in the first version of the tool (decimals compared as text, `2.00` vs `2`) and refused to swap until it was fixed; fixed by comparing decimals as numbers.

Readers fixed: `conform_player_insert_current_season.sql` (`key_mlbam::text IN (...)`); postseason builds and `report.py` read Lahman columns through `::text` so they work on text and integer columns alike (safe to merge before the swap). Integration run on the final code: 215 passed, 2 skipped (conform, report, report_postseason, health, migrations, coverage, lahman and register load, ingest_layer).

## Whole-database profile (task 2.1)
See `profile.md` once the read-only profile of all 150 raw tables finishes.
