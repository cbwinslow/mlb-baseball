# Roadmap

Only Phase 1 is broken into concrete steps right now — Phases 2 and 3 get planned when Phase 1 is actually done (see [NORTH_STAR.md](NORTH_STAR.md)).

## Phase 1 — Data ingestion pipeline

Rough build order, each step re-runnable and tested before moving to the next:

1. ✅ **Project scaffolding** — repo layout, `.env.example`, dependency management, DB connection helper, migration tooling for the raw/core/gold schemas.
2. ✅ **Chadwick Bureau Register connector** — the ID crosswalk. Built first because every other source gets joined against it.
3. ✅ **Lahman connector** — season-level historical stats. Current data requires a manual download (see `docs/DATA_SOURCES.md`); network fallback frozen at 2021.
4. ✅ **Retrosheet connectors** (eight — see `docs/DATA_SOURCES.md`) — pre-parsed CSV product (`retrosheet`, ADR-004); raw play-by-play event files via `cwevent`/`cwgame`, 1910–2025 plus post-season/all-star/Negro League (`retrosheet_event`, ADR-009/ADR-010); box-score-only games via `cwbox` for everything raw event files don't cover — 1871/1872/1874 NA seasons, 1898–1909, and additional Negro League games (`retrosheet_box`, ADR-012); classic game logs back to 1871 plus postseason logs (`retrosheet_gamelog`); ballpark/team/biographical reference data (`retrosheet_reference`); annual rosters (`retrosheet_roster`); planned schedules (`retrosheet_schedule`); the (frozen) transaction database (`retrosheet_transaction`). Reconciled against the CSV product end to end: 98.3% of all games have raw-file coverage; the remainder is a genuine gap in what Retrosheet has published as a standalone download, not a parsing limitation — see ADR-012.
5. ✅ **Reusable ingestion infrastructure** — disk-persisted downloads with a per-source JSON manifest so a bootstrap is resumable without re-fetching (`mlb_baseball/manifest.py`, ADR-008); `mlb doctor` hardened to report cleanly (not crash) on a database that's never been migrated, plus checks for the `downloads/` directory and the Chadwick CLI tools (ADR-011); `mlb_baseball/load.py`'s loader now tolerates a later batch having columns an earlier one didn't, rather than failing on COPY.
6. 🟡 **MLB Stats API connector** (`mlb_api`, ADR-015, supersedes ADR-014) — full-history schedule (1901–present) and standings (1969–present) done, via the `statsapi` package, plus append-only live-game-state capture (`raw.mlb_live_game`) for whatever's currently in progress — the piece that actually supports real-time odds later. Not done: boxscores, rosters (deferred to their own connector, same pattern as `retrosheet_box`); actually running `update()` on a repeating schedule so live capture is continuous, not just "whenever someone runs it by hand" (still the open scheduling/cron decision).
7. **Statcast (Baseball Savant) connector** — pitch-level data. Highest volume, needs chunked/paginated pulls.
8. 🟡 **Core layer** — dimensions built on top of the raw tables from steps 2–7, joined via the Chadwick crosswalk (`mlb_baseball/conform.py`, `mlb conform`, ADR-013). `core.player`/`core.team`/`core.game` done — real PK/FK/indices, verified against production (152 teams, 25,543 players, 224,877 games) and re-tied against the Don Larsen 1956 perfect game through the new tables. Not done: fact-level tables (play-by-play, per-game batting/pitching/fielding) — still raw-only, to be added once steps 6–7 (MLB Stats API, Statcast) land and there's a real join target for them.
9. **Polymarket connector** (stretch) — prediction-market probabilities.
10. **Kalshi connector** (stretch) — prediction-market probabilities.

Phase 1 is done when: all core connectors (2–7) run cleanly end-to-end, are idempotent, have tests, and land in the core layer — not just "the raw pull works." Dimension tables (step 8) are done; fact tables are the remaining piece.

## Phase 2 — ML modeling workflows

Not planned yet.

## Phase 3 — Astro website (oddstrader-style)

Not planned yet.
