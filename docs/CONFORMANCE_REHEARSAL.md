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

### Latest local evidence (2026-08-10)

The bounded run produced 20 matched Retrosheet games (10 each from 2008 and
2015), 1,547 Retrosheet plays, 753 current MLB plays, and 8,022 Statcast
pitches. All sampled pitches resolved to a canonical game and all sampled
plays had a valid game reference. The full schedule history intentionally
retained 180 repeated official game IDs; `core.game` had no duplicate populated
MLB keys.

Eight MLB-schedule-only canonical games remained without an MLB key. They are
known source-history ambiguity cases, including the suspended/resumed 2026
record, and correctly remain unresolved rather than being force-matched.

This run also found a production-data coverage limitation: `raw.retrosheet_team`
has team effective-date rows ending in 2021 although the landed Retrosheet game
and event feeds extend through 2024–25. This prevents safe current-era
Retrosheet team/game linking. It is an ingestion/reference-data repair task
before a production conformance recommendation—not an acceptable reason to
relax effective-date checks or guess a crosswalk.

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
