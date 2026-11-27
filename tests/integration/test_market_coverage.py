"""A market history fetched before the market closed does not count as held."""

import pandas as pd
import pytest

from mlb_baseball import cli
from mlb_baseball.coverage.model import KalshiCandles, MarketTrades
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
            "UPDATE meta.ingestion_item SET updated_at = '2026-07-01T01:00:00Z' "
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
