"""A market history fetched before the market closed does not count as held."""

import pandas as pd
import pytest

from mlb_baseball import cli
from mlb_baseball.connectors import polymarket
from mlb_baseball.coverage import model
from mlb_baseball.coverage.model import KalshiCandles, MarketTrades, PolymarketWindows
from mlb_baseball.ingest import record_items
from mlb_baseball.load import load_dataframe


@pytest.fixture
def markets(db_conn):
    frame = pd.DataFrame(
        [
            {
                "ticker": t,
                "open_time": "2026-07-01T00:00:00Z",
                "close_time": "2026-07-01T02:00:00Z",
                "volume_fp": "5.00",
            }
            for t in ("EARLY", "AFTER", "NEVER")
        ]
    )
    load_dataframe(db_conn, "raw.kalshi_market", frame)
    for dataset in ("candles", "trades"):
        record_items(
            db_conn,
            [
                {"source": "kalshi", "dataset": dataset, "item_key": key, "status": "loaded"}
                for key in ("EARLY", "AFTER")
            ],
        )
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE meta.ingestion_item SET retrieved_at = '2026-07-01T01:00:00Z' "
            "WHERE source = 'kalshi' AND item_key = 'EARLY'"
        )
    db_conn.commit()
    yield
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.kalshi_market")
        cur.execute("DELETE FROM meta.ingestion_item WHERE source = 'kalshi'")
    db_conn.commit()


@pytest.mark.parametrize("spec", [KalshiCandles(), MarketTrades("kalshi")])
def test_history_cut_off_before_the_close_is_missing(db_conn, markets, spec):
    with db_conn.cursor() as cur:
        (group,) = spec.measure(cur, "unused")

    assert (group.label, group.expected, group.held) == ("2026", 3, 1)


def test_trades_mode_is_refused_for_a_source_without_trades(capsys):
    with pytest.raises(SystemExit):
        cli.main(["ingest", "lahman", "--mode", "trades"])

    assert "no backfill_trades" in capsys.readouterr().out


def test_window_of_a_market_that_closed_early_is_missing_if_fetched_before_the_close(
    db_conn, monkeypatch
):
    window = polymarket.HISTORY_WINDOW_SECONDS
    cell = 1_750_000_000 // window * window
    closed = cell + 3600
    tokens = [
        {"clob_token_id": token, "start_ts": cell + 100, "end_ts": closed}
        for token in ("early", "after")
    ]
    monkeypatch.setattr(polymarket, "_price_tokens", lambda conn: tokens)
    # the market closed two days ago; its 14-day window is still running
    monkeypatch.setattr(model.time, "time", lambda: closed + 2 * 86400)
    record_items(
        db_conn,
        [
            {
                "source": "polymarket",
                "dataset": "price_history",
                "item_key": f"{token['clob_token_id']}:{cell}",
                "status": "loaded",
            }
            for token in tokens
        ],
    )
    try:
        with db_conn.cursor() as cur:
            for token, fetched in (("early", closed - 60), ("after", closed + 60)):
                cur.execute(
                    "UPDATE meta.ingestion_item SET retrieved_at = to_timestamp(%s) "
                    "WHERE source = 'polymarket' AND item_key = %s",
                    (fetched, f"{token}:{cell}"),
                )
            (group,) = PolymarketWindows().measure(cur, "unused")

        assert (group.expected, group.held) == (2, 1)
    finally:
        db_conn.rollback()
        with db_conn.cursor() as cur:
            cur.execute("DELETE FROM meta.ingestion_item WHERE source = 'polymarket'")
        db_conn.commit()
