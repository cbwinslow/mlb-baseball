# Tasks

- [x] `migrations/0099_analytics_extensions.sql` — pg_trgm, unaccent, btree_gist, tablefunc (no vector, no indexes)
- [x] `mlb_baseball/doctor.py` — `_analytics_extensions_enabled()` + wired into `_CORE_CHECKS`
- [x] `tests/integration/test_analytics_extensions.py` — functional check per extension
- [x] `tests/integration/test_doctor.py` — doctor-check case
- [x] ADR-280 in `docs/DECISIONS.md`
- [ ] Verify: `uv run pytest tests/integration/test_analytics_extensions.py tests/integration/test_doctor.py tests/integration/test_migrations.py -q` passes; `uv run ruff check . && uv run mypy mlb_baseball`
