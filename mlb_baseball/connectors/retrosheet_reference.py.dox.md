# retrosheet_reference.py DOX

## Purpose

Own Retrosheet reference/dimension products used for parks, teams, people,
coaches, managers, umpires, and relatives.

## Ownership

Source implementation: `retrosheet_reference.py`.

Owned raw relations include:

- `raw.retrosheet_park`
- `raw.retrosheet_team`
- `raw.retrosheet_biofile`
- `raw.retrosheet_biofile0`
- `raw.retrosheet_coach`
- `raw.retrosheet_relative`
- `raw.retrosheet_ballpark`
- `raw.retrosheet_coach0`
- `raw.retrosheet_manager`
- `raw.retrosheet_team0`
- `raw.retrosheet_umpire`

Registry source name: `retrosheet_reference`.

Focused integration test: `tests/integration/test_retrosheet_reference_load.py`.

## Source Contracts

Inputs are distinct official Retrosheet reference products:

- `parkcode.txt`
- `TEAMABR.TXT`
- `biofile.zip`
- `biodata.zip`

Several similarly named files have materially different schemas. Raw preserves
those products separately instead of silently merging superficially similar
records.

`TEAMABR.TXT` has a fixed six-field source layout. Its published latest-year
values may be stale/shared for current franchises; raw preserves that source fact,
while canonical core interpretation can treat the shared max year as open-ended
when justified.

## Runtime Contracts

- These are whole-file reference snapshots.
- `bootstrap()` and `update()` both full-reload the current downloaded reference
  set.
- Downloads are manifest-tracked before parsing.
- `biofile0.csv`/`relatives.csv` duplication across source archives should not
  cause duplicate raw tables; fetch each semantic source table once.
- Parser/source variants remain separate if their column meanings differ.
- Commit occurs after the reference set is loaded; run tracking records combined
  rows.

## Downstream Context

These are important identity and dimension inputs for canonical player/team/venue
reconciliation. Preserve Retrosheet IDs and source-specific temporal fields.

Do not make a name match authoritative when a stable Retrosheet or Chadwick ID is
available. Do not discard older aliases/reference variants simply because another
source has a more current display name.

## Verification

Run:

```bash
uv run pytest tests/integration/test_retrosheet_reference_load.py -q
uv run ruff check mlb_baseball/connectors/retrosheet_reference.py tests/integration/test_retrosheet_reference_load.py
```

When adding a member from `biofile.zip`/`biodata.zip`, verify it is genuinely new
or schema-distinct rather than a byte-for-byte duplicate already represented.
