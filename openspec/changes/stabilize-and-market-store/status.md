# Status (2026-10-12) — resume here

Change: `stabilize-and-market-store`. Read `proposal.md`, `design.md`, `tasks.md`, `results.md`; `review-opus.md` is the evidence behind the plan.

## Done
- 1.3 nightly exit code now reflects pipeline steps only; health steps (`doctor --populated`, `coverage`, `schema-watch`, `repair`) go into one end-of-run digest. Unit tests: `tests/unit/test_nightly_health.py`, `tests/unit/test_nightly.py`.
- 1.2 (code): run record `~/.mlb/nightly_run.json` and `mlb nightly --check`. The cron line is the remaining part (see below).
- 2.2, 2.3 Timescale scratch test passed (`results.md`): about 3.5 B/row Polymarket, 6.2 B/row Kalshi sample; projected total about 5-6 GB vs 150 GB.
- Alert plumbing: `scripts/mlb_alert.sh`, `scripts/mlb_alert_banner.sh`, gitignored `mlb.toml` (`alert_command`), one line in `~/.zshrc`.

## Waiting on the owner
- Discord webhook: owner creates `~/.mlb/alert.env` (`MLB_DISCORD_WEBHOOK=...`, chmod 600). Then send one test message and force a failing step to close task 1.1.
- Task 1.2 also needs a forced dead-run test to prove the watchdog alerts.
- Open question for a later change: do market ticks ever get published (rights doc says no today).

## Not done / next
- 1.4 weekly coverage/repair, 1.5 Retrosheet content-hash skip, 1.6 `mlb_api` tick narrowing, 1.7 DOX/changelog, 1.8 exit check (7 nights).
- Phase 1 (2.1, 2.4-2.11): reader inventory, bad-value discovery, typed hypertables, loaders with a `dlt` pilot, swap.
- 3.x ADRs: drafts are in `design.md`; write them into `docs/DECISIONS.md` only after owner approval.

## Things outside the repo to know about
- Scratch database `scratch_ts_test` exists on the production Postgres server (small). Drop it later; dropping forces a checkpoint, so not during a backfill.
- `HANDOFF_QUANT_ARCHITECTURE.md` was deleted from the repo root (identical copy in `~/workspace/mlb-quant/HANDOFF_TO_CLAUDE.md`). The prototype there has a wrong BaseRuns (`C = 3*outs`) and a broken docker-compose; do not import its code.
- OpenSpec CLI was installed globally with npm (`@fission-ai/openspec`, v1.14.1; needs `source ~/.nvm/nvm.sh`).
- Untracked `..env.swp` in the repo root is a stray editor swap file; left alone.
- Local DB-backed pytest was not run for these changes; CI runs the integration tests.

## Git state (decide before pushing)
- Work is committed locally on branch `stabilize-and-market-store` (one commit on top of `wip/uncommitted-2026-10-08`), not pushed, no PR.
- That wip branch is 22 commits ahead of and 3 behind `origin/main`, and differs in `nightly.py`/`cli.py`. A PR from this branch would carry those 22 unmerged commits. Either merge/clean the wip branch first, or cherry-pick the single commit on `stabilize-and-market-store` onto a branch from `origin/main` (expect small conflicts in `nightly.py` and `cli.py`).
- The cron jobs run from this checkout; its own crontab note says to keep it on `main`. Do not add the `mlb nightly --check` cron line until this change is merged and the checkout is on `main`.
