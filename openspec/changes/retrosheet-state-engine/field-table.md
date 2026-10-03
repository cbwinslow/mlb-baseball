# cwevent field table (tasks 1.1, 1.2)

Source: `cwevent -d` (Chadwick 0.10.0), `-f 0-96` (97 fields) then `-x 0-66` (67 fields) = 164 columns.
CSV column names are from a real run (`cwevent -q -n -f 0-96 -x 0-66`).

**Comparison scope.** `cwevent` is run on one event file with an empty team file and
no roster files, so every value comes from the event file alone. Under this scope the
**exclusion list is empty**: no field needs data outside the event file. Fields that
real rosters would change (bat/throw hand, `*_HAND_CD`) are compared in their
no-roster form (`?` unless the file's `badj`/`padj` records give a hand); the 2007,
1950 and other fixtures confirm this (`PIT_HAND_CD` is only `?`, `BAT_HAND_CD` is `?`
or `L`). If a later step needs roster-aware output, that is a separate scope.

Status: "already matched" = derived from play text in the earlier change (0 mismatches
on 7 seasons); "state-dependent" = needs the game state and is the work of this change.
Groups follow design D5 (order of work); a group number is tentative until built.
Counts: 164 columns total, of which the already-matched set is listed below.

| option | # | cwevent name | CSV column | status | group |
|---|---|---|---|---|---|
| -f | 0 | game id | GAME_ID | in scope, state-dependent | 1 lineup/game state |
| -f | 1 | visiting team | AWAY_TEAM_ID | in scope, state-dependent | 1 lineup/game state |
| -f | 2 | inning | INN_CT | in scope, state-dependent | 1 lineup/game state |
| -f | 3 | batting_team | BAT_HOME_ID | in scope, state-dependent | 1 lineup/game state |
| -f | 4 | outs | OUTS_CT | in scope, state-dependent | 1 lineup/game state |
| -f | 5 | balls | BALLS_CT | in scope, state-dependent | 1 lineup/game state |
| -f | 6 | strikes | STRIKES_CT | in scope, state-dependent | 1 lineup/game state |
| -f | 7 | pitch sequence | PITCH_SEQ_TX | in scope, state-dependent | 1 lineup/game state |
| -f | 8 | vis score | AWAY_SCORE_CT | in scope, state-dependent | 1 lineup/game state |
| -f | 9 | home score | HOME_SCORE_CT | in scope, state-dependent | 1 lineup/game state |
| -f | 10 | batter | BAT_ID | in scope, state-dependent | 1 lineup/game state |
| -f | 11 | batter hand | BAT_HAND_CD | in scope, state-dependent | 1 lineup/game state |
| -f | 12 | res batter | RESP_BAT_ID | in scope, state-dependent | 1 lineup/game state |
| -f | 13 | res batter hand | RESP_BAT_HAND_CD | in scope, state-dependent | 1 lineup/game state |
| -f | 14 | pitcher | PIT_ID | in scope, state-dependent | 1 lineup/game state |
| -f | 15 | pitcher hand | PIT_HAND_CD | in scope, state-dependent | 1 lineup/game state |
| -f | 16 | res pitcher | RESP_PIT_ID | in scope, state-dependent | 1 lineup/game state |
| -f | 17 | res pitcher hand | RESP_PIT_HAND_CD | in scope, state-dependent | 1 lineup/game state |
| -f | 18 | catcher | POS2_FLD_ID | in scope, state-dependent | 1 lineup/game state |
| -f | 19 | first base | POS3_FLD_ID | in scope, state-dependent | 1 lineup/game state |
| -f | 20 | second base | POS4_FLD_ID | in scope, state-dependent | 1 lineup/game state |
| -f | 21 | third base | POS5_FLD_ID | in scope, state-dependent | 1 lineup/game state |
| -f | 22 | shortstop | POS6_FLD_ID | in scope, state-dependent | 1 lineup/game state |
| -f | 23 | left field | POS7_FLD_ID | in scope, state-dependent | 1 lineup/game state |
| -f | 24 | center field | POS8_FLD_ID | in scope, state-dependent | 1 lineup/game state |
| -f | 25 | right field | POS9_FLD_ID | in scope, state-dependent | 1 lineup/game state |
| -f | 26 | first runner | BASE1_RUN_ID | in scope, state-dependent | 1 lineup/game state |
| -f | 27 | second runner | BASE2_RUN_ID | in scope, state-dependent | 1 lineup/game state |
| -f | 28 | third runner | BASE3_RUN_ID | in scope, state-dependent | 1 lineup/game state |
| -f | 29 | event text | EVENT_TX | in scope, state-dependent | 1 lineup/game state |
| -f | 30 | leadoff flag | LEADOFF_FL | in scope, state-dependent | 1 lineup/game state |
| -f | 31 | pinchhit flag | PH_FL | in scope, state-dependent | 1 lineup/game state |
| -f | 32 | defensive position | BAT_FLD_CD | in scope, state-dependent | 1 lineup/game state |
| -f | 33 | lineup position | BAT_LINEUP_ID | in scope, state-dependent | 1 lineup/game state |
| -f | 34 | event type | EVENT_CD | in scope, already matched (text-derived) | done in Slice A |
| -f | 35 | batter event flag | BAT_EVENT_FL | in scope, state-dependent | 2 outs/destinations/RBI |
| -f | 36 | ab flag | AB_FL | in scope, state-dependent | 2 outs/destinations/RBI |
| -f | 37 | hit value | H_CD | in scope, already matched (text-derived) | done in Slice A |
| -f | 38 | SH flag | SH_FL | in scope, already matched (text-derived) | done in Slice A |
| -f | 39 | SF flag | SF_FL | in scope, already matched (text-derived) | done in Slice A |
| -f | 40 | outs on play | EVENT_OUTS_CT | in scope, state-dependent | 2 outs/destinations/RBI |
| -f | 41 | double play flag | DP_FL | in scope, state-dependent | 2 outs/destinations/RBI |
| -f | 42 | triple play flag | TP_FL | in scope, state-dependent | 2 outs/destinations/RBI |
| -f | 43 | RBI on play | RBI_CT | in scope, state-dependent | 2 outs/destinations/RBI |
| -f | 44 | wild pitch flag | WP_FL | in scope, already matched (text-derived) | done in Slice A |
| -f | 45 | passed ball flag | PB_FL | in scope, already matched (text-derived) | done in Slice A |
| -f | 46 | fielded by | FLD_CD | in scope, state-dependent | 4 fielding credit |
| -f | 47 | batted ball type | BATTEDBALL_CD | in scope, already matched (text-derived) | done in Slice A |
| -f | 48 | bunt flag | BUNT_FL | in scope, already matched (text-derived) | done in Slice A |
| -f | 49 | foul flag | FOUL_FL | in scope, state-dependent | 2 outs/destinations/RBI |
| -f | 50 | hit location | BATTEDBALL_LOC_TX | in scope, already matched (text-derived) | done in Slice A |
| -f | 51 | num errors | ERR_CT | in scope, state-dependent | 3 errors |
| -f | 52 | 1st error player | ERR1_FLD_CD | in scope, state-dependent | 3 errors |
| -f | 53 | 1st error type | ERR1_CD | in scope, state-dependent | 3 errors |
| -f | 54 | 2nd error player | ERR2_FLD_CD | in scope, state-dependent | 3 errors |
| -f | 55 | 2nd error type | ERR2_CD | in scope, state-dependent | 3 errors |
| -f | 56 | 3rd error player | ERR3_FLD_CD | in scope, state-dependent | 3 errors |
| -f | 57 | 3rd error type | ERR3_CD | in scope, state-dependent | 3 errors |
| -f | 58 | batter dest (5 if scores and unearned, 6 if team unearned) | BAT_DEST_ID | in scope, state-dependent | 2 outs/destinations/RBI |
| -f | 59 | runner on 1st dest (5 if scores and unearned, 6 if team unearned) | RUN1_DEST_ID | in scope, state-dependent | 2 outs/destinations/RBI |
| -f | 60 | runner on 2nd dest (5 if scores and unearned, 6 if team unearned) | RUN2_DEST_ID | in scope, state-dependent | 2 outs/destinations/RBI |
| -f | 61 | runner on 3rd dest (5 if scores and unearned, 6 if team unearned) | RUN3_DEST_ID | in scope, state-dependent | 2 outs/destinations/RBI |
| -f | 62 | play on batter | BAT_PLAY_TX | in scope, state-dependent | 4 fielding credit |
| -f | 63 | play on runner on first | RUN1_PLAY_TX | in scope, state-dependent | 4 fielding credit |
| -f | 64 | play on runner on second | RUN2_PLAY_TX | in scope, state-dependent | 4 fielding credit |
| -f | 65 | play on runner on third | RUN3_PLAY_TX | in scope, state-dependent | 4 fielding credit |
| -f | 66 | SB for runner on 1st flag | RUN1_SB_FL | in scope, already matched (text-derived) | done in Slice A |
| -f | 67 | SB for runner on 2nd flag | RUN2_SB_FL | in scope, already matched (text-derived) | done in Slice A |
| -f | 68 | SB for runner on 3rd flag | RUN3_SB_FL | in scope, already matched (text-derived) | done in Slice A |
| -f | 69 | CS for runner on 1st flag | RUN1_CS_FL | in scope, already matched (text-derived) | done in Slice A |
| -f | 70 | CS for runner on 2nd flag | RUN2_CS_FL | in scope, already matched (text-derived) | done in Slice A |
| -f | 71 | CS for runner on 3rd flag | RUN3_CS_FL | in scope, already matched (text-derived) | done in Slice A |
| -f | 72 | PO for runner on 1st flag | RUN1_PK_FL | in scope, already matched (text-derived) | done in Slice A |
| -f | 73 | PO for runner on 2nd flag | RUN2_PK_FL | in scope, already matched (text-derived) | done in Slice A |
| -f | 74 | PO for runner on 3rd flag | RUN3_PK_FL | in scope, already matched (text-derived) | done in Slice A |
| -f | 75 | Responsible pitcher for runner on 1st | RUN1_RESP_PIT_ID | in scope, state-dependent | 5 pinch/responsible pitcher |
| -f | 76 | Responsible pitcher for runner on 2nd | RUN2_RESP_PIT_ID | in scope, state-dependent | 5 pinch/responsible pitcher |
| -f | 77 | Responsible pitcher for runner on 3rd | RUN3_RESP_PIT_ID | in scope, state-dependent | 5 pinch/responsible pitcher |
| -f | 78 | New Game Flag | GAME_NEW_FL | in scope, state-dependent | 1 lineup/game state |
| -f | 79 | End Game Flag | GAME_END_FL | in scope, state-dependent | 1 lineup/game state |
| -f | 80 | Pinch-runner on 1st | PR_RUN1_FL | in scope, state-dependent | 5 pinch/responsible pitcher |
| -f | 81 | Pinch-runner on 2nd | PR_RUN2_FL | in scope, state-dependent | 5 pinch/responsible pitcher |
| -f | 82 | Pinch-runner on 3rd | PR_RUN3_FL | in scope, state-dependent | 5 pinch/responsible pitcher |
| -f | 83 | Runner removed for pinch-runner on 1st | REMOVED_FOR_PR_RUN1_ID | in scope, state-dependent | 5 pinch/responsible pitcher |
| -f | 84 | Runner removed for pinch-runner on 2nd | REMOVED_FOR_PR_RUN2_ID | in scope, state-dependent | 5 pinch/responsible pitcher |
| -f | 85 | Runner removed for pinch-runner on 3rd | REMOVED_FOR_PR_RUN3_ID | in scope, state-dependent | 5 pinch/responsible pitcher |
| -f | 86 | Batter removed for pinch-hitter | REMOVED_FOR_PH_BAT_ID | in scope, state-dependent | 5 pinch/responsible pitcher |
| -f | 87 | Position of batter removed for pinch-hitter | REMOVED_FOR_PH_BAT_FLD_CD | in scope, state-dependent | 5 pinch/responsible pitcher |
| -f | 88 | Fielder with First Putout (0 if none) | PO1_FLD_CD | in scope, state-dependent | 4 fielding credit |
| -f | 89 | Fielder with Second Putout (0 if none) | PO2_FLD_CD | in scope, state-dependent | 4 fielding credit |
| -f | 90 | Fielder with Third Putout (0 if none) | PO3_FLD_CD | in scope, state-dependent | 4 fielding credit |
| -f | 91 | Fielder with First Assist (0 if none) | ASS1_FLD_CD | in scope, state-dependent | 4 fielding credit |
| -f | 92 | Fielder with Second Assist (0 if none) | ASS2_FLD_CD | in scope, state-dependent | 4 fielding credit |
| -f | 93 | Fielder with Third Assist (0 if none) | ASS3_FLD_CD | in scope, state-dependent | 4 fielding credit |
| -f | 94 | Fielder with Fourth Assist (0 if none) | ASS4_FLD_CD | in scope, state-dependent | 4 fielding credit |
| -f | 95 | Fielder with Fifth Assist (0 if none) | ASS5_FLD_CD | in scope, state-dependent | 4 fielding credit |
| -f | 96 | event num | EVENT_ID | in scope, state-dependent | 1 lineup/game state |
| -x | 0 | home team id | HOME_TEAM_ID | in scope, state-dependent | 1 lineup/game state |
| -x | 1 | batting team id | BAT_TEAM_ID | in scope, state-dependent | 1 lineup/game state |
| -x | 2 | fielding team id | FLD_TEAM_ID | in scope, state-dependent | 1 lineup/game state |
| -x | 3 | half inning (differs from batting team if home team bats first | BAT_LAST_ID | in scope, state-dependent | 1 lineup/game state |
| -x | 4 | start of half inning flag | INN_NEW_FL | in scope, state-dependent | 1 lineup/game state |
| -x | 5 | end of half inning flag | INN_END_FL | in scope, state-dependent | 1 lineup/game state |
| -x | 6 | score for team on offense | START_BAT_SCORE_CT | in scope, state-dependent | 2 outs/destinations/RBI |
| -x | 7 | score for team on defense | START_FLD_SCORE_CT | in scope, state-dependent | 2 outs/destinations/RBI |
| -x | 8 | runs scored in this half inning | INN_RUNS_CT | in scope, state-dependent | 2 outs/destinations/RBI |
| -x | 9 | number of plate appearances in game for team on offense | GAME_PA_CT | in scope, state-dependent | 1 lineup/game state |
| -x | 10 | number of plate appearances in inning for team on offense | INN_PA_CT | in scope, state-dependent | 1 lineup/game state |
| -x | 11 | start of plate appearance flag | PA_NEW_FL | in scope, state-dependent | 6 extended |
| -x | 12 | truncated plate appearance flag | PA_TRUNC_FL | in scope, state-dependent | 6 extended |
| -x | 13 | base state at start of play | START_BASES_CD | in scope, state-dependent | 1 lineup/game state |
| -x | 14 | base state at end of play | END_BASES_CD | in scope, state-dependent | 2 outs/destinations/RBI |
| -x | 15 | batter is starter flag | BAT_START_FL | in scope, state-dependent | 1 lineup/game state |
| -x | 16 | result batter is starter flag | RESP_BAT_START_FL | in scope, state-dependent | 1 lineup/game state |
| -x | 17 | ID of batter on deck | BAT_ON_DECK_ID | in scope, state-dependent | 1 lineup/game state |
| -x | 18 | ID of batter in the hold | BAT_IN_HOLD_ID | in scope, state-dependent | 1 lineup/game state |
| -x | 19 | pitcher is starter flag | PIT_START_FL | in scope, state-dependent | 1 lineup/game state |
| -x | 20 | result pitcher is starter flag | RESP_PIT_START_FL | in scope, state-dependent | 1 lineup/game state |
| -x | 21 | defensive position of runner on first | RUN1_FLD_CD | in scope, state-dependent | 6 extended |
| -x | 22 | lineup position of runner on first | RUN1_LINEUP_CD | in scope, state-dependent | 6 extended |
| -x | 23 | event number on which runner on first reached base | RUN1_ORIGIN_EVENT_ID | in scope, state-dependent | 6 extended |
| -x | 24 | defensive position of runner on second | RUN2_FLD_CD | in scope, state-dependent | 6 extended |
| -x | 25 | lineup position of runner on second | RUN2_LINEUP_CD | in scope, state-dependent | 6 extended |
| -x | 26 | event number on which runner on second reached base | RUN2_ORIGIN_EVENT_ID | in scope, state-dependent | 6 extended |
| -x | 27 | defensive position of runner on third | RUN3_FLD_CD | in scope, state-dependent | 6 extended |
| -x | 28 | lineup position of runner on third | RUN3_LINEUP_CD | in scope, state-dependent | 6 extended |
| -x | 29 | event number on which runner on third reached base | RUN3_ORIGIN_EVENT_ID | in scope, state-dependent | 6 extended |
| -x | 30 | Responsible catcher for runner on 1st | RUN1_RESP_CAT_ID | in scope, state-dependent | 6 extended |
| -x | 31 | Responsible catcher for runner on 2nd | RUN2_RESP_CAT_ID | in scope, state-dependent | 6 extended |
| -x | 32 | Responsible catcher for runner on 3rd | RUN3_RESP_CAT_ID | in scope, state-dependent | 6 extended |
| -x | 33 | number of balls thrown in plate appearance | PA_BALL_CT | in scope, state-dependent | 6 extended |
| -x | 34 | number of called balls in plate appearance | PA_CALLED_BALL_CT | in scope, state-dependent | 6 extended |
| -x | 35 | number of intentional balls in plate appearance | PA_INTENT_BALL_CT | in scope, state-dependent | 6 extended |
| -x | 36 | number of pitchouts in plate appearance | PA_PITCHOUT_BALL_CT | in scope, state-dependent | 6 extended |
| -x | 37 | number of pitches hitting batter in plate appearance | PA_HITBATTER_BALL_CT | in scope, state-dependent | 6 extended |
| -x | 38 | number of other balls in plate appearance | PA_OTHER_BALL_CT | in scope, state-dependent | 6 extended |
| -x | 39 | number of strikes thrown in plate appearance | PA_STRIKE_CT | in scope, state-dependent | 6 extended |
| -x | 40 | number of called strikes in plate appearance | PA_CALLED_STRIKE_CT | in scope, state-dependent | 6 extended |
| -x | 41 | number of swinging strikes in plate appearance | PA_SWINGMISS_STRIKE_CT | in scope, state-dependent | 6 extended |
| -x | 42 | number of foul balls in plate appearance | PA_FOUL_STRIKE_CT | in scope, state-dependent | 6 extended |
| -x | 43 | number of balls in play in plate appearance | PA_INPLAY_STRIKE_CT | in scope, state-dependent | 6 extended |
| -x | 44 | number of other strikes in plate appearance | PA_OTHER_STRIKE_CT | in scope, state-dependent | 6 extended |
| -x | 45 | number of runs on play | EVENT_RUNS_CT | in scope, state-dependent | 2 outs/destinations/RBI |
| -x | 46 | id of player fielding batted ball | FLD_ID | in scope, state-dependent | 4 fielding credit |
| -x | 47 | force play at second flag | BASE2_FORCE_FL | in scope, state-dependent | 6 extended |
| -x | 48 | force play at third flag | BASE3_FORCE_FL | in scope, state-dependent | 6 extended |
| -x | 49 | force play at home flag | BASE4_FORCE_FL | in scope, state-dependent | 6 extended |
| -x | 50 | batter safe on error flag | BAT_SAFE_ERR_FL | in scope, state-dependent | 3 errors |
| -x | 51 | fate of batter (base ultimately advanced to) | BAT_FATE_ID | in scope, state-dependent | 6 extended |
| -x | 52 | fate of runner on first | RUN1_FATE_ID | in scope, state-dependent | 6 extended |
| -x | 53 | fate of runner on second | RUN2_FATE_ID | in scope, state-dependent | 6 extended |
| -x | 54 | fate of runner on third | RUN3_FATE_ID | in scope, state-dependent | 6 extended |
| -x | 55 | runs scored in half inning after this event | FATE_RUNS_CT | in scope, state-dependent | 2 outs/destinations/RBI |
| -x | 56 | fielder with sixth assist | ASS6_FLD_CD | in scope, state-dependent | 4 fielding credit |
| -x | 57 | fielder with seventh assist | ASS7_FLD_CD | in scope, state-dependent | 4 fielding credit |
| -x | 58 | fielder with eighth assist | ASS8_FLD_CD | in scope, state-dependent | 4 fielding credit |
| -x | 59 | fielder with ninth assist | ASS9_FLD_CD | in scope, state-dependent | 4 fielding credit |
| -x | 60 | fielder with tenth assist | ASS10_FLD_CD | in scope, state-dependent | 4 fielding credit |
| -x | 61 | unknown fielding credit flag | UNKNOWN_OUT_EXC_FL | in scope, state-dependent | 6 extended |
| -x | 62 | uncertain play flag | UNCERTAIN_PLAY_EXC_FL | in scope, state-dependent | 6 extended |
| -x | 63 | text of count as appears in event file | COUNT_TX | in scope, state-dependent | 6 extended |
| -x | 64 | whether runner on first is an automatic runner | RUN1_AUTO_FL | in scope, state-dependent | 6 extended |
| -x | 65 | whether runner on second is an automatic runner | RUN2_AUTO_FL | in scope, state-dependent | 6 extended |
| -x | 66 | whether runner on third is an automatic runner | RUN3_AUTO_FL | in scope, state-dependent | 6 extended |
