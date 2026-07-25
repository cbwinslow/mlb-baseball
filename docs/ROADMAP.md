# Roadmap

Only Phase 1 is broken into concrete steps right now — Phases 2 and 3 get planned when Phase 1 is actually done (see [NORTH_STAR.md](NORTH_STAR.md)).

## Phase 1 — Data ingestion pipeline

Rough build order, each step re-runnable and tested before moving to the next:

1. ✅ **Project scaffolding** — repo layout, `.env.example`, dependency management, DB connection helper, migration tooling for the raw/conformed schemas.
2. ✅ **Chadwick Bureau Register connector** — the ID crosswalk. Built first because every other source gets joined against it.
3. ✅ **Lahman connector** — season-level historical stats. Current data requires a manual download (see `docs/DATA_SOURCES.md`); network fallback frozen at 2021.
4. ✅ **Retrosheet connectors** (three) — play-by-play plus per-game/per-player stats via retrosheet.org's own pre-parsed CSV downloads (`retrosheet`, see `docs/DECISIONS.md` ADR-004); classic game logs extending coverage back to 1871 (`retrosheet_gamelog`); ballpark/team-ID/biographical reference files (`retrosheet_reference`). Pre-1898 raw event data and Negro Leagues data explicitly deferred, not forgotten.
5. **MLB Stats API connector** — schedules, boxscores, live game state.
6. **Statcast (Baseball Savant) connector** — pitch-level data. Highest volume, needs chunked/paginated pulls.
7. **Conformed layer** — dimensions/facts built on top of the raw tables from steps 2–6, joined via the Chadwick crosswalk.
8. **Polymarket connector** (stretch) — prediction-market probabilities.
9. **Kalshi connector** (stretch) — prediction-market probabilities.

Phase 1 is done when: all core connectors (2–6) run cleanly end-to-end, are idempotent, have tests, and land in the conformed layer — not just "the raw pull works."

## Phase 2 — ML modeling workflows

Not planned yet.

## Phase 3 — Astro website (oddstrader-style)

Not planned yet.
