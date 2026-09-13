# Formulas & citations

Every rate statistic in the published backbone, its formula, and where the
definition comes from. All are computed from Retrosheet-derived counting stats
at each grain's summed numerator and denominator (see the
[grain ladder](grain-ladder.md)); each is **null when its denominator is zero**.

The counting-stat inputs (`PA`, `AB`, `H`, `SO`, `BB`, `HBP`, `SF`, `TB`, `R`,
`outs`, …) are event-classified from
[Retrosheet](https://www.retrosheet.org/) play-by-play using the same event
logic as the project's tied-out team builders.

## Batting rates

`gold.batting_season`, `gold.batting_team`, `gold.batting_career`.

| Statistic | Formula | Source of definition |
| --- | --- | --- |
| Batting average (`avg`) | \( \mathrm{AVG} = \dfrac{H}{AB} \) | [Baseball-Reference glossary](https://www.baseball-reference.com/bullpen/Batting_average) |
| On-base percentage (`obp`) | \( \mathrm{OBP} = \dfrac{H + BB + HBP}{AB + BB + HBP + SF} \) | [FanGraphs library — OBP](https://library.fangraphs.com/offense/obp/) |
| Slugging (`slg`) | \( \mathrm{SLG} = \dfrac{TB}{AB}, \quad TB = 1B + 2\cdot 2B + 3\cdot 3B + 4\cdot HR \) | [FanGraphs library — SLG](https://library.fangraphs.com/offense/slg/) |
| OPS (`ops`) | \( \mathrm{OPS} = \mathrm{OBP} + \mathrm{SLG} \) | [FanGraphs library — OPS](https://library.fangraphs.com/offense/ops/) |
| Isolated power (`iso`) | \( \mathrm{ISO} = \mathrm{SLG} - \mathrm{AVG} = \dfrac{TB - H}{AB} \) | [FanGraphs library — ISO](https://library.fangraphs.com/offense/iso/) |
| BABIP (`babip`) | \( \mathrm{BABIP} = \dfrac{H - HR}{AB - SO - HR + SF} \) | [FanGraphs library — BABIP](https://library.fangraphs.com/pitching/babip/) |
| Walk rate (`bb_pct`) | \( \mathrm{BB\%} = \dfrac{BB}{PA} \) | [FanGraphs library — plate discipline](https://library.fangraphs.com/offense/rate-stats/) |
| Strikeout rate (`k_pct`) | \( \mathrm{K\%} = \dfrac{SO}{PA} \) | [FanGraphs library — plate discipline](https://library.fangraphs.com/offense/rate-stats/) |

## Pitching rates

`gold.pitching_season`, `gold.pitching_team`, `gold.pitching_career`.
`IP = outs / 3`.

| Statistic | Formula | Source of definition |
| --- | --- | --- |
| Runs allowed per 9 (`ra9`) | \( \mathrm{RA9} = \dfrac{R \cdot 27}{outs} \) | [Baseball-Reference — RA9](https://www.baseball-reference.com/bullpen/Runs_allowed_per_nine_innings) |
| WHIP (`whip`) | \( \mathrm{WHIP} = \dfrac{(BB + H) \cdot 3}{outs} \) | [FanGraphs library — WHIP](https://library.fangraphs.com/pitching/whip/) |
| Strikeouts per 9 (`k9`) | \( \mathrm{K/9} = \dfrac{SO \cdot 27}{outs} \) | [FanGraphs library — K/9, BB/9](https://library.fangraphs.com/pitching/rate-stats/) |
| Walks per 9 (`bb9`) | \( \mathrm{BB/9} = \dfrac{BB \cdot 27}{outs} \) | [FanGraphs library — K/9, BB/9](https://library.fangraphs.com/pitching/rate-stats/) |
| Home runs per 9 (`hr9`) | \( \mathrm{HR/9} = \dfrac{HR \cdot 27}{outs} \) | [FanGraphs library — HR/9](https://library.fangraphs.com/pitching/rate-stats/) |
| Strikeout-to-walk (`k_bb`) | \( \mathrm{K/BB} = \dfrac{SO}{BB} \quad (\text{null when } BB = 0) \) | [Baseball-Reference — K/BB](https://www.baseball-reference.com/bullpen/Strikeout-to-walk_ratio) |

!!! warning "ERA is deliberately absent"
    The event-derived pitching relations do **not** produce earned-run average.
    Earned runs need reconstructed-inning logic that the Retrosheet event feed
    (`cwevent`) does not emit. `ra9` — total runs allowed per 9 innings — is the
    honest event rate. Official ERA, per player-season, is carried in the
    separate Baseball-Reference-sourced `gold.player_season` line. See
    [honest limitations](limitations.md).

## Roll-up direction

A season rate is computed from that season's summed components; a career rate
from the player's summed **combined** season rows. Rates are never averaged from
a finer grain — a career `AVG` is total career `H` over total career `AB`. See
the [grain ladder](grain-ladder.md).

## Full methodology

This page covers the classical box-score statistics in the public distribution.
The project's broader sabermetric and modeling methodology — expected-run
metrics, pitch physics, Markov simulation, calibration, and market math — is in
[`docs/THEORY_AND_METHODOLOGY.md`](https://github.com/cbwinslow/mlb-baseball/blob/main/docs/THEORY_AND_METHODOLOGY.md);
those metrics are part of the internal Engine, not the published backbone.
