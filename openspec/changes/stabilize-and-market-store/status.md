# Status (2026-10-13) — resume here

Change: `stabilize-and-market-store`. Read `proposal.md`, `design.md`, `tasks.md` (tags: `[auto]` agent alone, `[owner]` needs a decision/approval, `[measure]` needs elapsed time), `results.md`. `review-opus.md` is the evidence behind the plan.

## Where the work is
- Branch `stabilize-market-clean`, worktree `~/workspace/mlb-stabilize`, cut from `origin/main` (b7f83a2 and later). **Not pushed, no PR.** The older local branch `stabilize-and-market-store` (in `~/workspace/mlb`, on top of `wip/uncommitted-2026-10-08`) is superseded; leave it alone, cron runs from that checkout.
- Unit suite 1153 passed; affected integration suites passed on disposable databases (mlb_api load 53, connectors 52, market store/tables 17, conform/migrations/doctor/health/repair 160). Full integration suite not run locally; CI runs it.

## Done (code, tested, not deployed)
0.1 clean branch · 1.3 health digest split · 1.5 Retrosheet unchanged-archive skip · 1.6 5-minute tick narrowing (yesterday/today per tick; season schedule, standings, roster, transactions, draft hourly with hash skip) · 1.7 docs · 2.1 reader inventory · 2.2/2.3 Timescale scratch test · 2.5 migration 0117 + `meta.create_market_tables` (and `timescaledb` first in 0116) · 2.7 `market_store` append-only typed loaders + reject tables + doctor check.
Coverage cost (old 1.4) is already solved on `main` by ADR-303 (`coverage --light`); only the `pg_stat_statements` confirmation remains.

## Next: needs the owner
1. **Push and open the PR** from `stabilize-market-clean` (CI must pass `test`, `secrets`).
2. **1.1 / 1.2** alert channel: create `~/.mlb/alert.env` (`MLB_DISCORD_WEBHOOK=...`, chmod 600); test message and forced failure; `mlb nightly --check` cron line only after merge to `main`.
3. **2.7d** `dlt` pilot decision (see tasks).
4. **2.4** approve the full bad-value scan on production (read-only, heavy on the spinning disks).
5. **2.6 / 2.8** approve the production copy and the swap (pause backfills first; `odds-bulk-history` and `odds-history-capture` stay paused until after the swap).
6. **3.1** approve the ADR drafts in `design.md` (ADR-300 relax if `dlt` is piloted; Timescale for market data).

## Measure after deploy
1.4 (`pg_stat_statements`: no `count(*)` on market tables), 1.6m (`pg_stat_wal` 3 days), 1.8 (7 nights), 2.9 (size 10 GB or less).

## Outside the repo
- Scratch database `scratch_ts_test` is still on the production Postgres server (small); drop it later, not during a backfill (forces a checkpoint).
- OpenSpec CLI: `source ~/.nvm/nvm.sh` (v1.14.1).
- Untracked `..env.swp` in `~/workspace/mlb` is a stray editor swap file.
