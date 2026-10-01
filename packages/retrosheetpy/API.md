# Public API (planned, first stable surface)

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

Not in scope for this slice: game-state reduction, Chadwick-compatible output
tables, dataframe adapters.
