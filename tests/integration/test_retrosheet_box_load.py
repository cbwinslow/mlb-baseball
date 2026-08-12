"""Real DB, real cwbox subprocess parsing against real trimmed fixtures —
only the network downloads are mocked. Two archive shapes are tested
separately since they need different handling: "1900sbox.zip" bundles its
own real TEAM/roster files (mirrors the "na" pre-1898 archives), while
"1900sbox_no_team.zip" has neither (mirrors the actual "era"/"negro_league"
archives) and exercises the team-file-construction path."""

import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from mlb_baseball import chadwick_tools
from mlb_baseball.connectors import retrosheet_box as box

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "retrosheet_box"
SELF_CONTAINED_ZIP = FIXTURES_DIR / "1900sbox.zip"
NO_TEAM_ZIP = FIXTURES_DIR / "1900sbox_no_team.zip"
TEAMABR_FIXTURE = FIXTURES_DIR / "TEAMABR.TXT"
ROSTERS_FIXTURE = FIXTURES_DIR / "rosters.zip"

pytestmark = pytest.mark.skipif(
    bool(chadwick_tools.missing_tools()),
    reason=f"cwevent/cwgame/cwbox not installed: {chadwick_tools.missing_tools()}",
)


@pytest.fixture(autouse=True)
def _clean_tables(db_conn):
    yield
    with db_conn.cursor() as cur:
        for table in box.ALL_TABLES:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
    db_conn.commit()


@pytest.fixture(autouse=True)
def _isolated_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(box.manifest, "DOWNLOADS_ROOT", tmp_path)


def test_load_archive_self_contained_lands_all_four_tables(db_conn):
    with patch.object(box.manifest, "download", return_value=SELF_CONTAINED_ZIP):
        counts = box._load_archive(db_conn, "1900sbox.zip", "https://example.com/x", "na")
    db_conn.commit()

    assert counts[box.GAME_TABLE] == 2
    assert counts[box.BATTING_TABLE] > 0
    assert counts[box.FIELDING_TABLE] > 0
    assert counts[box.PITCHING_TABLE] > 0
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT game_id, visitor, home FROM {box.GAME_TABLE} ORDER BY game_id")
        rows = cur.fetchall()
    assert rows == [
        ("BRO190004210", "NY1", "BRO"),
        ("BRO190004280", "BSN", "BRO"),
    ]
    entry = box.manifest.load_manifest(box.SOURCE)["1900sbox.zip"]
    assert entry["parser_version"] == box.PARSER_VERSION
    assert entry["schema_fingerprint"]


def test_load_archive_lands_supplementary_event_lists(db_conn):
    # cwbox -X's seven supplementary lists (doubles/triples/homeruns/stolen
    # bases/double plays/triple plays/sac bunts) — previously not parsed at
    # all (see ADR-012). Two real games are enough to expect at least some
    # of these categories to have real rows without hand-picking exact counts
    # (a genuinely 0-row category for 2 games isn't itself a bug).
    with patch.object(box.manifest, "download", return_value=SELF_CONTAINED_ZIP):
        counts = box._load_archive(db_conn, "1900sbox.zip", "https://example.com/x", "na")
    db_conn.commit()

    for raw_table in box.SUPPLEMENTARY_TABLES.values():
        assert raw_table in counts, f"{raw_table} missing from counts"
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (box.SUPPLEMENTARY_TABLES["double"],))
        assert cur.fetchone()[0] is not None
        cur.execute(f"SELECT game_id, batter FROM {box.SUPPLEMENTARY_TABLES['double']} LIMIT 1")
        row = cur.fetchone()
        assert row is not None
        assert row[0] in ("BRO190004210", "BRO190004280")


def test_load_archive_constructs_team_file_when_archive_has_none(db_conn):
    def fake_download(source, filename, url, force=False):
        if filename == "1900sbox_no_team.zip":
            return NO_TEAM_ZIP
        if filename == "TEAMABR.TXT":
            return TEAMABR_FIXTURE
        if filename == "rosters.zip":
            return ROSTERS_FIXTURE
        raise AssertionError(f"unexpected download: {filename}")

    with patch.object(box.manifest, "download", side_effect=fake_download):
        counts = box._load_archive(db_conn, "1900sbox_no_team.zip", "https://example.com/x", "era")
    db_conn.commit()

    assert counts[box.GAME_TABLE] == 2
    with db_conn.cursor() as cur:
        # Confirms team names resolved correctly from the *constructed*
        # TEAM1900 file (built from the TEAMABR.TXT fixture) — this is
        # exactly the field that comes back blank without a real one.
        cur.execute(
            f"SELECT game_id, visitor, visitor_name, home, home_name "
            f"FROM {box.GAME_TABLE} ORDER BY game_id"
        )
        rows = cur.fetchall()
    assert rows == [
        ("BRO190004210", "NY1", "Giants", "BRO", "Dodgers"),
        ("BRO190004280", "BSN", "Braves", "BRO", "Dodgers"),
    ]


def test_reloading_an_archive_replaces_its_own_scope_only(db_conn):
    with patch.object(box.manifest, "download", return_value=SELF_CONTAINED_ZIP):
        box._load_archive(db_conn, "1900sbox.zip", "https://example.com/x", "na")
        db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            f"INSERT INTO {box.GAME_TABLE} (game_id, _season, _group, _scope) "
            "VALUES ('FAKE190112310', '1901', 'na', '1901_na')"
        )
    db_conn.commit()

    with patch.object(box.manifest, "download", return_value=SELF_CONTAINED_ZIP):
        box._load_archive(db_conn, "1900sbox.zip", "https://example.com/x", "na", force=True)
        db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(f"SELECT _season, count(*) FROM {box.GAME_TABLE} GROUP BY _season ORDER BY 1")
        rows = cur.fetchall()
    assert ("1901", 1) in rows
    assert any(season == "1900" for season, _ in rows)


def test_load_archive_skips_already_loaded_archive(db_conn):
    with patch.object(box.manifest, "download", return_value=SELF_CONTAINED_ZIP):
        box._load_archive(db_conn, "1900sbox.zip", "https://example.com/x", "na")
        db_conn.commit()

    with patch.object(box.manifest, "download") as mock_download:
        counts = box._load_archive(db_conn, "1900sbox.zip", "https://example.com/x", "na")

    assert counts == {}
    mock_download.assert_not_called()


def test_missing_archive_returns_empty_without_erroring(db_conn):
    with patch.object(box.manifest, "download", return_value=None):
        counts = box._load_archive(db_conn, "9999box.zip", "https://example.com/x", "na")

    assert counts == {}


def test_load_archive_accepts_an_authoritatively_empty_year(db_conn, tmp_path):
    """Retrosheet's current 1871 archive has TEAM1871 but no .EB* records."""
    empty_archive = tmp_path / "1871box.zip"
    with zipfile.ZipFile(empty_archive, "w") as zf:
        zf.writestr("TEAM1871", "BS1,NA,Boston,Red Stockings\n")

    with patch.object(box.manifest, "download", return_value=empty_archive):
        counts = box._load_archive(db_conn, "1871box.zip", "https://example.com/x", "na")
    db_conn.commit()

    assert counts == dict.fromkeys(box.ALL_TABLES, 0)
    assert box.manifest.load_manifest(box.SOURCE)["1871box.zip"]["status"] == "loaded"


def test_known_unparseable_year_is_explicitly_skipped(monkeypatch, tmp_path, capsys):
    archive_path = tmp_path / "allebr.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("1938.EBR", "id,FAKE193801010\n")
    monkeypatch.setattr(box, "_team_registry", lambda group: box.pd.DataFrame())
    monkeypatch.setattr(box, "_rosters_zip", lambda: tmp_path / "rosters.zip")
    monkeypatch.setattr(box, "_prepare_team_file", lambda *args: None)
    monkeypatch.setattr(
        box.chadwick_tools,
        "run_cwbox",
        lambda *args: (_ for _ in ()).throw(RuntimeError("Invalid integer value 'NA'")),
    )

    assert box._parse_archive(archive_path, "negro_league") == {}
    assert "skipping official 1938 Negro League" in capsys.readouterr().out
