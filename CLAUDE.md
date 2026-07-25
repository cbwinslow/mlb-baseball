# CLAUDE.md — Operating rules for this repo

This project was rebuilt from scratch after the original (Gemini-built) version accumulated bugs and inconsistent code quality. The rules below exist to prevent a repeat. Read [docs/NORTH_STAR.md](docs/NORTH_STAR.md) and [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) before making changes.

## Scope discipline

- We are in **Phase 1: data ingestion pipeline**. Do not start on ML modeling or the Astro website unless explicitly asked, even if it seems convenient to do "just a little" of it now.
- Don't add a data source that isn't listed in `docs/DATA_SOURCES.md`. If a new source is genuinely needed, add it to that doc (cost, access method, license note) in the same change.
- Assume $0/month budget. No paid API, database, or hosting dependency without asking first.

## Definition of done

A task is not complete until:
1. Tests exist and pass for the new/changed code (unit tests for parsing/transform logic; integration test hitting a real or fixtured API response for connectors).
2. The linter/formatter/type-checker configured for the repo passes clean.
3. Re-running the ingestion step is idempotent — running it twice doesn't duplicate or corrupt data.
4. Errors from upstream sources (rate limits, malformed responses, schema drift) are handled explicitly, not silently swallowed.
5. Any new data source or schema change is reflected in the docs in the same change, not as a follow-up.

## Code quality

- No dead code, no commented-out blocks, no TODOs left behind as a substitute for finishing the work.
- No silent `except: pass` — failures in ingestion must be visible (logged with enough context to debug, and surfaced as a non-zero exit / failed run).
- Prefer explicit, boring code over cleverness. This is a data pipeline; predictability matters more than elegance.
- Don't build abstractions for sources we don't have yet. Three similar connectors is fine; a plugin framework for a hypothetical fourth is not, until there's a fourth.

## Before declaring a task finished

Run the actual test suite and linter — don't assert success without having run them in this session.
