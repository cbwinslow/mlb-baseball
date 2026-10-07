## Why

PR #356 (ADR-296) added the operating protocol to root `AGENTS.md`, but left
gaps: `AGENTS.md`/`CLAUDE.md` grew and still overlap, about eight active
changes have no ADR, DOX sidecar freshness is unchecked, nested `AGENTS.md`
files do not mention the protocol, and the new `openspec/config.yaml` rules
were never confirmed to be applied by the OpenSpec CLI.

## What Changes

- Trim and de-duplicate root `AGENTS.md` and `CLAUDE.md` (one owner per fact, links not copies).
- Verify `openspec/config.yaml` `rules`/`operations` take effect via the CLI.
- Backfill ADRs in `docs/DECISIONS.md` for active changes that made real decisions without one.
- Audit the `*.dox.md` sidecars against their source; fix stale ones.
- Add a one-line protocol pointer to nested `AGENTS.md` files (`docs/`, `scripts/`, `tests/`, `transforms/`, `changelog/`).
- Record the findings and any rejected items in this change's design.

Documentation only; no code, SQL or data changes.

## Capabilities

### New Capabilities
<!-- none: docs-only (skip_specs) -->

### Modified Capabilities
<!-- none -->

## Impact

`AGENTS.md`, `CLAUDE.md`, `openspec/config.yaml`, `docs/DECISIONS.md`,
nested `AGENTS.md` files, stale `*.dox.md` sidecars. Out of scope: removing
Hugging Face publishing (separate change), branch-protection settings.
