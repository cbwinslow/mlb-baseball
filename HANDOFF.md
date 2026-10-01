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

## Update (later 2026-10-01): triage done, code written, rerun in progress

Root causes found from run 1 (all read-only checks; raw data untouched):
- **Games with a scorecard but no play-by-play** (exhibition/Negro League, 1912-1949):
  in csv_batting/gameinfo but in neither event nor csv_plays. 1921: 24 games, 1,753 PA =
  exactly the gap. New register entry **E4**.
- **Games the major-league game logs don't hold** (7,682 gameinfo games; 7,681 are
  exhibitions or clubs absent from that season's game logs). New entry **E5**.
  One real exception: `BRO190009190` (1900-09-19, SLN at BRO 9-0) is in gameinfo, not
  in the game log -> file a GitHub issue.
- **Game log `-1` = "not recorded"** (3,447 games 1872-1915) was summed as -2. SQL fixed:
  such a fact is NULL (blank rule). Games with NULL stats are now kept, not dropped.
- **Box scores are a sample**: now compared only on games box has, game/player level only
  (season level skips box). `SourceSpec.sample`, `compare(restrict_to=...)`.
- Season totals are now judged AFTER the game level and explained when they equal the sum
  of register-explained games (`rollup_games`, `assess(rollup=...)`).
- **Two real one-count differences -> file GitHub issues (like #267):**
  - 2002 `TBA200205030`: event `OA/G6.2-H(E2/TH)(UR);1-3` gives event_runs_ct 0 but the
    run scores (gameinfo 3-2 = 5; event total 4; csv_plays 5). Same family as #267.
  - 1947 `BRO194707200`: event file has a `99#` row (event 63, kurow101, 9th inn top)
    counted as a plate appearance (pa 69); CSV plays omits it (68).

Code state: edits to `mlb_baseball/tieout.py`, `tieout_run.py`, `sql/tieout_{game,season}_gamelog.sql`,
new `sql/tieout_game_meta.sql`, plus unit + integration tests. Verified: unit 43 + integration
tests (69 total) pass; ruff + mypy clean on the two modules. No full suite run.

In progress: rerun of the history gate (background), output at
`/tmp/claude-1000/-home-cbwinslow-workspace-mlb/a5cb2a09-9dcd-44bf-973f-007c0414cfb0/scratchpad/run2.log`
(may be gone; just rerun the command above, ~10 min). Look at what is still unexplained.

## Next steps, in order

1. Read the rerun result. Anything left that is not the two real items above or
   BRO190009190: triage again (register entry with evidence, or issue). Never excuse
   without evidence.
2. File the 3 GitHub issues (2002 run, 1947 `99#`, BRO190009190). Opening issues is
   pre-authorized. Update passmarks.md section 2 with E4/E5 (new commit naming this run).
3. Write `results-history.md` (command, elapsed, summary, outcomes); drop or fold the
   raw log `results-history-run1-raw.log`.
4. Task 4.3: update `scripts/AGENTS.md` / Retrosheet DOX sidecars (blank rule, -1 rule,
   sample sources); run `scripts/check_dox.py`.
5. Task 4.4: note result in `play-engine` change (task 2.3) and `openspec/project.md`
   NOW/NEXT; `openspec validate raw-source-tieout`; record the finish-line checklist.

## Ground rules to remember
- Production `mlb` is real data. Every gate run is read-only; always pass
  `--expect-db mlb`.
- Never state tests passed unless they ran. Last verified this session: the two
  test files above only; no full suite, lint, or type check was run.
- Keep replies to the owner short and plain (see `CLAUDE.md`).
- Server note from earlier sessions: Postgres is shared and on spinning disks;
  disposable-DB teardown can be slow when other jobs run (details in git history
  of this file, commit `0950f5b`).
