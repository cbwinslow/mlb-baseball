## 1. Generalise the tie-out script to every grain

- [ ] 1.1 Extend `TieOutCase` in `scripts/verify_baseball_reference_tie_out.py`: `table` accepts `batting_game` / `pitching_game` / `batting_team` / `pitching_team` / `batting_career` / `pitching_career` as well as the two season tables; add the grain key fields the case needs (`game_id`, `team_id`, `player_id`, `season` as applicable). Verify: `ruff check` + `basedpyright` clean on the file.
- [ ] 1.2 Replace `_fetch_combined_row` with a per-grain fetch that selects the right row by the case's grain key: `(game_id, player_id)` for a game, `(team_id, season)` for a team-season, `(player_id)` for a career, `(player_id, season, is_combined=true)` for a season. Keep the `ip = outs/3` derivation for pitching. Verify: the two existing season cases still pass unchanged when run against a built database.

## 2. Add tie-out cases (all figures fetched from the cited Baseball-Reference page — never typed from memory)

- [ ] 2.1 **Game grain** — pick one documented modern game; add one `batting_game` case (a hitter's box line) and one `pitching_game` case (the starter's box line), each `expected` read from that game's Baseball-Reference box-score page, `source_url` set to it. Verify: both cases pass against the built database.
- [ ] 2.2 **Season grain** — add at least: one mid-century case (~1950s–60s) batting, one mid-century pitching, and one traded-in-season player (checks the `is_combined` roll-up), each from the player's Baseball-Reference standard-batting / standard-pitching row. Verify: all pass against the built database.
- [ ] 2.3 **Team-season grain** — one `batting_team` case and one `pitching_team` case, `expected` from the team's Baseball-Reference team-batting / team-pitching totals row. Verify: both pass.
- [ ] 2.4 **Career grain** — one `batting_career` and one `pitching_career` case for a retired player, `expected` from the Baseball-Reference career (bottom) row. Verify: both pass.

## 3. Run the gate and record the result

- [ ] 3.1 Run `DATABASE_URL=<production mlb> uv run python scripts/verify_baseball_reference_tie_out.py` against the fully-built database. Verify: paste the full output into the PR; every case reports OK. Any mismatch is investigated before the change is marked done — a real builder bug is fixed here (separate commit), a Baseball-Reference figure typo is corrected, a genuine known-limitation delta is documented in the case and its tolerance widened with a comment.

## 4. Docs + validation

- [ ] 4.1 Add a one-line note to the milestone / release checklist (confirm the exact file during apply — likely `docs/PUBLIC_API.md` or a release doc) that `scripts/verify_baseball_reference_tie_out.py` is the relation-1–6 Baseball-Reference tie-out gate, run against a fully-built database before a release. Verify: the note exists and names the script + how to run it.
- [ ] 4.2 `openspec validate --all` and `openspec validate baseball-reference-tie-out-expansion --strict` both exit 0. Verify: both pass.
