# Source rights and data profiles

Status reviewed 2026-08-05. This is an engineering control and evidence log,
not legal advice. A source is *not* public-safe merely because the endpoint is
unauthenticated or the project currently uses it for noncommercial research.

| Source family | Evidence / current restriction | Local research | Licensed full | Public-safe display, redistribution, or ML |
|---|---|---:|---:|---:|
| Retrosheet data products | Retrosheet's published use policy permits giving away, selling, and commercial products; it asks users to acknowledge Retrosheet. | yes | yes | yes, with attribution |
| Lahman | Project documentation identifies CC BY-SA, but the exact release/license notice must travel with any public derivative. | yes | pending attribution/share-alike review | no automated approval |
| Chadwick Register | License and redistribution terms need a pinned-release review. | yes | no | no |
| MLB Stats API and Baseball Savant/Statcast | MLB terms prohibit automated scripts collecting or interacting with MLB Digital Properties. | yes, owner-risk research only | no | no |
| Baseball-Reference via pybaseball | No permission evidence recorded for automated collection, predictive ML, or redistribution. | yes, owner-risk research only | no | no |
| Polymarket / Kalshi | Public read access is not a redistribution, content, or commercial-display license. | yes, owner-risk research only | no | no |
| RSS/news feeds | Feed access does not establish rights to republish summaries, derived NLP features, or commercial content. | yes, owner-risk research only | no | no |

Evidence: [Retrosheet use policy](https://www.retrosheet.org/newsltr1.htm),
[Retrosheet site notice](https://www.retrosheet.org/index.html), and
[MLB Terms of Use](https://www.mlb.com/official-information/terms-of-use?bpexternal=true).
Before changing a row to public-safe, retain the source's current terms,
specific permitted use, attribution wording, redistribution terms, ML/model
training permission, generated-content permission, commercial permission, and
review date in the same pull request.

## Enforced profiles

- `local_research` is the default and permits owner-controlled research intake.
  It must not be used as evidence that a table, feature, model, chart, or
  download can be publicly served.
- `licensed_full` is intentionally no broader than `public_safe` until an
  executed license is recorded here.
- `public_safe` currently permits only Retrosheet connector families. Its
  ingest guard fails closed for every other connector.

Set `MLB_DATA_PROFILE` or pass `--profile` to `mlb ingest`, `mlb bootstrap`,
or `mlb update`. The CLI blocks a forbidden connector before it makes a
network request. Downstream public-serving controls remain a prerequisite for
Plan 05: each serving object must carry source lineage and call the same
profile guard before publication.

## Attribution

Public artifacts that use Retrosheet data must include the current Retrosheet
attribution/copyright notice supplied with the relevant data shipment. Preserve
the original source release and its notice in the ingestion manifest.
