# Differential validation (tasks 5.1-5.4)

Measured 2026-10-01. `retrosheetpy.crosswalk` derives the fields that follow
from one play string alone (event type, hit kind, bunt, batted-ball type,
steal/pickoff/wild-pitch flags, hit location). `retrosheetpy.validation`
compares them with two independent references, game by game:

- **Chadwick `cwevent` 0.10.0**, run on the same event files (dev-only; the
  adapter is `tests/chadwick_reference.py`, absent tool = clean skip).
- **Retrosheet's yearly `plays.csv`** (field meanings from
  `retrosheet.org/downloads/csvcontents.html`).

Fields that need game state (outs, base state, runs, RBI, putouts/assists) are
out of scope here and are Slice B work.

## Results

Rules were first tuned on 2019, 1915, 1950 and 1985, then run unchanged on seasons
never used for tuning.

| Season | Role | Events compared (Chadwick) | Chadwick mismatches |
| --- | --- | ---: | ---: |
| 2019 | tuned | 192,025 | 0 |
| 1915 | tuned | 147,799 | 0 |
| 1950 | tuned | 98,727 | 0 |
| 1985 | tuned | 166,546 | 0 |
| 1932 | held out | 99,313 | 0 |
| 1976 | held out | 153,958 | 0 |
| 1999 | held out | 196,563 | 0 |

No game failed to line up one-to-one with Chadwick's rows. The 8 fixture games
(1909-2007, including deduced, Negro League, all-star, post-season and
`presadj`/`ladj` games) also match, with captured output in CI.

## Disagreements that remain (reported, not resolved)

Against all 198,202 rows of the 2019 `plays.csv`, 40 plays disagree with the event
text. Chadwick agrees with the text on every one of them except where noted.

| Kind | Plays | What happens |
| --- | ---: | --- |
| `/FO` with an explicit `/F...` modifier (e.g. `54(1)/FO/F5D`) | 33 | CSV says ground ball; text and Chadwick say fly. |
| `FC.../F...` (e.g. `FC8/F8RS.1X2(85)`) | 2 | Same: CSV says ground ball. |
| `K/BF` | 4 | Chadwick says bunt; CSV `bunt` = 0 and `hittype` empty. |
| Hit location `13S` (`16/L13S`) | 1 | CSV normalises it to `13+`. |

The post-season fixture adds two location cases (`3L` -> `3+`, `56D` -> `56+`), pinned
in `test_reference.py` as known differences.

## Rules learned from the reference output (not in Retrosheet's published text)

- `cwevent` gives event code 8 for both `PO` and `POCS`; code 7 never occurred.
- `5E3` (fielder, then an error) is a generic out (2) for Chadwick; plain `E3` is 18.
- `POCS2` marks the runner on first as picked off and caught stealing (Chadwick);
  the CSV books it as a caught stealing only.
- `BGDP`/`BPDP` are bunts; `K/BF` is a bunt in Chadwick; `F` with `/IF` is a pop-up.
- Chadwick and the CSV infer a batted-ball type or location when the text has none;
  those are not derivable from the text, so they are not compared.

## Newly found unsupported syntax (visible, not skipped)

Not in the earlier 4.5 sample: modifier `B` (47 plays in 1976, e.g. `13/SH/B.2-3;1-2`)
and `B1S` (1 play in 1985). They are reported by `PlayCoverage`; meaning not guessed.

## Reproduce

```
uv run --package retrosheetpy python -m retrosheetpy.report FILES... \
    --chadwick-csv cwevent.csv --chadwick-version 0.10.0 --plays-csv 2019plays.csv
```

Captured fixtures: `tests/reference/chadwick/` (`capture.py`, with manifest and
fixture hashes) and `tests/reference/retrosheet_csv/` (`capture_csv.py`).
