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
