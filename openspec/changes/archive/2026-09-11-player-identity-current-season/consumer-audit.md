# Consumer audit — `core.player.retro_id` becomes nullable

**Question for each consumer:** with a NULL `retro_id` on a current-season
player, would this code compute a **wrong** result, or just **skip** that
player? Skipping is fine for Retrosheet-era (≤2025) consumers — those players
have no Retrosheet events anyway.

**Method:** `grep -rl '\bretro_id\b' mlb_baseball/` (excludes `retro_game_id` /
`retro_team_id` / the `pitcher_retro_id` local aliases). 17 files. Every
`JOIN core.player … ON …retro_id = …` inspected below.

**Verdict: no consumer produces a wrong result.** One improves. One docstring
is stale (fixed in this change).

| File | `retro_id` use | Sees a NULL-retro (2026+) player? | Verdict |
|---|---|---|---|
| `sql/conform_player_insert.sql` | first-pass `SELECT key_retro` into `core.player` | writes `retro_id`, does not join on it | n/a — the thing being changed |
| `sql/conform_player_insert_current_season.sql` | second pass, `WHERE key_retro IS NULL` | this change | n/a |
| `conform.py:385-387` | `LEFT JOIN core.player … ON retro_id = gi.wp/lp/save` from `raw.retrosheet_gameinfo` | No — Retrosheet publishes no current-season gameinfo | safe (empty) |
| `conform.py:993-994` | `LEFT JOIN core.player … ON retro_id = ev.bat_id/pit_id` from `raw.retrosheet_event` | No — event stream ends 2025 | safe (empty) |
| `report.py:606,631` | health-check `JOIN core.player ON retro_id = re.bat_id/resp_pit_id` over `raw.retrosheet_event` | No — event stream ends 2025; `NULL = <id>` never matches anyway | safe (empty) |
| `sql/batting_game_build.sql:116`, `sql/pitching_game_build.sql:109` | `JOIN core.player p ON p.retro_id = b.bat_id / pg.pit_id` — Retrosheet-event backbone builder | No — reads `raw.retrosheet_event` (≤2025). (`backbone-2026-source` additionally scopes these `season <= 2025` and adds a separate `mlbam_id`-keyed 2026 builder.) | safe (empty) |
| `sql/team_starter_retrosheet_update.sql:61-62` | `LEFT JOIN core.player … ON retro_id = …_starter_retro_id` | No — `*_retrosheet_*`, Retrosheet-event sourced | safe (empty) |
| `sql/statcast_expected_retrosheet_update.sql:16-17` | `SELECT hp.retro_id AS …_starter_retro_id` (join is on `hp.id`) | Statcast×Retrosheet overlap ends 2025 | safe (empty) |
| `sql/starter_strikeouts_reconcile.sql:8`, `sql/starter_outs_reconcile.sql:7` | `JOIN core.player p ON p.retro_id = re.resp_pit_id` from `raw.retrosheet_event` | No | safe (empty) |
| `sql/team_pitcher_estimators_retrosheet_update.sql`, `sql/team_leverage_re24_update.sql`, `sql/team_batted_ball_retrosheet_update.sql` | join `core.player` on `.id` (not `retro_id`); `retro_id` only appears in the `pitcher_retro_id` alias for `raw.retrosheet_event.resp_pit_id` | No — Retrosheet-event sourced | safe (empty) |
| `sql/platoon_splits_update.sql:37-38,43-44` | `COALESCE(NULLIF(hp.mlbam_id,''), NULLIF(hp.retro_id,''), f.home_starter_id::text)` — key-on-what-you-have fallback chain | Yes — a 2026 starter | **improved**: was falling through to the raw id text because the player wasn't in `core.player` at all; now resolves via `mlbam_id` (the first COALESCE branch). `retro_id` is only the 2nd fallback and is populated for the historical players that need it. |
| `model/props.py:267,274` | `COALESCE(hp.last_name, hp.retro_id) AS …_starter_name` — display label | Yes | safe: admitted players carry `last_name` from the register, so the COALESCE takes the first branch |
| `model/props.py:280-281`, `model/sim_predict.py:51-52` | join `core.player` on `.id` | n/a (not a `retro_id` join) | safe |
| `model/starter_workload.py:26` | comment only (`pitcher_retro_id ordered by …`) | n/a | safe |
| `player.py` | `crosswalk()` returns whatever ID columns the row has; `ID_COLUMNS["retro"]` lets you look up *by* `retro_id` | Yes | behaviourally correct — a 2026 player's crosswalk returns `"retro": None`, which is accurate. **Docstring line 11 ("retro_id is NOT NULL/UNIQUE … every conformed player has one") is now stale** → fixed in this change. |

## `WRONG`-verdicted consumers

None. No task 4.2 fix required.

## Doc/comment fixes folded into this change

- `mlb_baseball/player.py` docstring — `retro_id` is now nullable for
  current-season players.
