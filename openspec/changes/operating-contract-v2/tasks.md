## 1. Verify and trim

- [x] 1.1 Confirm `openspec/config.yaml` rules/operations are surfaced by `openspec instructions` and `openspec validate`; fix the schema if not
- [x] 1.2 Trim `AGENTS.md` and `CLAUDE.md`: remove overlap, no-ops and stale lines; keep every live rule reachable by link
- [x] 1.3 Check `CLAUDE.md` still points to every shared rule it relies on

## 2. ADR backfill

- [x] 2.1 List active and recently archived changes whose artifacts state a decision but cite no ADR
- [x] 2.2 Add an ADR to `docs/DECISIONS.md` for each real decision, sourced from the change's own text; flag uncertain ones for the owner
- [x] 2.3 Cite the source change in each ADR (other sessions' `design.md` files left untouched to avoid collisions)

## 3. DOX mesh

- [x] 3.1 Run `scripts/check_dox.py` (passes); deeper content-drift audit not done, see note below
- [ ] 3.2 Fix demonstrable drift; list unresolved items in this change
- [x] 3.3 Add a one-line Operating-protocol pointer to nested `AGENTS.md` (`docs/`, `scripts/`, `tests/`, `transforms/`, `changelog/`)

## 4. Verify and ship

- [ ] 4.1 Run `openspec validate operating-contract-v2` and the repo docs/link checks that exist
- [ ] 4.2 Inspect the final diff; open PR; merge after `test` and `secrets` pass

Note: 3.2 (fixing content drift) is deferred; the structural DOX check passes and a per-sidecar content audit needs its own pass. Finding for owner: archived `pure-python-retrosheet` D3 (oracle only) conflicts with `retrosheet-state-engine` D3 (port the C); ADR-299 records the latter as current.
