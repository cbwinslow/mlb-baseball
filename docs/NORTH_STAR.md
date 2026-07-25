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
| 1 | **Data ingestion pipeline** | Current focus — must be solid before moving on |
| 2 | **ML modeling workflows** | Not started |
| 3 | **Astro website (oddstrader-style)** | Not started |

Do not pull work forward from a later phase without an explicit decision to do so. Phase 1 is not "done" until ingestion is reliable, tested, documented, and re-runnable — not just "it worked once."

## Budget constraint

Assume **$0/month** ongoing spend unless explicitly approved. Prefer, in order: free/open-source self-hosted tools, free tiers of hosted services, then ask before introducing any paid dependency (including paid data feeds, e.g. traditional sportsbook odds APIs).

## What makes this different from baseball.computer

- Broader source coverage: Statcast (pitch-level), live MLB StatsAPI, not just Retrosheet/Lahman.
- Prediction-market data (Polymarket, Kalshi) as a **free** proxy for market-implied probabilities — a differentiator from both baseball.computer (no markets) and oddstrader (paid sportsbook feeds).
- Ships actual predictive models, not just a queryable database.
- Ships a consumer-facing product (the website), not just a data/query layer.

## Explicit non-goals (for now)

- No live bet placement or trading execution — decision support only.
- No natural-language/agent query layer until ingestion + models are solid.
- No paid data feeds or paid infra without an explicit ask.
- No scope-creep features not covered by one of the three pillars above.

## Reference, not blueprint

The prior repo (`cbwinslow/mlb-baseball-ml`, Gemini-built) may be consulted for *ideas* but no code, schema, or docs are carried over by default. Every choice gets re-evaluated from scratch.
