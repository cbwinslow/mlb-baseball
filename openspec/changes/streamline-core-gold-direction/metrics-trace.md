# Metric-to-source trace (task 0.5) — DRAFT, first pass

Written 2026-10-09 from `meta.metric` (50 documented metrics: 38 gold, 12 model) and the
`core.play` / `core.pitch` column lists. The `data_source` text in `meta.metric` is the
input list; it is hand-written, so each row is confirmed against the code when its core
addition is actually designed.

## What the data says

| Where the metric reads from | Metrics |
| --- | --- |
| `raw.retrosheet_event` directly | 21 |
| `raw.statcast_pitch` directly | 8 |
| other `raw.*` tables directly (FanGraphs guts/park factors, Statcast OAA, sprint speed, framing) | 5 |
| `core` / `gold` only | 11 |
| nothing (caller-supplied numbers) | 5 |

**29 of 45 metrics that read data skip `core` and read `raw` directly.** The reason is the
shape of `core`: `core.play` has 19 columns and `core.pitch` has 19, while the raw tables
have 168 and 122. A metric that needs one more field goes to `raw`.

This is the evidence for the metrics-first rule (decision 10): the missing `core` columns
are not a guess, they are the fields existing metrics already read from `raw`.

## Fields metrics read from raw that `core` lacks (from the `data_source` text)

`raw.retrosheet_event` → `core.play` (has: event code/description, batter, pitcher, inning,
half, scores, balls/strikes/outs):

| Missing field | Used by |
| --- | --- |
| `pitch_seq_tx` (pitch sequence) | pitch_discipline |
| `battedball_cd` (trajectory) | team_batted_ball_profile, pitcher_estimators |
| `bat_hand_cd`, `resp_bat_hand_cd` (handedness) | pitcher_estimators |
| base runners (`run1/2/3` ids and states) and base-out state | comprehensive_baserunning, run_expectancy_24, win_expectancy, leverage |
| fielder and play-detail codes | catcher framing, bullpen workload |

`raw.statcast_pitch` → `core.pitch` (has: type, name, speed, spin rate, launch speed/angle,
hit distance, description, event):

| Missing field | Used by |
| --- | --- |
| `vy0`, `ay`, `vz0`, `az` (kinematics) | starter_vaa |
| `pfx_z`, `zone`, `plate_x`, `plate_z` (location/movement) | pitcher_command_attack_zones, pitch_movement_profile, strike_zone density |
| `release_pos_x/z`, `vx0`, `ax` | pitch_tunneling_engine |
| `arm_angle` | arm_slot_engine |
| `estimated_ba_using_speedangle`, `bb_type`, batter stand | babip_luck_scanner, statcast_expected |

## Proposal (not yet decided)

1. Add the fields above to `core.play` and `core.pitch` in `conform`, driven by this list, not
   by "everything". Each addition needs a migration, a run-twice test and a parity check.
2. Move the 21 + 8 direct-`raw` metrics to read `core`, one at a time, after their fields
   exist. This also lets them run on `core`'s identity-resolved game and player keys.
3. Leave the 5 `raw`-only reference inputs (FanGraphs, OAA, sprint speed, framing) as source
   tables; they are season tables with their own keys.

## Open

- Validate each row against the code before its core change (this table is from docs).
- Rights: Statcast is `local_research` per its source profile, so adding its fields to
  `core` must respect that profile (`docs/SOURCE_RIGHTS.md`).
- The 99 raw tables no non-ingest code reads are not covered by this trace. A table with no
  metric asking for it stays in `raw`.
