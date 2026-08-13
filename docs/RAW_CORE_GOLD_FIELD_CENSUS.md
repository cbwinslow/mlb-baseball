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

### 2026-08-13 — OFF-01 era coverage for `bat_event_fl`/`event_cd`/`ab_fl`/`sf_fl`

OFF-01's admission-queue row requires measuring historical-era coverage of the
fields `mlb_baseball/model/team_rate.py::compute()` gates its K/BB/HBP/hit
counts on (`bat_event_fl = 'T'`, per ADR-034/ADR-061). `mlb field-census`
reports overall null counts and a season min/max per field but does not
bucket by era, so this evidence comes from a targeted, read-only,
decade-bucketed query run directly against production `mlb` through
`mlb_baseball.db.get_connection()` under
`SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY` (the same
read-only posture `field_census.py` itself uses), run concurrently with (not
blocking on) a separate full `mlb field-census --exact` scan:

```sql
SELECT
    (floor(_season::int / 10) * 10)::int AS decade,
    count(*) AS rows,
    count(*) FILTER (WHERE bat_event_fl IS NULL) AS bat_event_fl_null,
    count(*) FILTER (WHERE bat_event_fl = '') AS bat_event_fl_empty,
    count(*) FILTER (WHERE event_cd IS NULL) AS event_cd_null,
    count(*) FILTER (WHERE ab_fl IS NULL) AS ab_fl_null,
    count(*) FILTER (WHERE sf_fl IS NULL) AS sf_fl_null
FROM raw.retrosheet_event
GROUP BY 1
ORDER BY 1;
```

| Decade | Rows | `bat_event_fl` NULL | `bat_event_fl` empty | `event_cd` NULL | `ab_fl` NULL | `sf_fl` NULL |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1900 | 3,502 | 0 | 0 | 0 | 0 | 0 |
| 1910 | 1,071,290 | 0 | 0 | 0 | 0 | 0 |
| 1920 | 1,013,960 | 0 | 0 | 0 | 0 | 0 |
| 1930 | 1,122,781 | 0 | 0 | 0 | 0 | 0 |
| 1940 | 1,122,782 | 0 | 0 | 0 | 0 | 0 |
| 1950 | 982,006 | 0 | 0 | 0 | 0 | 0 |
| 1960 | 1,253,190 | 0 | 0 | 0 | 0 | 0 |
| 1970 | 1,579,855 | 0 | 0 | 0 | 0 | 0 |
| 1980 | 1,631,182 | 0 | 0 | 0 | 0 | 0 |
| 1990 | 1,751,354 | 0 | 0 | 0 | 0 | 0 |
| 2000 | 1,963,054 | 0 | 0 | 0 | 0 | 0 |
| 2010 | 1,938,115 | 0 | 0 | 0 | 0 | 0 |
| 2020 | 1,032,517 | 0 | 0 | 0 | 0 | 0 |

Row counts sum exactly to `raw.retrosheet_event`'s known 16,465,588-row total
(matching the 2026-08-12 baseline row above), and `min(_season)=1900`,
`max(_season)=2025`, confirmed separately in the same read-only connection.
`bat_event_fl`'s measured value domain is exactly two values: `'T'`
(15,894,527 rows) and `'F'` (571,061 rows) — no third value and no garbage.

**Finding: no coverage gap.** `bat_event_fl`, `event_cd`, `ab_fl`, and `sf_fl`
have zero NULLs and zero empty strings in every decade from the 1900s through
the 2020s — full coverage across the entirety of `raw.retrosheet_event`'s
landed range, which predates the 1910 floor OFF-01 asked about. There is no
early-era data gap for `team_rate.py::compute()`'s `bat_event_fl = 'T'` gate
to work around; OFF-01's "measure historical eras" requirement is satisfied
by this measurement, with a clean result.

This is separate, targeted evidence from the 2026-08-12 baseline row above
(which checked `raw.retrosheet_event`'s event/batter/pitcher ID completeness,
not these four fields' era coverage). A full field-by-field
`mlb field-census --exact` scan was also started against production the same
day, targeting `artifacts/census/mlb_era_coverage.{json,md}`. That scan does
not change the finding above (it does not report era buckets and was run
purely for the standard census artifact); it does not gate this entry, and
its output — if it had finished by the time of this commit — is committed
alongside this doc change under `artifacts/census/`.

## Safe workflow

1. Run the census against `mlb_test` as part of a fixture/rehearsal.
2. Run a separately recorded production **read-only** census only when current
   coverage evidence is needed.
3. Select no more than one or two candidates from
   [the feature-admission queue](FEATURE_ADMISSION_QUEUE.md).
4. Design a narrow gold family and its future-data/leakage fixtures.
5. Build it only after review; add it to an immutable experiment snapshot only
   after its own point-in-time and coverage gate passes.
