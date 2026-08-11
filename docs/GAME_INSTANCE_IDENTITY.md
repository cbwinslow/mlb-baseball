# MLB game identity

## Current decision

For an MLB Stats API game, `game_pk` is the provider's game identity.  It is
the natural key for an MLB game in this project.  A doubleheader consists of
two games with two different `game_pk` values; `gameNumber` and
`doubleHeader` describe the schedule, but are not part of the key.

This corrects an earlier project assumption.  `raw.mlb_schedule` has repeated
`game_id` rows, but those rows are schedule observations, not proof of two
games.  For example, production has two final schedule observations for game
`824912` on 2026-06-16 and 2026-06-17.  Its live feed identifies one game and
records the original and resume dates.  Postponements create the same shape:
game `68185` has four postponed observations and one final makeup observation.

The authoritative MLB field guide calls `gamePk`/`pk` the unique number for a
game.  baseballr independently documents `game_pk` as the unique game
identifier and returns `gameNumber` and `doubleHeader` separately.  See
[`KNOWLEDGE_BASE.md`](KNOWLEDGE_BASE.md) for source links and review dates.

## Grain and join rules

| Relation | Grain | Correct identity rule |
|---|---|---|
| `raw.mlb_schedule` | One API schedule observation | `(game_id, observed/loaded version)` is source history; `game_id` may repeat. |
| MLB live/play-by-play/Statcast sources | Provider record within one game | `game_pk` identifies the parent MLB game. |
| `core.game` | One completed canonical game | Keep surrogate `id` for database foreign keys; make `game_pk` unique when populated by an MLB source. Retrosheet-only games may have no MLB key. |
| `gold.game_feature` / `gold.prediction` for MLB | One game / immutable prediction snapshot | Use `mlb_game_pk` as the business identity, plus model/version/timestamp where appropriate. |
| Retrosheet | One Retrosheet game | `retro_game_id` remains its provider-native identity; do not manufacture a match when a verified MLB crosswalk is absent. |

`meta.game_instance` and `game_instance_key` already exist from the earlier
01F migration work.  They are retained for historical compatibility until a
forward migration removes or repurposes them safely.  They must not be used to
claim that a schedule date plus `game_pk` defines a second MLB game.

## Required follow-up before any production core/gold rebuild

1. Add an exact `core.game` identity audit: non-null MLB `game_pk` values must
   be unique; unresolved cross-source mappings must be counted and explained.
2. Preserve schedule revisions in `raw`, and land `officialDate`,
   `originalDate`, and `resumeDate` when the Stats API supplies them.  These
   explain postponements and suspensions; they are not substitute keys.
3. Reconcile the 216 repeated-final schedule IDs against the live feed and
   Retrosheet where available.  The historical `123347` case remains an
   explicit research exception until verified, not evidence for a new key.
4. Replace direct model joins on ambiguous current-feature rows with a tested
   canonical-game relation.  This must be developed and proven in `mlb_test`
   before owner-authorized production work.

## Null policy

There must not be a blanket “no NULLs” rule.  `NULL` is correct for an
unknown/absent source value, an upcoming game's final score, an unresolved
cross-source match, or a legitimately inapplicable measurement.  Required
columns are enforced with `NOT NULL`; optional columns need a documented
reason, a coverage expectation, and a health check where they affect research
or models.

For this project specifically, every MLB-native core game should have a
non-null `game_pk`; a Retrosheet-only game may not.  We must measure that
coverage by source and era before imposing a global `NOT NULL` constraint.

## Completed-game boundary

`core.game` is a completed-facts relation. The current-season MLB schedule
writer admits only `Final`, `Completed Early`, and `Forfeit` rows. It does not
use a broad “not scheduled” rule, because an unfamiliar future status must not
silently become a completed fact. Retrosheet's game number `0` is its normal
single-game convention; `1` and `2` distinguish a doubleheader only where the
source supplies those values.
