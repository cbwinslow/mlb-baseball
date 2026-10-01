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
