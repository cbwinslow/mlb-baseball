"""Pure parsing/dedup-key logic -- no network, no DB. See CLAUDE.md "Testing"."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from mlb_baseball.connectors import news

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "news"


def test_parses_title_link_guid_published_summary_and_tags_team():
    raw = (FIXTURES / "feed.xml").read_bytes()
    rows = news.parse_entries("mlb_com", "twins", raw)

    assert len(rows) == 2
    first = rows[0]
    assert first["source"] == "mlb_com"
    assert first["team"] == "twins"
    assert first["title"] == "Twins acquiring veteran starter Kremer from Orioles"
    assert first["link"] == "https://www.mlb.com/news/twins-trade-for-dean-kremer-from-orioles"
    assert first["guid"] == "https://www.mlb.com/news/twins-trade-for-dean-kremer-from-orioles"
    # guid present -> dedup_key is the guid itself, not a hash.
    assert first["dedup_key"] == first["guid"]
    assert first["published"] == datetime(2026, 8, 1, 6, 4, 0, tzinfo=UTC)
    assert "Kremer" in first["summary"]
    assert first["fetched_at"].tzinfo is not None


def test_league_wide_feed_has_no_team_tag():
    raw = (FIXTURES / "feed.xml").read_bytes()
    rows = news.parse_entries("mlb_com", None, raw)
    assert all(row["team"] is None for row in rows)


def test_falls_back_to_link_hash_when_guid_missing():
    raw = (FIXTURES / "no_guid.xml").read_bytes()
    rows = news.parse_entries("espn", None, raw)

    assert len(rows) == 1
    row = rows[0]
    assert row["guid"] is None
    expected = hashlib.sha256(row["link"].encode()).hexdigest()
    assert row["dedup_key"] == expected


def test_dedup_key_prefers_guid_over_link_hash():
    assert news._dedup_key("some-guid", "https://example.com/x") == "some-guid"


def test_dedup_key_hashes_link_when_guid_absent():
    link = "https://example.com/x"
    assert news._dedup_key(None, link) == hashlib.sha256(link.encode()).hexdigest()


def test_dedup_key_is_none_when_entry_has_neither():
    assert news._dedup_key(None, None) is None


def test_feeds_cover_all_30_teams_for_both_per_team_sources():
    feeds = news._feeds()
    mlb_com_teams = {team for source, team, _ in feeds if source == "mlb_com" and team}
    mlbtr_teams = {team for source, team, _ in feeds if source == "mlb_trade_rumors" and team}
    assert len(mlb_com_teams) == 30
    assert len(mlbtr_teams) == 30
    assert mlb_com_teams == mlbtr_teams  # same canonical team keys across both sources


def test_feeds_include_one_league_wide_entry_per_source():
    feeds = news._feeds()
    league_wide_sources = {source for source, team, _ in feeds if team is None}
    assert league_wide_sources == {"mlb_com", "mlb_trade_rumors", "espn"}
