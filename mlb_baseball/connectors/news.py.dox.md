# news.py DOX

## Purpose

Own lightweight MLB news/RSS ingestion for later research/event-signal work.
The connector stores headlines, links, summaries, publication time, and source/team
context; it deliberately does not ingest full article bodies.

## Ownership

Source implementation: `news.py`.

Owned raw relation: `raw.news`.

Registry source name: `news`.

Focused integration test: `tests/integration/test_news_load.py`.

## Source Contracts

Current verified feed families:

- MLB.com league-wide plus all 30 teams;
- MLB Trade Rumors league-wide plus all 30 teams;
- ESPN league-wide MLB feed.

Team feed URLs are explicit verified mappings. Do not invent URL patterns for
sources that have not been confirmed to expose a working team feed.

Only feed metadata/summary content is retained. Full article scraping would change
both rights risk and connector scope and requires a separate decision.

## Runtime Contracts

- RSS sources expose only recent feed windows; there is no historical archive to
  bootstrap. Therefore `bootstrap()` and `update()` poll the same feeds and
  history accrues from the first successful project poll forward.
- Feed items are append/deduplicated, not scope-replaced.
- `dedup_key` is the source-issued GUID/ID when present; otherwise SHA-256 of the
  link. Entries lacking both are skipped visibly.
- `raw.news` has a real UNIQUE constraint on `dedup_key`; inserts use
  `ON CONFLICT (dedup_key) DO NOTHING`.
- Each feed is committed independently. One broken feed must not roll back items
  already landed from other feeds or prevent remaining feeds from running.
- `fetched_at` represents when a genuinely new row first landed. Conflict-skipped
  refetches do not update it.

## Freshness Semantics

The last successful connector run is not enough to prove the feeds are producing
new content, because `_run()` intentionally tolerates per-feed failures.

`_freshness_check()` therefore separately examines the newest `fetched_at` value
and flags a long period without any newly inserted article. Preserve that
separation between "poll ran" and "new content arrived."

## Downstream Context

`raw.news` is an unstructured research input. Future injury/trade/rumor/NLP
features require their own reproducible extraction/versioning/PIT contracts.
Never use a story published after a game cutoff to build a pregame feature.

## Rights

Keep this connector limited to feed-provided metadata/summary material unless
source-rights review explicitly approves more. Feed availability does not imply
license to republish full source content.

## Verification

Run:

```bash
uv run pytest tests/integration/test_news_load.py -q
uv run ruff check mlb_baseball/connectors/news.py tests/integration/test_news_load.py
```

Verify duplicate polling, one-feed failure isolation, GUID/link fallback, and
freshness behavior when changing this connector.
