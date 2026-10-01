# Results and rules learned

Equality target: `cwevent` 0.10.0, `-f 0-96 -x 0-66`, run on event files with an empty
team file (see `field-table.md`). Rules below were found by comparing our rows with
Chadwick's output; each lists a play that showed it. No Chadwick code was copied.

## Validated seasons

| Season | Fields compared | Plays | Mismatches | Misaligned games |
|---|---|---|---|---|
| 2019 | 50 (groups 1-2, RBI) | 192,025 | 0 | 0 |

## Rules learned from Chadwick output

- **Count unknown (`?`)**: balls and strikes read as 0. (any 1920s file)
- **Responsible batter**: an `NP` line with a count of 3 balls or 2 strikes makes that
  batter responsible for a strikeout or walk finished by a pinch hitter; a lower count
  does not. (`NP` with count 22 then `K`: 2007 fixture; count 01 then `K`: MIN201906140)
- **Responsible pitcher**: a reliever is not charged with a walk when he entered on a
  count of 2-0, 2-1, 3-0, 3-1 or 3-2 (balls > strikes, at least 2); other plays use the
  pitcher on the field. (ARI201908200 vs MIA201905030)
- **`badj` hand**: applies to one plate appearance; `RESP_BAT_HAND_CD` always shows it,
  `BAT_HAND_CD` only if the named player is the batter. (WAS201904020)
- **Pinch hitter/runner**: a substitute for the DH becomes the DH (position 10). A pinch
  hitter is flagged on his first plate appearance only, and the flag is dropped when the
  half-inning ends. A batting pinch runner or an already-batted pinch hitter has
  position 0. (ANA201908300, CLE201905160, OAK201905090)
- **Pinch runner**: takes over the base of the player he replaced. (ladj fixture)
- **Out advance with an error**: `1X3(4E6)` is safe; `1XH(E1)(72)` (error plus a fielding
  credit) is still out. (TOR201904*, CLE201905040)
- **Unearned run**: `(UR)` makes the destination 5, `(TUR)` 6, also on `SBH(UR)`.
- **Third out**: when the inning ends on the play, runners not mentioned keep their
  base number (even if two share one); no forced advance is applied. (`5(2)/FO` with 2 outs)
- **Caught stealing/pickoff with an error** (`POCS2(1E3)`): the runner is safe at the
  target base.
- **Leadoff flag**: true for every row until a plate appearance is completed in the
  half-inning (so it stays true after a foul fly error). (ATL201904010)
- **Foul flag**: foul fly error, `FL`, or a hit location containing `F`.
- **RBI**: runs scored, minus `(NR)`, plus `(RBI)`; none by default on strikeouts,
  ground-ball double plays, or non-batter events; after an error only the runner from
  third counts by default.
- **Fielded-by (`FLD_CD`)**: first fielder of the play; 0 for strikeouts and home runs.
- **Putouts and assists**: per out, each fielder who threw to a *different* fielder gets
  one assist and the last fielder gets the putout; in a chain the fielder who made one out
  throws for the next (`64(1)3`: assists 6, 4; putouts 4, 3). Assists are not de-duplicated
  across outs (`CSH(13253)/DP.1X3(34)` credits fielder 3 twice). An unassisted `3(1)3` has no
  assist. A strikeout earns no putout when the batter reaches (`K+WP.B-1`).
- **Errors**: `5E3` is type D (dropped) with an assist to 5; `E5` is F; `/TH` makes T.
  An error inside a fielding string (`2X3(5E4)`) gives assists to the fielders before it.
  After a runner-only event (`SB`, `WP`, `OA`) a bare `(E4)` is D; for pickoffs `E1`/`E2`
  are T and others D.
- **Play text (`BAT_PLAY_TX`, `RUN*_PLAY_TX`)**: the fielders of each out, e.g. `63`, `64`
  for `64(1)`; in a chain the fielder who made one out is carried into the next but not listed
  twice (`3(1)3(B)` gives `3` and `3`; `4(1)3` gives `4` and `43`). A strikeout gives `2` (or the
  fielders given), blank if the batter reaches. A batter who reaches on `5E3` gets `5E3`; plain
  `E5` and `S6.B-2(E6/TH)` stay blank. Caught stealing, pickoffs and out advances keep the
  parenthesised text, a fielding credit winning over an error (`BX3(E9)(95)` gives `95`) but
  a lone error stays (`PO1(E1)` gives `E1`). (BAL201906250, MIN201908100, CLE201905040)
- **Pinch hitter fields**: the removed batter is the player the pinch hitter replaced and its
  position is the one that player came in at (a pinch runner who took the DH slot counts as DH,
  a pinch hitter who replaced another pinch hitter as 11, and a pinch hitter who has batted
  as the position he now holds). (ANA201904180, MIN201905120, BAL201904060)
- **Pinch runner fields**: flagged only on the first play after the substitution, with the
  runner he replaced. A substitution in a finished half-inning is not flagged.
- **Responsible pitcher of a runner**: the pitcher charged when he reached. A runner retired
  on a ground ball (a fielder's choice or a forced out written `n(m)`) passes his pitcher back
  to the runners behind him: those still on base, lead first, take the pitchers of the
  runners who were on base before the play (scored runners drop out), so a batter who
  reaches ends up with the pitcher of the runner he replaced. A hit that retires a runner
  and a fly-ball double play (`8/DP.2X2(84)`) do not shift. (ANA201904230, SLN201909280,
  KCA201903310, CHA201905270, DET201908150)
- **`presadj,pitcher,base`**: sets the responsible pitcher of the runner on that base
  (fixture `presadj`, a 1919 game).
- **Batted ball with no trajectory in the text** (`BATTEDBALL_CD`): a fielder's choice or an
  error is `G` (`F` if an outfielder made the error); `FLE` is `P` (`F` for an outfielder);
  an out is `P` on `/IF`, `G` on a sacrifice bunt, a force `n(m)` or more than one fielder,
  otherwise `F`; `/LDP` is `L` and `/GDP`, `/GTP`, `/FO` are `G`. Other plays stay blank.
  (NYN201908200, ARI201905180, HOU201905220)

## Extended fields (`cwevent -x 0-66`), 2019: 0 mismatches over 192,025 plays

- **Counters count plays before this one**: `GAME_PA_CT`, `INN_PA_CT` and `INN_RUNS_CT` are the
  team's completed plate appearances, the half-inning's plate appearances and its runs
  *before* the play; `FATE_RUNS_CT` is the runs scored in the rest of the half-inning,
  not counting this play. `INN_END_FL` is the last play of a half-inning in the file.
- **`PA_NEW_FL`** is `T` unless the previous play was a non-batter event of the same half
  (a steal, wild pitch ...). **`PA_TRUNC_FL`** is `T` for every non-batter play after the last
  batter event of a half-inning (the plate appearance never finished).
- **Pitch splits (33-44)** come from this play's `PITCH_SEQ_TX` only: `B` called ball, `I`
  intentional, `P` pitchout, `H` hit batter (each also a ball), `V` an "other" ball that is
  *not* counted in the ball total; strikes `C` called, `S M Q` swinging, `F L O R T` foul,
  `X Y` in play, `K` other. `1 2 3 . * + > N` count nothing. (`I Q R Y K` never occur in
  2019: assumed, to be confirmed on older seasons.)
- **Force flags** are set only by a `/FO` or `/GDP` out: the base after each runner retired
  in the fielding chain who was forced (every lower base occupied). With no chain marker
  (`FC1/FO.2X3(1E5)`) the out advances are used. `/DP`, `/GTP` and strikeouts set nothing.
  (HOU201905220, BAL201908190, MIN201904300, NYN201907280)
- **Batter safe on error**: a first event `E`, or a fielded out whose `BX` advance has an
  error in its parentheses (`36(1)/FO/G3.2-3;BX1(6E1)`). Not for hits with `BX2(74)`.
- **Runner lineup/position**: lineup slot of the runner; position is the one he was listed at
  when he reached (a pinch hitter 11, a pinch runner 12), shown as 0 unless a pinch hitter is
  batting now (Chadwick: `ph_flag`); a pinch runner for the DH is 10. (ANA201904090, ANA201909260)
- **Responsible catcher** travels with the runner like the responsible pitcher, including
  the shift back after a retired runner (PIT201909050, SFN201909240).
- **`PIT_START_FL`** is true only for a pitcher who started the game *as pitcher*; a position
  player who pitches is `F` (ANA201907250). `BAT_START_FL` is true for any starter.
- **`UNKNOWN_OUT_EXC_FL`**: a `99` fielding unknown anywhere in the play (`CS2(99)`,
  `BX2(99)`); **`UNCERTAIN_PLAY_EXC_FL`**: a `#` marker (fixtures `ladj`, `deduced`).
- **Automatic runner (2020+)**: `radj,player,base` comes before the first play of an extra
  half-inning (after the pitcher sub). The runner starts that half on the base, charged to the
  pitcher and catcher then on the field, `RUN_n_AUTO_FL` true, origin event 0. A pinch runner
  substituted before the first play takes over his base, is flagged `PR_RUN` with the runner he
  replaced, and keeps the auto mark. The auto mark travels with the responsible pitcher/catcher
  when exactly one runner is retired and the others shift back (batter on a fielder's choice
  inherits it); after a double play the survivors do not inherit it (SLN202107210, TEX202108190).
  (BAL202008010, CHN202009160, ANA202009040; 2020 full season 0 mismatches)
- **Responsible batter, refined**: a pinch hitter finishing a count is not charged only when the
  announced count has 2 strikes (strikeout) or 3 balls (walk). `NP` at 2-2 then a walk by the
  pinch hitter charges the pinch hitter (SEA202008190); 2019 still 0 mismatches.
- **Pitcher who bats in the DH slot**: a player already in the game (the pitcher) who pinch
  runs for the DH leaves the pitcher slot, takes the DH batting slot, and is listed 0, not 10
  (CIN202007260).

## 2021: first held-out season (11 mismatches, fixed by rule; 2021 is now tuned, not held out)

- **Force flag, no chain marker**: the out-advance fallback is for a fielder's choice only
  (`FC1/FO.2X3(1E5)`). `43/GDP.1X2(364)` sets nothing (CHN202104250).
- **Caught stealing safe on an error with (UR)**: the runner's destination is 5 (unearned run),
  like a steal of home (CHA202108270 `CSH(13E4)(UR)`).
- **Error on an advance after a pickoff**: coded `D`, as for other runner events
  (SLN202104080 `PO2(E1/TH).2-H(E8)(NR)`).
- **Full count, pinch hitter**: a strikeout at 3-2 still charges the batter who started the count
  (SLN201907150, 2019); a walk at 3-2 charges the pinch hitter (MIN202107110).
- **Intentional walk after a pitching change at 2-0 or worse** charges the earlier pitcher,
  like an ordinary walk (PHI202104040).
- **Auto mark after a double play**: runners already on base inherit it, the batter does not
  (MIN202108160; SLN202107210 and TEX202108190 still hold).

## 2022 (Ohtani and the pitcher-responsibility remap): 2019-2022 all 0 mismatches

- **Two-way player (2022+ DH rule)**: a player may start in both the pitcher slot (0) and a DH
  slot. A start record that lists him twice keeps both. His batting slot is the lowest one,
  slot 0 last (`BAT_LINEUP_ID`, on-deck and in-hold follow). When the pitcher leaves, the DH stays.
- **`badj` hand** shows in `RESP_BAT_HAND_CD` only when the named player is the batter or the responsible
  batter (ARI202208100: the named pinch hitter was replaced before batting, so `?`; 2007 fixture: the named pinch hitter batted, the starter was responsible, shown).
- **Pitcher/catcher/auto mark shown per base** (read in Chadwick `gameiter.c` for understanding,
  then confirmed by output): when the runner on third is retired on a fielder's choice and the
  runner from second scores, the runner on second shows third's pitcher and the runner on first
  shows second's (NYN202207220, SEA202207100). `_charged_base` in `state.py`.
- **Auto mark after a double play**: a runner put out by an advance (`3XH(...)`) rather than in
  the fielding chain does not pass the mark on; one retired in the chain does (SLN202107210,
  TEX202108190 no; MIN202108160, TOR202208290 yes). A fielder's choice with no chain marker
  counts its out advances as chain.
- **Assists**: every fielder but the last assists once; one fielder alone has none
  (`POCS3(1655)`: assists 1, 6, 5; OAK202205030).
- Walk charged to the earlier pitcher: Chadwick sets it when a pitching sub follows a play with
  count 2-0, 2-1 or 3-x (`state.walk_pitcher`), and our NP-count rule matches that.

## 2023-2024: 2019-2024 all 0 mismatches

- **Pitcher/catcher/auto handoff is Chadwick's retire-and-reassign, not "shift survivors"**
  (read in `gameiter.c` for understanding; own code in `_advance_runners`). Bases are processed
  from third down. A runner retired on a force or fielder's choice (`_fc_bases`: a chain marker
  `(n)`, not when the first marker is the batter's `(B)` unless the play is a GDP; for an `FC`
  event the out advances) hands his pitcher, catcher and auto mark to the next occupied base
  below, which hands its own down in turn, down to the batter. Scorers stay in the chain until
  they leave. This replaced the earlier survivor-pool rules (which approximated it).
- **Pitch `A`** (2023 automatic strike) is an "other" strike (`PA_OTHER_STRIKE_CT`) but not a
  pitch thrown (`PA_STRIKE_CT`).
- **An NP line counts only in the half-inning it was seen in**: a plate appearance cut short by
  the third out (a caught stealing) must not make the next half's batter "charged" to it
  (COL202406160, five plays in 2024).
