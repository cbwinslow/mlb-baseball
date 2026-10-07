# Tasks

## 1. Inventory

- [x] 1.1 Verify the origin and licence of the community MLB OpenAPI file and record it in `docs/SOURCE_RIGHTS.md`; verify the entry exists (absorbs `full-source-ingestion` 0.3)
- [x] 1.2 For the MLB Stats API, probe each endpoint family against live responses and record fields, first valid year and request cost in `docs/sources/mlb_api.md`; verify every endpoint is marked wanted, scope or unavailable with a reason (absorbs `full-source-ingestion` 1.1)
- [x] 1.3 Audit pybaseball: list every function, mark working, broken or already replaced by our connector, and record in `docs/sources/` ; verify no transactions, trades, umpire or park-factor source is unaccounted for
- [x] 1.4 Complete the inventory page for Savant, FanGraphs, Baseball-Reference, Retrosheet, Lahman, Chadwick, Kalshi and Polymarket (every board, file and table, with fields); verify the docs check passes
- [x] 1.5 Evaluate `dlt` and the community baseball MCP servers (stars, licence, activity, what they add over our code); record the decision and reasons in an ADR; verify nothing is installed without owner approval

## 2. Drift check (tests first)

- [x] 2.1 Write failing tests: a snapshot compare reports added, removed and changed fields, treats an unreachable source as unchecked, and writes nothing to `raw`; verify they fail for the right reason
- [x] 2.2 Implement the snapshot store and compare for MLB API datasets; verify tests pass and a re-run on unchanged data reports nothing
- [x] 2.3 Extend to file-list sources (Retrosheet, Lahman, Chadwick) and board lists (FanGraphs, Savant); verify a seeded new file is reported
- [x] 2.4 Add `mlb schema-watch` with `--json` and the `meta` findings table (migration); verify migration test and idempotent re-run

## 3. Self-repair (tests first)

- [x] 3.1 Write failing tests: only safe-listed repairs run, caps hold, a third failure suspends a repair, a second run changes nothing; verify against a real disposable PostgreSQL
- [x] 3.2 Define the safe list and caps in code, with a reason per entry (Statcast days, MLB per-game loads, Kalshi and Polymarket backfills with a per-night cap); verify unsafe gaps are only reported
- [x] 3.3 Implement `mlb repair --dry-run/--apply` using coverage gaps and the ledger; verify dry run writes nothing
- [ ] 3.4 Measure one night's real repair cost for Kalshi and Polymarket and set the caps from the measurement; record in the log

## 4. Namespace and library review

- [ ] 4.1 Inventory the upkeep-related `mlb` subcommands and functions: flags, read-only or write, JSON output, tests; record gaps in a table in this change
- [ ] 4.2 Write failing tests for the consistent surface (`--source`, `--mode`, `--dry-run`, `--json` on upkeep commands); then fix the commands without changing existing behaviour; verify old invocations still work
- [ ] 4.3 Generate the command index from the argparse tree and add a test that fails when it is stale; link it from `mlb_baseball/AGENTS.md`

## 5. Agent skill

- [ ] 5.1 Write the upkeep skill (read reports, dry run, show plan, ask before production writes, log); verify with a walkthrough on a seeded gap in a disposable database
- [ ] 5.2 Add the skill to `.claude/skills/` and `.agents/skills/` as the repository convention requires; verify it loads

## 6. Wire in and close

- [ ] 6.1 Add `schema-watch` and `repair` steps to `nightly.py` with tests; add the ADR; update `docs/ARCHITECTURE.md` and connector sidecars; verify `scripts/check_dox.py` passes
- [ ] 6.2 Run once against production read-only (`schema-watch`, `repair --dry-run`) and record results; production `--apply` only with a named owner yes
- [ ] 6.3 `openspec validate source-inventory` passes; mark `data-completeness` 3.3 done; archive after owner review
