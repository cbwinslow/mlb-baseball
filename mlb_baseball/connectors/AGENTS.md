# Source Connectors DOX

## Purpose

Own external-source acquisition adapters. Connectors land source-faithful raw data
and artifacts while preserving replayability, rights/profile gates, provenance,
idempotency, and source-specific error semantics.

This directory is a **file-documented DOX profile**: every direct source connector
`*.py` except `__init__.py` must have a same-directory sidecar named by appending
`.dox.md` to the full filename (for example `retrosheet.py.dox.md`).

## Ownership

Connectors own:

- remote/local source acquisition and parsing;
- `bootstrap` / `update` / source-specific backfill behavior;
- connector health checks;
- source artifact/download handling;
- raw/source-faithful table loads;
- run tracking and idempotency semantics at the acquisition boundary.

They do **not** own canonical cross-source identity, research statistic formulas,
model features, or public redistribution decisions beyond enforcing the source
profile/rights contract passed to them. Those belong to conformance, gold/stats,
modeling, and source-rights layers respectively.

## Local Contracts

### Common connector interface

Where the source supports it, preserve the registry-facing contract:

- `bootstrap(...)` — initial/full historical acquisition appropriate for the
  source;
- `update(...)` — bounded incremental/current refresh;
- `health_check() -> list[Check]` — actionable dependency/freshness/table/run
  health;
- explicit source-specific backfill/stage helpers only when needed.

Do not introduce a speculative plugin framework. The explicit connector registry
is preferred while the supported source set is known.

### Source-faithful raw data

- Preserve source-native identifiers and fields in `raw` whenever practical.
- Do not "clean" away source evidence to make conformance easier.
- Raw schema drift is observable and reviewed; it is not silently coerced into a
  different semantic field.
- Project-owned metadata such as season/scope/loaded-at/observed-at/checksum should
  have explicit semantics and strong types where the raw loader supports them.

### Replay and provenance

For landed artifacts/requests where applicable, preserve enough metadata to
answer:

- what source/URL/file produced these rows;
- when it was retrieved/observed;
- what season/date/scope was requested;
- checksum/schema/parser version when available;
- which data-rights profile allowed the acquisition.

Historical data should be replayable without relying on whatever the source
returns today whenever the connector stores source artifacts locally.

### Idempotency and incremental behavior

- Re-running the same bootstrap/update scope must not create duplicate canonical
  raw identities or corrupt prior scopes.
- Every connector must make snapshot-vs-append behavior explicit.
- Replacement scopes must be bounded precisely enough that one season/date refresh
  does not erase unrelated history.
- Incremental update should be cheap/bounded relative to bootstrap; do not turn a
  daily refresh into a silent full-history fetch.

### Network and external tool safety

- Use bounded retries/backoff for transient failures and rate limits.
- Respect `Retry-After`/source limits when available.
- Set connection/read timeouts; do not permit indefinite hangs.
- Validate archive paths/members/size before extraction where applicable.
- Partial failures must be visible and leave a safe retry path.
- Live remote calls are mocked/captured in automated tests; database behavior is
  tested against real PostgreSQL.
- Chadwick-backed Retrosheet connectors must verify required `cwevent`/`cwgame`/
  `cwbox` tooling and must not replace canonical Chadwick parsing with an
  unverified convenience parser.

### Rights and profiles

- Read `docs/SOURCE_RIGHTS.md` and `source_profiles.py` before broadening what a
  connector may ingest/export.
- `public_safe` is fail-closed and currently conservative; local availability does
  not imply redistribution permission.
- Do not scrape additional sportsbook/commercial sources simply to increase
  source count; require lawful/permitted access and a real research need.

### Third-party libraries

Established libraries may replace transport/parsing plumbing after a bounded
parity spike proves equal or better coverage, historical behavior, error handling,
provenance, performance, and tests. Keep our connector adapter as the project
contract so upstream SDK object models do not leak through the codebase.

## File-level DOX contract

Each `*.py.dox.md` sidecar owns durable knowledge for exactly one connector:

- Purpose and source/system;
- Owned raw tables/artifacts;
- Registry/public entry points;
- acquisition/bootstrap/update/backfill semantics;
- identifiers, scope, time/observed-at semantics;
- source rights/profile notes;
- important dependencies/external tools;
- downstream conformance/research consumers where known;
- known source quirks/failure modes;
- exact focused tests and health checks.

When a connector is added, removed, renamed, or behaviorally changed, update its
matching sidecar in the same change. Do not leave orphan sidecars after deletion
or rename.

Sidecars document contracts and non-obvious source knowledge; they must not paste
large chunks of source code or become a diary.

## Work Guidance

Before editing a connector:

1. read this file;
2. read the connector's `.dox.md`;
3. read `registry.py`, `source_profiles.py`, relevant source-rights/data-source
   docs, and the focused tests named by the sidecar as needed;
4. inspect the source module and neighboring connector patterns;
5. preserve unrelated source behavior and raw naming.

When a connector grows into a true subsystem (currently `mlb_api.py` is the main
example), prefer decomposing behind the stable connector facade rather than adding
more unrelated functions to one file.

## Verification

Every connector change should run its focused unit/integration tests and normally
verify:

- parse/normalization behavior;
- database load against real PostgreSQL;
- rerun/idempotency behavior;
- failure/run-tracking path;
- health check;
- rights/profile behavior when relevant.

Then run Ruff/mypy for touched Python. Do not claim live-source compatibility from
a mocked test alone if endpoint/schema behavior itself changed; perform a bounded
manual/source parity check when lawful and practical, recording what was checked.

## Child DOX Index

No connector child directories yet. `mlb_api.py` is a candidate for a future
`connectors/mlb/` child during decomposition; until then its file sidecar carries
the subsystem map.
