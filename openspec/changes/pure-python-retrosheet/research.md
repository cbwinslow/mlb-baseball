# Retrosheet / Chadwick ecosystem review

Reviewed 2026-09-23. This file records the evidence behind the design so the
implementation does not rediscover the same options.

## Chadwick

Repository: https://github.com/chadwickbureau/chadwick

Chadwick is the mature reference implementation. The repository is active in
2026 and is written in C under GPL-2.0. The current released behavior relevant
to this project is 0.10.0. Its master ChangeLog already contains a 0.11.0
section with behavior changes, including automatic-runner handling and new or
corrected event/game fields.

Implication: compatibility must be versioned. "Matches Chadwick" is too vague;
the first reference profile is chadwick-0.10.

The implementation is split roughly into:

- cwlib/parse.c: event syntax interpretation;
- cwlib/game.c: game records;
- cwlib/gameiter.c: evolving game state;
- cwlib/box.c: box-score/stat accumulation;
- cwtools/cwevent.c, cwgame.c, cwbox.c: output schemas and CLI behavior.

These are useful for understanding observable behavior, but this project will
not transliterate or copy the GPL implementation into a new parser. Retrosheet's
published format documentation defines the source contract; Chadwick is used as
a behavioral oracle in tests.

## pychadwick

Repository: https://github.com/bdilday/pychadwick
PyPI: https://pypi.org/project/pychadwick/

pychadwick is not a pure-Python Chadwick port. Its setup requires
scikit-build, ninja, and CMake. Its CMake build vendors Chadwick C sources into a
shared cwevent library, and the Python API calls that library through ctypes.
The package is version 0.6.1 and its bundled CMake metadata identifies the
embedded Chadwick line as 0.7.X.

Useful lesson: its Python-facing field/schema mapping is prior art for a
compatibility adapter. It is not an installation solution for a Python-only
package.

## pyretrosheet

Repository: https://github.com/rozelie/pyretrosheet
PyPI: https://pypi.org/project/pyretrosheet/

MIT-licensed Python implementation with typed Game, Play, event, advance, and
modifier objects. It is useful architectural prior art. Its README describes the
project as not feature complete. The parser includes hard-coded corrections for
individual source records and comments marking several encodings as unclear.

Useful lesson: keep the typed model, but separate syntax parsing, source quirks,
and state reduction more strongly. Unknown syntax must stay observable instead
of being silently ignored.

## calestini/retrosheet

Repository: https://github.com/calestini/retrosheet

MIT-licensed pure-Python parsing work with substantial event/game logic. The
repository has not seen implementation pushes since 2020 and documents itself
as work in progress with incomplete validation.

Useful lesson: there is genuine historical demand for this problem and useful
edge-case prior art, but it is not a maintained dependency to adopt.

## fungo

Repository: https://github.com/hedgertronic/fungo
PyPI: https://pypi.org/project/fungo/

Current MIT-licensed Python package. Its retrosheet namespace provides a clean
static-file client and cache for official game logs, parsed plays, schedules,
bio data, and yearly CSV bundles. It does not implement the raw event state
machine.

Useful lesson: follow the small source-client ergonomics, but do not make the
new standalone Retrosheet package depend on the entire fungo package. The new
package should remain narrow and should expose artifact metadata needed by
mlb-baseball's stronger provenance manifest.

## Official Retrosheet surfaces

Primary site: https://www.retrosheet.org/

Retrosheet publishes:

- original event/box/game-log archives;
- official parsed yearly CSV products;
- documentation for event records and play syntax;
- a parsed-play / Chadwick field crosswalk.

Retrosheet's data-use notice permits use of its data, including commercial use,
with required attribution. The package must preserve and document that
attribution requirement; it must not imply that Retrosheet endorses the
package.

## Decision

Adopt no existing parser as the runtime implementation.

Reuse ideas, specs, and observable behavior:

- Retrosheet documentation is the source-format authority.
- Chadwick 0.10.0 is the first differential behavior oracle.
- Retrosheet parsed CSVs are an independent second oracle.
- fungo informs acquisition ergonomics.
- pyretrosheet and calestini/retrosheet inform typed event-model design and
  edge-case test discovery.

The new package is implemented independently in Python and stays independent of
mlb-baseball.
