# Where each `core.game` and `core.play` column comes from

Task 1.2 of `raw-source-tieout`. Read from `mlb_baseball/conform.py` and
migrations `0005_core_player_team_game.sql` and `0006_core_play_pitch.sql` on
2026-09-27. Line numbers are for `conform.py` as of this branch; they move if the
file is edited, so re-check them before relying on one after a later change.

The tie-out only concerns rows built from Retrosheet (`retro_game_id` not null in
`core.game`, `source = 'retrosheet'` in `core.play`). `core.game` also has rows
built from `raw.mlb_schedule` (`conform.py:508-602`, the seasons Retrosheet has
not published yet, and `_build_completed_spring_games` from line 608), and
`core.play` also has `mlb_api` rows (`conform.py:1103-1134`). Those are out of
scope here.

## `core.game` (Retrosheet rows) — `_build_games`, `conform.py:416-493`

Base table: **`raw.retrosheet_gameinfo`** (the CSV product), `conform.py:480`.
Every row of that table becomes one `core.game` row; no filter.

| `core.game` column | Built from | Lines | Notes |
| --- | --- | --- | --- |
| `id` | `bigserial` | migration 0005 | generated |
| `retro_game_id` | `gameinfo.gid` | 437 | |
| `season` | `gameinfo._season::integer` | 438 | |
| `game_date` | `to_date(gameinfo.date, 'YYYYMMDD')` | 439 | |
| `game_number` | `gameinfo.number`, only if a plain number | 440 | non-numbers become NULL |
| `away_team_id` | `gameinfo.visteam` joined to `core.team.retro_team_id` within the team's year range | 441, 481-483 | unmatched teams give NULL |
| `home_team_id` | `gameinfo.hometeam`, same join | 442, 484-486 | |
| `away_score` | `gameinfo.vruns` | 443 | |
| `home_score` | `gameinfo.hruns` | 444 | |
| `game_type` | `lower(gameinfo.gametype)` | 453 | lower-cased because one source row has `Regular` |
| `site` | `gameinfo.site` | 454 | |
| `attendance` | `gameinfo.attendance`, only if a plain number | 455-456 | `6500?`, `<1000` become NULL |
| `duration_minutes` | `gameinfo.timeofgame`, only if a plain number | 457-458 | `-1` sentinel becomes NULL |
| `day_night` | `gameinfo.daynight` | 459 | |
| `winning_pitcher_id` | `gameinfo.wp` joined to `core.player.retro_id` | 460, 487 | NULL if no player row |
| `losing_pitcher_id` | `gameinfo.lp`, same join | 461, 488 | |
| `save_pitcher_id` | `gameinfo.save`, same join | 462, 489 | |
| `venue_id` | `gameinfo.site` joined to `core.venue.retro_park_id` | 463, 490 | |
| `temp_f` | `gameinfo.temp`, only if a plain number | 473 | |
| `wind_dir` | `gameinfo.winddir` (`unknown` becomes NULL) | 474 | |
| `wind_speed_mph` | `gameinfo.windspeed`, only if a plain number | 475-476 | |
| `sky` | `gameinfo.sky` (`unknown` becomes NULL) | 477 | |
| `precip` | `gameinfo.precip` (`unknown` becomes NULL) | 478 | |
| `field_cond` | `gameinfo.fieldcond` (`unknown` becomes NULL) | 479 | |
| `game_pk` | **not from Retrosheet.** Filled later from `raw.mlb_schedule` by three matching passes | 762-763 (date, teams, game number), 888-889 (team crosswalk), 1000-1001 (exact final score) | can stay NULL; not part of the Retrosheet tie-out |
| `_conformed_at` | default `now()` | migration 0005 | |

`away_team_id`, `home_team_id` and the three pitcher ids can also be filled or
corrected by later passes from `raw.mlb_schedule` (for example `conform.py:1024-1027`);
that is a schedule-derived correction and is not tied out here.

## `core.play` (Retrosheet rows) — `_build_plays`, `conform.py:1047-1099`

Base table: **`raw.retrosheet_event`** (Chadwick-parsed event files), one row per
(`game_id`, `event_id`), deduplicated with `DISTINCT ON (game_id, event_id)
ORDER BY ..., _scope` (`conform.py:1090-1093`). This drops the 1,872
Negro League games that are published in two archives.

The event rows are then **inner-joined to `core.game` on
`core.game.retro_game_id = event.game_id`** (`conform.py:1094`). Because
`core.game` comes from `raw.retrosheet_gameinfo`, **an event game that has no
`gameinfo` row does not reach `core.play`** (audit finding G7).

There is **no filter on event type**: every event row (batter events and
baserunning events alike) becomes a `core.play` row.

| `core.play` column | Built from | Lines | Notes |
| --- | --- | --- | --- |
| `id` | `bigserial` | migration 0006 | generated |
| `game_id` | `core.game.id` (join above) | 1068, 1094 | |
| `season` | `event._season::integer` | 1069 | |
| `source` | literal `'retrosheet'` | 1070 | |
| `play_index` | `event.event_id::integer` | 1071 | with `game_id` and `source` this is unique (`UNIQUE (game_id, source, play_index)`, migration 0006) |
| `inning` | `event.inn_ct` | 1072 | |
| `half_inning` | `event.bat_home_id` (`0` top, `1` bottom) | 1073 | |
| `batter_id` | `event.bat_id` joined to `core.player.retro_id` | 1074, 1095 | NULL if no player row |
| `pitcher_id` | `event.pit_id` joined to `core.player.retro_id` | 1075, 1096 | NULL if no player row |
| `event_code` | `event.event_cd` | 1076 | |
| `event_desc` | `event.event_tx` | 1077 | |
| `away_score` | `event.away_score_ct` | 1078 | see below |
| `home_score` | `event.home_score_ct` | 1079 | see below |
| `balls`, `strikes`, `outs` | **not set for Retrosheet rows** (not in the insert list, `conform.py:1062-1066`) | — | always NULL; use `raw.retrosheet_event` (`outs_ct`, etc.) |
| `home_win_probability`, `away_win_probability` | only set for `mlb_api` rows | 1155-1159 | NULL for Retrosheet |
| `_conformed_at` | default `now()` | migration 0006 | |

`away_score` and `home_score` are copied from `away_score_ct` / `home_score_ct`
(`conform.py:1078-1079`). The session handoff observed these are null for
2015–2025; the tie-out's sampled-attribute check (task 2.5) must compare them to
raw rather than assume they are populated.

## Consequences for the tie-out

1. **Complete comparison of `core.play`** is a keyed comparison of every deduplicated
   event row against `core.play`, by (`game_id`, `play_index`), restricted to event
   games that exist in `core.game`; event games missing from `core.game` are
   reported as their own count (they are not a `conform` defect, but they must be
   visible).
2. **Plate-appearance counts** need the batter-event set (event codes 2, 3 and
   14–23 for the modern seasons, ADR-283 and the play-engine design) because
   `core.play` itself does not carry a flag.
3. The description in migration `0006_core_play_pitch.sql:1` ("one row per plate
   appearance") is inaccurate for Retrosheet rows: they are one row per **event**.
   The migration is not edited (applied history); the owning DOX is corrected under
   task 4.3.
