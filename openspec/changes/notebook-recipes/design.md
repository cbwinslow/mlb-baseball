## Context

See `proposal.md` — Why. The published dataset exposes eight Retrosheet-derived
tables through `mlb_research.load(table, season=..., version=...)`. The tables
carry **surrogate keys only** (`player_id`, `team_id`) — no names — so recipes
must be league- or distribution-level, or self-join on the opaque id.
`marimo` is already in the `dev` extra; the existing notebook is a marimo
`app`-style `.py`.

## Goals / Non-Goals

**Goals:** four more recipes that each teach one idea, run offline-of-Postgres,
and are honest about provenance and the recompute-don't-average rule. A cheap
guard that a notebook never reaches for the database layer.

**Non-Goals:** running the notebooks in CI (they download from Hugging Face at
runtime — the existing notebook isn't CI-run either); player/team-name recipes;
any loader or dataset change.

## Decisions

### D1 — recipes are league/distribution-level, matching the data's shape

Each notebook aggregates across players (summing counting stats, then dividing)
or self-joins `batting_season` on `player_id` across consecutive seasons. None
needs a name. This is also the honest sabermetric framing — a league-wide rate
trend is a real finding; a "top 10 by surrogate id" table is not.

### D2 — verification is a local end-to-end run plus a static import guard

- **Local:** each notebook is executed top to bottom against the live published
  dataset (`v0.1.0` / `main`) and its printed finding checked against a known
  fact (e.g. the 2019 HR spike, K% > 20% after ~2013).
- **Static guard:** one `tests/unit` test parses every `notebooks/*.py` and
  asserts it imports `mlb_research` and neither `mlb_baseball` nor `psycopg`/
  `psycopg2` — the "no database connection" scenario, checkable without network.
- CI does **not** execute the notebooks (no network dependency added to the
  suite), consistent with the current notebook.

- **Alternative rejected — a papermill/nbclient CI job.** Adds a Hugging Face
  network dependency to CI for four demo files; the static guard plus the
  local run covers the spec's scenarios.

### D3 — one shared header cell, copied not abstracted

Each notebook repeats the ~5-line "load + provenance note" cell. Four near-
duplicate cells is not worth a shared helper module that would then have to ship
in the `mlb-research` package or sit awkwardly in `notebooks/`.

## Risks / Trade-offs

- **The published dataset could change under the notebooks** → each pins nothing
  (`version="latest"`) like the existing one; the recompute-from-components
  approach means a data refresh changes the numbers but not the narrative. If a
  finding ever inverts, that is a real data problem worth surfacing, not a
  notebook bug.
- **A notebook silently importing `mlb_baseball`** (e.g. via a copy-paste) →
  the static guard test fails.
