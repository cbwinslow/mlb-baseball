# Handoff — 2026-10-11 (fresh-database-bootstrap + widen-core-pitch-play)

## Pushed on `wip/uncommitted-2026-10-08` (no PR yet)
- `5ba69cb` core.play_retro + MLB play fields + doctor checks + migrate.run reconnect after CREATE EXTENSION.
- `1547b77` tests hermetic against host config (Kalshi key in .env, host backup folder, pg_stat_kcache).
- `6cd1090` proposed this change. `1e54618` `--since-year` (config, CLI, 9 connectors, tests).

## Running in the background (check before starting anything)
- Production catch-up: `logs/catchup_2026-10-11.log` (Kalshi candles backfill, then Polymarket price backfill). Afterwards run `mlb coverage` to confirm gaps closed.
- Rehearsal: `logs/rehearsal_slice.log` — empty DB `mlb_fresh_rehearsal`, downloads in `~/rehearsal_downloads`, `mlb bootstrap --since-year 2024 --skip kalshi --skip polymarket`. Production `mlb` is not touched. Do NOT use `pkill -f` / `pgrep -f` with a pattern that appears in your own command (it kills your shell).

## Next
1. When the slice finishes: `mlb coverage`, `mlb conform`, `mlb audit`, `mlb doctor` against `DATABASE_URL=postgresql:///mlb_fresh_rehearsal`; record every failure in this change (tasks 1.2-1.3, then 2.x).
2. Rehearse kalshi/polymarket catalog bootstrap once the production catch-up is done.
3. widen-core-pitch-play: value parity + timing on a production copy (2.3, 3.3 tie-out, 4.1), docs 4.2, production `conform` only with owner approval (4.3); then open the PR.
4. Known open: `raw.mlb_person` roster gap (10 ids); mypy error `doctor.py:189` (not ours); `test_mlb_research_integration.py` import error (`_cleanup_backbone_data`), not checked against base.
