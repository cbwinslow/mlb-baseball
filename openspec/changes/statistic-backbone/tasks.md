## 1. Record the Relation 6 decision

- [ ] 1.1 Add **ADR-281** to `docs/DECISIONS.md` (immediately after ADR-280): "grain-complete backbone Relation 6 — `gold.player_season` stays the Baseball-Reference / Lahman official season line; the event-derived `gold.batting_season` / `gold.pitching_season` are the parallel full-history team-aware line; neither is a view over or a second writer into the other." Include the rationale (they carry different data — `era` and BRef-only fields exist only in `player_season`; `ra9` and 1910+ coverage only in the event line — so a merge loses information; the two also serve as a mutual cross-check). Verify: ADR-281 is present, dated, and states the decision + rationale + a "Revisit if" line.
- [ ] 1.2 Update ADR-278's "**Relation 6 (the `gold.player_season` decision) is still open**" paragraph to note it is resolved by ADR-281 (keep both, parallel + documented). Verify: the paragraph no longer says "still open" / "Not yet decided" and points to ADR-281.

## 2. Point the data docs at the spec

- [ ] 2.1 `docs/DATA_DICTIONARY.md` §3 ("Grain-Complete Statistic Backbone") and `docs/TABLE_CONTRACTS.md` (the `gold.batting_game` … `gold.*_career` rows) each gain a one-line pointer to `openspec/specs/statistic-backbone/spec.md` as the authoritative contract. Verify: both files link the spec; run the repo link-check if one exists.
- [ ] 2.2 Confirm `docs/DATA_DICTIONARY.md` states the `gold.player_season` vs `gold.batting_season` relationship (BRef official vs event-derived, parallel, not wired). If it does not, add one sentence citing ADR-281. Verify: the relationship is stated in the data dictionary.

## 3. Verify the spec against the built system

- [ ] 3.1 Check each spec requirement against the running system and record the result in the PR body: the grain set matches migrations 0094–0098; the game builders read `raw.retrosheet_event` event flags (not `core.play`); `era` is absent from the pitching relations and `ra9` present; rates are NULL on a zero denominator (spot-check a real player-season); each relation has an integration test under `tests/integration/test_report_*` and the two-case tie-out script exists (`scripts/verify_baseball_reference_tie_out.py`); every backbone relation's `mlb export` allow-list entry is `local_research`. Verify: a written per-requirement PASS/GAP note in the PR; any GAP is either fixed here (if it is a doc/spec wording error) or filed as a follow-up issue with the spec noting it.

## 4. Validation

- [ ] 4.1 `openspec validate --all` and `openspec validate statistic-backbone --strict` both exit 0. Verify: both pass.
- [ ] 4.2 `docs/DECISIONS.md` renders (no broken ADR anchors); the new spec has no dangling links. Verify: link-check / markdown lint clean on the changed files.
