# retrosheet_schedule.py DOX

## Purpose

Own Retrosheet's planned-schedule product: one source row per scheduled game,
including postponement and makeup information.

## Ownership

Source implementation: `retrosheet_schedule.py`.

Owned raw relation: `raw.retrosheet_schedule`.

Registry source name: `retrosheet_schedule`.

Focused integration test: `tests/integration/test_retrosheet_schedule_load.py`.

## Source and Coverage Contracts

- Source archive: `retrosheet.org/schedule/schedule.zip`.
- Coverage currently spans historical schedules from the late 19th century
  through the published current/future schedule files.
- Each `{year}schedule.csv` is already headered.
- The source repeats column labels `League` and `Game` for visitor and home sides.
  The connector renames only those ambiguous duplicate headers to
  `visitor_league`, `visitor_game`, `home_league`, `home_game`; this is a clarity
  fix, not semantic normalization of source values.
- `_season` is derived from the member filename.

## Runtime Contracts

- This is a small whole-archive snapshot.
- `bootstrap()` and `update()` both full-reload the relation.
- Download is manifest-tracked before parsing.
- All schedule CSV members are concatenated into one source-faithful DataFrame.
- Reruns replace the snapshot and remain idempotent.

## Time and Identity Context

A scheduled game is an observation of planned state, not automatically the final
canonical game identity. Postponements, makeups, doubleheaders, suspended games,
and provider-native IDs must be reconciled downstream without overwriting the
source schedule evidence.

Do not infer a completed-game fact from schedule presence alone.

## Verification

Run:

```bash
uv run pytest tests/integration/test_retrosheet_schedule_load.py -q
uv run ruff check mlb_baseball/connectors/retrosheet_schedule.py tests/integration/test_retrosheet_schedule_load.py
```

When changing column renames, verify both visitor/home duplicated source headers
map to distinct stable raw columns.
