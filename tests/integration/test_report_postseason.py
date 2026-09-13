"""gold.batting_postseason / gold.pitching_postseason -- separate-postseason-stats
(ADR-282). Built from Lahman BattingPost / PitchingPost: per-round rows, an
is_combined all-rounds row per player-season, an is_career row per player.
Never contains a regular-season game (the whole source table is postseason).
"""

import pytest

from mlb_baseball import report

_RAW = (
    "raw.lahman_batting_post",
    "raw.lahman_pitching_post",
    "raw.lahman_teams",
    "raw.lahman_people",
)


@pytest.fixture(autouse=True)
def _raw_tables(db_conn):
    def _reset():
        db_conn.rollback()
        with db_conn.cursor() as cur:
            for t in _RAW:
                cur.execute(f"DROP TABLE IF EXISTS {t}")
            cur.execute("DELETE FROM gold.batting_postseason WHERE player_id IN (81001, 81002)")
            cur.execute("DELETE FROM gold.pitching_postseason WHERE player_id IN (81001, 81002)")
            cur.execute("DELETE FROM core.player WHERE id IN (81001, 81002)")
            cur.execute("DELETE FROM core.team WHERE id IN (8101, 8102)")
        db_conn.commit()

    _reset()
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.lahman_batting_post (yearid text, round text, playerid text, "
            "teamid text, lgid text, g text, ab text, r text, h text, n2b text, n3b text, "
            "hr text, rbi text, sb text, cs text, bb text, so text, ibb text, hbp text, "
            "sh text, sf text, gidp text)"
        )
        cur.execute(
            "CREATE TABLE raw.lahman_pitching_post (playerid text, yearid text, round text, "
            "teamid text, lgid text, w text, l text, g text, gs text, cg text, sho text, "
            "sv text, ipouts text, h text, er text, hr text, bb text, so text, baopp text, "
            "era text, ibb text, wp text, hbp text, bk text, bfp text, gf text, r text, "
            "sh text, sf text, gidp text)"
        )
        cur.execute("CREATE TABLE raw.lahman_teams (teamid text, yearid text, teamidretro text)")
        cur.execute("CREATE TABLE raw.lahman_people (playerid text, retroid text, bbrefid text)")
        cur.execute(
            "INSERT INTO core.team (id, retro_team_id, league, city, nickname, "
            "first_year, last_year) VALUES "
            "(8101, 'HOU', 'AL', 'Houston', 'Astros', 1962, 2030), "
            "(8102, 'LAN', 'NL', 'Los Angeles', 'Dodgers', 1958, 2030) "
            "ON CONFLICT (id) DO NOTHING"
        )
        # Player 81001 resolves directly via bbref_id; 81002 only via the
        # raw.lahman_people retro-id fallback (its bbref_id is NULL).
        cur.execute(
            "INSERT INTO core.player (id, retro_id, bbref_id, last_name, first_name) VALUES "
            "(81001, 'bregr001', 'bregman01', 'Bregman', 'Alex'), "
            "(81002, 'freed001', NULL, 'Freeman', 'Freddie') ON CONFLICT (id) DO NOTHING"
        )
        cur.execute(
            "INSERT INTO raw.lahman_teams (teamid, yearid, teamidretro) VALUES "
            "('HOU', '2019', 'HOU'), ('LAN', '2020', 'LAN')"
        )
        cur.execute(
            "INSERT INTO raw.lahman_people (playerid, retroid, bbrefid) VALUES "
            "('bregman01', 'bregr001', 'bregman01'), "
            "('freemfr01', 'freed001', 'freemfr01')"
        )
        db_conn.commit()
    yield
    _reset()


def _bat_row(**kw):
    cols = "g ab r h n2b n3b hr rbi sb cs bb so ibb hbp sh sf gidp".split()
    row = {c: "0" for c in cols}
    row.update({k: str(v) for k, v in kw.items()})
    return row


def _seed_batting(db_conn, rows):
    cols = (
        "yearid round playerid teamid lgid g ab r h n2b n3b hr rbi sb cs bb so ibb hbp sh sf gidp"
    ).split()
    with db_conn.cursor() as cur:
        for r in rows:
            cur.execute(
                "INSERT INTO raw.lahman_batting_post ("
                + ",".join(cols)
                + ") VALUES ("
                + ",".join(["%s"] * len(cols))
                + ")",
                tuple(r.get(c, "0") for c in cols),
            )
    db_conn.commit()


def _build(db_conn):
    report._build_backbone_relation(
        db_conn,
        "gold.batting_postseason",
        report._BATTING_POSTSEASON_SQL,
        source="raw.lahman_batting_post",
    )
    report._build_backbone_relation(
        db_conn,
        "gold.pitching_postseason",
        report._PITCHING_POSTSEASON_SQL,
        source="raw.lahman_pitching_post",
    )
    db_conn.commit()


def _rows(db_conn, player_id):
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT round, is_combined, is_career, season, g, pa, ab, h, hr, tb, bb, so, avg "
            "FROM gold.batting_postseason WHERE player_id = %s "
            "ORDER BY is_career, is_combined, round",
            (player_id,),
        )
        keys = "round is_combined is_career season g pa ab h hr tb bb so avg".split()
        return [dict(zip(keys, r, strict=True)) for r in cur.fetchall()]


def test_per_round_combined_and_career_rows(db_conn):
    # Bregman 2019: ALDS 5 G, ALCS 6 G, WS 7 G. HOU.
    _seed_batting(
        db_conn,
        [
            {
                **_bat_row(g=5, ab=18, r=2, h=5, n2b=1, hr=1, bb=3, so=4),
                "yearid": "2019",
                "round": "ALDS1",
                "playerid": "bregman01",
                "teamid": "HOU",
            },
            {
                **_bat_row(g=6, ab=21, r=4, h=6, n2b=2, hr=2, bb=5, so=3),
                "yearid": "2019",
                "round": "ALCS",
                "playerid": "bregman01",
                "teamid": "HOU",
            },
            {
                **_bat_row(g=7, ab=26, r=3, h=6, hr=2, bb=4, so=6),
                "yearid": "2019",
                "round": "WS",
                "playerid": "bregman01",
                "teamid": "HOU",
            },
        ],
    )
    _build(db_conn)
    rows = _rows(db_conn, 81001)

    per_round = [r for r in rows if not r["is_combined"] and not r["is_career"]]
    combined = next(r for r in rows if r["is_combined"])
    career = next(r for r in rows if r["is_career"])

    assert {r["round"] for r in per_round} == {"ALDS1", "ALCS", "WS"}
    assert all(r["season"] == 2019 for r in per_round)

    # combined = sum of the three rounds
    assert combined["round"] is None and combined["season"] == 2019
    assert combined["g"] == 18  # 5 + 6 + 7
    assert combined["ab"] == 65  # 18 + 21 + 26
    assert combined["h"] == 17  # 5 + 6 + 6
    assert combined["hr"] == 5
    assert combined["bb"] == 12
    # PA = AB + BB + HBP + SF + SH = 65 + 12 = 77
    assert combined["pa"] == 77
    # TB: h=17, 2b=3, 3b=0, hr=5 -> 17 + 3 + 0 + 15 = 35
    assert combined["tb"] == 35
    assert float(combined["avg"]) == pytest.approx(17 / 65, abs=1e-6)

    # career == combined here (only one postseason season), season NULL
    assert career["season"] is None and career["round"] is None
    assert (career["g"], career["ab"], career["h"], career["hr"]) == (18, 65, 17, 5)


def test_float_formatted_source_counts_are_parsed(db_conn):
    # raw.lahman_*_post columns are text and pandas float-formats any nullable
    # integer column ("4.0", not "4") when the source left blanks in it -- true
    # for so / ibb / hbp / sf / sh / cs / gidp across ~18k real BattingPost rows.
    # The build must cast via ::numeric::integer or it raises
    # InvalidTextRepresentation and no postseason relation is built at all.
    _seed_batting(
        db_conn,
        [
            {
                **_bat_row(g=7, ab=26, h=6, hr=2, bb=4),
                "so": "6.0",
                "ibb": "0.0",
                "hbp": "1.0",
                "sf": "0.0",
                "sh": "0.0",
                "gidp": "2.0",
                "yearid": "2019",
                "round": "WS",
                "playerid": "bregman01",
                "teamid": "HOU",
            },
        ],
    )
    _build(db_conn)
    combined = next(r for r in _rows(db_conn, 81001) if r["is_combined"])
    assert combined["so"] == 6
    # PA = AB + BB + HBP + SF + SH = 26 + 4 + 1 = 31
    assert combined["pa"] == 31


def test_player_resolved_only_via_retro_id_fallback_is_not_dropped(db_conn):
    # Freeman: core.player.bbref_id is NULL; resolves via lahman_people retroid.
    _seed_batting(
        db_conn,
        [
            {
                **_bat_row(g=7, ab=28, h=10, n2b=2, hr=1, bb=3, so=5),
                "yearid": "2020",
                "round": "WS",
                "playerid": "freemfr01",
                "teamid": "LAN",
            },
        ],
    )
    _build(db_conn)
    rows = _rows(db_conn, 81002)
    assert {r["round"] for r in rows if not r["is_combined"] and not r["is_career"]} == {"WS"}
    assert any(r["is_career"] for r in rows)


def test_rebuild_is_idempotent(db_conn):
    _seed_batting(
        db_conn,
        [
            {
                **_bat_row(g=7, ab=26, h=6, hr=2),
                "yearid": "2019",
                "round": "WS",
                "playerid": "bregman01",
                "teamid": "HOU",
            },
        ],
    )
    _build(db_conn)
    _build(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM gold.batting_postseason WHERE player_id = 81001")
        # 1 per-round + 1 combined + 1 career
        assert cur.fetchone() == (3,)
