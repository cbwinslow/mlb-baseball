# Grain ladder

The statistic backbone provides a batting relation and a pitching relation at
every grain a sabermetric researcher expects. Figures at a coarser grain are
**rolled up from the finer grain**, and every rate is **recomputed from the
summed numerator and denominator** — never averaged from finer-grain rates.

<figure markdown="span">
<svg viewBox="0 0 760 470" role="img" aria-labelledby="ladder-title ladder-desc"
     style="max-width:760px;width:100%;height:auto;color:var(--md-default-fg-color)">
  <title id="ladder-title">The grain ladder</title>
  <desc id="ladder-desc">The game-grain relation rolls up into per-stint season
  lines, a combined season line, and a team-season line; the combined season
  line rolls up into the career line.</desc>
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7"
            markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0 L10 5 L0 10 z" fill="currentColor"/>
    </marker>
  </defs>
  <g fill="none" stroke="currentColor" stroke-width="1.5">
    <path d="M380 96 C380 130 130 120 130 168" marker-end="url(#arrow)"/>
    <path d="M380 96 L380 168" marker-end="url(#arrow)"/>
    <path d="M380 96 C380 130 630 120 630 168" marker-end="url(#arrow)"/>
    <path d="M380 262 L380 350" marker-end="url(#arrow)"/>
  </g>
  <g font-size="12.5" text-anchor="middle" fill="currentColor">
    <g>
      <rect x="250" y="26" width="260" height="70" rx="8"
            fill="currentColor" fill-opacity="0.06" stroke="currentColor"/>
      <text x="380" y="46" font-weight="700">Game</text>
      <text x="380" y="64">batting_game / pitching_game</text>
      <text x="380" y="80" fill-opacity="0.75">one line per (game, player, team); counting stats only</text>
    </g>
    <g>
      <rect x="20" y="170" width="220" height="92" rx="8"
            fill="currentColor" fill-opacity="0.06" stroke="currentColor"/>
      <text x="130" y="192" font-weight="700">Season, per stint</text>
      <text x="130" y="210">batting_season / pitching_season</text>
      <text x="130" y="228" fill-opacity="0.75">is_combined = false</text>
      <text x="130" y="246" fill-opacity="0.75">one line per (player, season, team)</text>
    </g>
    <g>
      <rect x="270" y="170" width="220" height="92" rx="8"
            fill="currentColor" fill-opacity="0.06" stroke="currentColor"/>
      <text x="380" y="192" font-weight="700">Season, combined</text>
      <text x="380" y="210" fill-opacity="0.75">is_combined = true, team = NULL</text>
      <text x="380" y="228" fill-opacity="0.75">one line per (player, season)</text>
      <text x="380" y="246" fill-opacity="0.75">a traded season, counted once</text>
    </g>
    <g>
      <rect x="520" y="170" width="220" height="92" rx="8"
            fill="currentColor" fill-opacity="0.06" stroke="currentColor"/>
      <text x="630" y="192" font-weight="700">Team season</text>
      <text x="630" y="210">batting_team / pitching_team</text>
      <text x="630" y="228" fill-opacity="0.75">one line per (team, season)</text>
    </g>
    <g>
      <rect x="270" y="352" width="220" height="82" rx="8"
            fill="currentColor" fill-opacity="0.06" stroke="currentColor"/>
      <text x="380" y="374" font-weight="700">Career</text>
      <text x="380" y="392">batting_career / pitching_career</text>
      <text x="380" y="410" fill-opacity="0.75">one line per player</text>
      <text x="380" y="426" fill-opacity="0.75">summed from the combined season rows</text>
    </g>
  </g>
</svg>
</figure>

## Rules the ladder enforces

- **Roll-ups flow one direction.** A season line is aggregated from the
  game-grain relation; a career line is aggregated from the season relation's
  **combined** rows, so a player traded mid-season is counted once. A relation
  is never built from a sibling relation at the same grain.
- **Rates are recomputed, not averaged.** A career batting average is
  `total career H / total career AB`, not the mean of the season averages. A
  season K% is `total SO / total PA`. Averaging already-computed rates would
  over-weight low-denominator lines (an 18-PA September call-up would count as
  much as a 700-PA regular).
- **A rate is null when its denominator is zero** — never `0`, never an error.
- **Counting stats at the game grain only.** `batting_game` / `pitching_game`
  carry `PA`, `AB`, `H`, `SO`, `BB`, … but no `AVG` / `OBP` / `ERA`: a rate over
  one game's denominator is noise. Rates appear at the season, team, and career
  grains where the denominator is meaningful.
- **Team is part of the key at the game grain.** A player who appears for both
  clubs in one `game_id` (a suspended game resumed after a trade) gets two rows,
  not a collision.
- **Two-way players appear in both relations** at every grain.

## A traded season, worked

A player who plays for two teams in 2024 has, in `batting_season`:

| `team_id` | `is_combined` | meaning |
| --- | --- | --- |
| TEAM A | `false` | the stint line for team A |
| TEAM B | `false` | the stint line for team B |
| `NULL` | `true` | the full-season line — its counting stats equal the sum of the two stint lines, and its rates are recomputed from those sums |

`WHERE is_combined` always yields exactly one full-season line per player, which
matches Baseball-Reference's `2TM` / `3TM` row. A one-team player's combined line
equals their single stint.

See the [data dictionary](data-dictionary.md) for the column list at each grain
and the [formulas](formulas.md) page for each rate's definition.
