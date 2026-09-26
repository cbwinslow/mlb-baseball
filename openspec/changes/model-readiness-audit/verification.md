# Verification record

Recorded 2026-09-26. The following checks passed after the readiness contract,
report, DuckDB audit-denominator columns, CLI, and documentation changes:

```text
uv run pytest packages/mlb-research/tests/test_feature_sets.py tests/unit/test_readiness.py tests/unit/test_cli_dispatch.py -q
# 143 passed

uv run pytest tests/unit/test_catalog.py tests/unit/test_check_metric_catalog.py -q
# 36 passed

uv run ruff format --check <changed Python paths>
# 9 files already formatted

uv run ruff check <changed Python paths>
# All checks passed

uv run mypy mlb_baseball/readiness.py mlb_baseball/cli.py mlb_baseball/feat.py
# Success: no issues found in 3 source files

git diff --check
# passed

uv run openspec validate model-readiness-audit --strict
# Change 'model-readiness-audit' is valid
```

`tests/integration/test_feat_form.py` is run separately because it builds the
feature artifact from a disposable PostgreSQL database and can take several
minutes:

```text
uv run pytest tests/integration/test_feat_form.py -q
# 20 passed in 320.35s
```

The required real-evidence run remains intentionally pending: it needs an
owner-designated, fully-built verification database and its explicit target
identity. This change must not guess or use an ambiguous production target.
