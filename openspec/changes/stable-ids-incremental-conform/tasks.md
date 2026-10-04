## 1. Measure first (no code changes)

- [ ] 1.1 Time `mlb conform` by step and, for `core.play` / `core.pitch`, by season on production (read-only timings from `pg_stat_statements` and a dry run on a copy or the test database with the same shape); record in `results.md` in this change and verify the table lists every step with seconds
- [ ] 1.2 Profile `mlb predict` (47 min): which steps dominate and whether they rebuild unchanged seasons; record in `results.md` and verify it names the top three costs
- [ ] 1.3 Time `mlb report` by relation; record whether career-grain tables (batting/pitching career) are cheap enough to rebuild in full, and verify the answer is written in `results.md`

## 2. Keys and fingerprints

- [ ] 2.1 Read the venue, team, player and game build SQL and confirm each table's natural key and which are already unique; write the finding into `design.md` D1 and verify no table lacks a unique natural key (or list the migration needed)
- [ ] 2.2 Add a migration for the missing unique constraints, `core.game.game_pk_rule` and `meta.input_fingerprint`; verify it applies on the disposable test database and `scripts/check_dox.py` passes
- [ ] 2.3 Implement the fingerprint read/write (`mlb_baseball/conform_state.py` or similar, one module) and verify with a PostgreSQL integration test that a `--refresh`-style reload of one season changes only that season's fingerprint; measure its scan cost on production and record it in `results.md`

## 3. Upsert core entities

- [ ] 3.1 Convert `core.team` and `core.venue` builds from truncate+insert to upsert on the natural key; verify with an integration test that two runs leave ids unchanged
- [ ] 3.2 Convert `core.player` to upsert (strongest key first; fill the other id when it arrives; never auto-merge two existing rows; log conflicts); verify tests for the "gains a Retrosheet id later" scenario and for a conflict being logged, not merged
- [ ] 3.3 Convert `core.game` to upsert on `retro_game_id` / `game_pk`; verify an integration test that a second run keeps every id and that the 2020 doubleheader / `game_number` cases stay distinct

## 4. Match once

- [ ] 4.1 Collapse the five game-linking functions into one ordered rule list that records `game_pk_rule` and runs only over games with a null `game_pk`; verify tests per rule plus "existing match is kept" and "unmatched stays null"
- [ ] 4.2 Compare the new linker's results with today's production linking (read-only); verify every difference is listed in `results.md` and explained (the 75 post-2015 unmatched games should be examined: All-Star games, 2020 regular-season games)

## 5. Season-level rebuild

- [ ] 5.1 Implement dirty-season detection and per-season replace for `core.game`, `core.market` (delete-by-season in one transaction) and `core.play` / `core.pitch` (staged load then partition swap); verify integration tests for "normal night", "one republished past season" and "nothing changed"
- [ ] 5.2 Add `mlb conform --full` and print rebuilt/skipped seasons plus the earliest rebuilt season; verify `tests/unit/test_cli_dispatch.py` cases through `cli.main([...])`
- [ ] 5.3 Equivalence test: build a fixture in two incremental steps and once in full; verify counts and natural-key checksums match, ignoring ids and `_conformed_at`

## 6. Downstream and cleanup

- [ ] 6.1 Run a one-off production comparison: incremental result vs full rebuild on a restored copy (not production directly); record the outcome in `results.md` and verify zero unexplained differences
- [ ] 6.2 Make `report` rebuild only the seasons `conform` rebuilt (unless task 1.3 shows a full rebuild is cheap); verify gold row counts match a full run on the fixture
- [ ] 6.3 Switch `scripts/mlb_daily_update.sh` to the default incremental mode and remove the 23-table `TRUNCATE`, the bulk-index drop/recreate and the nightly rematching code; verify unit and integration tests still pass and the daily script's tests pass
- [ ] 6.4 Update `mlb_baseball/conform.py.dox.md` / `cli.py.dox.md`, `docs/ARCHITECTURE.md` conform description and add an ADR; verify `scripts/check_dox.py` and `openspec validate stable-ids-incremental-conform` pass
- [ ] 6.5 Run the first stable (full) conform on production after a backup, then a normal incremental night; record both timings in `results.md` and verify the nightly job time is reported against the 2 h 7 min baseline
