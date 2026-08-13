# Raw → core → gold field census runbook

Run this read-only command before proposing a new feature family:

```sh
DATABASE_URL=postgresql://.../mlb_test uv run mlb field-census --exact \
  --output-json artifacts/census/mlb_test.json \
  --output-markdown artifacts/census/mlb_test.md
```

`--exact` scans each landed raw field for its null count, distinct count, and
available season range. It is appropriate for `mlb_test` and an intentional,
operator-approved production read-only evidence run; it may be expensive on a
fully populated database. Without `--exact`, relation counts and field
null/distinct figures are PostgreSQL catalog estimates and must be labeled as
such.

The command opens a repeatable-read, read-only PostgreSQL transaction. It does
not ingest, conform, rebuild features, migrate, or write to any schema.

## Classification meanings

| Classification | Meaning | Next action |
| --- | --- | --- |
| `canonical_core` | Stable identity/fact has a declared core destination. | Use the documented core contract; do not duplicate it. |
| `existing_gold` | Field already reaches a declared derived or reporting relation. | Check whether its timing permits the proposed target. |
| `raw_only_by_design` | Source/provenance, final-state, or source-native detail intentionally remains raw. | Retain it; do not call it lost. |
| `unconformed_candidate` | A stable canonical fact may be missing. | Write a narrow identity/conformance proposal. |
| `invalid_or_low_value` | Not useful or valid for the stated purpose. | Keep raw evidence but do not promote. |
| `needs_research` | Business field lacks an approved grain, availability, formula, or PIT contract. | Review the admission queue before implementation. |

The JSON artifact is the complete machine-readable evidence. The Markdown
artifact is a compact summary. Neither grants a field model eligibility: that
requires the admission record, source-rights check, point-in-time rule, null
policy, formula version, and tests.

## Recorded production read-only baseline

On 2026-08-12, the catalog census inspected **138 raw relations** and **3,545
raw fields**. A targeted exact, read-only coverage check found:

| Source evidence | Rows / period | Relevant completeness finding | Interpretation |
| --- | ---: | --- | --- |
| `raw.mlb_schedule` | 239,364; 1901–2026 | 0 missing `game_datetime`; 69,622 home probable-pitcher values | Schedule cutoff is strong; probable-pitcher history is not yet enough proof of an as-of starter feature. |
| `raw.mlb_probable` | 128 rows / 77 games | captures only 2026-08-09 through 2026-08-12 | Must retain capture time and unknown/changed-starter flags. |
| `raw.retrosheet_event` | 16,465,588 / 205,890 games | 0 missing event/batter/pitcher IDs in this check | Strong path for prior-event historical rates, subject to era and player crosswalk tests. |
| `raw.retrosheet_gameinfo` | 224,877; 1898–2025 | 5,494 missing temperature; 4,653 missing home umpire | Actual weather/umpire data is sparse and postgame; not pregame input. |
| `raw.statcast_pitch` | 13,400,779; 2008–2026 | 2,458,745 launch-speed and 211,663 release-speed gaps | Statcast families need coverage flags and era-restricted profiles. |
| `raw.bref_war_batting` | 126,462; 1871–2026 | 12,023 missing WAR | Provider final-season value remains reporting-only until reconstructed as-of. |
| `raw.statcast_oaa` | 2,975; 2016–2026 | no missing checked player/OAA fields | Coverage begins too late for all-era use and timing remains unproven. |

This baseline is coverage evidence only. No production data, schema, migration,
feature, prediction, or run record was changed.

## Safe workflow

1. Run the census against `mlb_test` as part of a fixture/rehearsal.
2. Run a separately recorded production **read-only** census only when current
   coverage evidence is needed.
3. Select no more than one or two candidates from
   [the feature-admission queue](FEATURE_ADMISSION_QUEUE.md).
4. Design a narrow gold family and its future-data/leakage fixtures.
5. Build it only after review; add it to an immutable experiment snapshot only
   after its own point-in-time and coverage gate passes.
