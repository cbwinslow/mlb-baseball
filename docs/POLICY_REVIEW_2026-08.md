# Policy review — 2026-08-13

Prompted by a direct challenge to this project's own conventions: is nesting
SQL as Python strings actually good practice, and more broadly, is this
project reinventing things the wider software/ML world has already solved?
Six independent research passes, each with real citations, checked this
project's stated policies against outside practice. Full findings live in
each linked report; this doc is the synthesis and the record of what
actually changed as a result.

This is a research-and-correction record, not a new architecture decision —
see `docs/DECISIONS.md` for the project's ADR log, which is where any future
*design* decision belongs.

## Method

Six parallel research agents, each independently researching one policy
area with real web sources (no fabricated citations — every claim below
traces to a URL). Findings were read in full and cross-checked against this
project's own code and docs before anything was changed. Working notes
(source excerpts, per-thread detail) were kept in a local scratch directory
during the review and are not committed here, consistent with
`docs/KNOWLEDGE_BASE.md`'s own rule against copying another source's
content verbatim into this repository — this document is the durable,
source-attributed record of what was found and what changed, in this
project's own words. Two research threads failed on the first attempt (a
session usage-limit error, not a
content problem) and were re-run cleanly.

## Findings, area by area

### 1. SQL organization (inline Python strings vs. named `.sql` files)

**Verdict: current policy (`docs/SQL_OWNERSHIP.md`) is correct, not behind
the field.** dbt, SQLMesh, and the `aiosql`/`yesql` line of Python libraries
all independently draw the same line this project already draws: static,
reusable business-logic SQL belongs in files; SQL whose identifiers or
control flow are only known at runtime (dynamic identifier composition,
diagnostics, procedural logic) stays inline, because parameterized queries
literally cannot bind identifiers — that's a mechanical fact about how
`psycopg`/every SQL driver works, not a stylistic excuse.

**What actually changed:** the policy's real gap was zero automated
enforcement — 27 named `.sql` files existed with nothing checking them.
Fixed:
- Added **SQLFluff** (`.sqlfluff`, `.sqlfluffignore`) linting
  `mlb_baseball/sql/*.sql` in CI (`.github/workflows/ci.yml`). Configured to
  check parseability and genuine correctness, not retroactively reformat 27
  already-tested files to match a linter's layout opinion — several
  individual findings (AM03, AM05, RF02) were checked by hand and confirmed
  false positives for patterns this project genuinely and correctly uses
  before being excluded, not excluded on volume. Two real long lines in
  `team_starter_retrosheet_update.sql` were wrapped; four files
  (`team_war_update.sql`, `team_framing_update.sql`,
  `team_bullpen_live_update.sql`, `team_bullpen_retrosheet_update.sql`) use
  SQL shapes sqlfluff's parser genuinely can't handle (a Python
  `.format()`-based `{values_clause}` placeholder distinct from this
  project's usual `%(name)s` psycopg params; a computed `INTERVAL` in a
  window-frame bound) and are listed in `.sqlfluffignore` with the reason
  recorded.
- A custom lint check for "is this inline SQL allowed to be inline" (the
  bespoke enforcement the research found no off-the-shelf tool for) was
  **not** built — flagged as a real, scoped follow-up rather than attempted
  today; see "Deferred, not forgotten" below.

### 2. Postgres vs. a dedicated analytics database (ClickHouse/DuckDB)

**Verdict: `docs/CLICKHOUSE_DECISION.md`'s "stick with Postgres" call is
well-supported, not revisited.** Every source found — from qualitative blog
claims to a hard billion-row benchmark — places the point where Postgres
analytical performance actually degrades well above this project's current
scale (13.4M rows, ~700K/year growth). The one real trigger documented
elsewhere (PostHog's own migration story) is concurrent multi-tenant query
pressure, a workload shape this single-owner batch pipeline doesn't have.

**What changed: nothing code-level.** One thing worth recording for later:
if this project's own stated revisit gate ever fires, evaluate **DuckDB
attached directly to the existing Postgres instance** (via DuckDB's
`postgres` scanner extension — zero new server, zero data duplication, fits
the $0/month constraint) before ClickHouse, which needs a separate server
process. Not acted on now — no measured problem exists to justify it.

### 3. Migration tooling (hand-rolled `migrate.py` vs. Alembic)

**Verdict: keep as-is.** The current numbered-`.sql`-file runner is the same
recognized pattern used by Flyway, golang-migrate, dbmate, and Rails'
ActiveRecord (which added the identical `pg_try_advisory_lock` concurrency
guard `migrate.py` already has, in Rails 5 — this project had it from day
one). Alembic requires SQLAlchemy as a hard dependency even for raw-SQL use,
and its headline features (autogenerate, branch-merge) either need ORM
metadata this project has no other use for, or solve a multi-contributor
problem a solo, direct-to-`main` project doesn't have.

**One real gap the research surfaced, already independently closed:** the
report flagged "no backup/restore story" as the one thing that would make a
downgrade-script feature meaningful, and recommended a backup/restore
runbook as a docs task. `mlb backup`/`mlb restore`
(`mlb_baseball/backup.py`) were built the same day, independently of this
review — noting the overlap here so it isn't mistaken for two separate
efforts.

### 4. Point-in-time / leakage-prevention design

**Verdict: matches or exceeds established practice on the core mechanism;
one real, scoped gap on the small-sample-noise fix.** This project's
"feature cutoff" is the exact same concept dedicated feature-store products
(Feast, Tecton, Hopsworks) call **point-in-time correctness**, implemented
via an **as-of join** — same mechanism, different (but not wrong) name. The
chronological walk-forward fold design with a frozen, never-touched final
holdout is stricter than most public writeups on backtest discipline
describe as adequate.

**What changed:**
- Added a terminology cross-reference note to `docs/TABLE_CONTRACTS.md` (as-of
  join / point-in-time correctness / event timestamp) so a reader coming
  from the MLOps/feature-store literature recognizes this project's own
  vocabulary.
- Added a note to `docs/EXPERIMENT_RUNBOOK.md` explaining explicitly why
  purging/embargo (a financial-ML walk-forward technique) isn't needed here
  — this project's same-day-resolved target has no overlapping-label window
  to purge, unlike the forward-return-window case that technique exists for.
- Added an addendum to `docs/DECISIONS.md` ADR-062 recording **empirical
  Bayes shrinkage toward league average** as the specific technique to
  reach for if/when this project's already-flagged wOBA small-sample risk
  gets addressed — not adopted now (would be new scope beyond issue #8), but
  the hard `MIN_PA=10`/`MIN_AB=8` gate only excludes the single-game
  extreme, not the general small-sample-noise problem a continuous
  shrinkage estimator would fix. FanGraphs' published stabilization points
  (OBP needs ~460 PA, not 10) are recorded as the calibration reference.

### 5. Testing strategy (real Postgres, no mocking, no dbt/Great
Expectations/Soda/Pandera)

**Verdict: matches recognized good practice, no gap.** "Test against a real,
disposable database, never mock the DB layer" is the mainstream-recommended
position (Neon, the Testcontainers ecosystem, multiple independent
engineering blogs all make the identical argument this project's own
CLAUDE.md makes). On data-quality frameworks: `mlb_baseball/health.py`
already hand-implements, in readable Python with docstrings explaining *why*
each check exists, every substantive category dbt tests/Great
Expectations/Soda/Pandera are sold on (schema drift, freshness, referential
integrity, uniqueness, partition completeness, cross-source reconciliation)
— and every one of those checks was demonstrably built in response to a real
bug found in this codebase, not written speculatively.

**What changed: nothing.** The one framework capability genuinely missing —
automatic statistical/profiling anomaly detection without a hand-specified
reference — is real but low-value at this project's scale (finite,
well-understood source set, no streaming/high-velocity ingestion). If that
ever changes, Pandera (12 dependencies vs. Great Expectations' 107) is the
cheapest option to revisit.

### 6. Existing MLB prediction prior art (repos, papers, `baseballr`)

**Verdict: this project's own feature set, leakage discipline, and admission
process already exceed nearly everything found publicly.** No GitHub repo
found in this space breaks 20 stars; none document a leakage-prevention
discipline comparable to `docs/FEATURE_ADMISSION_QUEUE.md`'s governed
PIT/null-policy/test-requirement process, and several public repos claiming
67–93% accuracy are very likely leakage-inflated by this project's own
already-documented standard (`docs/RESEARCH.md` already warns about exactly
this).

**What changed:**
- **Fixed a real citation error.** `docs/RESEARCH.md` previously attributed
  "starting pitcher quality ranks among the most predictive factors" to
  three sources as unanimous "research consensus." Having now read the
  actual papers: 2 of 4 checked sources support that claim (Donaker 2005,
  Chen & He 2010); the other 2 (Cui 2020's Wharton thesis, Li et al. 2022)
  found team-record/OBP-type signals dominate, and Cui's own thesis
  specifically attributes weak pitching signal to using lagged season
  aggregates — which is evidence *for* this project's own choice to build a
  rolling within-season pitcher stat instead of using `raw.bref_pitching`
  directly, not evidence that pitcher quality is a top predictor in the
  abstract. `docs/RESEARCH.md` now cites all four sources by name with what
  each actually found, instead of a vague three-source "consensus" claim.
- Added a new, explicitly speculative admission-queue candidate,
  **OFF-09 run-scoring consistency** (`docs/FEATURE_ADMISSION_QUEUE.md`) —
  a team's game-to-game run-scoring/allowing volatility, the one feature
  category found in outside work (`baseballr::team_consistency()`
  methodology) that nothing currently planned captures. Filed as `later`,
  requiring the same field-census + outcome-correlation evidence process
  every other row needs before promotion — not a strong push, explicitly
  flagged as possibly redundant with variance already absorbed by existing
  rate stats.
- Confirmed (did not newly discover) that probability calibration —
  already flagged as a known gap in `docs/PROJECT_REVIEW.md` — is exactly
  what a live, actively-maintained 2026 practitioner repo does. Outside
  confirmation of an already-correct internal finding, recorded here for
  completeness, no doc change needed.

## Deferred, not forgotten

Real, scoped follow-ups the research surfaced that were **not** done today,
with why:

1. **Custom lint check for inline-vs-file SQL placement.** No off-the-shelf
   tool enforces this project's specific taxonomy (`docs/SQL_OWNERSHIP.md`'s
   categories) automatically — it would need a bespoke ~50-line
   AST-walking script. SQLFluff (today's change) covers the "are the 27
   `.sql` files themselves valid and parseable" half of enforcement; the
   "did a mutating business-logic query accidentally land inline in Python"
   half remains a real, open gap.
2. **Empirical Bayes shrinkage for small-sample rate stats.** Recorded as an
   ADR-062 addendum (see §4) rather than implemented — would be new scope
   beyond what issue #8 committed to.
3. **OFF-09 run-scoring consistency.** Filed in the admission queue as
   `later`, pending its own field-census + evidence gate, same as every
   other row.

## Sources

Every claim above traces to a real, checked source in the six underlying
research reports (each includes its own full source list): SQL organization
research covered dbt, SQLMesh, `aiosql`, Astronomer's Airflow guidance, and
real production repo examples; the Postgres/OLAP research covered PostHog's
own migration writeups, a real billion-row Postgres-vs-ClickHouse benchmark,
and DuckDB's own `postgres` scanner documentation; the migration-tooling
research covered Flyway, golang-migrate, dbmate, Alembic's own docs and
GitHub discussions, and Rails' own advisory-lock commit; the point-in-time
research covered Feast/Tecton/Hopsworks documentation, the James-Stein/
empirical-Bayes shrinkage literature, and FanGraphs' published stabilization
points; the testing-strategy research covered Neon, the Testcontainers
ecosystem, and direct comparisons of dbt tests/Great Expectations/Soda/
Pandera; the MLB prior-art research covered Cui (2020), Donaker (2005),
Chen & He (2010), Li et al. (2022), and a systematic GitHub search across
the MLB win-prediction niche.
