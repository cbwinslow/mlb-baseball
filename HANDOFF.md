# Session handoff — 2026-10-01

Branch: `feat/raw-source-tieout`. Read `openspec/changes/raw-source-tieout/tasks.md`
for the live checklist. Only open tasks: **4.2, 4.3, 4.4**. Untracked `.idea/` is
IDE config, not ours; leave it.

## Where task 4.2 stands (history run, 1871–2014)

4.1 (2015–2025) is done and recorded in `results-2015-2025.md`.

**Gate fix made this session (committed with this note):** the first history run
aborted ("cannot run: csv_batting game: NULL k at SLA191007312") because the CSV
batting product leaves stat columns blank for early seasons (b_k is blank for most
of 1898–1915; every stat column has blanks somewhere). Blank = "not recorded",
never zero. Changes:
- `mlb_baseball/tieout.py`: a blank fact is kept as `None`, skipped by `compare`,
  and counted in `Comparison.unrecorded`; the report prints
  "N fact values left blank by a source (not recorded, not compared)".
- `mlb_baseball/sql/tieout_{season,game,player}_csv_batting.sql`: a total is NULL
  unless every row in the group has a value, so a partly-blank game cannot
  silently under-count.
- Tests: unit `tests/unit/test_tieout.py` (32 pass), integration
  `tests/integration/test_tieout_run.py` (22 pass).

**Second run finished: exit 1 (FAILED), 556.6s, read-only against production `mlb`.**
Command (from repo root):
```
set -a && . ./.env && set +a
uv run python scripts/verify_retrosheet_tie_out.py --expect-db mlb --from 1871 --to 2014 \
    --levels season,game,player_game --statement-timeout-minutes 25
```
Full raw output is saved at
`openspec/changes/raw-source-tieout/results-history-run1-raw.log` (rename or fold
into `results-history.md`). Summary of what it shows (not yet triaged):
- **event vs csv_plays, season:** 103 match, 2 unexplained — 1947 `pa` off by 1
  (101409 vs 101408), 2002 `r` off by 1 (22771 vs 22772). Likely real small gaps
  like the 2025 OBS one (issue #267); look at the game level to find the games.
- **event vs csv_batting, season:** 66 match, 39 unexplained, 162 blank values
  skipped. Differences cluster in 1912–1921 (e.g. 1921 pa 97084 vs 98837, g 1248
  vs 1272).
- **event vs gameinfo, season:** 63 match, 42 unexplained; same era; `g` and `r`.
  Note `event` only holds comprehensive `pbp` data from 1910; the 1910s gaps may
  be the event files missing games, not CSV errors (check `passmarks.md` section 3
  before concluding).
- **gamelog:** 63 explained (existing register), 38 unexplained, e.g. 1910 `k`
  9393 vs 9305.
- The game and player_game levels also have output (see the log, ~1260 lines).
- Roster identity check passed for 1871–2014.

## Next steps, in order

1. Triage the log: for each unexplained difference decide *register entry with
   evidence* (a rule the gate can verify, new commit naming this run — see
   `passmarks.md` section 4) or *GitHub issue*. Do not excuse anything without
   evidence. Start with the era 1910–1921 (likely one root cause), then the two
   single-count items (1947, 2002).
2. Write `results-history.md` (command, elapsed time, summary, triage outcomes);
   delete or keep the raw log, then commit. 1871–1909 and 1898–1909 CSV-only
   seasons show as "not comparable" for `event` — that is expected.
3. Task 4.3: update `scripts/AGENTS.md` / Retrosheet DOX sidecars if a contract
   changed (the blank-value rule is one); run `scripts/check_dox.py`.
4. Task 4.4: note the result in the `play-engine` change (task 2.3 gate) and
   `openspec/project.md` NOW/NEXT; `openspec validate raw-source-tieout`; record
   the finish-line checklist in the change.

## Ground rules to remember
- Production `mlb` is real data. Every gate run is read-only; always pass
  `--expect-db mlb`.
- Never state tests passed unless they ran. Last verified this session: the two
  test files above only; no full suite, lint, or type check was run.
- Keep replies to the owner short and plain (see `CLAUDE.md`).
- Server note from earlier sessions: Postgres is shared and on spinning disks;
  disposable-DB teardown can be slow when other jobs run (details in git history
  of this file, commit `0950f5b`).
