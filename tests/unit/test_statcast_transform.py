"""Pure transform/logic — pybaseball itself is mocked, no DB, no real HTTP."""

from datetime import date

from mlb_baseball.connectors import statcast


def test_season_date_ranges_covers_feb_through_dec_in_weekly_chunks():
    ranges = statcast._season_date_ranges(2015)

    assert ranges[0][0] == date(2015, 2, 1)
    assert ranges[-1][1] == date(2015, 12, 1)
    # each chunk is at most 7 days (start through start+6), and chunks tile
    # the range exactly — the next one starts the day after the last ends.
    for start, end in ranges:
        assert (end - start).days <= 6
    for i in range(len(ranges) - 1):
        assert (ranges[i + 1][0] - ranges[i][1]).days == 1


def test_season_date_ranges_caps_at_today_for_the_current_season(monkeypatch):
    class _FixedDate(date):
        @classmethod
        def today(cls):
            return date(2026, 6, 15)

    monkeypatch.setattr(statcast, "date", _FixedDate)

    ranges = statcast._season_date_ranges(2026)

    assert ranges[-1][1] == date(2026, 6, 15)


def test_season_date_ranges_empty_for_a_season_that_hasnt_started_yet(monkeypatch):
    class _FixedDate(date):
        @classmethod
        def today(cls):
            return date(2025, 1, 1)

    monkeypatch.setattr(statcast, "date", _FixedDate)

    assert statcast._season_date_ranges(2026) == []


def test_first_statcast_year_matches_real_confirmed_coverage():
    # Confirmed via direct testing against the real API before writing this:
    # pybaseball.statcast() returns real rows (with pitch trajectory data)
    # starting 2008 — the PITCHf/x era, predating true Statcast (2015+).
    # Statcast-exclusive columns (launch_speed, release_spin_rate) are null
    # for 2008-2014 but the rows themselves are real, not empty.
    assert statcast.FIRST_STATCAST_YEAR == 2008
