## 1. Generalise the tie-out script

- [x] 1.1 Extend `TieOutCase` in `scripts/verify_baseball_reference_tie_out.py`: `table` accepts the game / team / career tables as well as the two season tables; add grain key fields (`game_retro_id`, `team_retro_id`, `retro_id`, `season`) with a `__post_init__` check. Verify: `ruff check` + `mypy` clean.
- [x] 1.2 Replace `_fetch_combined_row` with a per-grain fetch keyed by the case's grain. Verify: the two existing cited cases (Judge 2022, Cole 2023) still pass against the built database.

## 2. Broad validation via a bulk cross-check

- [x] 2.1 Add `_cross_check()`: for 2008-2019 (the years `gold.player_season` is trustworthy), compare `gold.batting_season` / `gold.pitching_season` against `gold.player_season` field-by-field for every qualified player-season; fail the gate if any field is outside a small documented tolerance on more than 2% of them. Exclude 2020+ (`gold.player_season` folds in postseason from 2021 -- tracked separately). Verify: the cross-check runs and passes against the built database (batting ~3300 seasons, pitching ~1800).
- [x] 2.2 Keep the 2 cited Baseball-Reference cases as anchors; leave the case shape ready for game/team/career cited cases to be added later. Verify: the cited cases still pass.

## 3. Run the gate

- [x] 3.1 Run `DATABASE_URL=<mlb> uv run python scripts/verify_baseball_reference_tie_out.py` against the fully-built database. Verify: paste the full output into the PR; the cited cases and the cross-check all pass.

## 4. Docs + validation

- [x] 4.1 Honest-limitations doc (`docs/RESEARCH.md` -- confirm during apply): record (a) career-grain / pre-2000 exact tie-out is not achievable (Retrosheet vs Baseball-Reference divergence), and (b) `gold.player_season` includes postseason from 2021 (root cause + that ADR-282 tracks the fix). Add a one-line note where the release checklist lives that this script is the tie-out gate and how to run it. Verify: both notes exist.
- [x] 4.2 `openspec validate --all` and `openspec validate baseball-reference-tie-out-expansion --strict` both exit 0. Verify: both pass.
