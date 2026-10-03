## Why

The 06:00 pipeline takes about 2 h 7 min and almost all of it redoes unchanged work (issue #275). `mlb conform` truncates 23 core and gold tables and rebuilds them every night, which re-issues every internal team, player, venue and game id. Because no id survives a night, nothing downstream can be updated in place, and the whole gold layer must be emptied and refilled. Retrosheet also republishes old seasons (2026-08-09), so "only process new games" is not safe either: the rebuild must follow what changed in the inputs, not the calendar.

## What Changes

- **Measure first.** Per-step and per-season timings for `conform`, `report` and `predict` on production, recorded in this change, before any rewrite. `predict` (47 min) has not been looked at yet and is only measured here.
- **Stable internal ids.** `core.team`, `core.player`, `core.venue` and `core.game` stop being truncated. Each row keeps its id for life; `conform` matches incoming rows on their natural keys and updates in place (insert new, update changed). The core table is itself the key map.
- **Rebuild only changed seasons.** A small `meta` table records, per layer and season, a fingerprint of the raw inputs used. `conform` rebuilds the seasons whose fingerprint changed plus the current season; `core.play` and `core.pitch` (already partitioned by season) replace one season's partition at a time.
- **Match once.** The chain of five nightly heuristics that link Retrosheet games to MLB `game_pk` runs only for games that have no match yet, and records how each match was made.
- **Full rebuild stays.** `mlb conform --full` rebuilds everything from scratch. A test proves the incremental result equals the full result.
- **Simplify.** The 23-table `TRUNCATE`, the drop-and-recreate of bulk indexes, and the nightly rematching are removed from the default path once the equivalence test passes.
- **BREAKING (internal):** after the first stable run, `conform` no longer re-issues ids and no longer empties gold. `report` is changed to rebuild only the seasons `conform` reports as changed (see design D5).

## Capabilities

### New Capabilities
- `incremental-conform`: stable internal ids, season-level change detection, match-once game linking, and equivalence between incremental and full rebuilds.

### Modified Capabilities

(none; no existing requirement text changes)

## Impact

- Code: `mlb_baseball/conform.py` (largest change), `mlb_baseball/report.py`, `mlb_baseball/cli.py` (`conform --full`, status output), `scripts/mlb_daily_update.sh`.
- Database: new `meta` fingerprint table; unique natural-key constraints on `core.team` / `core.player` / `core.venue` if missing; a column recording how a game match was made. Numbered migrations.
- Everything that stores `core.*` ids (`gold.*`, `core.market`, `core.play`, `core.pitch`, predictions, features) benefits: ids stay valid. One-time cost: the first stable run is a full rebuild that fixes the id baseline.
- Verification relies on real PostgreSQL integration tests (project rule), not mocks.
