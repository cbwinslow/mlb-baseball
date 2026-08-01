"""Real DB, real RSS parsing -- the network is mocked, returning small
committed fixture XML (see tests/fixtures/news/). CLAUDE.md "Testing":
every connector needs an integration test that actually loads rows and
asserts idempotency, plus (per this connector's own design point) a test
that one feed's failure doesn't lose or block data from the others."""

from pathlib import Path
from unittest.mock import patch

import pytest

from mlb_baseball.connectors import news

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "news"

_FAKE_FEEDS = [
    ("mlb_com", "twins", "https://www.mlb.com/twins/feeds/news/rss.xml"),
    ("espn", None, "https://www.espn.com/espn/rss/mlb/news"),
]

_FEED_CONTENT = {
    "https://www.mlb.com/twins/feeds/news/rss.xml": (FIXTURES / "feed.xml").read_bytes(),
    "https://www.espn.com/espn/rss/mlb/news": (FIXTURES / "no_guid.xml").read_bytes(),
}


class _FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self) -> None:
        return None


def _fake_get_with_retry(url, **kwargs):
    return _FakeResponse(_FEED_CONTENT[url])


@pytest.fixture(autouse=True)
def _clean_table(db_conn):
    yield
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM raw.news")
    db_conn.commit()


def test_bootstrap_lands_rows_from_every_feed(db_conn):
    with (
        patch.object(news, "_feeds", return_value=_FAKE_FEEDS),
        patch.object(news, "get_with_retry", side_effect=_fake_get_with_retry),
    ):
        counts = news.bootstrap()

    assert counts[news.TABLE] == 3  # 2 items from feed.xml + 1 from no_guid.xml
    with db_conn.cursor() as cur:
        cur.execute("SELECT source, team, guid, dedup_key FROM raw.news ORDER BY id")
        rows = cur.fetchall()
    assert rows[0] == (
        "mlb_com",
        "twins",
        "https://www.mlb.com/news/twins-trade-for-dean-kremer-from-orioles",
        "https://www.mlb.com/news/twins-trade-for-dean-kremer-from-orioles",
    )
    assert rows[2][0] == "espn"
    assert rows[2][1] is None
    assert rows[2][2] is None  # no <guid> on this entry
    assert rows[2][3] is not None  # dedup_key falls back to a link hash


def test_rerunning_inserts_zero_duplicates(db_conn):
    with (
        patch.object(news, "_feeds", return_value=_FAKE_FEEDS),
        patch.object(news, "get_with_retry", side_effect=_fake_get_with_retry),
    ):
        first_counts = news.bootstrap()
        second_counts = news.update()

    assert first_counts[news.TABLE] == 3
    assert second_counts[news.TABLE] == 0  # every item already seen -> ON CONFLICT DO NOTHING
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.news")
        (count,) = cur.fetchone()
    assert count == 3


def test_one_feed_failing_does_not_lose_or_block_the_others(db_conn):
    def _flaky_get(url, **kwargs):
        if "twins" in url:
            raise ConnectionError("simulated network failure")
        return _fake_get_with_retry(url, **kwargs)

    with (
        patch.object(news, "_feeds", return_value=_FAKE_FEEDS),
        patch.object(news, "get_with_retry", side_effect=_flaky_get),
    ):
        counts = news.bootstrap()

    # espn's single item still lands even though the twins feed raised.
    assert counts[news.TABLE] == 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT source FROM raw.news")
        sources = {row[0] for row in cur.fetchall()}
    assert sources == {"espn"}
