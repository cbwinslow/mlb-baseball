# Product direction — betting site, research database, model ladder

Written 2026-08-28 after a Grok session with the owner. This is the durable
handoff so Claude, Agy, or any later agent can continue without a recap.
It does not replace `NORTH_STAR.md`, `AGENTS.md`, or the numbered `plans/`.
It says *how those documents compose into the product the owner actually
wants*, and what not to do next.

**Course correction (ADR-271):** two products (research warehouse +
play-then-sim ladder). Named `.sql` is the formula; SQLMesh is a promotion;
one writer per table. pybaseball fetches; we query gold. RE24 is accounting;
Layer 2 estimates matchup-specific PA outcome distributions (point-in-time,
shrunk toward league) that feed `simulate_game`. Spec:
[`superpowers/specs/2026-08-28-course-correction-design.md`](superpowers/specs/2026-08-28-course-correction-design.md).
Do not add a metric, GBM column, or Engine without reading that.

Companion plan (pipeline health, still active): [`superpowers/plans/2026-08-28-product-and-pipeline-next.md`](superpowers/plans/2026-08-28-product-and-pipeline-next.md).
Decision records: ADR-266 and ADR-271 in [`DECISIONS.md`](DECISIONS.md).

---

## What we are building (owner's words, restated)

A membership site that helps people make *educated* Kalshi and Polymarket
decisions on MLB, plus research-grade charts and tables.

The chain is:

1. Estimate a fair probability that a team wins (later: totals, F5, props).
2. Read Kalshi and Polymarket's pre-game price for the same contract.
3. If our number is honestly better than theirs after vig, that is the advice.
4. Parlays only from a joint simulation of the same game, never from
   multiplying independent odds.
5. Present that on an original site in the *spirit* of
   [oddstrader.com/mlb](https://www.oddstrader.com/mlb) — daily grid, model %,
   market %, projected score, edge — plus ESPN/MLB.com/baseballr-style
   player and pitch content.
6. Also ship a core research database any baseball researcher can use,
   more complete than baseball.computer or baseballr, with formulas that
   have been tied out.

"Likely winner" is not "bet this." Model probability, market price, fair
price, and a pick are four different fields. AI agents write explanations
from a fact packet. They do not invent the probability.

Source rights still bind the public site: Retrosheet is public-safe;
Statcast / MLB API / Savant charts are `local_research` until a license is
recorded in `SOURCE_RIGHTS.md`.

---

## Two jobs every metric has to declare

Agy (Gemini 3.7, conversation `f1e15173-…`, 2026-08-21–25) built a large
catalog of engines, charts, and indexes. That work is **not a dead end**.
It is unfinished. Every package is one of:

| Job | What it is | Goes into the betting model? | Goes on the site? |
|---|---|---|---|
| **A. Model input** | A point-in-time number from history only that can move win probability | Yes, after admission + tie-out | Maybe, as a table cell |
| **B. Display content** | Heat map, spray chart, pitcher card, RE24 grid, pitch-type split | No (or only its raw components) | Yes, that's the membership surface |
| **C. Prototype calculator** | CLI that takes typed numbers; invented composite (BBCRI, IZHSMI, …) | Not as the composite. Wire the ingredients or relabel | Badge only, after constants are cited or fit |

Default for C is **WIRE** — connect the raw components to `raw`/`core`/`gold`,
replace invented weights with a cited or data-fit constant, keep the pretty
index as display. The Bucket B rubric and wiring plan live on branch
`metrics/bucket-b-triage-rubric` (not this change). Classification table:
`PACKAGE_VALIDATION_STATUS.md`. Do not add package 160. Do not dump 110
indexes into GBM.

**Agy planning artifacts** from 2026-08-21–23 (metric catalog, platform
assessment) are in `~/.gemini/antigravity-cli/brain/f1e15173-07f1-47eb-a34c-8cffad6befd9/`
and were copied toward `docs/reference/agy/` on that same Bucket B branch.
The Aug 21 catalog is the research list to keep executing. The Aug 24 Engine
batch is the wiring backlog.

---

## The prediction ladder (do this, not a bigger feature soup)

Honest MLB game-winner ceiling is about 55–58%. Home teams already win
~53%. An out-of-sample game-winner result above ~58% (or a suspiciously
low log loss) is a **red flag that triggers a documented leakage
review** — chronological folds, feature cutoffs, the `RESEARCH.md`
failure modes — whose finding is written down (an ADR entry or the
promotion-review record) before the number is trusted or promoted. It
is not, on its own, proof of leakage, and it does not automatically
block the work. Verbatim, from `docs/DECISIONS.md` ADR-274: "A candidate
that does not beat its baselines is not automatically barred from
promotion. The evidence ... goes to a promotion review that records an
explicit decision" — one of **promote**, **hold**, or
**return-with-gaps**.

| Layer | Predicts | Owner today | Next |
|---|---|---|---|
| 0 | Baselines | `log5.py` (v2, correct James formula), `elo.py` | Fill Elo in production; starter-adjusted Elo still missing |
| 1 | Pre-game GBM | `gbm.py` (`gbm-v1.json` on disk; code says v2) | Frozen `FEATURE_COLUMNS`. Retrain, then a promotion review of its held-out scores vs Elo *and* `markov-v1` (ADR-274) |
| 2 | PA / base-out | `estimate_matchup_distribution` (team/starter vs offense, M=350) | Handedness split when n≥50 |
| 3 | Full game | `sim_predict.py` writes `markov-v1` for upcoming games (ADR-272) | Run + review the holdout vs Elo; home/away split (ADR-080 machinery, deferred by ADR-272); joint parlays from the same sims |
| 4 | Market comparison | `market.py` (decided + upcoming moneyline, ADR-267) | Evaluate sim vs Kalshi/Polymarket, one row per game |
| 5 | Advice | not shipped | model % − market % after vig; no pick when coverage is missing |

A neural net on a flat per-game row will mostly rediscover Elo. Sequence /
embedding models belong at pitch or PA grain later (Plan 04 owner note),
and the K80/K40 cards cannot run modern PyTorch (Agy platform assessment, 2026-08-23).

Stacking (`stack.py`) already failed to beat GBM on a small sample (ADR-058).
Do not revive it until GBM's decided-game count is much larger.

---

## Do not delete `mlb conform` or `mlb predict`

The owner asked whether to get rid of these because they are slow. **No.**
They are the orchestrators. The slowness is *what they currently do*, not
that they exist.

| Command | Must keep | Why it is slow today | What replaces the slow part |
|---|---|---|---|
| `mlb update` | yes | connector stalls (Kalshi 429), `mlb_api` lock clash (fixed, #85) | per-connector timeout; skip already-running sources |
| `mlb conform` | yes | identity resolution is multi-pass Python; some set-based SQL still rebuilds too much | keep Python for identity; incremental SQLMesh for stable set-based builders later |
| `mlb predict` / `mlb features` | yes | one long transaction, 33 sequential enrichments, full-history rebuild, missing raw indexes, HDD | checkpointed stages, indexes, incremental gold models, session `work_mem` (already in #86) |

Tracked as [issue #84](https://github.com/cbwinslow/mlb-baseball/issues/84)
and the spec
[`superpowers/specs/2026-08-28-pipeline-performance-design.md`](superpowers/specs/2026-08-28-pipeline-performance-design.md).

### SQLMesh vs named `.sql` files (the question that keeps coming up)

Both. They are not competitors.

- **Numbered migrations** (`migrations/`) — DDL only.
- **Named `.sql` resources** (`mlb_baseball/sql/`) — operational statements
  the Python pipeline runs today (`UPDATE gold.game_feature …`, health
  checks, Markov counts). These stay. Researchers and agents can read the
  formula in a file. That is the "raw SQL files I like" path.
- **SQLMesh models** (`transforms/models/`) — the *incremental* version of
  the same set-based gold math: "only recompute seasons/games that changed."
  Plan 02B spike is accepted; it is **not** writing production `core`/`gold`
  yet (`SQLMESH_OPERATIONS.md`). ADR-088 / [issue #70](https://github.com/cbwinslow/mlb-baseball/issues/70)
  already decided: new set-based feature modules should be SQLMesh going
  forward; port existing ones table-by-table after a full-table tie-out;
  **never two writers of the same table**.

SQLMesh does **not** replace:

- `conform.py` identity (2004 Hurricane Frances, doubleheader `game_pk` —
  already-paid bugs; ADR-088 reaffirmed no-go).
- Elo's sequential walk.
- Markov simulation and model training.
- The `mlb predict` CLI that registers provenance and writes `gold.prediction`.

What "adopting SQLMesh" actually entails, in practice:

1. Author the formula once as a SQLMesh model with `INCREMENTAL_BY_TIME_RANGE`
   (or unique key) on `game_date`.
2. DuckDB unit test + audit (bounds, null rate).
3. Tie out against the current Python writer on `mlb_test` (full table +
   sampled PIT). Zero unexplained diffs.
4. Only then stop the Python writer and let SQLMesh own that relation.
5. `mlb predict` still runs; it reads the SQLMesh-built table instead of
   calling `module.compute()`.

Until step 4, the named `.sql` resource **is** the canonical formula.
Do not duplicate it in a SQLMesh model that also writes production.

ClickHouse stays a measured future option (`CLICKHOUSE_DECISION.md`). Do
not add it to make `conform` feel faster.

---

## Research database (better than baseball.computer / baseballr)

This is a first-class objective, not a side effect of the betting site.

What we already have that those tools do not, in one place: Retrosheet
events 1910–2025, Statcast pitches 2008–2026, live 2026 MLB API, Kalshi
and Polymarket, Chadwick register, BRef WAR, point-in-time `gold.game_feature`.

What they still beat us on for a *researcher sitting down to query*:

- baseball.computer: a public query UI and a documented, stable grain for
  every table.
- baseballr: one function per well-known stat, with the formula in the
  help page.

The gap to close (without copying either project):

1. **Public-safe marts** — `gold.player_season` / `team_season` already
   exist (ADR-057) but `mlb report` / doctor checks were still unwired
   when that ADR landed. Finish that. Add Retrosheet-only pitch-code rates,
   RE24, wSB, FIP, wOBA at player-season and player-game grains.
2. **`mlb dump` / query recipes** — `RESEARCH_QUERY_RUNBOOK.md` plus a
   documented dump of public-safe tables. Do not dump Statcast in a
   `public_safe` profile.
3. **Formula pages** — every admitted gold family already has THEORY +
   registry + a hand fixture. That *is* the baseballr help page. Keep it
   honest (Plan 06 tie-outs).
4. **Dynamic windows** — Agy's catalog asked for trailing 10 / 30 / season
   / custom. Prefer parameterized SQL over 12 copies of every stat. Do not
   build a window we cannot PIT-test.

Statcast heat maps and spray (`hc_x`/`hc_y`) stay local_research. BAT-01
(`PROGRESS.md` 2026-08-20) is the design; it needs a `core.pitch` column
add + conform change, owner-reviewed, not a silent schema grab.

---

## Validation bar (non-negotiable)

Copied from the owner, 2026-08-21 (Agy history) and restated 2026-08-28:

> We can't produce incorrect calculations. Validate every formula against
> proven sources.

For anything that ships in `gold`, `serve`, or the site:

1. Cited formula (FanGraphs library, *The Book*, Retrosheet spec, Nathan,
   Pitcher List, …) or an explicit "project index, constants fit on our
   data, method: …".
2. Hand-calculated fixture.
3. Real player-season or game vs an external published number, with a
   stated tolerance.
4. Point-in-time / no-lookahead test.
5. Idempotency (run twice, same rows).
6. `mlb doctor` check.

A unit test that feeds the function its own defaults is **not** (3).

---

## Production snapshot, 2026-08-28 ~04:45 UTC (read-only, database `mlb`)

Do not start a second `mlb predict`. One is already running.

| Fact | Value |
|---|---|
| In-flight job | `model` / `bootstrap` (`mlb predict`), pid **3860016**, started 03:44 UTC, ~1h in, currently `UPDATE` for PLT-01 platoon SQL (~18 min on that statement) |
| Last *successful* predict | 2026-08-20 07:14 UTC |
| Last `gold.prediction` write | 2026-08-20 (elo-v1, log5-v2, kalshi-v1, polymarket-v1). `gbm-v1` last wrote **2026-08-04** |
| `gold.game_feature` | 217,195 rows, 419 upcoming |
| `home_elo` | **0 non-null** right now — expected until this run reaches `elo.compute_ratings()` after enrichment. Re-check when the run finishes. |
| Upcoming 2026 starters | 35 / 419 have `home_starter_id`; 39 have FIP |
| Failed predict causes since Aug 21 | `gdp_fl` typo (ADR-260, fixed on main); earlier `home_starter_xfip` missing-column; several SIGKILL stale runs reaped 2026-08-28 03:40 |

After the in-flight run ends: `mlb doctor`, then a read-only recount of
Elo / starter / xFIP / RE24. If Elo is still NULL, that is a P0 — do not
retrain GBM on empty ratings.

---

## Ordered next work (agents: follow this)

Do not pull Plan 05 Astro until 1–4 below are green enough to put a number
on a page. Plan 06 wiring and Plan 04 Markov can proceed in parallel with
pipeline speed (#84).

1. **Let the in-flight production predict finish. Do not overlap it.**
   Then doctor + coverage recount. Supervised catch-up is still in the
   #84 Phase 0.5 list; owner previously held it until speed wins.
2. **Pipeline speed** — issue #84 Phase 1: hypopg + indexes on
   `raw.retrosheet_event(pit_id, bat_id)` and `raw.statcast_pitch(pitcher, batter)`
   only if EXPLAIN pays; checkpoint `model.run()` so a crash does not
   throw away 40 minutes. Session `work_mem` already landed (#86).
3. **Live pre-game market match** — extend `market.py` so tomorrow's
   Kalshi `KXMLBGAME*` and Polymarket *moneyline* sit next to tomorrow's
   model row. Today `record()` is retrospective. [#87](https://github.com/cbwinslow/mlb-baseball/issues/87).
4. **Player-aware Markov** — starter vs opponent lineup (or team offense
   vs this starter as v1) → simulated win % and score distribution.
   Compare log-loss to Elo and GBM *and* to Kalshi/Polymarket on the
   same games. This is also the parlay engine. [#88](https://github.com/cbwinslow/mlb-baseball/issues/88).
5. **GBM retrain** — only on populated, admitted columns. Champion file
   on disk is still `models/gbm-v1.json` while code says `gbm-v2`. Do not
   change `FEATURE_COLUMNS` without a saved artifact (ADR-044 lesson).
6. **Wire Agy Job A/B packages** through the admission queue (Bucket B
   plan). Display composites stay out of `FEATURE_COLUMNS` unless they
   independently beat the gate.
7. **Research mart + dumps** — finish ADR-057 wiring; public-safe
   player/team/game tables a stranger can query. [#89](https://github.com/cbwinslow/mlb-baseball/issues/89).
8. **Plan 05 Astro** — original daily board. No copied OddsTrader layout.
   Methodology page that a researcher would not laugh at.

---

## Documentation contract for this stream

Same places Claude and Agy already write:

| What happened | Where it goes |
|---|---|
| Evidence of a run, a number, a production check | `plans/PROGRESS.md` dated section |
| A decision (including "we will not delete predict") | `docs/DECISIONS.md` new ADR, newest first |
| A feature family admitted | `FEATURE_REGISTRY.md` + admission-queue row |
| Formula / citation | `THEORY_AND_METHODOLOGY.md` + the named `.sql` |
| SQLMesh vs Python ownership | `SQL_OWNERSHIP.md` / this file |
| Durable "why the product exists" | this file |
| Per-session implementation plan | `docs/superpowers/plans/YYYY-MM-DD-*.md` |
| Known gap not fixed in the same change | GitHub issue on `cbwinslow/mlb-baseball` |

Commit messages explain *why*. PRs go into `main`; do not push `main`.
Say which database a command targets before any `DROP`/`TRUNCATE`/`predict`
against production.
