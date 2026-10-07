## Context

ADR-296 (PR #356) put the Operating protocol in root `AGENTS.md`. Root
`AGENTS.md` is the shared contract; `CLAUDE.md` is Claude-only behavior, so
shared rules must live once, in `AGENTS.md`. Evidence from the audit: about
half of the active OpenSpec changes cite no ADR; 42 `*.dox.md` sidecars exist
with no freshness check; `openspec/config.yaml` `rules` were added but not
confirmed to be consumed by the CLI.

## Goals / Non-Goals

**Goals:** shorter, non-overlapping operating docs; ADR coverage for real
decisions; verified (not assumed) config rules; accurate DOX sidecars; the
protocol discoverable from every nested `AGENTS.md`.

**Non-Goals:** code/SQL/data changes; removing Hugging Face publishing
(separate change); branch-protection settings; rewriting archived history or
existing ADR text.

## Decisions

- **Trim by pointer.** Where `CLAUDE.md` restates `AGENTS.md`, replace with a link. Test each line: does it change agent behavior versus the default? If not, delete it (mattpocock `writing-for-agents`).
- **Keep our ADR log, not `docs/adr/`.** `docs/DECISIONS.md` (newest first) stays the single ADR home; the domain-modeling skill's format is used only for "is this ADR-worthy" (hard to reverse, surprising, real trade-off).
- **Backfill only real decisions.** Each backfilled ADR must come from a decision already stated in that change's artifacts; no invented rationale. Changes with no real decision get no ADR.
- **DOX audit is read-only first.** Compare each sidecar to its source; fix only demonstrable drift, list the rest as findings.
- **Nested pointers are one line each**, linking to root Operating protocol.

## Risks / Trade-offs

- Another session may touch the same files: work stays in this worktree, small PR, rebase before merge.
- Backfilled ADRs could misstate intent: draft from change artifacts and flag uncertain ones to the owner instead of guessing.
- Over-trimming could drop a live rule: each deletion is justified in the PR description.
