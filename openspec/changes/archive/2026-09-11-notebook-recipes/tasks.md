## 1. Notebooks

- [x] 1.1 `notebooks/02-home-run-era.py` — league HR per PA by season from
  `batting_season` combined rows (`sum(hr)/sum(pa)` per season). Verify: runs
  top to bottom against the published dataset with no DB; the printed series
  shows the 2000 and 2017/2019 spikes and a trough in the early 1980s.
- [x] 1.2 `notebooks/03-three-true-outcomes.py` — `(sum(bb)+sum(so)+sum(hr)) /
  sum(pa)` by season from `batting_season` combined rows. Verify: runs with no
  DB; TTO share rises from well under 25% mid-century to over ~33% by the 2020s.
- [x] 1.3 `notebooks/04-babip-is-mostly-luck.py` — self-join `batting_season`
  combined rows on `player_id` for consecutive seasons, qualified (`pa >= 400`
  both years); report the year-to-year Pearson correlation of `babip` and of
  `k_pct`. Verify: runs with no DB; `k_pct` correlation is markedly higher than
  `babip` correlation (K% is a skill, single-season BABIP is largely noise).
- [x] 1.4 `notebooks/05-strikeouts-and-scoring.py` — league `k_pct` and runs per
  game (`sum(r) / (sum(g)/2)` — two teams per game) by season from
  `batting_season` combined rows; scatter + correlation. Verify: runs with no
  DB; the finding notes that rising K% has *not* driven scoring down (HR growth
  offsets it).
- [x] 1.5 Each notebook opens with a markdown cell naming its source table(s),
  the "regular season, Retrosheet event-derived, 1910–2025" provenance, and the
  recompute-not-average rule; and ends with a one-sentence finding cell. Verify:
  present in all four.

## 2. Guard

- [x] 2.1 `tests/unit/test_notebook_recipes.py` — parse every `notebooks/*.py`,
  assert each imports `mlb_research` and imports neither `mlb_baseball` nor
  `psycopg` / `psycopg2`; assert there are ≥5 notebooks. Verify: red-green —
  add `import psycopg` to a notebook, watch it fail; remove, watch it pass.

## 3. Docs + spec

- [x] 3.1 Apply the `delivery` delta (≥5 notebooks). Verify:
  `openspec validate --strict notebook-recipes` passes.
- [x] 3.2 `openspec/project.md` — note the ≥5-notebook v1 criterion is met (5
  notebooks present). Verify: consistent with the NOW block.
- [x] 3.3 `notebooks/` — add or update a short `README.md` listing the five
  recipes and the one-line `pip install mlb-research && marimo edit
  notebooks/0X-...py` usage. Verify: lists all five.

## 4. Verification

- [x] 4.1 Run all five notebooks (`uv run marimo export ...` or execute as a
  script) end to end against the live published dataset; capture each finding.
  Verify: all exit 0, no Postgres connection attempted.
- [x] 4.2 `uv run pytest tests/unit/test_notebook_recipes.py -q`, `ruff`,
  `openspec validate --all`, full `pre-commit` — all clean.

### Verification evidence

- **1.1–1.5 / 4.1** All five notebooks run headless (`python notebooks/0X.py`,
  marimo `app.run()`) exit 0 against the live published dataset. Findings
  checked against the data directly:
  - 02: top-10 HR seasons = 2019,2020,2017,2021,2023,2025,2016,2018,**2000**,2024
    (2000 the only pre-2016). 1981 HR/PA 0.0168 -> 2019 0.0363.
  - 03: 1946-1960 TTO 22.2% -> 2015+ 33.8%, peak 36.1% (2020).
  - 04: 12,005 consecutive qualified pairs; BABIP y/y r=0.46, K% y/y r=0.92.
  - 05: K% vs R/G corr -0.16; 1968 K%15.8%/R3.37 vs 2019 K%23.0%/R4.81.
- **2.1** `tests/unit/test_notebook_recipes.py` 6 passed; red-green verified
  (add `import psycopg` to a notebook -> fails).
- **3.1** `openspec validate --strict notebook-recipes` valid; main
  `openspec/specs/delivery/spec.md` untouched (delta applies at archive).
- **4.2** ruff + mypy clean on the test; `openspec validate --all` passes.
