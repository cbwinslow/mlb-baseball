# Researcher workflow audit — task 3.1

Scope is deliberately bounded to the entry points a new researcher uses.
Classifications below are current as of 2026-09-26; deferred items are not
authorization for a broader cleanup in this change.

| Surface | Owner/path | Finding | Classification | Action in this change |
| --- | --- | --- | --- | --- |
| CLI | `mlb_baseball/cli.py`, `mlb --help` | `build` creates the local `feat.*` artifact and `verify` checks its mechanics, but neither made model admission explicit. | blocking ambiguity | Add read-only `mlb readiness` with required artifact and tie-out target. |
| Public package | `packages/mlb-research/mlb_research/__init__.py`, `feature_sets.py` | There was no stable model-specific allow-list; callers could assemble arbitrary refs. | blocking ambiguity | Export versioned `get_feature_set` / `game-win:v1` declaration. |
| Feature-store guide | `docs/FEATURE_STORE.md` | Canonical `feat.*` boundary was clear, but no admission workflow, auditable null explanation, or finish line was published. | blocking ambiguity | Document declaration, report, audit denominators, and completion hierarchy. |
| Metric registry | `docs/FEATURE_REGISTRY.md` | Opening wording could make legacy `gold.game_feature` look like the current training surface. | stale/duplicate documentation | Relabel as legacy Engine registry and link to canonical feature store. |
| SQL location | `mlb_baseball/sql/duckdb/feat_game.sql` | Team rates lacked persisted denominator metadata, preventing a report from proving whether NULL was expected. | blocking ambiguity | Add audit-only denominator columns and health checks; never admit them as features. |
| Tests | `tests/integration/test_feat_form.py`, `tests/unit/test_readiness.py`, package feature-set tests | Existing checks covered build/leakage; no unified acceptance or coverage/null report tests existed. | blocking ambiguity | Add declared-contract, report, coverage, and real PostgreSQL→DuckDB integration cases. |
| Legacy model/Engine commands | `mlb_baseball/model/`, historical docs | Multiple paused Phase-B interfaces remain for compatibility. | deferred cleanup | Preserve; do not rewrite/reopen them during Phase-A readiness work. |

The canonical researcher path after this change is: build the backbone and
DuckDB feature artifact, run `mlb readiness` against explicit targets, then
open a separate chronological-model proposal only when the report is `ready`.
