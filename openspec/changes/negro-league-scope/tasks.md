## 1. Measure first (read-only)

- [ ] 1.1 Count candidate Negro League games by season using three sources (registry club match, `_group = 'negro_league'` in event/box tables, Lahman `lgid`) and compare with the 3,750 readiness-gap games; record in `results.md` and verify every disagreement is listed
- [ ] 1.2 List every reader of `core.game` with `game_type = 'regular'` (model, feature store, report, readiness, doctor) and note which should read `core.game_mlb`; record in `results.md` and verify the list covers `mlb_baseball/`, `mlb_research` and SQL files
- [ ] 1.3 Record before-values: gold season totals (PA, HR, games) for 1935–1949, Lahman and Baseball-Reference reconciliation results, Retrosheet tie-out for the same seasons; verify numbers are in `results.md`

## 2. Flag and view

- [ ] 2.1 Migration adding the flag column(s) and the `core.game_mlb` view; verify it applies on the disposable test database and `scripts/check_dox.py` passes
- [ ] 2.2 Set the flag in `conform` from the registry (era-aware); verify an integration test with a Negro League game, a NULL-league non-Negro club, and idempotent re-run
- [ ] 2.3 Add a `mlb doctor` check that no flagged game involves an AL/NL club; verify with a failing and a passing fixture

## 3. Use the pool

- [ ] 3.1 Point the game-win feature build, `model/season.py` and readiness at `core.game_mlb`; verify `feat.game` has no flagged game and unit and integration tests pass
- [ ] 3.2 Decide from 1.3 whether gold backbone excludes flagged games; record the decision with the measured effect and verify gold totals against Lahman/Baseball-Reference
- [ ] 3.3 Re-run `mlb build --only-features` and `mlb readiness --feature-set game-win` on a scratch build; verify the remaining unexplained nulls are listed and handled as explained gaps

## 4. Document and verify

- [ ] 4.1 Update `conform.py.dox.md`, add the ADR to `docs/DECISIONS.md`, one line in `docs/DATA_SOURCES.md`; verify `scripts/check_dox.py` and `openspec validate negro-league-scope` pass
- [ ] 4.2 Production (owner applies the migration and runs `mlb conform`): record after-values next to the before-values and verify every difference is explained in `results.md`
