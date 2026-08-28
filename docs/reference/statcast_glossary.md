# Statcast metric definitions for Engine-package WIRE work

Quoted definitions are from MLB/Statcast glossary pages. Input columns
are this project’s `raw.statcast_pitch` (pybaseball’s ~119-column Savant
export) unless noted. **Statcast is `local_research` only**
(`docs/SOURCE_RIGHTS.md`). Do not put these on a public page without a
recorded license.

A WIRE of VAA / barrel / xwOBA should expose **these published metrics**,
not an invented composite on top, unless the composite’s weights are
cited or fit (Bucket B rubric).

| Metric | Published definition (source) | Our inputs |
|---|---|---|
| **Barrel** | “The Barrel classification is assigned to batted-ball events whose comparable hit types (in terms of exit velocity and launch angle) have led to a minimum .500 batting average and 1.500 slugging percentage since Statcast was implemented Major League wide in 2015.” At 98 mph, 26–30°; the angle window widens as EV rises. [MLB glossary](https://www.mlb.com/glossary/statcast/barrel) | `launch_speed`, `launch_angle` (or Savant’s `barrel` flag if present on the row) |
| **Hard-hit** | Batted balls with exit velocity ≥ 95 mph. [MLB glossary: Hard-hit Rate](https://www.mlb.com/glossary/statcast/hard-hit-rate) | `launch_speed` |
| **Sweet spot** | Launch angle 8–32°. [MLB glossary: Sweet Spot](https://www.mlb.com/glossary/statcast/sweet-spot) | `launch_angle` |
| **Exit velocity (EV)** | Speed of the batted ball off the bat, mph. [MLB glossary](https://www.mlb.com/glossary/statcast/exit-velocity) | `launch_speed` |
| **Launch angle (LA)** | Vertical angle of the batted ball, degrees. [MLB glossary](https://www.mlb.com/glossary/statcast/launch-angle) | `launch_angle` |
| **xBA / xSLG / xwOBA** | Statcast expected batting average / slugging / wOBA from quality of contact (EV, LA, and in xwOBA sprint speed on some versions). [xBA](https://www.mlb.com/glossary/statcast/expected-batting-average), [xSLG](https://www.mlb.com/glossary/statcast/expected-slugging-percentage), [xwOBA](https://www.mlb.com/glossary/statcast/expected-woba) | Player-season: `raw.statcast_batter_expected` / `raw.statcast_pitcher_expected`. Pitch-level: do not invent a second x-model; use Savant’s values when landed, or EV/LA bins we estimate ourselves and **do not name xwOBA**. |
| **IVB (induced vertical break)** | Vertical movement of the pitch relative to a no-spin trajectory, typically inches, Statcast `pfx_z`. Physical background: Alan Nathan, pitch-movement notes (THEORY bibliography). | `pfx_z` (feet in the raw file — convert ×12 for inches) |
| **HB (horizontal break)** | Horizontal movement, Statcast `pfx_x`. | `pfx_x` |
| **VAA (vertical approach angle)** | Angle of the pitch path as it crosses the front of home plate, degrees (usually negative). Not an MLB glossary entry; used in public pitching research (e.g. Driveline / Baseball Savant trajectory). Approximate from release and plate height over the 50-ft flight. | `release_pos_z`, `plate_z`, `release_extension` / `release_pos_x` as needed. Engine `vaa.py` currently takes CLI numbers — WIRE means compute this from `raw.statcast_pitch`, drop the invented “flatness index” unless fitted. |
| **HAA (horizontal approach angle)** | Same idea, horizontal. | `release_pos_x`, `plate_x` |
| **Active spin / spin efficiency** | Fraction of spin that is useful (transverse) vs gyro. Statcast publishes `spin_axis` / active-spin estimates on some leaderboards. | `release_spin_rate`, `spin_axis`, `pfx_x`, `pfx_z`. Do not name a project number “Statcast active spin” unless it matches Savant’s published method. |
| **Attack zone** | Heart / Shadow / Chase / Waste, Statcast zone map (Petriello). | `plate_x`, `plate_z`, `zone` |
| **Spray / hit coordinates** | Landing location on the field. | `hc_x`, `hc_y` — **not yet on `core.pitch`** (BAT-01 proposal). Public spray charts are `local_research` until rights change. |

When a WIRE package only needs the published metric (VAA in degrees, barrel
flag, chase%), put **that column** on `gold.game_feature`. Keep any
acronym score as display/derived and out of `gbm.FEATURE_COLUMNS` until it
beats Elo on a chronological holdout.
