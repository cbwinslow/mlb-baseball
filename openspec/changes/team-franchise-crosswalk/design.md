## Context

`core.team` is one row per team-era (`retro_team_id`, `first_year`,
`last_year`), by design (ADR-013) — Retrosheet reuses `retro_team_id`
across non-contiguous eras, so there is no franchise-level row today.
`core.team.mlb_team_id` (ADR-029) already anchors a franchise across
renames and is confirmed populated for all 30 current teams with zero
gaps, but nothing resolves "given any era's code, what's the current one"
from it — three call sites hand-patch that fact instead
(`report.py` x2, `mlb_baseball/model/season.py` x3, added in the PR
fixing the immediate Athletics symptom).

Verified against real production data while designing this:
`core.game.home_team_id`/`away_team_id` already resolve correctly per
season — 2023/2024 Athletics home games point to the `OAK` era row, 2025
games point to the `ATH` era row (`conform_team_insert.sql`'s year-range
match already picks the narrower/correct era despite `OAK`'s
`last_year = 9999` range technically overlapping 2025 too). The bug is
downstream of that, in code that assumes `last_year = 9999` means
"the current era" instead of querying which era actually applies.

**A second, previously undiscovered instance of the same root cause**:
`_build_team_aliases` (`conform.py`) seeds `core.team_alias` rows with
`WHERE retro_team_id = %s AND last_year = 9999` — for the Athletics this
attaches the Kalshi `"ATH"` ticker alias to the **old `OAK` row's**
`team_id`, not the real 2025 `ATH` row's `team_id`. Since `_game_lookup`
keys off `core.game`'s actual (correct, per-season) `home_team_id`/
`away_team_id`, a real 2025 Kalshi Athletics market resolves to the wrong
`team_id` and silently fails to match its game (dropped under the
project's existing "don't guess, drop instead" precedent — no crash, just
a quiet coverage gap for exactly the games this was built to cover). Not
reported anywhere before this investigation. Small, same-file fix
alongside the rest of this change: replace `last_year = 9999` there with
a join through the new franchise resolution.

## Goals / Non-Goals

**Goals:**
- One authoritative, queryable answer for "what is franchise X's current
  Retrosheet code," derived from data already ingested.
- Retire the `CASE WHEN 'ATH' THEN 'OAK'` duplication in `report.py` and
  `season.py`, and fix `_build_team_aliases`'s same-cause alias-target bug.
- Fail loudly (via `mlb doctor`), not silently, when a future team-era
  can't be resolved to a franchise that Lahman's data should cover.

**Non-Goals:**
- Not replacing `core.team.mlb_team_id` or `core.team_alias` — this adds a
  franchise dimension alongside them, for a different question
  (mlb_team_id: "is this the same franchise as MLB's own API"; team_alias:
  "what string does an external source use"; team_franchise: "what's this
  franchise's current code").
- Not making `season.py`'s `ALL_MLB_TEAMS`/`MLB_DIVISIONS` dynamic (see
  proposal.md — deferred, separate problem).
- Not modeling point-in-time division/league history.
- Not a general n-way historical crosswalk UI/export — this closes the
  specific "current code for a franchise" gap that has now caused two real
  bugs, not a speculative bigger reconciliation project.

## Decisions

**Source the franchise dimension from Lahman, not from `mlb_team_id`
alone.** `mlb_team_id` alone would resolve the immediate case (it's
already populated and correct for all 30 current teams), but it's null
for 106 of 152 `core.team` rows — every pre-1901 team-era, per ADR-029.
Lahman's own `franchid` (`raw.lahman_teams_franchises` +
`raw.lahman_teams.franchid`/`teamidretro`, already confirmed matching
`core.team.retro_team_id`) covers the same franchise-continuity question
back to 1871 and is already ingested — no new source, and it covers
strictly more of `core.team` than `mlb_team_id` would alone. Where both
exist they should agree (a cheap cross-check worth adding as a `mlb
doctor` sanity assertion, not a hard requirement of this change).

**`current_retro_team_id` = the resolved era with the greatest
`first_year`, not `last_year = 9999`.** Verified directly (see Context):
`last_year = 9999` reflects Retrosheet's own source file being stale, not
which era is actually current. `first_year` is set once, from the era's
own start, and isn't subject to the same staleness.

**Added during implementation: `core.team_franchise` also carries
`legacy_retro_team_id` (the resolved era with the *smallest* `first_year`
— the franchise's original code), alongside `current_retro_team_id`.**
Discovered while wiring the consumers this change was meant to fix:
`report.py`'s `gold.team_season` (`UNIQUE (team_id, season)`) and
`season.py`'s `load_schedule_from_db` both need one *stable* `core.team`
row per franchise across a relocation, for reasons independent of "what's
the real current code" — `gold.team_season` was already deliberately
anchoring every Athletics season on the old `OAK` row (accepting that its
`team_city`/`team_nickname` columns show "Oakland" even for the 2025 row,
rather than let a relocation change `team_id`), and `season.py`'s
`ALL_MLB_TEAMS`/`MLB_DIVISIONS` (out of scope for this change, still
hardcoded to `OAK`) would crash on an unrecognized `ATH` key. Anchoring
both on `current_retro_team_id` (`ATH`) would flip which years show the
wrong city in `gold.team_season` (old seasons would show "Sacramento"
instead) and would crash the simulation outright — both real regressions,
not neutral. Owner decision: anchor both on `legacy_retro_team_id`
instead, preserving their exact current behavior while still removing the
hand-patched `CASE WHEN` duplication in favor of one real crosswalk table.
`current_retro_team_id` remains what `_build_team_aliases` uses (that
consumer needs the real current code, to match an external source's
live ticker) — the two columns serve genuinely different, already-real
consumer needs, not redundant data.

**One row per franchise in `core.team_franchise`, built and truncated the
same way `core.team_alias` already is** (a plain builder function called
from `run()`, truncated centrally) — follows this file's existing
pattern rather than inventing a new lifecycle.

**`core.team.franchise_id` as a nullable FK**, backfilled by an `UPDATE`
after `core.team_franchise` is built (same shape as
`_backfill_mlb_team_id`) — not a NOT NULL column, because a real subset of
rows (documented pre-1969 gaps) will never resolve, and the project's
established precedent is an honest null over a fabricated link.

**Alternatives considered:**
- *Keep hand-patching each new relocation as it happens.* Rejected: this
  is the second bug from the same cause in one review pass; the pattern
  doesn't scale and each new call site is a chance to miss a spot.
- *Add a Python-level static dict (`{"ATH": "OAK"}`) instead of a table.*
  Rejected per the owner's own choice earlier in this conversation: it's
  not self-updating from real data, doesn't cover pre-1901 franchises, and
  gives `core.team_alias`'s same-cause bug no natural place to be fixed
  from.
- *Derive current code from `mlb_team_id` only (skip Lahman).* Rejected:
  leaves the pre-1901 rows exactly as unresolved as today, for no savings
  — the Lahman data is already sitting in `raw` unused.

## Risks / Trade-offs

- **[Lahman data lags a brand-new team by some window]** → the health
  check (spec requirement) surfaces the gap explicitly instead of a wrong
  or silent answer; `core.team.franchise_id` stays null for that team in
  the meantime, same honest-null precedent as everywhere else.
- **[`mlb_team_id` and Lahman's `franchid` could theoretically disagree
  for some row]** → not treated as a hard failure in this change (no
  evidence either way yet); worth a `mlb doctor` informational check, not
  a blocking one, so a real disagreement is visible without inventing a
  reconciliation rule for a case that hasn't been observed.
- **[Doubleheader/expansion edge cases in the franchise resolution
  query]** → mitigated by testing against real production data (already
  spot-checked for the Athletics in this session) plus the two documented
  historical id-reuse cases from ADR-013 (HOU 1962-2012 vs 2013-2021, MIL
  1970-1997 vs 1998-2021) as explicit fixture cases, since both are real,
  known, non-contiguous-era situations already on record.

## Migration Plan

1. Migration adds `core.team_franchise` and `core.team.franchise_id`
   (additive, no backfill required at migration time — conform.py
   populates both on its next run).
2. `conform.py` gains the new builder + backfill step and the
   `_build_team_aliases` fix, wired into `run()` after `_build_teams()`
   (franchise resolution needs `core.team` populated first) and before
   `_build_team_aliases()` (which now depends on it).
3. `season.py`/`report.py` switch to resolving through
   `core.team_franchise`; their existing inline `CASE WHEN` is deleted,
   not left as a dead fallback.
4. `mlb doctor` gains the new check.
5. No rollback complexity beyond a normal migration-down: the new
   column/table are additive and nothing existing depends on their
   presence until step 3 lands in the same change.
