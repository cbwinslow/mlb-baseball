## Context

- Negro League games reach `core.game` two ways: the Retrosheet play-by-play
  CSV/event files (`_group = 'negro_league'`, 1935–1949) and box-score files
  (1903–1961, 3,941 games). `raw.retrosheet_game._scope` is `<year>_pbp` for
  them, so the raw game table does not carry a Negro League marker; the
  `_group` marker exists only on `raw.retrosheet_event` and
  `raw.retrosheet_box_*`.
- 1,872 games appear in both the general and the Negro League event archives
  (conform already de-duplicates them, `conform.py` ~line 1082).
- `core.team.league` is NULL for 145 teams spanning 1871–2025, so it cannot be
  the flag. Retrosheet's registry for these clubs is `biodata.zip`
  `teams0.csv` (used by `retrosheet_box._negro_league_team_registry`). Lahman
  also carries `lgid` values such as `NNL` for Negro League team-seasons.
- Existing code already excludes them in places: the Lahman team-count and
  win-total reconciliations filter to `lgid IN ('AL','NL')` (`conform.py`
  ~1998–2090); the tie-out register treats them as an explained scope (`nogl`).
- Retrosheet's Negro League downloads page (checked 2026-10-02) offers a
  dedicated 7-file CSV set, `negroleagues.zip` (gameinfo, teamstats, batting,
  pitching, fielding, plays, allplayers; 8,215 games, with `stattype`
  value/lower/upper for uncertain lines), plus event files (`allevr.zip`, 2,192
  play-by-play games as of the Summer 2026 release) and box files (`allebr.zip`,
  4,653 games). `downloads/` holds `allebr.zip` and the general CSVs only; no
  `negroleagues.zip` is on disk. Whether the general CSVs already carry all
  8,215 games is unchecked; task 1.1 counts it. Not needed for the flag, since
  Negro League games are being separated, not studied.
- #258 raised it; `play-engine` fits 2015+ and is unaffected.

## Goals / Non-Goals

**Goals:** one source-derived flag, one view as the model pool, raw untouched,
downstream effect measured, rule documented once.

**Non-Goals:** studying or modelling the Negro Leagues; deleting any data;
building backbone lines for box-only games (#257); any change to 2015+ data.

## Decisions

- **D1 Flag in the table, view on top.** Store the flag on `core.game`
  (set by `conform`, so it is a plain filter, indexable, visible to every
  reader) and expose `core.game_mlb` as the single pool definition. Tables
  alone make every consumer repeat the filter (and drift); a view alone makes
  the rule invisible to anyone querying `core.game`. Rejected: deleting or
  excluding rows in `conform` (loses data, and `conform` truncates and
  re-issues ids nightly, so exclusion rules would hide real rows).
- **D2 The rule is registry membership.** A club is Negro League when it is in
  Retrosheet's Negro League registry for that season (era-aware via
  `first_year`/`last_year`); a game is flagged when both clubs are. Task 1.1
  measures this against `_group`, Lahman `lgid` and the 3,750 readiness-gap
  games before the rule is fixed; any mismatch is reported, not coded around.
  Team codes can repeat across leagues in different eras, so the era check is
  required.
- **D3 Where it is documented.** The rule and its source live in
  `mlb_baseball/conform.py.dox.md` (the owner of the flag), an ADR in
  `docs/DECISIONS.md`, and one line in `docs/DATA_SOURCES.md`. The root
  `AGENTS.md` is not changed (it stays small); if a model-facing rule is
  needed, `mlb_baseball/model/AGENTS.md` links to the DOX.
- **D4 Downstream totals.** Raw and Lahman are untouched, so Lahman agrees
  as before. The gold backbone is built from `raw.retrosheet_event`, which
  includes Negro League events in 1935–1949; whether the backbone excludes
  them is decided from the task 1.3 measurement (Lahman's main batting tables
  and Baseball-Reference omit them, so excluding probably improves agreement).
  Not assumed here.

- **D5 Registry lives in raw (checked 2026-10-06).** `raw.retrosheet_team0`
  (178 Negro League clubs, `first_g`/`last_g` dates) is the registry, so the
  flag derives from the database and survives a bootstrap. It has no league
  column; membership in this table is the signal.
- **D6 API games.** Production holds Negro League games from the MLB Stats API
  for some seasons (1930: 324 of 1,564 schedule rows; none for 1924-1929), with
  team ids 14xx/15xx that are not Retrosheet codes; only 7 of the 324 reach
  `core.game`. The flag must also cover them, by matching club name and season
  to the registry. Unmatched clubs are reported (task 1.4).
- **D7 Mixed games.** One registry club plus one other club is `mixed`, not MLB
  and not Negro League.

## Risks / Trade-offs

- Wrong registry match flags a real MLB game or misses a Negro League one.
  Mitigation: counts by season checked against `_group` and recorded; a
  `mlb doctor` check for any flagged game involving an AL/NL club.
- Both this change and `stable-ids-incremental-conform` edit `conform`; land
  one first.
- The migration is applied by the nightly `mlb migrate`; no manual owner step.
- Name matching for API clubs may be ambiguous; mitigated by the era check and the unmatched-club report.

## Owner decision (2026-10-07)

The owner left the choice to Claude, asking only for consistency. Decision: **keep every Negro League game in the database, from every source (Retrosheet and the MLB API), flagged by the same rule, and leave them out of the major-league pool by default** (`core.game_mlb`). This is what the proposal already does; nothing is deleted and any future Negro League study keeps its data. Consistency rule: whatever the flag says for a game applies to every table and every source; no source gets a different treatment.
