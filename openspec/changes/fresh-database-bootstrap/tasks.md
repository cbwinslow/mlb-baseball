## 1. Rehearse on an empty database

- [ ] 1.1 Create a disposable database `mlb_fresh_rehearsal` (name it in the log; never `mlb`). Run `mlb preflight --with-conform`, `mlb migrate`, and record the result. Verify: every migration applies from empty; failures listed with their step.
- [ ] 1.2 Run `mlb bootstrap` for a two-season slice (or the closest the commands allow; record how a slice is selected). Verify: per-source outcome, rows, request count and time recorded in `design.md`.
- [ ] 1.3 Run `mlb coverage`, `mlb conform`, `mlb audit`, `mlb doctor`. Verify: every FAIL and every gap listed with the command that closes it.

## 2. Fix what the rehearsal finds

- [ ] 2.1 For each failure or hidden manual step, fix it at its originating layer with a test that starts from an empty schema. Verify: one task line added per finding; each closes with a passing test.
- [ ] 2.2 Decide and record how the price backfills and `raw.mlb_person` roster gap join the new-user path (new ADR if the decision is hard to reverse).

## 3. One command for a new user

- [ ] 3.1 Add the chaining command (resumable, safe to re-run, stops on a failed hard step with the step name and fix). Verify: dispatch-level test through the real argument parser; run-twice test on the fixture slice.
- [ ] 3.2 Add the automated fixture-slice proof to the test suite. Verify: passes on a disposable PostgreSQL.

## 4. Close out

- [ ] 4.1 Update `docs/BOOTSTRAP_RUNBOOK.md` (single command, time and disk estimates from the ledger, skipped-source reasons).
- [ ] 4.2 Changelog entry in `changelog/`; `mlb doctor` clean on the rehearsal database.
