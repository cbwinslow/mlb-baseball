"""Real DB, real cwevent/cwgame subprocess parsing against the fixture zip
(a synthetic two-year archive built from a trimmed real 2024 event file,
duplicated to a second season) — only the network download is mocked."""

from pathlib import Path
from unittest.mock import patch

import pytest

from mlb_baseball import chadwick_tools
from mlb_baseball.connectors import retrosheet_event as event

FIXTURE_ZIP = (
    Path(__file__).resolve().parent.parent / "fixtures" / "retrosheet_event" / "decade.zip"
)

# Every test in this file exercises real cwevent/cwgame subprocess parsing
# (only the network download is mocked) — skip cleanly, not fail, if these
# aren't installed. See README.md "Requirements".
pytestmark = pytest.mark.skipif(
    bool(chadwick_tools.missing_tools()),
    reason=f"cwevent/cwgame not installed: {chadwick_tools.missing_tools()}",
)


@pytest.fixture(autouse=True)
def _clean_tables(db_conn):
    def _drop() -> None:
        db_conn.rollback()
        with db_conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {event.EVENT_TABLE}")
            cur.execute(f"DROP TABLE IF EXISTS {event.GAME_TABLE}")
        db_conn.commit()

    _drop()
    yield
    _drop()


@pytest.fixture(autouse=True)
def _isolated_manifest(tmp_path, monkeypatch):
    # Every test here uses filename "decade.zip", which would otherwise
    # write real manifest state to downloads/retrosheet_event/manifest.json
    # (the same file the real production bootstrap uses) and leak status
    # between tests, since manifest.download() is mocked but manifest.mark_status()
    # and manifest.load_manifest() are not — they'd hit the real file. Redirect
    # to a fresh tmp_path per test instead.
    monkeypatch.setattr(event.manifest, "DOWNLOADS_ROOT", tmp_path)


def test_load_archive_lands_both_tables_for_every_year_present(db_conn):
    with patch.object(event.manifest, "download", return_value=FIXTURE_ZIP):
        counts = event._load_archive(db_conn, "decade.zip", "https://example.com/decade.zip", "pbp")
    db_conn.commit()

    assert counts[event.EVENT_TABLE] > 0
    assert counts[event.GAME_TABLE] > 0
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT DISTINCT _season FROM {event.EVENT_TABLE} ORDER BY 1")
        assert cur.fetchall() == [("2024",), ("2025",)]
        cur.execute(f"SELECT game_id, bat_id, pit_id FROM {event.EVENT_TABLE} LIMIT 1")
        assert cur.fetchone() is not None
        cur.execute(f"SELECT game_id, home_team_id, away_team_id FROM {event.GAME_TABLE} LIMIT 1")
        assert cur.fetchone() is not None

    entry = event.manifest.load_manifest(event.SOURCE)["decade.zip"]
    assert entry["parser_version"] == event.PARSER_VERSION
    assert entry["schema_fingerprint"]


def test_reloading_an_archive_replaces_its_years_without_touching_others(db_conn):
    with patch.object(event.manifest, "download", return_value=FIXTURE_ZIP):
        event._load_archive(db_conn, "decade.zip", "https://example.com/decade.zip", "pbp")
        db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            f"INSERT INTO {event.EVENT_TABLE} (game_id, _season) VALUES ('FAKE202301010', '2023')"
        )
    db_conn.commit()

    with patch.object(event.manifest, "download", return_value=FIXTURE_ZIP):
        event._load_archive(db_conn, "decade.zip", "https://example.com/decade.zip", "pbp")
        db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            f"SELECT _season, count(*) FROM {event.EVENT_TABLE} GROUP BY _season ORDER BY 1"
        )
        rows = cur.fetchall()
    assert ("2023", 1) in rows
    assert any(season == "2024" for season, _ in rows)
    assert any(season == "2025" for season, _ in rows)


def test_loading_a_different_group_for_the_same_season_does_not_wipe_the_first(db_conn):
    # Regression: a real production run lost ~16M regular-season rows this
    # way. Multiple archives independently cover the same season (a
    # regular-season decade zip, post-season, all-star, Negro League), and
    # scoping the replace on _season alone meant loading a later archive for
    # a year already covered by an earlier one deleted the earlier archive's
    # rows before inserting its own much smaller set. The fix scopes on
    # _season + _group combined (_scope) instead.
    with patch.object(event.manifest, "download", return_value=FIXTURE_ZIP):
        event._load_archive(db_conn, "decade.zip", "https://example.com/decade.zip", "pbp")
        db_conn.commit()
        with db_conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {event.EVENT_TABLE} WHERE _season = '2024'")
            (pbp_only_count,) = cur.fetchone()
        assert pbp_only_count > 0

        # force=True: in production, a distinct filename always maps to one
        # group (e.g. "allpost.zip" is always "postseason"), so the
        # already-loaded skip only ever applies within the same group. Here
        # the same fixture filename is deliberately reused under a second
        # group to isolate the _scope fix from that skip behavior.
        event._load_archive(
            db_conn,
            "decade.zip",
            "https://example.com/decade.zip",
            "postseason",
            force=True,
        )
        db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            f"SELECT _group, count(*) FROM {event.EVENT_TABLE} "
            "WHERE _season = '2024' GROUP BY _group ORDER BY 1"
        )
        by_group = dict(cur.fetchall())

    assert by_group["pbp"] == pbp_only_count
    assert by_group["postseason"] > 0


def test_load_archive_skips_already_loaded_archive_without_reparsing(db_conn):
    # Resuming a partly-failed bootstrap shouldn't redo cwevent/cwgame on
    # every already-successful archive — only the manifest lookup should
    # happen; download() must not even be called.
    with patch.object(event.manifest, "download", return_value=FIXTURE_ZIP):
        event._load_archive(db_conn, "decade.zip", "https://example.com/decade.zip", "pbp")
        db_conn.commit()

    with patch.object(event.manifest, "download") as mock_download:
        counts = event._load_archive(db_conn, "decade.zip", "https://example.com/decade.zip", "pbp")

    assert counts == {}
    mock_download.assert_not_called()


def test_load_archive_force_reparses_even_when_already_loaded(db_conn):
    with patch.object(event.manifest, "download", return_value=FIXTURE_ZIP):
        event._load_archive(db_conn, "decade.zip", "https://example.com/decade.zip", "pbp")
        db_conn.commit()

        counts = event._load_archive(
            db_conn, "decade.zip", "https://example.com/decade.zip", "pbp", force=True
        )

    assert counts[event.EVENT_TABLE] > 0


def test_missing_archive_returns_empty_without_erroring(db_conn):
    with patch.object(event.manifest, "download", return_value=None):
        counts = event._load_archive(
            db_conn, "9999seve.zip", "https://example.com/9999seve.zip", "pbp"
        )

    assert counts == {}


def test_bootstrap_loads_configured_archives(monkeypatch, db_conn):
    monkeypatch.setattr(event, "PBP_DECADE_ARCHIVES", {"decade.zip": range(2024, 2026)})
    monkeypatch.setattr(event, "SPECIAL_ARCHIVES", {})

    with patch.object(event.manifest, "download", return_value=FIXTURE_ZIP):
        totals = event.bootstrap()

    assert totals[event.EVENT_TABLE] > 0
    assert totals[event.GAME_TABLE] > 0


def test_one_years_cwevent_failure_does_not_lose_other_years_in_same_archive(db_conn):
    # Regression: a real full-history bootstrap hit a genuine cwevent bug on
    # a single year (1919, the last year of the 1910s decade archive) with
    # no per-year isolation in _parse_archive -- results was only ever
    # loaded into the database after the *whole* archive finished parsing,
    # so that one failure lost every other year already sitting in the same
    # archive too (2024's decade.zip fixture here stands in for that: 2024
    # and 2025 share one archive, same as any real decade zip's years do).
    real_run_cwevent = chadwick_tools.run_cwevent

    def flaky_run_cwevent(event_dir, year):
        if year == 2024:
            raise RuntimeError("simulated cwevent bug, e.g. an invalid field spec")
        return real_run_cwevent(event_dir, year)

    with (
        patch.object(event.manifest, "download", return_value=FIXTURE_ZIP),
        patch.object(event.chadwick_tools, "run_cwevent", side_effect=flaky_run_cwevent),
    ):
        counts = event._load_archive(db_conn, "decade.zip", "https://example.com/decade.zip", "pbp")
    db_conn.commit()

    assert counts[event.EVENT_TABLE] > 0
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT DISTINCT _season FROM {event.EVENT_TABLE}")
        assert cur.fetchall() == [("2025",)]


def test_bootstrap_continues_past_a_failing_archive(monkeypatch, db_conn):
    # Regression: bootstrap() had no per-archive exception handling either,
    # so with 12 decade archives plus several special ones, one archive
    # failing outright (as above) aborted every remaining archive too --
    # confirmed the hard way: a real bootstrap produced zero rows for this
    # entire source. Mirrors retrosheet.py's per-year fix (ADR-059).
    monkeypatch.setattr(event, "PBP_DECADE_ARCHIVES", {"bad-decade.zip": None, "decade.zip": None})
    monkeypatch.setattr(event, "SPECIAL_ARCHIVES", {})
    real_load_archive = event._load_archive

    def flaky_load_archive(conn, filename, url, group, *, force=False):
        if filename == "bad-decade.zip":
            raise RuntimeError("simulated archive-level failure")
        return real_load_archive(conn, filename, url, group, force=force)

    with (
        patch.object(event.manifest, "download", return_value=FIXTURE_ZIP),
        patch.object(event, "_load_archive", side_effect=flaky_load_archive),
    ):
        totals = event.bootstrap()

    assert totals[event.EVENT_TABLE] > 0
    assert totals[event.GAME_TABLE] > 0
