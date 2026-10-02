# Session handoff — 2026-10-01 (evening)

Branch: `feat/raw-source-tieout`. Untracked `.idea/` is IDE config, not ours.

## What happened this session (plain version)

The Retrosheet tie-out gate (compares the redundant Retrosheet copies, read-only) now
**passes for 1871–2014**; 2015–2025 has one known difference (`BOS202509030`, issue #267).
Results: `openspec/changes/raw-source-tieout/results-history.md`. All its tasks are ticked.

The gate then exposed a bigger problem: **Retrosheet republished every file on 2026-08-09**;
our production `raw.retrosheet_*` tables were loaded in July, and nothing noticed. So we are
refreshing production from Retrosheet's current files through our own commands.

## Production writes done (owner-approved)

- 2000s event archive force-reloaded (105 of 1.94M rows changed, none added/lost).
- `mlb ingest retrosheet_gamelog --refresh` — done, same row counts.
- Chain started 19:47 UTC: `retrosheet_roster`, `retrosheet_reference`, `retrosheet_schedule`
  (all done, small row-count changes), `retrosheet_box` (done, see below), then
  **`retrosheet_event --refresh` — STILL RUNNING when this was written** (pid 176049, ~30+ min).
  Log: `<scratchpad>/refresh_chain.log` (scratchpad path of the previous session may be gone).
  Check it finished with `mlb status` / `psql` row counts for `raw.retrosheet_event`
  (before: 16,465,588; before-counts for every Retrosheet table were saved in
  `<scratchpad>/status_before.txt`).
- Old downloads were NOT deleted: they are under `downloads/<source>/_superseded/<UTC ts>/`
  (rollback = reload from them). A full pg_dump from 2026-08-17 is in `backups/`.

## Findings to act on

1. **Box scores (`retrosheet_box`)**: current parser skips Negro League box files for 1933–1938
   (cwbox cannot read `NA` positions) and drops ~130 single games; skipped years KEEP their old
   rows, so production holds box rows a fresh install would not have. Vs the 17 Aug backup,
   18 games disappeared (12 from 1939, 4 from 1948, 2 from 1944 negro_league scopes) and 931
   appeared (1897_era 807, rest Negro League). The log's "17,418 rows" was rows loaded this run,
   not the table size (18,467). Decision needed: keep documented skips (matches a fresh
   install) or fix the parser so those games load.
2. **CSV products (`retrosheet`: plays/batting/gameinfo)** have no cached downloads on this
   machine, so staleness cannot be seen from a manifest. After the event refresh, rerun the
   gate; if event (new) vs CSV (old) now disagree, run `mlb ingest retrosheet --refresh`
   (128 yearly zips, long).
3. Derived tables (`core`, `gold`) were built from the pre-refresh raw rows. Rebuild with the
   normal path (`mlb conform`, `mlb report`, or `mlb build`) — NOT done, needs owner OK.

## Commands to run next (in order)

```
set -a && . ./.env && set +a
uv run python scripts/verify_retrosheet_tie_out.py --expect-db mlb --from 1871 --to 2014 \
    --levels season,game,player_game --statement-timeout-minutes 25      # ~25 min, read-only
```
Expect: any new unexplained differences are from stale CSV vs refreshed event. Triage with
`--show-all`. Then CSV refresh if needed, rerun gate, then ask the owner about the rebuild.

## Code/spec state

- Committed: tie-out gate + register (E1–E8) `1ed8ff7`, docs `9e53e56`,
  `mlb ingest <source> --refresh` + `manifest.supersede` `d50b9c0` (tests pass: 160 CLI/manifest).
- **New OpenSpec change `source-change-check`** (planning done and validated, NOT implemented,
  NOT committed): `mlb source-check` (HEAD vs manifest, no downloads, exit codes 0/1/2),
  spec for `--refresh`, and "rows loaded vs table total" ingest output. Start with
  `/opsx:apply` for it. Decision recorded in its design.md.
- Friction found: `mlb status` ~3 min; `mlb preflight` plans plain bootstrap (cannot plan a
  refresh); download cache assumed closed archives never change (fixed by `--refresh`).
- Not run: the full test suite. Never state otherwise without running it.

## Ground rules to remember

- Production `mlb` is real data; gate runs are read-only with `--expect-db mlb`.
- Gate = checker, never a fixer; raw is stored as published. A difference is explained,
  filed, or a stale load reloaded through its connector (`--refresh`).
- Keep replies to the owner short and plain (see `CLAUDE.md`).
- The permission system blocked production writes and log reads until the owner approved via
  `/permissions`; if blocked, stop and ask rather than work around.
