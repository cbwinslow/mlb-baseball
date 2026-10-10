# Proposal

## Why

`core.pitch` keeps 19 of the 121 data columns in `raw.statcast_pitch`, and `core.play` keeps 19 of the 168 in `raw.retrosheet_event` (and 22 in `raw.mlb_playbyplay`). Pitch location, movement, spin axis, release point, base state, fielders, handedness and run-expectancy deltas are all missing, so pitch-level, Markov and neural models cannot be built from `core`. The owner decided on 2026-10-10 that `core` carries every measured field at its finest grain (ADR-305; parent change `streamline-core-gold-direction`, task 6.2).

## What Changes

- Widen `core.pitch` to carry every measured `raw.statcast_pitch` column, typed (numeric/integer/date/text) instead of raw text, with `NULL` for blank values.
- Add Retrosheet event detail to `core` as a one-to-one detail table keyed to `core.play`, carrying every `raw.retrosheet_event` column except pure load metadata; add the few MLB play-by-play fields `core.play` lacks (event type, batting side, pitching hand, RBI, names stay in `raw`).
- Every widened row keeps a key back to its source row (`source_game_pk` + `at_bat_number` + `pitch_number` for pitches; `event_id` for Retrosheet plays) so `raw` stays reachable.
- A written reason is recorded for any raw column not carried (only load metadata and columns marked deprecated by the source; nothing else is dropped).
- Run-twice test, row-count and value parity against `raw`, and a roll-up tie-out for each widened table.
- Public exports keep explicit column lists so the new Statcast fields do not leak (ADR-304).

## Capabilities

### New Capabilities
- `core-event-detail`: what `core.pitch` and `core.play` (plus its Retrosheet detail table) must carry from their raw sources, how values are typed and nulled, how rows link back to `raw`, and the checks that prove nothing was lost.

### Modified Capabilities

None. Existing specs (`retrosheet-parsing`, `retrosheet-tie-out`) are unchanged in requirements.

## Impact

- Code: `mlb_baseball/conform.py` (`_build_pitches`, `_build_plays`), new named SQL files, a numbered migration, `conform.py.dox.md`.
- Data: `core.pitch` (13.6M rows) and `core.play` (about 16.8M rows) grow wider; `conform` runtime and table size rise (to be measured).
- Docs: `docs/TABLE_CONTRACTS.md`, `docs/DATA_DICTIONARY.md`, the parent change's `core-coverage.md`.
- Out of scope: new `core` tables for other groups, `gold` tables, linking pitches to plays, `raw.retrosheet_plays` (see design open question).
