# Roadmap

Only Phase 1 is broken into concrete steps right now — Phases 2 and 3 get planned when Phase 1 is actually done (see [NORTH_STAR.md](NORTH_STAR.md)).

## Phase 1 — Data ingestion pipeline

Rough build order, each step re-runnable and tested before moving to the next:

1. ✅ **Project scaffolding** — repo layout, `.env.example`, dependency management, DB connection helper, migration tooling for the raw/core/gold schemas.
2. ✅ **Chadwick Bureau Register connector** — the ID crosswalk. Built first because every other source gets joined against it.
3. ✅ **Lahman connector** — season-level historical stats. Current data requires a manual download (see `docs/DATA_SOURCES.md`); network fallback frozen at 2021.
4. ✅ **Retrosheet connectors** (eight — see `docs/DATA_SOURCES.md`) — pre-parsed CSV product (`retrosheet`, ADR-004); raw play-by-play event files via `cwevent`/`cwgame`, 1910–2025 plus post-season/all-star/Negro League (`retrosheet_event`, ADR-009/ADR-010); box-score-only games via `cwbox` for everything raw event files don't cover — 1871/1872/1874 NA seasons, 1898–1909, and additional Negro League games (`retrosheet_box`, ADR-012); classic game logs back to 1871 plus postseason logs (`retrosheet_gamelog`); ballpark/team/biographical reference data (`retrosheet_reference`); annual rosters (`retrosheet_roster`); planned schedules (`retrosheet_schedule`); the (frozen) transaction database (`retrosheet_transaction`). Reconciled against the CSV product end to end: 98.3% of all games have raw-file coverage; the remainder is a genuine gap in what Retrosheet has published as a standalone download, not a parsing limitation — see ADR-012.
5. ✅ **Reusable ingestion infrastructure** — disk-persisted downloads with a per-source JSON manifest so a bootstrap is resumable without re-fetching (`mlb_baseball/manifest.py`, ADR-008); `mlb doctor` hardened to report cleanly (not crash) on a database that's never been migrated, plus checks for the `downloads/` directory and the Chadwick CLI tools (ADR-011); `mlb_baseball/load.py`'s loader now tolerates a later batch having columns an earlier one didn't, rather than failing on COPY.
6. ✅ **MLB Stats API connector** (`mlb_api`, ADR-015/016/017/018) — full-history schedule (1901–present), standings (1969–present), rosters (1901–present), transactions (2000–present, fills the real gap left by `retrosheet_transaction`'s Nov 2021 freeze), venues (~1,667, full catalog), team configuration history, player bios, and amateur draft picks (1965–present); play-by-play/box-scores/umpire-assignments/win-probability from 2026 on (exactly where Retrosheet's own most recent published season stops, verified play-for-play equivalent on a real shared game first); append-only live-game-state capture (`raw.mlb_live_game`). Scheduled via cron every 5 minutes (`scripts/mlb_api_update.sh`, ADR-016) so live/current-season data actually stays fresh, not just updated on manual runs. Deliberately not built: `person_stats` (redundant with box scores) and per-game umpire lookup via `jobs_umpire_games`/`jobs_officialScorers` (wrong endpoint shape — see ADR-018).
7. ✅ **Statcast connector** (`statcast`, ADR-017) — pitch-level tracking data via `pybaseball.statcast()`, full history from 2008 (PITCHf/x era; full Statcast fidelity from 2015). Confirmed a strict superset of MLB API's own pitch data (119 columns vs. ~20), so all pitch-level tracking lives here exclusively. Weekly date-range batching, ~2.6s/day confirmed. Full 2008–present history bootstrapped against production (13.4M+ rows), zero known gaps.
8. ✅ **Core layer** — dimensions and facts built on top of the raw tables, joined via the Chadwick crosswalk (`mlb_baseball/conform.py`, `mlb conform`, ADR-013). `core.player`/`core.team`/`core.game` (dimensions, real PK/FK/indices) and `core.play`/`core.pitch` (facts, unifying Retrosheet+MLB API plays and Statcast pitches respectively) all built and verified against production.
8b. ✅ **Statcast leaderboards + Baseball-Reference connectors** (`statcast_leaderboard`, `bref`, ADR-018) — 8 Savant tracking leaderboards not derivable from pitch-level data (sprint speed, catcher pop time/framing, outfielder jump/catch-probability/directional-OAA, outs-above-average, baserunning splits), plus Baseball-Reference season batting/pitching stats. FanGraphs itself confirmed blocked (Cloudflare 403) — not built; see `docs/DATA_SOURCES.md` Deferred section.
8c. ✅ **Unified bootstrap/update** — `mlb bootstrap`/`mlb update` run every registered connector in one command, iterating `registry.CONNECTORS` (the same list `mlb doctor` uses), logging and continuing past any single connector's failure.
9. **Polymarket connector** (stretch) — prediction-market probabilities.
10. **Kalshi connector** (stretch) — prediction-market probabilities.

Phase 1's core ingestion pipeline (steps 2–8c) is done: every connector runs cleanly end-to-end, is idempotent, has tests, and (where it has a natural join target) lands in the core layer. Remaining Phase 1 work is the stretch prediction-market connectors (9–10), not core baseball data.

## Phase 2 — ML modeling workflows

Not planned yet.

## Phase 3 — Astro website (oddstrader-style)

Not planned yet.
