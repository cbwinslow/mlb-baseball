"""Loads a small *real* event fixture through the real connector code path
(``chadwick_tools.run_cwevent``/``run_cwgame``, not a hand-made table) and
checks its plate-appearance, strikeout and home-run counts against known
totals -- closing `raw-source-tieout` audit finding G3 (task 3.2):

    "No test loads a real (small) event fixture and checks known counts
    beyond `larsen`'s one game (plate appearances, strikeouts, home runs
    for a fixture with known totals)."

``tests/fixtures/retrosheet_event/decade.zip`` (already used by
``test_tieout_connector_columns.py``) contains one real Chadwick event file,
``2024ANA.EVA``, with two real 2024 regular-season games: BOS at ANA on
2024-04-05 (``ANA202404050``) and 2024-04-06 (``ANA202404060``). Real, not
synthetic -- the ``info`` records name real 2024 players/umpires (wp
``martc007`` Chris Martin, lp ``sorij002`` Jose Soriano, save ``jansk001``
Kenley Jansen for the first game; wp ``detmr001`` Reid Detmers, lp
``weisg001`` Greg Weissert, save ``estec001`` Carlos Estevez for the second).

The known totals below come from two independent sources, not from this
test's own load:

1. Hand-counting the fixture's own ``play`` records by event code (``K`` =
   strikeout, ``HR`` = home run, anything else that isn't a no-play (``NP``)
   or a baserunner-only code (``SB``/``CS``/``POCS``) = a plate appearance).
2. Production ``mlb``'s already-loaded ``raw.retrosheet_event`` for these
   same two real game ids (loaded independently, from the full 2024 season
   archive, months before this test was written), queried read-only via the
   ``bat_event_fl``/``event_cd`` columns this project's own tie-out design
   already treats as the plate-appearance/strikeout/home-run definition (see
   ``docs/archive`` session notes: event codes 3 = strikeout, 23 = home run,
   `bat_event_fl='T'` = plate appearance).

Both agree exactly, which is why they're pinned here as known facts rather
than merely "whatever this test's own parse produces".

The fixture-loaded ``decade.zip`` also contains a second, synthetic
"2025" copy of the same file (game ids relabeled ``ANA202504050`` /
``ANA202504060`` to give the column-contract tests two seasons to diff) --
that copy is not a real game and is deliberately not asserted on here.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from mlb_baseball import chadwick_tools
from mlb_baseball.connectors import retrosheet_event as event

EVENT_FIXTURE_ZIP = (
    Path(__file__).resolve().parent.parent / "fixtures" / "retrosheet_event" / "decade.zip"
)

pytestmark = pytest.mark.skipif(
    bool(chadwick_tools.missing_tools()),
    reason=f"cwevent/cwgame not installed: {chadwick_tools.missing_tools()}",
)

# Known totals for the two real 2024 games in the fixture, cross-checked
# against production's independently-loaded raw.retrosheet_event (see
# module docstring). event_cd '3' = strikeout, '23' = home run,
# bat_event_fl = 'T' = plate appearance.
KNOWN_COUNTS = {
    "ANA202404050": {"total_rows": 85, "pa": 84, "k": 16, "hr": 6},  # BOS 2024-04-05 @ ANA
    "ANA202404060": {"total_rows": 71, "pa": 67, "k": 24, "hr": 0},  # BOS 2024-04-06 @ ANA
}


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
    monkeypatch.setattr(event.manifest, "DOWNLOADS_ROOT", tmp_path)


@pytest.fixture
def _loaded(db_conn):
    with patch.object(event.manifest, "download", return_value=EVENT_FIXTURE_ZIP):
        event._load_archive(db_conn, "decade.zip", "https://example.com/decade.zip", "pbp")
    db_conn.commit()
    return db_conn


@pytest.mark.parametrize("game_id", sorted(KNOWN_COUNTS))
def test_real_event_fixture_matches_known_pa_k_hr_counts(_loaded, game_id):
    expected = KNOWN_COUNTS[game_id]
    with _loaded.cursor() as cur:
        cur.execute(
            f"SELECT count(*), "
            "count(*) FILTER (WHERE bat_event_fl = 'T'), "
            "count(*) FILTER (WHERE event_cd = '3'), "
            "count(*) FILTER (WHERE event_cd = '23') "
            f"FROM {event.EVENT_TABLE} WHERE game_id = %s",
            (game_id,),
        )
        total_rows, pa, k, hr = cur.fetchone()
    assert (total_rows, pa, k, hr) == (
        expected["total_rows"],
        expected["pa"],
        expected["k"],
        expected["hr"],
    )


def test_real_event_fixture_matches_known_totals_across_both_games(_loaded):
    """Same known facts, summed -- the shape a season-level tie-out
    comparison actually runs (a single aggregate across many games), not
    just a per-game lookup."""
    with _loaded.cursor() as cur:
        cur.execute(
            "SELECT count(*), "
            "count(*) FILTER (WHERE bat_event_fl = 'T'), "
            "count(*) FILTER (WHERE event_cd = '3'), "
            "count(*) FILTER (WHERE event_cd = '23') "
            f"FROM {event.EVENT_TABLE} WHERE game_id = ANY(%s)",
            (list(KNOWN_COUNTS),),
        )
        total_rows, pa, k, hr = cur.fetchone()
    assert (total_rows, pa, k, hr) == (
        sum(v["total_rows"] for v in KNOWN_COUNTS.values()),
        sum(v["pa"] for v in KNOWN_COUNTS.values()),
        sum(v["k"] for v in KNOWN_COUNTS.values()),
        sum(v["hr"] for v in KNOWN_COUNTS.values()),
    )
