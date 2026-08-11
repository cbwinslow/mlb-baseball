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
