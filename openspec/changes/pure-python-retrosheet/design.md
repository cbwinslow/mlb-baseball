## Context

mlb-baseball currently has two complementary Retrosheet paths:

1. The official parsed yearly CSV product is downloaded and read directly in
   Python. This path needs no Chadwick tool.
2. The original event and box-score archives are retained as independent source
   products. They are currently parsed through system cwevent, cwgame, and cwbox
   binaries.

The second path is valuable for provenance, independent reconstruction, older
box-score-only coverage, and cross-validation. Removing it would make the
project simpler but weaker as a research system. The design therefore removes
the native installation dependency without removing the raw source path.

## Goals / Non-Goals

Goals:

- A standalone package with no dependency on mlb_baseball or PostgreSQL.
- A Python-only core install: no compiler, CMake, autotools, or native Chadwick.
- Lossless parsing: every parsed object retains the raw source representation.
- Streaming operation over files and archives.
- Clean separation between syntax, game-state reduction, and output schemas.
- Explicit compatibility profiles, starting with Chadwick 0.10.0.
- Differential verification before any production connector replacement.

Non-goals for this slice:

- Replacing cwevent/cwgame/cwbox in production.
- Implementing cwbox parity.
- Reproducing every Chadwick CLI flag.
- Rewriting the existing official parsed-CSV connector.
- Adding PostgreSQL or warehouse concepts to the standalone package.
- Correcting Retrosheet source records silently.

## Decisions

### D1 — Standalone dependency direction

The new package sits below mlb-baseball:

Retrosheet package -> no mlb-baseball dependency
mlb-baseball -> may depend on the Retrosheet package later

The core package uses standard-library models and iterators. DataFrame libraries
are adapters, not parser dependencies.

Rationale: the useful public artifact is a reusable Retrosheet library. A
warehouse-specific parser would recreate the coupling this work is intended to
remove.

### D2 — Separate acquisition, syntax, state, and compatibility

The intended package shape is:

- client: official URL/catalog, download, cache, artifact metadata;
- records: id/info/start/sub/play/data/comment/adjustment record framing;
- play: play-description lexer/parser and typed event representation;
- state: game state plus deterministic reducer;
- compat: Chadwick-versioned schemas and emitters;
- adapters: optional pandas/Arrow/Polars conversion.

A parsed play does not mutate a game. The reducer consumes a parsed play and a
game state and produces the next state plus derived facts.

Rationale: existing Python attempts tend to mix regex recognition, baseball
semantics, and statistic accumulation. Separating these layers makes failures
testable and lets users consume the syntax parser without accepting a particular
derived-stat interpretation.

### D3 — Retrosheet specification is the contract; Chadwick is an oracle

Implementation behavior comes from Retrosheet's published file and event
documentation. Chadwick source code is not copied or transliterated.

Chadwick 0.10.0 is executed in differential tests to reveal disagreements.
Retrosheet's official parsed CSVs and its Chadwick crosswalk provide a second
independent comparison.

If all three disagree, the package reports the discrepancy and preserves the
source record; it does not silently choose whichever value makes a test green.

Rationale: this gives strong correctness evidence without making the Python
architecture a disguised C port or inheriting implementation details that do
not belong in the public API.

### D4 — Compatibility is versioned

The first explicit compatibility profile is chadwick-0.10.

The native Python model is not named after Chadwick fields. A compatibility
emitter maps the native model to the field set expected by that profile.

A future Chadwick 0.11 profile can differ where upstream behavior changed.

Rationale: this project has already encountered changing cwevent field ranges.
Versioning makes that dependency visible instead of encoding it in magic
constants.

### D5 — Strict parsing is the correctness default

Every parsed node stores its raw text.

Strict mode raises a structured ParseError containing file, game, line number,
record type, raw value, and parser stage.

A diagnostic/tolerant mode may return Unknown or Unsupported nodes, but these
remain visible to callers and are counted. It never drops an unsupported event.

Rationale: research ingestion must distinguish "unknown to the parser" from
"did not happen."

### D6 — Acquisition stays narrow and provenance-aware

The source client owns only Retrosheet concerns:

- canonical official resource URLs;
- archive/member discovery where the layout is deterministic;
- safe zip extraction;
- local cache policy;
- SHA-256;
- retrieval timestamp;
- source URL and local path.

It does not own the mlb-baseball manifest or database. mlb-baseball can consume
the returned artifact metadata and record it in its existing manifest later.

Fungo is prior art for API ergonomics, but the standalone package does not take
a broad fungo dependency solely for a small Retrosheet client.

### D7 — First implementation slice stops before production replacement

This change implements:

- package scaffold and install smoke test;
- source/catalog and artifact model;
- lossless raw record framing;
- typed play syntax representation;
- fixtures and a differential-harness shell that can invoke Chadwick when
  available;
- documentation of unsupported syntax and parse coverage.

It does not implement the full state reducer or switch a connector.

Follow-up slice B implements the state reducer plus cwevent/cwgame compatible
emitters and drives parity over representative eras and then full history.

Follow-up slice C addresses cwbox and only then evaluates removing Chadwick as a
user-visible dependency from mlb-baseball.

### D8 — Licensing and attribution are explicit

Code created in this repository follows the repository's AGPL-3.0-or-later
license unless a later owner decision changes the standalone package license.

No Chadwick GPL source is copied into the implementation.

Retrosheet attribution and data-use requirements are documented in the package
README and source-client documentation.

## Validation strategy

The package is tested at five levels:

1. Unit examples from Retrosheet's published syntax documentation.
2. Property/invariant tests for bases, outs, runner movement, and round-trip raw
   preservation.
3. Captured real-game fixtures from materially different eras.
4. Differential output against Chadwick 0.10.0 for supported compatibility
   fields.
5. Cross-check against Retrosheet's official parsed plays via its published
   field crosswalk.

A connector may not switch to the Python backend merely because unit tests pass.
The replacement decision requires a recorded parity report covering field-level
mismatch counts and all unsupported event syntax.

## Risks / Trade-offs

- Full Chadwick parity is larger than the syntax parser. The state reducer is the
  hard part. This is why production replacement is a later gate.
- Historical records contain rare encodings and source errors. Lossless unknown
  nodes and corpus-wide parse coverage keep those visible.
- A pure-Python parser may initially be slower than C. Streaming is mandatory;
  optimization follows measurement rather than pre-emptive complexity.
- Package naming on PyPI must be checked before implementation. Existing
  pyretrosheet means that name is not available to this project.

## Roadmap

Slice A — this change: standalone foundation, client, typed/lossless syntax,
fixtures, and differential harness.

Slice B — state engine plus chadwick-0.10 cwevent/cwgame compatibility; parity
report; optional non-default backend in mlb-baseball.

Slice C — cwbox/box-score-only support, full connector parity, and a separate
decision on making Python the default and removing system Chadwick from the
normal install path.