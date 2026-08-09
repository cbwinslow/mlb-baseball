# Plan 02 acceptance evidence

Last audited: 2026-08-06. This is an evidence record, not a production
SQLMesh cutover approval.

> Current-environment note (2026-08-09): the evidence below names the former
> `mlb_test_codex` database. The reusable local test database is `mlb_test`;
> follow the current operating docs rather than creating an additional test
> database.

## Passed gates

- Named, packaged SQL now owns the stable venue, park factor, game-feature
  rebuild, team speed, OAA, framing, WAR, and market-prediction mutations.
  Python retains source availability checks, parameters, transactions, and
  sequencing.
- The SQLMesh project is reproducible without creating a database:
  `uv run sqlmesh -p transforms test` passed 2 DuckDB tests;
  `uv run sqlmesh -p transforms plan --no-prompts` reported no changes; and
  all 8 audits for `core.venue`, `gold.park_factor`, and `gold.team_woba`
  passed against the pre-existing spike gateway.
- The existing `mlb_test_codex` database—never a newly created test
  database—passed 66 focused integration tests covering ingestion locks,
  loader drift/identity behavior, Retrosheet CSV/event/box parsing, and the
  refactored feature/model families. The unit suite passed 193 tests.
- Connector evidence includes atomic artifacts/manifests, bounded retry,
  archive validation, advisory locking, explicit snapshot identities, schema
  drift policy, and parser/schema provenance for all three Retrosheet parser
  families (CSV, event, and box).
- `docs/CLICKHOUSE_DECISION.md` records the benchmarked decision not to add
  ClickHouse now.

## Remaining promotion work

- `core.venue`, `gold.park_factor`, and `gold.team_woba` remain candidate
  SQLMesh models. Their outputs must not replace Python writers until the
  documented existing-`mlb_test_codex` candidate namespace and full-table,
  point-in-time, identity-preserving tie-outs are implemented.
- Remaining identity-sensitive conformance SQL still needs incremental
  extraction and per-family tie-outs. Existing
  production behavior is deliberately retained until those gates pass.
- Repository-wide Ruff formatting is not presently a green gate because ten
  pre-existing, unrelated files would be reformatted. Ruff lint is clean and
  every file changed in this plan's current acceptance run is format-clean.

## Final acceptance verification — 2026-08-06

- Tests no longer create or drop databases. The former fresh-database cases
  simulate `psycopg.errors.UndefinedTable`; the doctor and conformance fixtures
  also reset their dynamic raw-table state on the one existing
  `mlb_test_codex` database. Exact verification:
  `TEST_DATABASE_URL=postgresql:///mlb_test_codex uv run pytest -q
  tests/integration/test_doctor.py tests/integration/test_inventory.py
  tests/integration/test_health.py` → `49 passed in 14.65s`; and
  `TEST_DATABASE_URL=postgresql:///mlb_test_codex uv run pytest -q
  tests/integration/test_conform.py::test_reset_dynamic_tables_survives_an_aborted_transaction
  tests/integration/test_conform.py::test_run_populates_team_player_and_game`
  → `2 passed in 13.87s`.
- `core.team`'s stable set-based insert is now the named
  `conform_team_insert.sql` resource. Exact checks: `uv run pytest -q
  tests/unit/test_sql_resources.py` → `23 passed in 0.18s`; targeted team
  parity through `conform.run()` → `1 passed in 13.20s`.
- The non-default SQLMesh `candidate` gateway targets only the existing
  `mlb_test_codex` database, with state in `sqlmesh_plan02_candidate`. A
  review-only plan for `plan02_candidate` proposed only
  `core__plan02_candidate.*` and `gold__plan02_candidate.*`; its apply prompt
  was explicitly declined. `uv run sqlmesh -p transforms test` → `2 passed`.
  `scripts/verify_sqlmesh_candidate.py` is the read-only, fail-closed gate for
  surrogate-ID and completed/scheduled parity.
- Gate semantics are exercised against real PostgreSQL fixture relations in
  only the isolated candidate schemas: `TEST_DATABASE_URL=postgresql:///mlb_test_codex
  uv run pytest -q tests/integration/test_sqlmesh_candidate_gate.py` →
  `1 passed in 0.91s`. It proves exact `core.venue.id` parity and both a
  completed `game_id` and scheduled `mlb_game_pk` feature identity; teardown
  left no candidate schemas or core/gold rows. This validates the gate, not a
  promotion claim for the current SQLMesh models.
- Final focused acceptance commands passed: `uv run ruff check`;
  `uv run sqlmesh -p transforms test` → `2 passed`; the existing-test safety,
  lock, doctor, inventory, health, and candidate-gate selection → `57 passed
  in 15.73s`; and named SQL resources → `23 passed in 0.12s`.
- The full conformance suite was rerun serially after the dynamic-table repair:
  `TEST_DATABASE_URL=postgresql:///mlb_test_codex uv run pytest -q
  tests/integration/test_conform.py` → `46 passed in 644.44s (0:10:44)`.
- The candidate-plan review proposed only `core__plan02_candidate.*` and
  `gold__plan02_candidate.*`, and its apply prompt was declined. Final checks
  found neither candidate schema nor any advisory lock remaining. No test
  database was created; `mlb` was never targeted.

Plan 02 is accepted. This does **not** approve a SQLMesh production writer:
the current spike candidates still lack the surrogate-ID/wide-feature contract
required for cutover, and Python remains the production writer until a future,
explicitly approved promotion change passes this gate with its actual outputs.
