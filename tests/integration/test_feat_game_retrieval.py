"""feat.game's starter columns must equal what mlb_research.get_historical_features
returns from feat.pitcher_form at that game's first pitch (feature-store-v1, task
4.1). This is the contract that keeps the curated wide assembly and the retrieval
path from drifting.

Convergence holds because a form row's available_ts == visible_ts == its own
event_ts (its value is entering form), so an ASOF join at a game's event_ts
lands on exactly the feat.pitcher_form row feat_game.sql joins by
(player_id, retro_game_id).

Standalone minimal fixture (own pitchers/games); does not share with
test_feat_form.py.
"""

import os

import duckdb
import mlb_research
import pandas as pd
import pytest

from mlb_baseball import feat

SEASON = 2024
_TEAMS = [(7201, "GRA"), (7202, "GRB")]
_PLAYERS = [(72001, "gpa001"), (72002, "gpb001")]  # home starter, away starter
# id, retro, date, game_number, home, away, hs, as, type
_GAMES = [
    (7920001, "GRT202405010", "2024-05-01", 0, 7201, 7202, 3, 2, "regular"),
    (7920002, "GRT202405100", "2024-05-10", 0, 7202, 7201, 1, 4, "regular"),
    (7920003, "GRT202405200", "2024-05-20", 0, 7201, 7202, 5, 5, "regular"),
    (7920004, "GRT202405280", "2024-05-28", 0, 7202, 7201, 2, 6, "regular"),
]
# per game per pitcher: bf, outs, so, bb
_LINES = {
    (7920001, 72001): (24, 18, 7, 2),
    (7920001, 72002): (23, 15, 5, 3),
    (7920002, 72001): (26, 21, 9, 1),
    (7920002, 72002): (22, 18, 6, 2),
    (7920003, 72001): (20, 12, 4, 4),
    (7920003, 72002): (25, 20, 8, 1),
    (7920004, 72001): (27, 24, 10, 0),
    (7920004, 72002): (21, 15, 6, 3),
}
_PIT_COLS = (
    "gs",
    "bf",
    "outs",
    "h",
    "r",
    "bb",
    "ibb",
    "so",
    "hr",
    "hbp",
    "wp",
    "bk",
    "w",
    "l",
    "sv",
)
_GID = {g[0] for g in _GAMES}


def _cleanup(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.pitching_game WHERE game_id = ANY(%s)", (list(_GID),))
        cur.execute("DELETE FROM core.game WHERE id = ANY(%s)", (list(_GID),))
        cur.execute("DELETE FROM core.player WHERE id = ANY(%s)", ([p[0] for p in _PLAYERS],))
        cur.execute("DELETE FROM core.team WHERE id = ANY(%s)", ([t[0] for t in _TEAMS],))
    db_conn.commit()


@pytest.fixture
def built(db_conn, tmp_path):
    _cleanup(db_conn)
    with db_conn.cursor() as cur:
        for tid, retro in _TEAMS:
            cur.execute(
                "INSERT INTO core.team (id, retro_team_id, league, city, nickname, "
                "first_year, last_year) VALUES (%s, %s, 'AL', 'X', 'Y', 1901, 2026)",
                (tid, retro),
            )
        for pid, retro in _PLAYERS:
            cur.execute(
                "INSERT INTO core.player (id, retro_id, last_name, first_name) "
                "VALUES (%s, %s, 'P', 'X')",
                (pid, retro),
            )
        for gid, retro, date, gn, home, away, hs, as_, gtype in _GAMES:
            cur.execute(
                "INSERT INTO core.game (id, retro_game_id, season, game_date, game_number, "
                "home_team_id, away_team_id, home_score, away_score, game_type) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (gid, retro, SEASON, date, gn, home, away, hs, as_, gtype),
            )
        by_id = {g[0]: g for g in _GAMES}
        for (gid, pid), (bf, outs, so, bb) in _LINES.items():
            # 72001 always starts for team 7201, 72002 for 7202.
            team_id = 7201 if pid == 72001 else 7202
            vals = {c: 0 for c in _PIT_COLS}
            vals.update(gs=1, bf=bf, outs=outs, so=so, bb=bb)
            names = ["game_id", "player_id", "team_id", "season", "game_date", *_PIT_COLS]
            cur.execute(
                f"INSERT INTO gold.pitching_game ({', '.join(names)}) "
                f"VALUES ({', '.join(['%s'] * len(names))})",
                (gid, pid, team_id, SEASON, by_id[gid][2], *(vals[c] for c in _PIT_COLS)),
            )
    db_conn.commit()
    dbfile = tmp_path / "mlb.duckdb"
    try:
        feat.build(duckdb_path=dbfile, pg_url=os.environ["DATABASE_URL"], feature_version="v1")
        yield dbfile
    finally:
        _cleanup(db_conn)


def _attach(dbfile):
    con = duckdb.connect()
    con.execute(f"ATTACH '{dbfile}' AS mlbfeat (READ_ONLY)")
    con.execute("USE mlbfeat")
    return con


def test_feat_game_starter_columns_equal_get_historical_features(built):
    con = _attach(built)
    games = con.execute(
        "SELECT game_pk, event_ts, home_team_id, away_team_id, "
        "home_starter_k_minus_bb_pct_30d, home_starter_fip_like_30d, home_starter_bf_30d, "
        "away_starter_k_minus_bb_pct_30d, away_starter_fip_like_30d, away_starter_bf_30d "
        "FROM feat.game ORDER BY event_ts"
    ).df()
    con.close()
    assert len(games) == 4

    checked = 0
    for _, g in games.iterrows():
        for side, starter in (
            ("home", 72001 if g["home_team_id"] == 7201 else 72002),
            ("away", 72001 if g["away_team_id"] == 7201 else 72002),
        ):
            entity = pd.DataFrame({"player_id": [starter], "event_timestamp": [g["event_ts"]]})
            got = mlb_research.get_historical_features(
                entity,
                [
                    "pitcher_form:k_minus_bb_pct_30d",
                    "pitcher_form:fip_like_30d",
                    "pitcher_form:bf_30d",
                ],
                db=built,
            ).iloc[0]
            for rcol, fcol in (
                ("k_minus_bb_pct_30d", f"{side}_starter_k_minus_bb_pct_30d"),
                ("fip_like_30d", f"{side}_starter_fip_like_30d"),
                ("bf_30d", f"{side}_starter_bf_30d"),
            ):
                a, b = got[rcol], g[fcol]
                if pd.isna(a) and pd.isna(b):
                    continue
                assert a == pytest.approx(b), (g["game_pk"], side, fcol, a, b)
                checked += 1
    assert checked > 0


def test_first_game_has_no_prior_form(built):
    con = _attach(built)
    bf, kbb = con.execute(
        "SELECT home_starter_bf_30d, home_starter_k_minus_bb_pct_30d "
        "FROM feat.game WHERE game_pk = 'GRT202405010'"
    ).fetchone()
    con.close()
    assert bf == 0  # no prior appearances -> 0 exposure
    assert kbb is None  # ...and the rate is NULL, not 0
