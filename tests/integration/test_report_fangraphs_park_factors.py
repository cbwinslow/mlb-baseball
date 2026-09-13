"""gold.fangraphs_park_factors -- fangraphs-conform Beat 1 (ADR-290).

Conforms raw.fangraphs_park_factors to core.team via the 'fangraphs'
core.team_alias block, scoped season >= 2003. Verifies: a resolvable nickname
-> one row per (season, team_id); a pre-2003 row -> no row; an unresolvable
nickname -> no row AND the coverage health check goes red; idempotency.
"""

from decimal import Decimal

from mlb_baseball import conform, report

# raw.fangraphs_park_factors text columns, verified against production (task).
_PF_COLS = (
    "season",
    "team",
    "basic__5yr_",
    "n3yr",
    "n1yr",
    "n1b",
    "n2b",
    "n3b",
    "hr",
    "so",
    "bb",
    "gb",
    "fb",
    "ld",
    "iffb",
    "fip",
)

_FANGRAPHS_ALIASES = [
    (retro, alias) for retro, alias, src in conform._TEAM_ALIAS_SEED if src == "fangraphs"
]


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.fangraphs_park_factors")
        cur.execute("TRUNCATE gold.fangraphs_park_factors")
        cur.execute("DELETE FROM core.team_alias WHERE source = 'fangraphs'")
        cur.execute("DELETE FROM core.team WHERE id IN (930001, 930002)")
    db_conn.commit()


def _seed_core(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team (id, retro_team_id, league, city, nickname, "
            "first_year, last_year) VALUES "
            "(930001, 'NYA', 'AL', 'New York', 'Yankees', 1903, 9999), "
            "(930002, 'TBA', 'AL', 'Tampa Bay', 'Rays', 1998, 9999)"
        )
        # Only the FanGraphs aliases for the two seeded franchises.
        for retro, alias in _FANGRAPHS_ALIASES:
            if retro in ("NYA", "TBA"):
                cur.execute(
                    "INSERT INTO core.team_alias (team_id, alias, source) "
                    "SELECT id, %s, 'fangraphs' FROM core.team "
                    "WHERE retro_team_id = %s AND last_year = 9999",
                    (alias, retro),
                )
    db_conn.commit()


def _create_raw(db_conn, rows):
    with db_conn.cursor() as cur:
        cols_ddl = ", ".join(f"{c} text" for c in _PF_COLS)
        cur.execute(
            f"CREATE TABLE raw.fangraphs_park_factors ({cols_ddl}, "
            "_season text, _loaded_at timestamptz DEFAULT now())"
        )
        placeholders = ", ".join(["%s"] * len(_PF_COLS))
        for row in rows:
            cur.execute(
                f"INSERT INTO raw.fangraphs_park_factors ({', '.join(_PF_COLS)}) "
                f"VALUES ({placeholders})",
                tuple(row.get(c, "") for c in _PF_COLS),
            )
    db_conn.commit()


def _build(db_conn):
    count = report._build_backbone_relation(
        db_conn,
        "gold.fangraphs_park_factors",
        report._GOLD_FANGRAPHS_PARK_FACTORS_SQL,
        source="raw.fangraphs_park_factors",
    )
    db_conn.commit()
    return count


def _pf_row(season="2015", team="Yankees", **overrides):
    row = {c: "" for c in _PF_COLS}
    row.update(
        season=season,
        team=team,
        basic__5yr_="101",
        n3yr="102",
        n1yr="103",
        n1b="100",
        n2b="104",
        n3b="98",
        hr="110",
        so="99",
        bb="101",
        gb="100",
        fb="103",
        ld="100",
        iffb="97",
        fip="105",
    )
    row.update(overrides)
    return row


def _coverage_check(db_conn):
    _ = db_conn  # health checks open their own connection (DATABASE_URL == test DB)
    for check in report._fangraphs_health_checks():
        if "resolves every raw.fangraphs_park_factors team" in check.name:
            return check
    raise AssertionError("park-factor coverage check not present")


def test_resolvable_team_yields_one_row_per_season_team(db_conn):
    _reset(db_conn)
    _seed_core(db_conn)
    _create_raw(
        db_conn,
        [
            _pf_row(season="2015", team="Yankees"),
            _pf_row(season="2016", team="Yankees", hr="112"),
            _pf_row(season="2009", team="Rays"),
            _pf_row(season="2005", team="Devil Rays"),  # TBA's 2003-07 nickname
        ],
    )

    assert _build(db_conn) == 4

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT season, team_id, basic_5yr, pf_3yr, pf_hr, pf_fip "
            "FROM gold.fangraphs_park_factors ORDER BY season, team_id"
        )
        rows = cur.fetchall()

    assert rows == [
        (2005, 930002, Decimal("101"), Decimal("102"), Decimal("110"), Decimal("105")),
        (2009, 930002, Decimal("101"), Decimal("102"), Decimal("110"), Decimal("105")),
        (2015, 930001, Decimal("101"), Decimal("102"), Decimal("110"), Decimal("105")),
        (2016, 930001, Decimal("101"), Decimal("102"), Decimal("112"), Decimal("105")),
    ]
    assert _coverage_check(db_conn).ok is True

    _reset(db_conn)


def test_pre_2003_rows_are_not_conformed(db_conn):
    _reset(db_conn)
    _seed_core(db_conn)
    _create_raw(
        db_conn,
        [
            _pf_row(season="2002", team="Yankees"),
            _pf_row(season="1998", team="Devil Rays"),
            _pf_row(season="2003", team="Yankees"),
        ],
    )

    assert _build(db_conn) == 1

    with db_conn.cursor() as cur:
        cur.execute("SELECT season FROM gold.fangraphs_park_factors")
        assert cur.fetchall() == [(2003,)]
    # pre-2003 rows are out of scope, so the coverage check ignores them too.
    assert _coverage_check(db_conn).ok is True

    _reset(db_conn)


def test_unresolvable_team_is_dropped_and_turns_the_coverage_check_red(db_conn):
    _reset(db_conn)
    _seed_core(db_conn)
    _create_raw(
        db_conn,
        [
            _pf_row(season="2015", team="Yankees"),
            _pf_row(season="2015", team="Athletics"),  # no 'fangraphs' alias seeded here
        ],
    )

    assert _build(db_conn) == 1

    with db_conn.cursor() as cur:
        cur.execute("SELECT DISTINCT team_id FROM gold.fangraphs_park_factors")
        assert cur.fetchall() == [(930001,)]

    check = _coverage_check(db_conn)
    assert check.ok is False
    assert "1 < expected 2" in check.detail

    _reset(db_conn)


def test_park_factors_build_is_idempotent(db_conn):
    _reset(db_conn)
    _seed_core(db_conn)
    _create_raw(db_conn, [_pf_row(season="2015", team="Yankees")])

    assert _build(db_conn) == 1
    assert _build(db_conn) == 1

    with db_conn.cursor() as cur:
        cur.execute("SELECT season, team_id FROM gold.fangraphs_park_factors")
        assert cur.fetchall() == [(2015, 930001)]

    _reset(db_conn)
