# `cli.py` DOX

## Purpose

Own the current `mlb` command-line interface and its dispatch/orchestration layer. This file is a large compatibility surface (~383 KB) and the repository's largest structural debt area; preserve CLI behavior while decomposing it incrementally rather than rewriting the parser/command tree wholesale.

## Ownership

Implementation: `cli.py`.

Major command families currently include database lifecycle/migrations, connector ingestion, bootstrap/update orchestration, conformance, features/reports/research/model operations, inventory/status/metrics/doctor, exports and other operational/research commands.

The CLI owns:

- argument/subparser definition;
- user-facing command names/options/help;
- source-profile/rights gating at command boundaries;
- command dispatch and exit status;
- top-level connector orchestration/concurrency;
- concise rendering of command results/errors.

The CLI should **not** own domain/business formulas, substantial SQL, connector parsing, database algorithms, or model implementations. Those belong to package modules that CLI handlers call.

## Compatibility Contract

- Treat existing command names/options/output semantics as a public interface for scripts/users unless a deliberate change updates tests/docs/callers together.
- A new/changed subcommand must have dispatch-level tests through `cli.main([...])` / real argparse parsing, not only tests of the called function.
- Do not read an argparse attribute that was not defined on every parser path that can reach the handler; this has caused real runtime bugs.
- Exit non-zero when requested work fails materially. Do not swallow connector/group failures merely to finish printing output.
- Source-profile violations should be explicit skips/errors, not silent access to disallowed source data.

## Connector Contract at the CLI Boundary

Registered connectors are expected to expose the standard connector behavior used by CLI orchestration:

- `bootstrap()`
- `update()`
- `health_check()`

Some connectors may additionally expose an expensive/manual `backfill` mode. Backfill must remain opt-in and must not accidentally run as part of routine bootstrap/update.

When adding a connector, update the explicit registry and applicable source/profile/docs/tests. Do not build a second plugin-discovery framework inside the CLI.

## Bootstrap / Update Concurrency Contract

Top-level connector concurrency is intentionally grouped by **external server**, not simply "all connectors in parallel."

Current logic:

- `_SAME_SERVER_GROUPS` identifies connectors known to hit the same upstream host.
- connectors inside one same-server group run sequentially;
- groups run concurrently with each other;
- unknown/unclassified connectors default to singleton groups;
- group/connector failures are isolated and reported while other independent sources continue;
- a final non-zero exit communicates that at least one source failed.

This design exists because same-server connector concurrency previously produced a real Retrosheet/thread hang, while fully serial orchestration made the extremely broad MLB API bootstrap impractically slow.

Do not:

- flatten everything into one large thread pool;
- remove same-server grouping based on aesthetic simplicity;
- add a connector to a group by guessing its host;
- add nested concurrency without reviewing whether the connector itself already parallelizes requests.

Any concurrency change requires explicit upstream-host mapping, bounded worker counts, failure behavior, and a measured reason.

## Source Profiles / Rights

The CLI is an enforcement point for source profiles:

- call `require_sources(...)` or the current shared profile mechanism before operations using restricted/disallowed sources;
- keep public/export/research commands consistent with rights-safe profiles;
- do not add convenience flags that bypass rights checks.

Profile logic belongs in `source_profiles` / rights metadata; the CLI should orchestrate it rather than duplicate policy tables.

## Database Safety

- Commands with destructive or production-affecting database behavior must make target/impact clear in help/output and defer core safety to the owning module.
- Do not special-case pytest database internals here; tests own their run-specific disposable DB lifecycle.
- Migration/restore/destructive commands should not become easier to invoke ambiguously while refactoring dispatch.

## Handler Design

Desired direction:

1. keep parser/behavior stable;
2. extract coherent named handler functions for command families;
3. move dispatch into an explicit mapping/router where it improves readability/testability;
4. split durable command families into a `mlb_baseball/cli/` package only after handlers are isolated;
5. retain a stable `main()`/console entry facade.

Do not combine structural extraction with broad command renaming/semantic changes.

A command handler should generally:

- validate/translate CLI arguments;
- invoke the owning package API;
- commit only if the owning API contract requires caller-managed transactions;
- format concise output;
- map expected domain errors to understandable CLI errors/exit statuses.

It should not embed a second implementation of the domain operation.

## Model / Engine Command Freeze

The CLI currently exposes a very broad collection of model/metric/Engine-related commands inherited from prior expansion. During the research-database consolidation phase:

- do not keep adding one top-level command per new metric/Engine;
- preserve existing commands for compatibility;
- classify/validate/consolidate them before deciding whether many should eventually move under a grouped `mlb engine <name>` / research namespace;
- make grouping decisions separately from behavior-preserving structural decomposition.

## Lazy Imports / Dependency Weight

Large/optional command families may import heavyweight dependencies lazily inside handlers when that improves research-only CLI startup/install behavior without hiding import errors.

Do not eagerly force ML dependencies on commands that only query/export the research database if dependency extras are later split.

## Help and Documentation Contract

When user-facing syntax changes:

- update CLI dispatch tests;
- update `docs/USER_MANUAL.md` / runbooks/examples that use the command;
- keep `--help` accurate;
- avoid undocumented aliases/hidden behavior that agents/users must rediscover from source.

## Work Guidance

Before editing `cli.py`:

1. identify the exact command family and owning module;
2. search `tests/unit/test_cli_dispatch.py` and related CLI tests;
3. inspect docs/examples using that syntax;
4. determine whether the edit is semantic or only structural;
5. preserve unrelated parser branches.

For structural decomposition, make small commits/PRs with no behavior changes and use dispatch snapshot/argument tests to prove compatibility.

## Verification

Expected checks for CLI changes include:

- targeted CLI dispatch tests using real argparse;
- error/exit-code tests for changed failure paths;
- connector grouping tests when orchestration changes;
- source-profile gating tests when source permissions change;
- docs/help examples for changed syntax;
- owning module integration tests where CLI invokes database/source behavior;
- Ruff/mypy.

A parser refactor is not verified merely because the underlying Python function tests pass.

## Decomposition Target

A future healthy shape may resemble:

```text
mlb_baseball/cli/
  __init__.py       # stable main facade
  parser.py         # top-level parser construction
  ingest.py         # ingest/bootstrap/update handlers
  database.py       # migrate/backup/restore/doctor/status
  research.py       # research/export/query surfaces
  model.py          # model/experiment commands while supported
  dispatch.py       # explicit routing/shared output helpers
```

This is guidance, not a required one-shot layout. Existing code/tests should determine the actual extraction boundaries.

## Child DOX Index

No child files while `cli.py` remains monolithic. When a real `cli/` package exists, add `cli/AGENTS.md` and move family-specific context into local sidecars/contracts; keep this file only if `cli.py` remains the compatibility facade.