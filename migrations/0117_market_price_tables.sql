-- Typed, compressed storage for the two big market price tables
-- (openspec change stabilize-and-market-store, spec market-price-store).
--
-- raw.polymarket_price (110 GB) and raw.kalshi_candle (40 GB) hold every value as text.
-- This migration creates NOTHING large and touches neither table: it adds
--   * meta.create_market_tables(suffix)  builds the typed target tables, and
--   * the two reject tables for values that fail their type check.
-- The one-off conversion of production is an owner-approved step that calls
--   SELECT meta.create_market_tables('_new');
-- then copies in month chunks and swaps names. A fresh database calls it with '' from the
-- new loaders' bootstrap path. When the timescaledb extension is present the tables are
-- hypertables with 30-day chunks (ts is epoch seconds) and columnar compression
-- segmented by the market key; without it (a stock postgres:16) they are plain tables
-- with the same columns and keys, so nothing above the storage layer changes.

-- Optional at the server level, like the extensions of 0116: created only when the server ships
-- timescaledb (and it is preloaded); otherwise skipped, and the tables below are plain tables.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb') THEN
        BEGIN
            CREATE EXTENSION IF NOT EXISTS timescaledb;
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'timescaledb not created (%); market tables will be plain tables', SQLERRM;
        END;
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS raw.polymarket_price_reject (
    clob_token_id text,
    _market       text,
    _event        text,
    ts            text,
    price         text,
    reason        text NOT NULL,
    rejected_at   timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE raw.polymarket_price_reject IS
    'Polymarket price rows whose values failed their type check, kept as the source text (spec market-price-store).';

CREATE TABLE IF NOT EXISTS raw.kalshi_candle_reject (
    ticker      text,
    ts          text,
    source_row  jsonb NOT NULL,
    reason      text NOT NULL,
    rejected_at timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE raw.kalshi_candle_reject IS
    'Kalshi candle rows whose values failed their type check, kept as the source text in source_row (spec market-price-store).';

CREATE OR REPLACE FUNCTION meta.create_market_tables(suffix text DEFAULT '')
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    poly text := format('raw.%I', 'polymarket_price' || suffix);
    kal  text := format('raw.%I', 'kalshi_candle' || suffix);
    price_cols text;
    has_ts boolean := EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb');
BEGIN
    IF to_regclass(poly) IS NULL THEN
        EXECUTE format($f$
            CREATE TABLE %s (
                clob_token_id text             NOT NULL,
                _market       integer,
                _event        integer,
                ts            bigint           NOT NULL,
                price         double precision,
                _loaded_at    timestamptz      NOT NULL DEFAULT now(),
                UNIQUE (clob_token_id, ts)
            )$f$, poly);
        IF has_ts THEN
            EXECUTE format('SELECT create_hypertable(%L, %L, chunk_time_interval => 2592000)', poly, 'ts');
            EXECUTE format(
                'ALTER TABLE %s SET (timescaledb.compress, timescaledb.compress_segmentby = %L, timescaledb.compress_orderby = %L)',
                poly, 'clob_token_id', 'ts');
        END IF;
    END IF;

    IF to_regclass(kal) IS NULL THEN
        SELECT string_agg(format('%I numeric(10,4)', c), ', ' ORDER BY ord)
          INTO price_cols
          FROM unnest(ARRAY[
              'yes_bid_close_dollars', 'yes_bid_high_dollars', 'yes_bid_low_dollars', 'yes_bid_open_dollars',
              'yes_ask_close_dollars', 'yes_ask_high_dollars', 'yes_ask_low_dollars', 'yes_ask_open_dollars',
              'price_close_dollars', 'price_high_dollars', 'price_low_dollars', 'price_mean_dollars',
              'price_open_dollars', 'price_previous_dollars',
              'price_close', 'price_high', 'price_low', 'price_mean', 'price_open', 'price_previous',
              'yes_bid_close', 'yes_bid_high', 'yes_bid_low', 'yes_bid_open',
              'yes_ask_close', 'yes_ask_high', 'yes_ask_low', 'yes_ask_open'
          ]) WITH ORDINALITY AS t(c, ord);
        EXECUTE format($f$
            CREATE TABLE %s (
                ticker        text          NOT NULL,
                ts            bigint        NOT NULL,
                open_interest numeric(14,2),
                volume        numeric(14,2),
                _loaded_at    timestamptz   NOT NULL DEFAULT now(),
                %s,
                UNIQUE (ticker, ts)
            )$f$, kal, price_cols);
        IF has_ts THEN
            EXECUTE format('SELECT create_hypertable(%L, %L, chunk_time_interval => 2592000)', kal, 'ts');
            EXECUTE format(
                'ALTER TABLE %s SET (timescaledb.compress, timescaledb.compress_segmentby = %L, timescaledb.compress_orderby = %L)',
                kal, 'ticker', 'ts');
        END IF;
    END IF;
END;
$$;
COMMENT ON FUNCTION meta.create_market_tables(text) IS
    'Creates the typed (hypertable when timescaledb exists) raw.polymarket_price<suffix> and raw.kalshi_candle<suffix> if absent. Does nothing to a table that already exists.';
