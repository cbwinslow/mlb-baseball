-- raw.news: headlines/links/summaries polled from per-team and league-wide
-- RSS feeds (MLB.com, MLB Trade Rumors, ESPN) -- see docs/DATA_SOURCES.md
-- "News/RSS" row and docs/DECISIONS.md ADR-047.
--
-- Unlike every other raw table (deliberately untyped, no constraints -- see
-- docs/ARCHITECTURE.md "Layered schema"), this one is hand-authored with a
-- real UNIQUE constraint. RSS feeds re-serve the same items every poll, so
-- idempotency here means "the same item, seen again, inserts nothing" --
-- an ON CONFLICT DO NOTHING against a unique index, which load_dataframe's
-- untyped-text/full-reload and append_dataframe's pure-insert patterns
-- can't express (see ADR-047 for why a fourth loading pattern is justified
-- here specifically, not generalized).
--
-- dedup_key is the feed's own guid where present, falling back to a sha256
-- of the link for the rare feed that omits one -- computed in news.py, not
-- here, so the connector can control the fallback logic.
CREATE TABLE IF NOT EXISTS raw.news (
    id bigserial PRIMARY KEY,
    source text NOT NULL,
    team text,
    title text,
    link text,
    guid text,
    dedup_key text NOT NULL,
    published timestamptz,
    summary text,
    fetched_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS news_dedup_key_idx ON raw.news (dedup_key);
