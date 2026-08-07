# North Star

## Vision

A free, self-hosted MLB data and research platform that:

1. **Ingests** historical and live baseball data more completely than [baseball.computer](https://baseball.computer) (which covers Retrosheet + pre-1901 Lahman only) — adding Statcast/pitch-level data, live MLB StatsAPI data, and prediction-market data.
2. **Predicts** — builds and continually improves ML models on top of that data (game outcomes, totals, player props).
3. **Presents** — a public website in the spirit of oddstrader.com (built in Astro) that surfaces model output alongside market data, for both the research community and the project owner's own betting/research use.

Audience: **both** the open baseball-research community *and* personal use, from day one. That means: data licensing is respected and documented, no secrets or paid-account credentials ever land in the public repo, and docs are written well enough for a stranger to use the data.

## The three pillars (in build order)

| Phase | Pillar | Status |
|---|---|---|
| 1 | **Data ingestion pipeline** | Foundation established; reliability and operating contracts remain active work |
| 2 | **ML modeling workflows** | Foundation in place; current priority is reproducible feature/prediction contracts before model breadth |
| 3 | **Astro website (oddstrader-style)** | Planned; public output remains rights-gated and may begin as static research/methodology content |

Do not pull work forward from a later phase without an explicit decision to do so. Phase 1 is not "done" until ingestion is reliable, tested, documented, and re-runnable — not just "it worked once."

## Non-negotiable research contracts

- A forecast is identified by a durable game instance, not an external game ID
  assumed unique.
- Every result carries its feature/data/model cutoff and source-rights lineage.
- Feature builds are independently health-checked before reproducible prediction
  runs consume them; a fingerprint is not an immutable feature snapshot.
- Broad model search is welcome, but promotion is strict: chronological
  validation, calibration, matched samples, uncertainty, and stable gains over
  transparent baselines are required.

## Budget constraint

Assume **$0/month** ongoing spend unless explicitly approved. Prefer, in order: free/open-source self-hosted tools, free tiers of hosted services, then ask before introducing any paid dependency (including paid data feeds, e.g. traditional sportsbook odds APIs).

## What makes this different from baseball.computer

- Broader source coverage: Statcast (pitch-level), live MLB StatsAPI, not just Retrosheet/Lahman.
- Prediction-market data (Polymarket, Kalshi) as a **free** proxy for market-implied probabilities — a differentiator from both baseball.computer (no markets) and oddstrader (paid sportsbook feeds).
- Ships actual predictive models, not just a queryable database.
- Ships a consumer-facing product (the website), not just a data/query layer.

## Keep the end goal in mind

Every piece of work should be done with the three pillars above in view — not just the immediate task. Before building something, ask whether it's actually in service of ingestion, modeling, or the website, and whether it's the right shape to support the other two pillars later (e.g. ingestion should land data in a form that modeling can actually consume; modeling output should be something the website can actually display).

## Reference, not blueprint

The prior repo (`cbwinslow/mlb-baseball-ml`, Gemini-built) may be consulted for *ideas* but no code, schema, or docs are carried over by default. Every choice gets re-evaluated from scratch.
