@AGENTS.md

# Claude Code — connector rules

Shared connector/source contracts live in `AGENTS.md` and each module's `*.dox.md`. This file contains only Claude-specific operating guidance for connector work.

## Progressive disclosure

- When changing `foo.py`, read `foo.py.dox.md` first if it exists; do not load every connector sidecar.
- If the sidecar links an ADR/source-rights entry/test, open only the references needed for the behavior being changed.
- Treat unverified source assumptions as hypotheses. If a coverage/endpoint/schema fact matters and current source/tests do not prove it, perform a bounded source check before coding when tooling/access permits.

## Claude-specific work discipline

- Use a research/review subagent for a bounded external-client parity check only when it materially helps a connector decision; keep implementation deterministic and project-owned.
- When delegating a connector edit, explicitly include: source module, matching sidecar, permitted source profile, target raw tables, expected idempotency grain, and tests to run.
- Do not allow a delegated agent to add a new source, paid service, or broad endpoint family without returning for owner/plan review.
- If an upstream SDK appears to solve the problem, compare it against the connector's existing behavior before recommending replacement. A library being newer or cleaner is not sufficient evidence.
- Preserve source-faithful raw quirks even when Claude can infer a seemingly obvious normalization; normalization belongs downstream unless the source contract says otherwise.

## Verification

- For network code, prefer captured/mocked payloads in routine tests and a separate bounded real-source smoke/parity check when needed.
- Re-run connector integration/idempotency tests yourself after delegated changes.
- If real-source behavior was checked, record the exact observed boundary/quirk in the sidecar or ADR when it becomes durable project knowledge.
