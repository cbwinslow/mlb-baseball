# cli.py DOX

## Purpose

Own the `mlb` command-line surface: argument parsing, user-facing command routing,
whole-pipeline orchestration, and formatting of command results.

This is a known gravity well with a very large parser/dispatch surface. Refactor it
mechanically behind stable command behavior; do not combine decomposition with a
large command redesign.

## Ownership

Source implementation: `cli.py`.

Key responsibilities include:

- parser/subparser construction;
- `mlb ingest <source>` and optional source-specific backfill routing;
- `mlb bootstrap` / `mlb update` multi-connector orchestration;
- migrate/conform/report/features/predict/train/doctor/audit/export and research/
  operational commands;
- numerous legacy Engine/display commands while those remain supported;
- source-profile enforcement at CLI boundaries;
- human-readable/JSON output selection for command families.

Primary unit regression surface includes `tests/unit/test_cli_dispatch.py` plus
feature/command-specific tests.

## CLI Compatibility Contract

A documented command is an external interface. Mechanical refactors must preserve:

- command/subcommand names;
- option names/defaults/types;
- argparse validation/error exit behavior;
- source-profile checks;
- return/output shape where documented or tested;
- existing supported aliases/deprecated behavior until intentionally removed.

Every new or changed subcommand needs a dispatch-level test through real
`cli.main([...])`/argparse. Testing only the underlying function is insufficient;
this repository has previously caught real missing-subparser-option bugs only at
the CLI layer.

## Connector Orchestration Contract

`mlb bootstrap`/`mlb update` run registered connectors with bounded outer
concurrency.

- `_SAME_SERVER_GROUPS` keeps connectors hitting the same upstream server
  sequential within a group.
- Different groups may run concurrently.
- The Retrosheet family stays serialized against `retrosheet.org` because a prior
  same-server threaded implementation hung in production.
- Statcast and Statcast leaderboards share Savant and are grouped accordingly.
- Unknown/new connectors default to their own singleton group until explicitly
  classified.
- One connector failure is reported but does not automatically abort unrelated
  source groups.

Do not increase concurrency or merge groups from intuition; verify actual upstream
hosts and measure behavior.

## Source Profile Contract

Commands that access source-backed data must honor `source_profiles.py` and
`require_sources()`. `local_research`, `public_safe`, and other profiles are not
cosmetic CLI flags; they enforce data-rights boundaries.

Do not add a bypass flag that makes restricted sources silently available to a
`public_safe` workflow.

## Backfill Contract

`--mode backfill` is optional and connector-specific. It is intentionally separate
from routine bootstrap/update because market-history backfills can be orders of
magnitude more expensive. Only dispatch it when the selected connector actually
implements the capability.

## Decomposition Direction

Preferred staged shape:

```text
mlb_baseball/cli/
  main.py
  parser.py
  commands/
    database.py
    ingestion.py
    research.py
    operations.py
    modeling.py
    engines.py
```

Exact filenames are not binding. Recommended sequence:

1. extract named handler functions without changing parser behavior;
2. introduce an explicit dispatch map/registry;
3. move coherent handlers into command modules;
4. only after parity, evaluate whether the large legacy Engine command surface
   should collapse behind a namespaced `mlb engine <name>` interface.

Keep a compatibility facade/import if callers/tests currently import
`mlb_baseball.cli.main` or other symbols from the old module.

## Output and Error Guidance

- User input/usage errors should use argparse/clear exit codes rather than Python
  tracebacks where practical.
- Operational/source failures should name the failing source/stage and remain
  actionable.
- Do not swallow a nonzero failure merely to keep pretty output.
- Keep structured JSON output stable for machine consumers when supported.

## Verification

At minimum for CLI changes:

```bash
uv run pytest tests/unit/test_cli_dispatch.py -q
uv run ruff check mlb_baseball/cli.py tests/unit/test_cli_dispatch.py
uv run mypy mlb_baseball/cli.py
```

Also run the focused underlying command tests. During decomposition, compare parser
help/dispatch behavior before and after and keep each extraction small enough to
review mechanically.
