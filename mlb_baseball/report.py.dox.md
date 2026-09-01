# report.py DOX

## Purpose

Own the current gold-layer researcher-facing season/reporting rebuild stage. It
turns already-conformed core relations plus selected source season tables into
entity-level `gold` relations used for direct research queries.

## Ownership

Source implementation: `report.py`.

Major outputs currently include:

- `gold.player_season`
- `gold.team_season`
- `gold.division_standing`

Registry/run source name: `report`.

Primary integration contract: `tests/integration/test_report.py`.

## Stage Contract

`mlb report` is a distinct stage:

```text
ingest -> conform -> report
```

It is not a connector and performs no network I/O. It should not be silently
folded into prediction or ingestion workflows merely because they share inputs.

Required conformed relations such as `core.player`, `core.team`, and
`core.standing` must be populated first. Fail prerequisites with an actionable
"run mlb conform" message rather than producing partial misleading marts.

## Rebuild Contract

Current reporting relations are small enough that full truncate/rebuild is the
intentional strategy. Builder order matters where one pass depends on values
created by an earlier pass (for example park-factor-dependent calculations).

Do not make one relation incremental without defining immutable keys/history and
proving parity; research reproducibility is more important than saving seconds on
small season marts.

## Statistical Ownership Caveat

This module currently imports sabermetric constants/mappings from
`model.offense`/`model.war`. That dependency direction is recognized technical
debt: reusable stat definitions should eventually live in a neutral statistics
package/registry used by both reporting and modeling.

Until that refactor occurs:

- do not create another copy of wOBA/related constants in `report.py`;
- preserve parity with the existing canonical implementation;
- when moving constants/formulas, add hand-calculated and cross-language/relation
  parity tests before changing outputs.

## Grain and Aggregation Contracts

- `gold.player_season` is player-season-role/stat-line research output; preserve
  explicit pitcher/batter interpretation and source/canonical player join rules.
- `gold.team_season` is team-season output.
- `gold.division_standing` is season/division/team standing output.
- Do not average game-level rate statistics to create season rates. Aggregate
  underlying numerators/denominators when the source/definition supports it.
- Source season tables may be final-season values and are **not** automatically
  point-in-time-safe pregame features. Keep the distinction explicit in docs and
  downstream model code.

## Source Join Doctrine

The stage intentionally uses selected raw season/reference tables where core does
not yet expose an equivalent stable relation. Exact source ID mappings are
preferred; ambiguous historical records should be omitted/null rather than merged
on an invented assumption.

Source-specific team/name quirks should remain small/local and evidence-backed.
If the same mapping becomes broadly reused, move it to a canonical identity layer
rather than duplicating it in multiple report/stat modules.

## Future Direction

As the research grain ladder matures, reporting should become a thin orchestrator
over stable game/season/career relations and neutral stat definitions. Good future
ownership may include SQLMesh models plus a small Python facade, but migration must
preserve exact row/grain/formula tie-outs.

## Verification

Run:

```bash
uv run pytest tests/integration/test_report.py -q
uv run ruff check mlb_baseball/report.py tests/integration/test_report.py
uv run mypy mlb_baseball/report.py
```

For formula changes, add deterministic hand fixtures and tie out representative
player/team seasons against a credible source or the prior accepted relation.
