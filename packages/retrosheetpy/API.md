# Public API

The Chadwick port lives in `retrosheetpy.cw` (modules mirror the C files; the six tools are also console
scripts). The four areas below are the older, non-port surface and are unchanged.

Only four areas are public. Everything else is internal and may change.

1. **Source acquisition** — `Artifact` (source URL, product, season/group, local
   path, SHA-256, size, retrieved time) plus a client that resolves official
   Retrosheet URLs, downloads safely into a cache, and iterates zip members.
2. **Record iteration** — a streaming reader yielding typed records
   (id, info, start, sub, play, data, comment, adjustment). Each carries source
   file, line number, game id when known, and exact raw text.
3. **Play parsing** — parses a play description into primary event, modifiers,
   runner advances, fielding credits, and raw/unknown parts. No game state.
4. **Structured errors** — `ParseError` with parser stage, file, line, raw text.
   Strict mode raises; diagnostic mode returns visible unsupported nodes.

Game-state iteration and Chadwick-compatible output are provided by `retrosheetpy.cw`. Dataframe
adapters are not in scope.
