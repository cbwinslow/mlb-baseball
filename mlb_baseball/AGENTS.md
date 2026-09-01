# Python Package DOX

## Purpose

Own the importable `mlb_baseball` package: configuration, database access,
ingestion/conformance orchestration, research/statistics logic, operational APIs,
CLI behavior, health/audit/export surfaces, and later modeling components.

## Ownership

Package code owns runtime behavior. SQL DDL belongs in `migrations/`; SQLMesh
models belong in `transforms/`; package-owned operational SQL resources belong in
`mlb_baseball/sql/`; human-facing explanation belongs in `docs/`.

The package should gradually become easier to use as a library, not merely as a
CLI implementation detail.

## Local Contracts

### Dependency direction

- Keep pure domain/stat/math modules importable without unnecessary PostgreSQL or
  ML dependencies where practical.
- Database/network adapters may depend on domain types; pure domain logic should
  not depend on connector implementations.
- Avoid eager imports that make lightweight submodules require XGBoost/psycopg
  unless those dependencies are genuinely needed by that import path.
- Do not expose third-party SDK object models as canonical project contracts.

### Public/API compatibility

- Preserve documented public imports and CLI behavior during mechanical
  refactors unless the change explicitly includes a versioned breaking decision.
- Prefer thin facades over callers reaching into large internal modules.
- Do not build an ORM for the research database. Stable typed query helpers over
  documented relations are preferred.

### Python design

- Use clear typing and small composable functions/classes.
- Use `Protocol` for real pluggable behavior, `StrEnum` for stable domain choices,
  and frozen/slotted dataclasses for immutable value/config/result objects where
  they reduce ambiguity.
- Do not create abstract base hierarchies for hypothetical future implementations.
- Prefer explicit mappings/registries to magical discovery when the set of
  supported sources/components is known.
- Keep exceptions specific and actionable; never silently swallow ingestion or
  database failures.

### SQL ownership

Follow `docs/SQL_OWNERSHIP.md`:

- DDL -> numbered migrations;
- deterministic relational derived models -> SQLMesh where promoted/tied out;
- operational statements that Python executes -> named `mlb_baseball/sql/*.sql`;
- very small parameterized statements may remain inline only when extracting
  them would make the code less clear.

Do not grow new large SQL strings inside Python gravity-well modules.

### Research correctness

- Every table/query/stat must respect its documented grain and time semantics.
- Season/game/career rates are calculated from appropriate aggregate components,
  not averages of lower-grain rates.
- Use outs recorded as canonical pitching innings where arithmetic matters;
  baseball `x.y` innings notation is display formatting, not a decimal.
- Keep source coverage/null behavior explicit; absence of measurement is not zero.

## Work Guidance

Before modifying a module, inspect its callers, tests, SQL resources, and any
matching `.dox.md` required by the nearest child contract.

Large modules should be decomposed mechanically behind stable facades rather than
rewritten wholesale. `cli.py`, `conform.py`, and the MLB API connector are known
gravity wells; preserve behavior and tests while splitting by responsibility.

When a reusable sabermetric formula is currently trapped under `model/`, prefer
moving shared pure definitions toward a neutral statistics/domain package as part
of a scoped refactor, with parity tests.

## Verification

Typical package changes require:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy mlb_baseball
uv run pytest
```

Use narrower checks during iteration and the child-specific requirements for SQL,
connectors, models, or DB behavior.

## Child DOX Index

| Child | Scope |
| --- | --- |
| [connectors/AGENTS.md](connectors/AGENTS.md) | External source acquisition, replay, rights, idempotency, connector sidecars. |
| [model/AGENTS.md](model/AGENTS.md) | Legacy/current feature/model/simulation code, PIT and evaluation discipline. |
| [sql/AGENTS.md](sql/AGENTS.md) | Named package-owned SQL resources and placeholder/ownership rules. |

Other package subtrees should gain child DOX only when they become durable
boundaries with distinct contracts. Ordinary modules remain covered here unless a
source-adjacent `.dox.md` adds clear value.
