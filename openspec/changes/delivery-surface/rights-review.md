# Backbone table publish-eligibility review (apply task 1.1)

Reviewed 2026-09-02, for the `delivery-surface` change. Determines which of
the ten candidate backbone tables (`proposal.md` "Data scope") may ship in
the public `backbone` HF export preset. This is a **redistribution rights**
decision, separate from `mlb_baseball/export.py`'s existing `ExportRelation.profile`
field / `MLB_DATA_PROFILE` gate, which governs per-source *intake* permission
(see `docs/SOURCE_RIGHTS.md`) and is stricter than needed here: it fails a
table the moment any joined dimension touches a non-Retrosheet source, even
when that join contributes only a structural surrogate key and no borrowed
content. The test applied below is content-based: does the exported
**column data** originate from a source `docs/SOURCE_RIGHTS.md` marks
"no"/"no automated approval" for public-safe redistribution?

Evidence: each table's defining migration (`migrations/0094`-`0098`,
`migrations/0030`) and `docs/SOURCE_RIGHTS.md`'s source-rights table.

| Table | Content source | FK/join content | `docs/SOURCE_RIGHTS.md` verdict | Publishable |
|---|---|---|---|---|
| `gold.batting_game` | `raw.retrosheet_event` only (`source = 'retrosheet_event'` default) | `core.game`/`core.player`/`core.team` — integer surrogate keys only, no borrowed columns | Retrosheet: "yes, with attribution" | **Yes** |
| `gold.pitching_game` | `raw.retrosheet_event` only | same as above | Retrosheet: yes | **Yes** |
| `gold.batting_season` | Rolled up from `gold.batting_game` | same surrogate-key-only joins | Retrosheet: yes | **Yes** |
| `gold.pitching_season` | Rolled up from `gold.pitching_game` | same | Retrosheet: yes | **Yes** |
| `gold.batting_team` | Rolled up from `gold.batting_game` | same | Retrosheet: yes | **Yes** |
| `gold.pitching_team` | Rolled up from `gold.pitching_game` | same | Retrosheet: yes | **Yes** |
| `gold.batting_career` | Rolled up from `gold.batting_season` | same | Retrosheet: yes | **Yes** |
| `gold.pitching_career` | Rolled up from `gold.pitching_season` | same | Retrosheet: yes | **Yes** |
| `gold.player_season` | `raw.bref_batting`/`raw.bref_pitching` (Baseball-Reference via `pybaseball`) + `core.player_war` (Baseball-Reference WAR) — `migrations/0030_gold_reporting.sql` | — | Baseball-Reference via pybaseball: **"no"** (no permission evidence for redistribution) | **No** |
| `gold.team_season` | `raw.lahman_teams` (traditional totals) + `core.player_war` (war column, Baseball-Reference) — `migrations/0030_gold_reporting.sql` | — | Lahman: **"no automated approval"**; Baseball-Reference: **"no"** | **No** |

## Result

`backbone` preset publishes **8 of 10** candidates:
`batting_game`, `pitching_game`, `batting_season`, `pitching_season`,
`batting_team`, `pitching_team`, `batting_career`, `pitching_career`.

Excluded, each with its reason recorded in the export manifest and log
(`mlb_baseball/export.py::BACKBONE_EXCLUDED`):
- `gold.player_season` — Baseball-Reference-sourced (`raw.bref_batting`/`raw.bref_pitching`, `core.player_war`); no redistribution permission on record.
- `gold.team_season` — Lahman-sourced (`raw.lahman_teams`) plus Baseball-Reference WAR (`core.player_war`); no redistribution permission on record for either source.

This matches the risk `design.md` flagged in advance ("A backbone table
turns out `local_research`-only → it can't ship... a real possibility for
`player_season`... and `team_season`") — confirmed, not merely anticipated.
The milestone's "ten backbone tables" coverage claim in `openspec/project.md`
should read eight publishable relations plus two excluded on rights grounds,
not ten; `docs/PUBLIC_API.md` / the delivery docs are updated accordingly in
task 5.4.
