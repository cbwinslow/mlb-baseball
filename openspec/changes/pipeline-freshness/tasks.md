## 1. Phase 1 — stop the recurring empties

- [ ] 1.1 Add a failing test that the feature build raises, naming the relation, when any of `core.game`, `gold.batting_game` or `gold.pitching_game` is empty (one case per relation); then implement the source check in `mlb_baseball/feat.py`. Verify the test passes and the existing feature-store tests still pass.
- [ ] 1.2 Update `scripts/mlb_daily_update.sh` to run `migrate`, then `update`, `conform`, `report`, `predict`, each as its own tracked step, and end with the populated check. Verify with the existing daily-script tests plus a new test that `report` follows `conform` and an empty relation makes the run exit non-zero.
- [ ] 1.3 Make the populated check name every empty backbone relation and reuse the existing `mlb doctor` checks. Verify with a test against a disposable database with one relation emptied.
- [ ] 1.4 Update `docs/ARCHITECTURE.md` "Scheduling" and the daily script header to the new order. Verify with `scripts/check_dox.py` and the docs build.

## 2. Phase 2 — measure

- [ ] 2.1 Record start, end and duration for each step in the daily log. Verify a test parses them from a sample run.
- [ ] 2.2 Profile where `conform` (about 40 minutes) and `report` (about 12 minutes) spend their time, read-only or against a disposable copy; record the table in this change.

## 3. Production catch-up (needs an explicit owner yes)

- [ ] 3.1 On production `mlb`, named explicitly: apply pending migrations, then run `mlb report`. Verify every backbone relation is non-empty and the Baseball-Reference tie-out passes; record row counts.
- [ ] 3.2 Rebuild the feature store from the refreshed backbone and re-run the model-readiness report (`model-readiness-audit` tasks 4.2 and 4.3); record the result there.
- [ ] 3.3 Confirm three consecutive scheduled runs end with all steps ok and a passing populated check.

## 4. Phase 3 — incremental decision (only after Phase 2)

- [ ] 4.1 Answer the design D6 open questions with evidence (which seasons can change; what references `core.game` ids) and record a go / no-go.
- [ ] 4.2 If go: write the full-versus-incremental equality test first, then implement season-level replace with id-stable upserts; verify equality on a disposable fixture and a read-only production comparison. If no-go: record why and stop.

## 5. Wrap-up

- [ ] 5.1 Run `openspec validate pipeline-freshness`; update `openspec/project.md` NOW/NEXT; record the finish-line result.
