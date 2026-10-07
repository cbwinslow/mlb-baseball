# Namespace and library review (task 4.1)

Upkeep-related `mlb` commands as of 2026-10-07 (full generated list: `docs/COMMANDS.md`). "JSON" and "dry run" mean the command offers `--json` or a way to preview without writing.

| Command | Read-only? | JSON | Dry run | Tests | Gap and action |
|---|---|---|---|---|---|
| `coverage` | yes | yes | n/a | yes | none |
| `source-check` | yes | no | n/a | yes | JSON not needed yet; exit codes carry the verdict |
| `schema-watch` (new) | writes snapshots and `meta.schema_finding` | yes | n/a | yes | none |
| `repair` (new) | dry run default | yes | yes | yes | none |
| `ingest` | no | added | added | yes (`test_cli_upkeep_surface.py`) | had neither; both added in 4.2 |
| `bootstrap`, `update` | no | no | no | yes | run many sources; use `preflight` to preview; add `--dry-run` only if an agent needs it |
| `doctor` | yes | added | n/a | yes | JSON added in 4.2 |
| `preflight` | yes | no | is itself the preview | yes | JSON would help agents; not added (no consumer yet) |
| `status`, `runs`, `metrics`, `audit`, `field-census`, `inventory`, `schema` | yes | no | n/a | partly | text output only; add JSON when a skill needs the value |
| `migrate`, `conform`, `report`, `nightly`, `repair-runs`, `odds-capture`, `backfill-game-identities` | no | no | no | yes | scheduled jobs; not agent entry points |
| `backup`, `restore` | backup reads; restore is destructive | no | no | yes | `restore` already needs `--yes` |

Decisions: add only what the upkeep skill needs now (`ingest --dry-run/--json`, `doctor --json`); everything else stays as is so old invocations keep working. `--source` is not uniform (`ingest` takes it positionally); changing that would break cron lines, so it is documented, not changed.
