## 1. Schema: `er` / `era` on the pitching relations

- [ ] 1.1 Migration `migrations/NNNN_pitching_er_era.sql` — `ADD COLUMN er integer` on `gold.pitching_game`, `gold.pitching_season`, `gold.pitching_career`; `ADD COLUMN era numeric` on `gold.pitching_season`, `gold.pitching_career`. Additive, no backfill. Column comments state the 1910–2025-null / 2026+-populated coverage cliff. Verify: `mlb migrate` against a scratch DB applies it; `\d gold.pitching_game` shows `er`; the pytest migrate picks it up (existing `test_report_pitching_*` still pass).

## 2. Scope the Retrosheet game builders to ≤ 2025

- [ ] 2.1 `sql/batting_game_build.sql` / `sql/pitching_game_build.sql` — add `AND g.season <= 2025` to the `WHERE`, update the header comment (it already says "1910–2025" — make the bound explicit and point at the MLB builder for 2026+). The pitching builder writes `er = NULL` (new column). Verify: `test_report_batting_game.py` / `test_report_pitching_game.py` still pass; a targeted assertion that a seeded 2026 `core.game` produces no Retrosheet-sourced row.

## 3. MLB box-score game builders (2026+)

- [ ] 3.1 `sql/batting_game_mlb_build.sql` — `raw.mlb_boxscore_batting` JOIN `core.game` on `game_pk`, `WHERE g.season >= 2026 AND g.game_type = 'regular' AND (%(season)s::integer IS NULL OR g.season = %(season)s::integer)`. Map the columns per design §Context; `b1 = h − b2 − b3 − hr`; `source = 'mlb_boxscore'`; `player_id` via `core.player` on the MLB id; `team_id` from `core.game` home/away by the box score's `team_id`. One parameterized statement (psycopg prepare). Verify: `test_report_batting_game_mlb.py` — a hand-built `raw.mlb_boxscore_batting` + `core.game` fixture produces the expected `gold.batting_game` row (PA/AB/H/singles/TB/RBI/BB hand-checked), idempotent on a second run.
- [ ] 3.2 `sql/pitching_game_mlb_build.sql` — `raw.mlb_boxscore_pitching` the same way; map `outs`, `bf←batters_faced`, `er←earned_runs`, `gs←games_started`, `w`/`l`/`sv`, `h`/`r`/`bb`/`ibb`/`so`/`hr`/`hbp←hit_batsmen`/`wp←wild_pitches`/`bk←balks`; `source = 'mlb_boxscore'`. Verify: `test_report_pitching_game_mlb.py` — fixture row with `earned_runs` produces `er` populated; a Retrosheet-era fixture (task 2.1) still leaves `er` null; idempotent.

## 4. Multi-source dispatch in `report.run()`

- [ ] 4.1 Extend `report._build_backbone_relation` (or add `_build_backbone_relation_multi`) to accept an ordered list of `(build_sql, source)` pairs: pre-check each source, `TRUNCATE` the target once, run every build whose source table is present, return the summed count. Preserve the single-pair signature for the season/team/career callers. Verify: unit-style test that with only `raw.retrosheet_event` present it behaves exactly as before (returns the same count, no error on the absent `raw.mlb_boxscore_*`).
- [ ] 4.2 Wire `gold.batting_game` / `gold.pitching_game` in `run()` to the two-source list (`[(retrosheet_sql, 'raw.retrosheet_event'), (mlb_sql, 'raw.mlb_boxscore_batting')]`). Verify: `test_report.py::test_run_is_idempotent` still passes; a new test seeds a 2025 Retrosheet game + a 2026 box-score game and asserts `gold.batting_game` has one row from each `source` and no key collision.

## 5. Season / team / career roll-ups: `er` / `era`

- [ ] 5.1 `sql/pitching_season_build.sql` / `pitching_team_build.sql` — add `er` (guarded: `CASE WHEN count(*) = count(er) THEN sum(er) END`) and `era` (`CASE WHEN outs > 0 AND <er guard> THEN er_sum * 27.0 / outs END`) alongside the existing `ra9`. Verify: `test_report_pitching_season.py` — a 2026 pitcher-season rolls up a real `era`; a 1910–2025 pitcher-season has `era` null and `ra9` unchanged; mutation check that a wrong `er` sum or wrong `27` constant fails an assertion.
- [ ] 5.2 `sql/pitching_career_build.sql` — same `er` / `era` recompute from the season combined rows; `era` null unless every season has non-null `er`. Verify: `test_report_career.py` — a career spanning only 2026 has `era`; a career spanning 2025–2026 has `era` null (mixed coverage), `ra9` populated.

## 6. `mlb doctor` checks

- [ ] 6.1 `report.health_check()` — (a) `gold.batting_game` / `gold.pitching_game` join coverage for `source = 'mlb_boxscore'` rows against `raw.mlb_boxscore_*` (unresolved player/team surfaces as a shortfall); (b) a no-double-write guard: 0 `(game_id, player_id, team_id)` groups with `count(DISTINCT source) > 1`. Verify: `test_report.py` / `test_health.py` — `health_check()` includes the two new checks; a seeded double-write row makes the guard fail.

## 7. Play-by-play cross-check gate

- [ ] 7.1 `scripts/verify_mlb_boxscore_tie_out.py` (or a section in `verify_baseball_reference_tie_out.py`) — sample complete 2026 games (PA count in the expected band), group `raw.mlb_playbyplay` by `(game_pk, batter_id)`, map `event_type → PA/AB/H/BB/SO/HBP/SF/SH/HR`, compare to `mlb_boxscore`-sourced `gold.batting_game` field-by-field, fail if a counting stat is outside the documented tolerance on > the documented fraction. An unmapped `event_type` fails loudly. Read-only, safe against prod. Verify: the script runs against the built DB and passes within the documented tolerance; a unit test of the `event_type` map covers the edge cases (`field_error`, `fielders_choice`, `catcher_interf`, empty).

## 8. Docs

- [ ] 8.1 `docs/DATA_DICTIONARY.md` + `docs/TABLE_CONTRACTS.md` — the 2026-onward MLB box-score source, the `source` values, the `er` / `era` coverage cliff (null ≤ 2025, populated ≥ 2026), the box-score-vs-event methodology note. `docs/RESEARCH.md` honest-limitations section: same. `docs/DECISIONS.md` — new ADR (MLB box score is the current-season backbone source; pbp is the tie-out). Verify: `grep` the changed table/column names across `docs/` leaves nothing stale; `openspec validate backbone-2026-source --strict` passes.
- [ ] 8.2 Sync the spec delta into `openspec/specs/statistic-backbone/spec.md` (`/opsx:sync` or manual) as part of archive. Verify: the main spec's coverage / source / null-policy / tie-out requirements read as the delta's MODIFIED versions.

## 9. Verification (owner-run against production)

- [ ] 9.1 `mlb migrate` + `mlb report` on production `mlb`. Verify: `SELECT source, count(*), min(season), max(season) FROM gold.batting_game GROUP BY 1` shows `retrosheet_event` ≤ 2025 and `mlb_boxscore` ≥ 2026; the no-double-write guard returns 0; `report.health_check()` passes; a spot check of 3 known 2026 player-games against MLB.com box scores matches exactly.
- [ ] 9.2 Run `scripts/verify_mlb_boxscore_tie_out.py` and the existing `verify_baseball_reference_tie_out.py` against the rebuilt production DB. Verify: both exit 0 within their documented tolerances.
