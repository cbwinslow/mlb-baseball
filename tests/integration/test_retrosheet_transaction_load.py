"""Real DB, real CSV parsing — the network is mocked, returning a small
committed zip (two synthetic rows matching the real 16-field tran.txt layout)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from mlb_baseball.connectors import retrosheet_transaction as transaction

FIXTURE_ZIP = (
    Path(__file__).resolve().parent.parent / "fixtures" / "retrosheet_transaction" / "tranDB.zip"
)


@pytest.fixture(autouse=True)
def _clean_table(db_conn):
    yield
    with db_conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {transaction.TABLE}")
    db_conn.commit()


def test_bootstrap_lands_all_sixteen_fields(db_conn):
    with patch.object(transaction, "manifest") as mock_manifest:
        mock_manifest.download.return_value = FIXTURE_ZIP
        counts = transaction.bootstrap()

    assert counts[transaction.TABLE] == 2
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_schema = 'raw' AND table_name = 'retrosheet_transaction'"
        )
        (column_count,) = cur.fetchone()
        # 16 documented fields + _loaded_at (see load.py) — no scope_column here.
        assert column_count == 17
        cur.execute(
            f"SELECT player_id, from_team, to_team FROM {transaction.TABLE} "
            "ORDER BY player_id LIMIT 1"
        )
        row = cur.fetchone()
    assert row == ("aardd001", None, "SFN")


def test_rerunning_replaces_instead_of_duplicating(db_conn):
    with patch.object(transaction, "manifest") as mock_manifest:
        mock_manifest.download.return_value = FIXTURE_ZIP
        first_counts = transaction.bootstrap()
        second_counts = transaction.update()

    assert first_counts == second_counts
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {transaction.TABLE}")
        (count,) = cur.fetchone()
    assert count == first_counts[transaction.TABLE]
