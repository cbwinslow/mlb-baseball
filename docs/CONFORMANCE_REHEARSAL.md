# Core conformance rehearsal

This is the production-safe Plan 01 gate for `raw` to `core` conformance. It
runs only against `mlb_test`; it never contacts a source or changes production
`mlb`.

## Run it

```bash
TEST_DATABASE_URL=postgresql://mlb@localhost/mlb_test \
  uv run pytest -q \
  tests/integration/test_conform.py::test_multi_source_conformance_rehearsal_ties_out_across_grains
```

The test itself loads a small source-faithful fixture, runs `mlb conform`
twice, runs `mlb audit`, and removes all fixture data afterward. It covers:

1. a 1944 Retrosheet-only game with an honest missing MLB key;
2. a 2025 doubleheader, with two distinct official MLB keys;
3. repeated postponed/final schedule observations for one 2026 key;
4. a current completed MLB-only game plus scheduled/live rows that must not
   enter `core.game`;
5. Retrosheet and MLB play-by-play records; and
6. resolved and unresolved Statcast pitches, including a retained source key.

The focused coverage regressions additionally prove that a completed historical
Spring Training schedule row enters `core.game` with its MLB key and a NULL
`retro_game_id`, that scheduled/live Spring rows remain raw-only, and that
Retrosheet's official supplemental team records resolve historical/Negro League
codes without display-name matching:

```bash
uv run pytest -q \
  tests/integration/test_conform.py::test_conform_adds_only_completed_spring_games_and_links_statcast_pitches \
  tests/integration/test_conform.py::test_conform_uses_official_supplemental_retrosheet_team_identities
```

## What it proves

- A repeated conformance run has identical `core.game`, `core.play`,
  `core.pitch`, and raw row-count snapshots.
- Raw schedule history stays intact; it is not converted into duplicate games.
- Game-level values tie out: season, date, doubleheader number, scores, teams,
  and expected weather nulls.
- Play-level values tie out: source, ordering, inning, half inning, and score.
- Pitch-level values tie out: source game key, resolved state, season,
  plate-appearance/pitch number, and player-link coverage.
- `mlb audit` has no failures. The deliberately unresolved Statcast fixture is
  a warning because its repairable source key remains present.

## Production-shaped raw sample (read-only source, `mlb_test` target)

The fixture test above is the fast regression gate. Use this second gate when
you need evidence from data already landed in a local production database. It
opens the source in a read-only transaction and refuses a target whose database
name does not contain `test`.

```bash
SOURCE_DATABASE_URL="$DATABASE_URL" \
TEST_DATABASE_URL=postgresql://mlb@localhost/mlb_test \
  uv run python scripts/rehearse_sample.py

DATABASE_URL=postgresql://mlb@localhost/mlb_test uv run mlb conform
DATABASE_URL=postgresql://mlb@localhost/mlb_test uv run mlb audit --scope statcast
```

The bounded sample includes ten safely matched Retrosheet games per available
selected historical season, all schedule observations for 2008, 2015, 2024,
2025, and 2026, plus ten completed current-season MLB games with play-by-play.
It keeps the corresponding Retrosheet events, people, MLB play-by-play, and
Statcast pitches. Raw tables are recreated only in `mlb_test`; conformance is
then run explicitly, so the source remains untouched.

To return the test database to its raw/core clean boundary without changing
migrations or metadata:

```bash
SOURCE_DATABASE_URL=unused \
TEST_DATABASE_URL=postgresql://mlb@localhost/mlb_test \
CLEAR_REHEARSAL_SAMPLE=1 uv run python scripts/rehearse_sample.py
```

### Latest local evidence (2026-08-11)

The bounded run produced 40 matched Retrosheet games (10 each from 2008, 2015,
2024, and 2025), 3,167 Retrosheet plays, 753 current MLB plays, and 14,154
Statcast pitches. Conformance produced 2,303 canonical games, 3,920 plays, and
14,154 pitches. All sampled pitches resolved to a canonical game and all
sampled plays had a valid game reference. The full schedule history intentionally
retained repeated official game IDs; `core.game` had no duplicate populated MLB
keys.

Exactly one canonical game remained without an MLB key: the then-synthetic
MLB-only row for `824912` on
2026-06-17, a retained suspended/resumed schedule-history case. It correctly
remains unresolved rather than being force-matched. A second conformance run
had identical raw and core row-count/key snapshots, proving this sample's
rebuild idempotency.

This run confirmed an upstream reference-data limitation: the official
`TEAMABR.TXT` file has not been updated since 2020 and lists the shared latest
season for active franchises as 2021, although landed Retrosheet game/event
data extends through 2024–25. Raw retains that official value exactly. During
conformance, the file's shared maximum is deliberately treated as open-ended
for active franchises; historical intervals remain exact. The production-shaped
sampler mirrors that proven rule so modern Retrosheet linkage is tested rather
than accidentally excluded. This is a documented upstream limitation, not a
reason to overwrite raw data or guess crosswalks.

The rehearsal also copies the compact `raw.mlb_team_history` reference table.
Its stable numeric IDs resolve the current name differences that Retrosheet
cannot express literally: Tampa Bay Rays/Devil Rays, Los Angeles Angels/Anaheim
Angels, and Athletics/Oakland Athletics. After this crosswalk, the only 2026
sample team links left null are 34 away and 6 home roles in exhibition or
All-Star games involving national, college, minor-league, or All-Star teams.
Those entities are outside the MLB-team contract and are retained without a
guessed `core.team` identity.

## Optional baseballr comparison

This repository does not install or require R. If an investigator already has
R and baseballr, export a same-date independent schedule reference:

```bash
Rscript scripts/validate_baseballr_schedule.R 2025-04-01 /tmp/baseballr-2025-04-01.csv
```

Compare only like-for-like fields: official game key, official date, game
number, doubleheader flag, and team names. The official MLB API and retained
project fixture remain the reproducible test evidence. A difference is not a
failure until it is classified as source history, provider timing/definition,
an expected null, an unresolved crosswalk, a fixture issue, or a real defect.

## Before requesting production approval

1. Run this rehearsal and the full test suite against `mlb_test`.
2. Run `mlb audit --scope game` against `mlb_test` after a representative
   conformance run; resolve every failure and record every warning.
3. Keep the production raw Statcast-to-schedule audit result with the request.
4. Obtain explicit owner approval before migrating or conforming production.
