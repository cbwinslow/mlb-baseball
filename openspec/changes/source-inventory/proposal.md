## Why

`data-completeness` proved the database can be checked against what sources offer, but only for the datasets we already knew about. Nothing tells us when a source adds an endpoint or a column, no step repairs the gaps the check finds, and the `mlb` commands are not laid out for an AI agent to do upkeep safely. The owner wants a database that detects, compares, repairs and stays correct on its own, without touching data it already holds.

## What Changes

- **Complete source inventory.** For each source (MLB Stats API, pybaseball, FanGraphs, Savant, Retrosheet, Lahman, Chadwick, Baseball-Reference, Kalshi, Polymarket) list every endpoint/file/table offered, its fields, first valid year, cost and the raw table that holds it or the recorded reason it does not. Lives in `docs/sources/<source>.md`; the MLB page is checked field by field, not only from the community OpenAPI file.
- **Schema snapshots and drift check.** A nightly, read-only step saves a small sample response (or file header) per offered dataset, compares field names and types with the last snapshot, and reports added, removed or changed fields and new files or endpoints. It never loads data.
- **Self-repair step (data-completeness 3.3).** A bounded nightly step reads the coverage gaps, runs only the repair commands marked safe (additive, resumable, rate-limited), caps work per night, and logs every action. Anything else is reported, not run.
- **Library and namespace review.** Audit the Python functions and `mlb` subcommands used for upkeep: one documented entry point per upkeep action, consistent flags (`--source`, `--mode`, `--dry-run`, `--season`), machine-readable output, tests for each.
- **Agent skill for upkeep.** A skill that tells an AI agent how to read the coverage and drift reports, choose a repair command, and ask the owner before any production write.
- **Evaluate, do not adopt blindly:** `dlt` (schema inference and evolution) and community baseball MCP servers. Nothing is installed or wired in without the owner's approval and a rights check.

## Capabilities

### New Capabilities
- `source-schema-drift`: snapshot each source's offered datasets and fields, detect additions, removals and changes, report them, and keep the source pages in step.
- `self-repair`: detect gaps from coverage, run a bounded set of safe repair commands automatically, and report the rest.
- `agent-upkeep`: a clear, tested command and function surface plus a skill that lets an AI agent do database upkeep safely.

### Modified Capabilities

(none; `source-refresh`, `source-ingestion` (in `full-source-ingestion`) and the coverage tool keep their own scope and are extended by tasks here, not by changing their requirements)

## Impact

- Code: `mlb_baseball/coverage/` (repair plan), a new `mlb_baseball/schema_watch/` or similar module, `cli.py` (`mlb schema-watch`, `mlb repair`), `nightly.py` (two steps), tests for each.
- Data: a small snapshot store under `downloads/schema_snapshots/` and a `meta` table for drift findings; no change to existing `raw.*` data.
- Docs: `docs/sources/*`, `docs/ARCHITECTURE.md`, a new ADR, `.claude/skills/` (upkeep skill), connector sidecars.
- Rights: probing endpoints stays within the existing `local_research` profile; no new or paid source. MCP servers and `dlt` need owner approval first.
- Relationship: closes `data-completeness` 3.3; absorbs `full-source-ingestion` 0.8, 0.13 and 1.1 (inventory and probes) instead of duplicating them.
