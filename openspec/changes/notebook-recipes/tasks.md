## 1. Notebooks

- [ ] 1.1 `notebooks/02-home-run-era.py` — league HR per PA by season from
  `batting_season` combined rows (`sum(hr)/sum(pa)` per season). Verify: runs
  top to bottom against the published dataset with no DB; the printed series
  shows the 2000 and 2017/2019 spikes and a trough in the early 1980s.
- [ ] 1.2 `notebooks/03-three-true-outcomes.py` — `(sum(bb)+sum(so)+sum(hr)) /
  sum(pa)` by season from `batting_season` combined rows. Verify: runs with no
  DB; TTO share rises from well under 25% mid-century to over ~33% by the 2020s.
- [ ] 1.3 `notebooks/04-babip-is-mostly-luck.py` — self-join `batting_season`
  combined rows on `player_id` for consecutive seasons, qualified (`pa >= 400`
  both years); report the year-to-year Pearson correlation of `babip` and of
  `k_pct`. Verify: runs with no DB; `k_pct` correlation is markedly higher than
  `babip` correlation (K% is a skill, single-season BABIP is largely noise).
- [ ] 1.4 `notebooks/05-strikeouts-and-scoring.py` — league `k_pct` and runs per
  game (`sum(r) / (sum(g)/2)` — two teams per game) by season from
  `batting_season` combined rows; scatter + correlation. Verify: runs with no
  DB; the finding notes that rising K% has *not* driven scoring down (HR growth
  offsets it).
- [ ] 1.5 Each notebook opens with a markdown cell naming its source table(s),
  the "regular season, Retrosheet event-derived, 1910–2025" provenance, and the
  recompute-not-average rule; and ends with a one-sentence finding cell. Verify:
  present in all four.

## 2. Guard

- [ ] 2.1 `tests/unit/test_notebook_recipes.py` — parse every `notebooks/*.py`,
  assert each imports `mlb_research` and imports neither `mlb_baseball` nor
  `psycopg` / `psycopg2`; assert there are ≥5 notebooks. Verify: red-green —
  add `import psycopg` to a notebook, watch it fail; remove, watch it pass.

## 3. Docs + spec

- [ ] 3.1 Apply the `delivery` delta (≥5 notebooks). Verify:
  `openspec validate --strict notebook-recipes` passes.
- [ ] 3.2 `openspec/project.md` — note the ≥5-notebook v1 criterion is met (5
  notebooks present). Verify: consistent with the NOW block.
- [ ] 3.3 `notebooks/` — add or update a short `README.md` listing the five
  recipes and the one-line `pip install mlb-research && marimo edit
  notebooks/0X-...py` usage. Verify: lists all five.

## 4. Verification

- [ ] 4.1 Run all five notebooks (`uv run marimo export ...` or execute as a
  script) end to end against the live published dataset; capture each finding.
  Verify: all exit 0, no Postgres connection attempted.
- [ ] 4.2 `uv run pytest tests/unit/test_notebook_recipes.py -q`, `ruff`,
  `openspec validate --all`, full `pre-commit` — all clean.
