# Grain backbone relations 3–6, and what comes after

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:executing-plans`
> (or `superpowers:subagent-driven-development`). Steps use `- [ ]` for
> tracking. Read `docs/superpowers/plans/2026-09-01-grain-backbone-plan.md`
> and its spec first.

**Goal:** Finish the grain-complete statistic backbone (Plan 03B, ADR-278) —
land relations 3–6, add the real Baseball-Reference tie-outs, then open
Stage 2 — while the four in-flight PRs get merged in order.

**Architecture:** unchanged. PostgreSQL + `mlb` CLI. Each backbone relation
is a named `mlb_baseball/sql/*_build.sql` + a migration, built by
`mlb report` via `report._build_backbone_relation`, checked by `mlb doctor`,
registered in `mlb_baseball/export.py` as `local_research`. Season/team/
career roll-ups read the relation one grain below them, never `raw`.

**Tech stack:** PostgreSQL 16 (`mlb` prod / `mlb_test` tests), Python 3.12,
`uv`, `pytest` integration tests against `mlb_test`.

**Spec:** `docs/superpowers/specs/2026-09-01-grain-complete-stat-backbone-design.md`,
ADR-278 (with the relation 3 / 4 / 5 addenda), `plans/03-research-statistics-and-features.md` §03B.

## Global constraints

- Production DB is `mlb`, test DB is `mlb_test`. Name the target before any
  destructive command. All this work is `mlb_test` only.
- No SB/CS anywhere in the batting roll-ups until `gold.baserunning_game`
  exists (steals are not in `gold.batting_game`).
- No ERA in the pitching roll-ups — `gold.pitching_game` has no earned runs.
  `ra9` is the honest rate; ERA stays in `gold.player_season` (BRef).
- Backbone relations are `local_research`, not `public_safe` — they join
  conformed `core` dims. A `public_safe` retro-id-keyed variant is a
  separate future issue, not this work.
- `ruff` / `ruff format` / `mypy` / `sqlfluff` clean before every commit.
- **Do not run two `pytest` sessions against `mlb_test` at once** — they
  contend on the shared server + template-DB locks and both crawl.

---

## State as of 2026-09-01 (end of session)

### In-flight PRs — a linear stack into `main`

| PR | Branch | Base | Contents | CI | Merge state |
|----|--------|------|----------|----|-----|
| #126 | `feat/gold-pitching-game` | `main` | S1 relations 1–2 (spec, ADR-278, `batting_game`, `pitching_game`) + all review fixes | all green | **BLOCKED** — see below |
| #129 | `feat/gold-batting-season` | #126's branch | relation 3 (`batting_season` / `batting_team`) | no CI (base ≠ main) | needs #126 first |
| #130 | `feat/gold-pitching-season` | #129's branch | relation 4 (`pitching_season` / `pitching_team`) | no CI (base ≠ main) | needs #129 first |
| #131 | `feat/gold-career` | #130's branch | relation 5 (`batting_career` / `pitching_career`) + this plan doc | no CI (base ≠ main) | needs #130 first |
| #117 | `fix/issue-115-season-validation` | `main` | season-arg validation (independent) | all green | **BLOCKED** — see below |
| #75 | dependabot `setup-uv` 7.6.0→10.0.1 | `main` | action bump | last run green | BEHIND main — needs rebase |
| #127 / #128 | owner docs | `main` | deep-review notes / Sept consolidation | — | owner's call; #128 CHANGES_REQUESTED |

### Why #126 and #117 are BLOCKED

`main` branch protection has **"Require conversation resolution"** ON and
`dismiss_stale_reviews` ON, but `required_approving_review_count` = 0 and
`enforce_admins` = **false**. Both PRs carry a stale CodeRabbit
`CHANGES_REQUESTED` review whose findings were all addressed in later
commits and answered in comments — CodeRabbit is rate-limited and has not
re-reviewed to clear it. So `mergeStateStatus` = `BLOCKED`.

To merge, one of:
1. Owner clicks "Resolve conversation" on the CodeRabbit threads + dismisses
   the stale review, then squash-merges (only squash is enabled).
2. Owner uses admin override (`enforce_admins` is off): the GitHub UI
   "Merge without waiting for requirements" / `gh pr merge --admin`.
3. `@coderabbitai review` eventually clears it if the bot re-runs.

The Claude Code auto-mode classifier **blocks `gh pr merge` from this
session** — the owner (or a session with a Bash allow-rule for `gh pr
merge`) must do the merges.

### Merge order once unblocked

```
1. Merge #117            (independent)
2. Merge #126            (squash -> main)
3. git fetch; rebase feat/gold-batting-season onto main; force-push;
   retarget #129 -> main via `gh api -X PATCH .../pulls/129 -f base=main`;
   merge #129
4. same for #130 (rebase onto main, retarget, merge)
5. push feat/gold-career, open PR -> main, merge (relation 5)
6. #75: `@dependabot rebase` or rebase locally, then merge
```

`gh pr edit --base` currently 500s on a projects-classic GraphQL bug — use
`gh api -X PATCH repos/cbwinslow/mlb-baseball/pulls/NNN -f base=main`.

---

## Task 1 — land relations 3–5 (mostly done; finish WS-3c)

**Files:** `migrations/0096`–`0098`, `mlb_baseball/sql/*_{season,team,career}_build.sql`,
`mlb_baseball/report.py`, `mlb_baseball/export.py`,
`tests/integration/test_report_{batting,pitching}_season.py`,
`tests/integration/test_report_career.py`, docs.

- [x] Relation 3 — `gold.batting_season` / `gold.batting_team` (#129)
- [x] Relation 4 — `gold.pitching_season` / `gold.pitching_team` (#130)
- [x] Relation 5 — `gold.batting_career` / `gold.pitching_career` (#131)
- [x] **conform FK fix (each PR):** every new backbone relation FKs
  `core.player` / `core.team`, so `conform.run()`'s consolidated one-shot
  `TRUNCATE` (which must name the full FK closure or Postgres refuses to
  truncate `core.*` at all) needs the new tables added — #129 adds
  `batting_season`/`_team`, #130 adds `pitching_season`/`_team`, #131 adds
  `batting_career`/`pitching_career`. Same regression class as the
  `batting_game`/`pitching_game` fix in #126. `test_conform.py`'s
  `_reset_dynamic_tables` DELETE list and the
  `test_rerunning_does_not_crash_when_a_backbone_relation_references_core`
  regression test grow with each. **Any future backbone relation that FKs
  `core` must do the same.**
- [x] **Step 1:** push `feat/gold-career`, open PR (#131) into `feat/gold-pitching-season`.
- [ ] **Step 2:** after the stack merges, rebase every branch onto `main`
  in order (see "Merge order").
- [ ] **Step 3:** one clean `pytest -q` of the whole integration suite on
  `main` after the last merge (~1 h — CI covers it too).

### Design decisions already applied (don't re-litigate)

- **D1** — `gold.batting_season` / `gold.pitching_season` carry a stint row
  per `(player, season, team)` plus one `is_combined` full-season row per
  `(player, season)` (`team_id` NULL). One-team player's combined row == the
  stint. `CHECK (is_combined = (team_id IS NULL))` + a partial unique index.
- **D2** — no SB/CS/SB%.
- **D4** — `source` column kept (default `retrosheet_event`).
- Rate stats computed at each grain from summed components, NULL on a zero
  denominator. Batting: AVG/OBP/SLG/OPS/ISO(=(TB−H)/AB)/BABIP/BB%/K%.
  Pitching: RA9/WHIP/K9/BB9/HR9 (= component × 27 / outs), K:BB (= SO/BB,
  NULL on zero BB).
- Career = sum of a player's per-season `is_combined` rows + `seasons` /
  `first_season` / `last_season`; rates recomputed from career totals.
- The career builders take **no** `%(season)s` bind;
  `_build_backbone_relation` only passes params when the SQL contains the
  bind.

---

## Task 2 — real Baseball-Reference tie-outs (the plan's blocking gate for 3+)

**Files:** `tests/integration/fixtures/` (new — trimmed real event extracts),
`tests/integration/test_tieout_*.py`.

The plan's tie-out contract:
> counting stats match exactly or the delta is understood and documented
> (e.g. a known BRef correction); rate stats (AVG/OBP/SLG) match within a
> few thousandths. A documented, understood delta is a pass — any delta
> must be traced to a specific, named cause before the test passes with
> tolerance. An unexplained delta blocks the relation.

- [ ] **Step 1:** pick reference seasons — **2023 Aaron Judge** (batting)
  and **2023 Gerrit Cole** (pitching). Both modern (post-1988), so
  batted-ball / scoring gaps are minimal.
- [ ] **Step 2:** build a fixture: the full `raw.retrosheet_event` rows for
  those player-seasons, trimmed to the columns the builders read, committed
  as compressed test data (or a `pytest.mark.skip` marker with a clear
  reason if the data genuinely can't be committed — never a silent pass).
- [ ] **Step 3:** build `batting_game` → `batting_season`, assert the
  `is_combined` line vs the Baseball-Reference 2023 Judge line. Same for
  Cole → `pitching_season` (RA9 vs BRef RA9, not ERA).
- [ ] **Step 4:** one team-season tie-out — e.g. 2023 Braves team batting
  vs the BRef team totals.
- [ ] **Step 5:** write every delta and its cause into `docs/RESEARCH.md`
  (the honest-ceiling / known-failure-modes doc).

---

## Task 3 — relation 6: the `gold.player_season` decision (ADR)

**Files:** `docs/DECISIONS.md` (new ADR-279), `docs/DATA_DICTIONARY.md`,
`docs/TABLE_CONTRACTS.md`. **No schema change** if the recommendation holds.

- [ ] **Step 1:** write **ADR-279** recording the decision. The
  recommendation (forward-plan D3, owner-approved): **keep
  `gold.player_season` as the Baseball-Reference-sourced "official" season
  line** (2008+, combined `is_pitcher` shape). The new
  `gold.batting_season` / `gold.pitching_season` are the "event-computed,
  1910–2025, team-aware" line. Two products, clearly labelled. Consolidating
  them (a view) is a possible later effort, not this one.
- [ ] **Step 2:** update `gold.player_season`'s `DATA_DICTIONARY` /
  `TABLE_CONTRACTS` rows to name it the "official-source" line and
  cross-reference the new tables.
- [ ] **Step 3:** confirm no code path writes both — `mlb report` builds
  `gold.player_season` from `raw.bref_*` and the new tables from the game
  relations; they never touch the same rows. Add a one-line assertion or
  doctor note if useful.

---

## Task 4 — Stage 2: advanced layer at the new grains (its own plan doc first)

Do **not** start until Tasks 1–3 land. Write
`docs/superpowers/plans/<date>-grain-backbone-stage-2.md` +
`docs/superpowers/specs/<date>-grain-backbone-stage-2-design.md` as a
separate unit — Stage 2 is roughly the size of all of Stage 1.

Scope (from the S1 spec's "Stage 2" section), each re-plumbing an
**already-tied-out** `mlb_baseball/model/*.py` formula to the new grains,
reusing the exact constants, changing only the `GROUP BY`:

- [ ] `gold.linear_weights` (season) from `gold.run_expectancy_24` — the one
  genuinely-new build; foundation for wOBA/wRAA.
- [ ] wOBA / wRC+ on `gold.batting_season` / `_team` (from `model/offense.py`).
- [ ] **wRAA** as a standalone column — today it exists only folded into the
  wRC+ numerator, so this is partly new work and gets its own fixture.
- [ ] FIP / xFIP / SIERA on `gold.pitching_game` / `_season` (from
  `model/starter.py`, `model/pitcher_estimators.py` — FIP has the strongest
  tie-out in the repo).
- [ ] RE24 / WPA per PA (from `model/run_expectancy.py` +
  `gold.run_expectancy_24` + `gold.win_expectancy`).
- [ ] BsR / wSB / UBR / wGDP on season/team (from `model/bsr.py`).
- [ ] Batted-ball rates, pitch discipline at player-game / player-season.

Each still gets its own fixture + tie-out at the new grain.

---

## Task 5 — housekeeping / follow-up issues to open

- [ ] Issue: `public_safe` backbone export variant keyed by Retrosheet ids
  (`retro_id` / `retro_game_id`) instead of the `core` surrogate keys —
  would let `batting_game` … `pitching_career` ship in the `public_safe`
  Parquet bundle. ADR-278 / SOURCE_RIGHTS.md context.
- [ ] Issue: `gold.pitching_game` earned runs — the reconstructed-inning
  pass that would let `pitching_season` / `_career` carry real ERA.
- [ ] Issue: `gold.baserunning_game` — SB / CS / pinch-runner appearances;
  unblocks SB/CS/SB% in `batting_season` and the pure-pinch-runner rows
  `batting_game` currently drops.
- [ ] Issue: 2026+ `raw.mlb_playbyplay` builders for `batting_game` /
  `pitching_game` (the historical/live split the S1 spec describes;
  `source` column already in place).

---

## Roadmap beyond the backbone (owner-directed, unscheduled)

Per `scratchpad`-tracked context and the `project_prediction_ladder_state`
memory:

1. Grain backbone Stages 3–5 (historical-completeness honesty;
   parameterized rolling windows; export bundle + machine-readable stat
   catalog) — detailed once Stage 2 lands.
2. **markov-v2 / matchup model (#88)** — the big frozen model piece. Models
   are frozen pending research-DB v1, but v1's core (export/interop #123,
   #76, docs #122) has **shipped**. Worth a **freeze re-check with the
   owner** as its own conversation before touching model code.
3. Prediction ladder wave 2 (#79 #67 #81 #57 #58) — never dispatched.

Recommendation: backbone (Task 1 → 2 → 3 → 4) is the coherent next arc —
it's the active fast-follow to v1, has a worked example per relation, and a
written tie-out contract. Revisit the model freeze separately.
