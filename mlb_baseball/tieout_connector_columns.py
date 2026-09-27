"""Pinned columns for the two Retrosheet raw tables whose shape comes from a
Chadwick CLI tool's configured field spec, not a source-supplied CSV header
(task 3.1, design D6).

``mlb_baseball.tieout_schema_contract.RAW_SCHEMA_CONTRACT`` (task 2.6) pins
what *production* currently has, read from its own ``information_schema``.
Design D6 is explicit that this can legitimately differ from what today's
connector code actually produces: raw tables are created and only ever
*extended* (``mlb_baseball.load._check_schema_drift`` issues ``ALTER TABLE ...
ADD COLUMN``, never drops one), so a column landed under an older, wider field
request stays in production forever even after the request narrows. This
module is the other half of D6: it pins what a *fresh* parse under the
connector's current, configured field spec produces, checked in the
disposable test database against a real fixture -- not production.

Captured 2026-09-27 by running ``mlb_baseball.chadwick_tools.run_cwevent``/
``run_cwgame`` (the same functions ``connectors/retrosheet_event.py`` calls,
with its same ``CWEVENT_FIELDS``/``CWEVENT_EXTENDED_FIELDS`` constants)
against ``tests/fixtures/retrosheet_event/decade.zip``'s 2024 event file,
using the Chadwick 0.10.0 binary installed in this environment, then
lowercasing/cleaning column names the same way ``mlb_baseball.load`` does
before a DataFrame lands in Postgres.

**Verified discrepancy against the production pin, not a bug in either
pin:** a fresh ``raw.retrosheet_event`` parse under today's
``CWEVENT_EXTENDED_FIELDS = "0-63"`` produces 161 data columns (165 with the 4
``_season``/``_group``/``_scope``/``_loaded_at`` meta columns) -- three fewer
than ``RAW_SCHEMA_CONTRACT``'s pinned 168: ``run1_auto_fl``, ``run2_auto_fl``,
``run3_auto_fl``. Chadwick's own ``cwevent -d`` lists these as extended fields
64-66, one past the "0-63" ceiling ``chadwick_tools.py``'s ADR-060 comment set
after reportedly finding "0-66" fail outright. Directly re-tested here against
the currently installed binary: `cwevent -y 2024 -f 0-96 -x 0-66 -n
2024ANA.EVA` exits 0 and produces exactly these 3 extra columns, not a
failure -- so the original ADR-060 failure was not reproduced against this
modern fixture/binary combination (it may be specific to the older/deduced
event file that triggered it, not tested here). This module does not change
``CWEVENT_EXTENDED_FIELDS`` on that evidence alone; it only means production's
three extra columns are inert leftovers from before ADR-060 narrowed the
request, not something a fresh load can or should reproduce. See
``openspec/changes/raw-source-tieout/audit.md`` finding G10.

Re-pin (regenerate this file) deliberately, after confirming a real connector
change, not to make a failing run pass.
"""

# ruff: noqa: E501

from __future__ import annotations

# fmt: off
CONNECTOR_FIELD_CONTRACT: dict[str, frozenset[str]] = {
    "raw.retrosheet_event": frozenset({
        'ab_fl', 'ass10_fld_cd', 'ass1_fld_cd', 'ass2_fld_cd',
        'ass3_fld_cd', 'ass4_fld_cd', 'ass5_fld_cd', 'ass6_fld_cd',
        'ass7_fld_cd', 'ass8_fld_cd', 'ass9_fld_cd', 'away_score_ct',
        'away_team_id', 'balls_ct', 'base1_run_id', 'base2_force_fl',
        'base2_run_id', 'base3_force_fl', 'base3_run_id', 'base4_force_fl',
        'bat_dest_id', 'bat_event_fl', 'bat_fate_id', 'bat_fld_cd',
        'bat_hand_cd', 'bat_home_id', 'bat_id', 'bat_in_hold_id',
        'bat_last_id', 'bat_lineup_id', 'bat_on_deck_id', 'bat_play_tx',
        'bat_safe_err_fl', 'bat_start_fl', 'bat_team_id', 'battedball_cd',
        'battedball_loc_tx', 'bunt_fl', 'count_tx', 'dp_fl',
        'end_bases_cd', 'err1_cd', 'err1_fld_cd', 'err2_cd',
        'err2_fld_cd', 'err3_cd', 'err3_fld_cd', 'err_ct',
        'event_cd', 'event_id', 'event_outs_ct', 'event_runs_ct',
        'event_tx', 'fate_runs_ct', 'fld_cd', 'fld_id',
        'fld_team_id', 'foul_fl', 'game_end_fl', 'game_id',
        'game_new_fl', 'game_pa_ct', 'h_cd', 'home_score_ct',
        'home_team_id', 'inn_ct', 'inn_end_fl', 'inn_new_fl',
        'inn_pa_ct', 'inn_runs_ct', 'leadoff_fl', 'outs_ct',
        'pa_ball_ct', 'pa_called_ball_ct', 'pa_called_strike_ct', 'pa_foul_strike_ct',
        'pa_hitbatter_ball_ct', 'pa_inplay_strike_ct', 'pa_intent_ball_ct', 'pa_new_fl',
        'pa_other_ball_ct', 'pa_other_strike_ct', 'pa_pitchout_ball_ct', 'pa_strike_ct',
        'pa_swingmiss_strike_ct', 'pa_trunc_fl', 'pb_fl', 'ph_fl',
        'pit_hand_cd', 'pit_id', 'pit_start_fl', 'pitch_seq_tx',
        'po1_fld_cd', 'po2_fld_cd', 'po3_fld_cd', 'pos2_fld_id',
        'pos3_fld_id', 'pos4_fld_id', 'pos5_fld_id', 'pos6_fld_id',
        'pos7_fld_id', 'pos8_fld_id', 'pos9_fld_id', 'pr_run1_fl',
        'pr_run2_fl', 'pr_run3_fl', 'rbi_ct', 'removed_for_ph_bat_fld_cd',
        'removed_for_ph_bat_id', 'removed_for_pr_run1_id', 'removed_for_pr_run2_id', 'removed_for_pr_run3_id',
        'resp_bat_hand_cd', 'resp_bat_id', 'resp_bat_start_fl', 'resp_pit_hand_cd',
        'resp_pit_id', 'resp_pit_start_fl', 'run1_cs_fl', 'run1_dest_id',
        'run1_fate_id', 'run1_fld_cd', 'run1_lineup_cd', 'run1_origin_event_id',
        'run1_pk_fl', 'run1_play_tx', 'run1_resp_cat_id', 'run1_resp_pit_id',
        'run1_sb_fl', 'run2_cs_fl', 'run2_dest_id', 'run2_fate_id',
        'run2_fld_cd', 'run2_lineup_cd', 'run2_origin_event_id', 'run2_pk_fl',
        'run2_play_tx', 'run2_resp_cat_id', 'run2_resp_pit_id', 'run2_sb_fl',
        'run3_cs_fl', 'run3_dest_id', 'run3_fate_id', 'run3_fld_cd',
        'run3_lineup_cd', 'run3_origin_event_id', 'run3_pk_fl', 'run3_play_tx',
        'run3_resp_cat_id', 'run3_resp_pit_id', 'run3_sb_fl', 'sf_fl',
        'sh_fl', 'start_bases_cd', 'start_bat_score_ct', 'start_fld_score_ct',
        'strikes_ct', 'tp_fl', 'uncertain_play_exc_fl', 'unknown_out_exc_fl',
        'wp_fl',
        '_season', '_group', '_scope', '_loaded_at',
    }),
    "raw.retrosheet_game": frozenset({
        'attend_park_ct', 'away_err_ct', 'away_finish_pit_id', 'away_hits_ct',
        'away_lineup1_bat_id', 'away_lineup1_fld_cd', 'away_lineup2_bat_id', 'away_lineup2_fld_cd',
        'away_lineup3_bat_id', 'away_lineup3_fld_cd', 'away_lineup4_bat_id', 'away_lineup4_fld_cd',
        'away_lineup5_bat_id', 'away_lineup5_fld_cd', 'away_lineup6_bat_id', 'away_lineup6_fld_cd',
        'away_lineup7_bat_id', 'away_lineup7_fld_cd', 'away_lineup8_bat_id', 'away_lineup8_fld_cd',
        'away_lineup9_bat_id', 'away_lineup9_fld_cd', 'away_lob_ct', 'away_score_ct',
        'away_start_pit_id', 'away_team_id', 'base1_ump_id', 'base2_ump_id',
        'base3_ump_id', 'base4_ump_id', 'daynight_park_cd', 'dh_fl',
        'edit_record_ts', 'field_park_cd', 'game_ct', 'game_dt',
        'game_dy', 'game_id', 'gwrbi_bat_id', 'home_err_ct',
        'home_finish_pit_id', 'home_hits_ct', 'home_lineup1_bat_id', 'home_lineup1_fld_cd',
        'home_lineup2_bat_id', 'home_lineup2_fld_cd', 'home_lineup3_bat_id', 'home_lineup3_fld_cd',
        'home_lineup4_bat_id', 'home_lineup4_fld_cd', 'home_lineup5_bat_id', 'home_lineup5_fld_cd',
        'home_lineup6_bat_id', 'home_lineup6_fld_cd', 'home_lineup7_bat_id', 'home_lineup7_fld_cd',
        'home_lineup8_bat_id', 'home_lineup8_fld_cd', 'home_lineup9_bat_id', 'home_lineup9_fld_cd',
        'home_lob_ct', 'home_score_ct', 'home_start_pit_id', 'home_team_id',
        'inn_ct', 'input_record_ts', 'inputter_record_id', 'lf_ump_id',
        'lose_pit_id', 'method_record_cd', 'minutes_game_ct', 'park_id',
        'pitches_record_cd', 'precip_park_cd', 'rf_ump_id', 'save_pit_id',
        'scorer_record_id', 'sky_park_cd', 'start_game_tm', 'temp_park_ct',
        'translator_record_id', 'win_pit_id', 'wind_direction_park_cd', 'wind_speed_park_ct',
        '_season', '_group', '_scope', '_loaded_at',
    }),
}
# fmt: on
