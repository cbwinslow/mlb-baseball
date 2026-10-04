"""Comparison logic and register of the Retrosheet tie-out gate (``mlb_baseball.tieout``).

Pure counts in, verdicts out, no database. These tests are the evidence that a
planted mismatch fails, a matching pair passes, and that the register cannot
quietly excuse or hide a difference (openspec change ``raw-source-tieout``,
``passmarks.md``).
"""

import pytest

from mlb_baseball import tieout
from mlb_baseball.tieout import (
    INITIAL_REGISTER,
    Register,
    Report,
    Series,
    TieOutError,
    assess,
    check_columns,
    compare,
    coverage,
    rollup_games,
    series_from_rows,
)


def _season(source, rows, facts=("hr", "k", "bb", "r", "g")):
    return Series(
        source=source,
        level="season",
        facts=frozenset(facts),
        counts={(season,): dict(values) for season, values in rows.items()},
    )


def _game(source, rows, facts=("hr", "k", "bb", "r", "g")):
    return Series(
        source=source,
        level="game",
        facts=frozenset(facts),
        counts={(s, g): dict(values) for (s, g), values in rows.items()},
    )


NO_ENTRIES = Register(entries=())


def _run(a, b, *, register=NO_ENTRIES, ctx=None):
    cov = coverage(a, b)
    comparison = compare(a, b, seasons=cov.comparable)
    return assess(comparison, register, ctx or {}, only_a=cov.only_a, only_b=cov.only_b)


# --- match ------------------------------------------------------------------


def test_matching_sources_pass_and_are_recorded():
    a = _season("event", {"2019": {"hr": 6873, "k": 43576}})
    b = _season("batting", {"2019": {"hr": 6873, "k": 43576}})

    result = _run(a, b)

    assert result.passed
    assert result.comparison.keys_compared == 1
    assert [(r.season, r.status) for r in result.seasons] == [("2019", "match")]


# --- unexplained mismatch ---------------------------------------------------


def test_a_single_strikeout_difference_fails_and_names_both_values():
    a = _season("event", {"2019": {"k": 43576}})
    b = _season("batting", {"2019": {"k": 43575}})

    result = _run(a, b)

    assert not result.passed
    (diff,) = result.unexplained
    assert (diff.fact, diff.a_value, diff.b_value) == ("k", 43576, 43575)
    assert diff.key == ("2019",)
    assert "event 43576 vs batting 43575" in diff.describe()
    assert [(r.season, r.status) for r in result.seasons] == [("2019", "unexplained")]


def test_tolerance_is_zero_even_for_a_difference_of_one_in_a_million():
    a = _season("event", {"2019": {"hr": 1_000_000}})
    b = _season("batting", {"2019": {"hr": 1_000_001}})

    assert not _run(a, b).passed


# --- explained mismatch (E1) -----------------------------------------------


def _e1_context(post_rows):
    return {("gamelog_post", "season"): _season("gamelog_post", post_rows)}


def test_regular_season_game_log_shortfall_is_explained_by_the_postseason_total():
    events = _season("event", {"2019": {"hr": 6873}})
    regular = _season("gamelog", {"2019": {"hr": 6767}})
    ctx = _e1_context({"2019": {"hr": 106}})

    result = _run(events, regular, register=INITIAL_REGISTER, ctx=ctx)

    assert result.passed
    ((diff, entry_id),) = result.explained
    assert entry_id == "E1"
    assert (diff.a_value, diff.b_value) == (6873, 6767)
    assert [(r.season, r.status) for r in result.seasons] == [("2019", "explained")]


def test_the_rule_has_a_direction_a_game_log_that_is_larger_is_not_explained():
    events = _season("event", {"2019": {"hr": 6767}})
    regular = _season("gamelog", {"2019": {"hr": 6873}})
    ctx = _e1_context({"2019": {"hr": 106}})

    result = _run(events, regular, register=INITIAL_REGISTER, ctx=ctx)

    assert not result.passed
    assert len(result.unexplained) == 1


def test_a_difference_of_the_wrong_size_is_not_explained_and_the_entry_is_stale():
    events = _season("event", {"2019": {"hr": 6872}})
    regular = _season("gamelog", {"2019": {"hr": 6767}})
    ctx = _e1_context({"2019": {"hr": 106}})  # rule predicts 106, real gap is 105

    result = _run(events, regular, register=INITIAL_REGISTER, ctx=ctx)

    assert not result.passed
    assert len(result.unexplained) == 1
    (stale,) = result.stale
    assert stale.entry_id == "E1"
    assert stale.found is not None and stale.found.a_number - stale.found.b_number == 105


def test_e1_does_not_excuse_a_comparison_with_some_other_source():
    events = _season("event", {"2019": {"hr": 6873}})
    batting = _season("batting", {"2019": {"hr": 6767}})
    ctx = _e1_context({"2019": {"hr": 106}})

    result = _run(events, batting, register=INITIAL_REGISTER, ctx=ctx)

    assert not result.passed
    assert not result.explained


def test_e1_explains_a_postseason_game_present_only_in_the_event_source():
    events = _game("event", {("1956", "NYA195610080"): {"hr": 0, "k": 7, "g": 1}})
    regular = _game("gamelog", {("1956", "NYA195505010"): {"hr": 1, "k": 5, "g": 1}})
    events_more = Series(
        "event",
        "game",
        events.facts,
        {**events.counts, ("1956", "NYA195505010"): {"hr": 1, "k": 5, "g": 1}},
    )
    post = _game("gamelog_post", {("1956", "NYA195610080"): {"hr": 0, "k": 7, "g": 1}})
    ctx = {("gamelog_post", "game"): post}

    result = _run(events_more, regular, register=INITIAL_REGISTER, ctx=ctx)

    assert result.passed, result.unexplained
    assert {d.fact for d, _ in result.explained} == {"k", "g"}


# --- E4: a game with a scorecard but no play-by-play ------------------------

_BAT = ("pa", "k", "bb", "hr", "r", "g")
_SCORED = {"pa": 70, "k": 5, "bb": 3, "hr": 1, "r": 6, "g": 1}
_PLAYED = {"pa": 75, "k": 8, "bb": 4, "hr": 2, "r": 7, "g": 1}


def _e4_context(*, plays_games, batting_games, event_games=None):
    """Every series the register may consult; the event files default to the games
    the CSV plays hold (they agree except where a test says otherwise)."""
    return {
        ("event", "game"): _game(
            "event", plays_games if event_games is None else event_games, _BAT
        ),
        ("csv_plays", "game"): _game("csv_plays", plays_games, _BAT),
        ("csv_batting", "game"): _game("csv_batting", batting_games, _BAT),
    }


def _e4_pair(extra_in_batting=True):
    played = {("1921", "NYA192105010"): _PLAYED}
    scored = dict(played)
    if extra_in_batting:
        scored[("1921", "PH5192105020")] = _SCORED
    return _game("event", played, _BAT), _game("csv_batting", scored, _BAT), played, scored


def test_e4_explains_a_game_missing_from_both_play_by_play_products():
    event, batting, played, scored = _e4_pair()
    ctx = _e4_context(plays_games=played, batting_games=scored)

    result = _run(event, batting, register=INITIAL_REGISTER, ctx=ctx)

    assert result.passed, (result.unexplained, result.stale)
    assert {entry for _, entry in result.explained} == {"E4"}
    assert {d.fact for d, _ in result.explained} == set(_BAT)


def test_e4_does_not_excuse_a_game_the_csv_plays_do_have():
    event, batting, played, scored = _e4_pair()
    ctx = _e4_context(
        plays_games={**played, ("1921", "PH5192105020"): _SCORED}, batting_games=scored
    )

    result = _run(event, batting, register=INITIAL_REGISTER, ctx=ctx)

    assert not result.passed
    assert not result.explained


def test_e4_needs_the_csv_plays_loaded_for_that_season():
    event, batting, played, scored = _e4_pair()
    ctx = _e4_context(plays_games=played, batting_games=scored)
    ctx[("csv_plays", "game")] = _game("csv_plays", {("1922", "OTHER"): _PLAYED}, _BAT)

    result = _run(event, batting, register=INITIAL_REGISTER, ctx=ctx)

    assert not result.passed


def test_e4_does_not_excuse_a_game_that_differs_in_value_rather_than_in_presence():
    event = _game("event", {("1921", "NYA192105010"): _PLAYED}, _BAT)
    batting = _game("csv_batting", {("1921", "NYA192105010"): {**_PLAYED, "k": 9}}, _BAT)
    ctx = _e4_context(
        plays_games={("1921", "NYA192105010"): _PLAYED},
        batting_games={("1921", "NYA192105010"): {**_PLAYED, "k": 9}},
    )

    result = _run(event, batting, register=INITIAL_REGISTER, ctx=ctx)

    assert not result.passed
    assert [d.fact for d in result.unexplained] == ["k"]


def test_e4_also_explains_that_games_player_lines():
    event = Series("event", "player_game", frozenset({"pa"}), {})
    batting = Series(
        "csv_batting",
        "player_game",
        frozenset({"pa"}),
        {("1921", "PH5192105020", "smitj101"): {"pa": 4}},
    )
    ctx = _e4_context(
        plays_games={("1921", "NYA192105010"): _PLAYED},
        batting_games={("1921", "PH5192105020"): _SCORED},
    )

    result = _run(event, batting, register=INITIAL_REGISTER, ctx=ctx)

    assert result.passed, result.unexplained


# --- E5: a game the major-league game logs are not meant to hold ------------


def _e5_context(meta_flags, *, gamelog_games, post_games=None):
    return {
        ("gamelog", "game"): _game("gamelog", gamelog_games),
        ("gamelog_post", "game"): _game("gamelog_post", post_games or {}),
        ("gamemeta", "game"): _game("gamemeta", meta_flags, ("exh", "nogl", "fft")),
        ("gameinfo", "game"): _game(
            "gameinfo",
            {
                ("1930", "KCM193005010"): {"r": 9, "g": 1},
                ("1930", "NYA193005010"): {"r": 4, "g": 1},
            },
            ("r", "g"),
        ),
    }


def _e5_pair():
    info = _game(
        "gameinfo",
        {("1930", "KCM193005010"): {"r": 9, "g": 1}, ("1930", "NYA193005010"): {"r": 4, "g": 1}},
        ("r", "g"),
    )
    log = _game("gamelog", {("1930", "NYA193005010"): {"r": 4, "g": 1}}, ("r", "g"))
    return info, log


def test_e5_explains_a_game_whose_clubs_are_not_in_the_game_logs_and_rolls_up_to_the_season():
    info, log = _e5_pair()
    ctx = _e5_context(
        {("1930", "KCM193005010"): {"exh": 0, "nogl": 1}}, gamelog_games=dict(log.counts)
    )

    game = _run(info, log, register=INITIAL_REGISTER, ctx=ctx)
    assert game.passed, (game.unexplained, game.stale)
    assert {entry for _, entry in game.explained} == {"E5"}

    season_info = _season("gameinfo", {"1930": {"r": 13, "g": 2}}, ("r", "g"))
    season_log = _season("gamelog", {"1930": {"r": 4, "g": 1}}, ("r", "g"))
    comparison = compare(season_info, season_log, seasons=["1930"])
    season = assess(comparison, INITIAL_REGISTER, ctx, rollup=rollup_games(game))
    assert season.passed, season.unexplained
    assert {entry for _, entry in season.explained} == {"E5"}


def test_e5_explains_a_forfeit_the_game_log_does_not_hold():
    info, log = _e5_pair()
    ctx = _e5_context(
        {("1930", "KCM193005010"): {"exh": 0, "nogl": 0, "fft": 1}},
        gamelog_games=dict(log.counts),
    )

    result = _run(info, log, register=INITIAL_REGISTER, ctx=ctx)

    assert result.passed, (result.unexplained, result.stale)
    assert {entry for _, entry in result.explained} == {"E5"}


def test_e5_does_not_excuse_a_major_league_game_the_game_log_lacks():
    info, log = _e5_pair()
    ctx = _e5_context(
        {("1930", "KCM193005010"): {"exh": 0, "nogl": 0}}, gamelog_games=dict(log.counts)
    )

    result = _run(info, log, register=INITIAL_REGISTER, ctx=ctx)

    assert not result.passed
    assert not result.explained


def test_e5_does_not_excuse_a_game_that_is_in_the_game_log_with_other_numbers():
    info = _game("gameinfo", {("1930", "NYA193005010"): {"r": 4, "g": 1}}, ("r", "g"))
    log = _game("gamelog", {("1930", "NYA193005010"): {"r": 5, "g": 1}}, ("r", "g"))
    ctx = _e5_context(
        {("1930", "NYA193005010"): {"exh": 1, "nogl": 1}}, gamelog_games=dict(log.counts)
    )

    result = _run(info, log, register=INITIAL_REGISTER, ctx=ctx)

    assert not result.passed


def test_a_season_difference_the_explained_games_do_not_add_up_to_stays_unexplained():
    season_info = _season("gameinfo", {"1930": {"r": 14, "g": 2}}, ("r", "g"))
    season_log = _season("gamelog", {"1930": {"r": 4, "g": 1}}, ("r", "g"))
    comparison = compare(season_info, season_log, seasons=["1930"])

    result = assess(
        comparison,
        NO_ENTRIES,
        {},
        rollup={("1930", "r"): (9, ("E5",)), ("1930", "g"): (1, ("E5",))},
    )

    assert [d.fact for d in result.unexplained] == ["r"]
    assert [(d.fact, e) for d, e in result.explained] == [("g", "E5")]


# --- a sample source is compared only on the games it holds -----------------


def test_a_sample_source_is_compared_only_on_the_keys_it_holds():
    full = _game(
        "event",
        {("1916", "BOS191604120"): {"k": 10}, ("1916", "BOS191604130"): {"k": 5}},
        ("k",),
    )
    sample = _game("box", {("1916", "BOS191604120"): {"k": 10}}, ("k",))

    unrestricted = compare(full, sample, seasons=["1916"])
    restricted = compare(full, sample, seasons=["1916"], restrict_to=set(sample.counts))

    assert len(unrestricted.differences) == 1
    assert restricted.differences == ()
    assert restricted.keys_compared == 1


def test_a_sample_game_that_disagrees_is_still_a_difference():
    full = _game("event", {("1916", "BOS191604120"): {"k": 10}}, ("k",))
    sample = _game("box", {("1916", "BOS191604120"): {"k": 9}}, ("k",))

    restricted = compare(full, sample, seasons=["1916"], restrict_to=set(sample.counts))

    assert [(d.a_value, d.b_value) for d in restricted.differences] == [(10, 9)]


# --- stale register entry ---------------------------------------------------


def test_a_register_entry_that_predicts_a_difference_which_is_absent_fails():
    # The post-season log has 106 home runs, but the sources agree exactly:
    # the excuse no longer matches reality, so it must not pass silently.
    events = _season("event", {"2019": {"hr": 6767}})
    regular = _season("gamelog", {"2019": {"hr": 6767}})
    ctx = _e1_context({"2019": {"hr": 106}})

    result = _run(events, regular, register=INITIAL_REGISTER, ctx=ctx)

    assert not result.unexplained
    assert not result.passed
    (stale,) = result.stale
    assert stale.found is None
    assert "the sources agree" in stale.describe()
    assert [(r.season, r.status) for r in result.seasons] == [("2019", "unexplained")]


def test_a_stale_prediction_for_a_season_not_being_compared_is_ignored():
    events = _season("event", {"2019": {"hr": 5}})
    regular = _season("gamelog", {"2019": {"hr": 5}})
    ctx = _e1_context({"2018": {"hr": 106}})  # 2018 is not in this comparison

    assert _run(events, regular, register=INITIAL_REGISTER, ctx=ctx).passed


# --- not comparable ---------------------------------------------------------


def test_a_season_only_one_source_covers_is_not_comparable_and_never_a_pass():
    events = _season("event", {"1900": {"hr": 3}, "2019": {"hr": 5}})
    boxes = _season("box", {"1900": {"hr": 3}, "1961": {"hr": 8}})

    cov = coverage(events, boxes)
    assert cov.comparable == {"1900"}
    assert cov.only_a == {"2019"} and cov.only_b == {"1961"}

    result = _run(events, boxes)
    statuses = {r.season: r.status for r in result.seasons}
    assert statuses == {"1900": "match", "2019": "not_comparable", "1961": "not_comparable"}
    assert result.passed
    assert set(result.not_comparable) == {("2019", "event"), ("1961", "box")}


def test_a_run_that_compares_nothing_cannot_pass():
    events = _season("event", {"2019": {"hr": 5}})
    boxes = _season("box", {"1900": {"hr": 3}})
    report = Report()
    report.add(_run(events, boxes))

    assert not report.passed
    assert any("compared anything" in line for line in report.lines())


def test_a_fact_only_one_source_supplies_is_not_compared_and_not_treated_as_zero():
    a = _season("event", {"2019": {"hr": 5, "pa": 100}}, facts=("hr", "pa"))
    b = _season("gamelog", {"2019": {"hr": 5}}, facts=("hr",))

    result = _run(a, b)

    assert result.comparison.facts == ("hr",)
    assert result.passed


# --- absence and cancelling errors ------------------------------------------


def test_an_absent_key_counts_as_zero_but_is_shown_absent():
    a = _game("event", {("2019", "G1"): {"k": 2, "g": 1}, ("2019", "G2"): {"k": 1, "g": 1}})
    b = _game("batting", {("2019", "G1"): {"k": 2, "g": 1}})

    result = _run(a, b)

    diffs = {(d.fact, d.key[1]): d for d in result.unexplained}
    assert set(diffs) == {("k", "G2"), ("g", "G2")}
    assert diffs[("k", "G2")].b_value is None
    assert "absent" in diffs[("k", "G2")].describe()


def test_an_all_zero_row_and_an_absent_row_agree():
    a = _game("event", {("2019", "G1"): {"k": 2}})
    b = _game("batting", {("2019", "G1"): {"k": 2}, ("2019", "G2"): {"k": 0}})

    assert _run(a, b).passed


def test_two_opposite_game_errors_cancel_in_the_season_total_but_show_at_game_level():
    season_a = _season("event", {"2019": {"k": 5}})
    season_b = _season("batting", {"2019": {"k": 5}})
    game_a = _game("event", {("2019", "G1"): {"k": 3}, ("2019", "G2"): {"k": 2}})
    game_b = _game("batting", {("2019", "G1"): {"k": 2}, ("2019", "G2"): {"k": 3}})

    assert _run(season_a, season_b).passed  # the season total alone is fooled
    result = _run(game_a, game_b)
    assert not result.passed
    assert {d.key[1] for d in result.unexplained} == {"G1", "G2"}


# --- construction guards -----------------------------------------------------


def test_comparing_different_levels_is_a_programming_error():
    with pytest.raises(ValueError, match="cannot compare"):
        compare(_season("a", {}), _game("b", {}), seasons=[])


def test_a_key_with_the_wrong_number_of_parts_is_rejected():
    with pytest.raises(ValueError, match="expected 2"):
        Series("event", "game", frozenset({"k"}), {("2019",): {"k": 1}})


def test_unknown_level_is_rejected():
    with pytest.raises(ValueError, match="unknown level"):
        Series("event", "inning", frozenset(), {})


# --- series_from_rows --------------------------------------------------------


def test_series_from_rows_builds_counts_keyed_by_season_and_game():
    series = series_from_rows(
        "event",
        "game",
        ["k", "g"],
        ["season", "game_id", "k", "g"],
        [(2019, "ATL201904010", 12, 1), (2019, "ATL201904020", 9, 1)],
    )

    assert series.counts[("2019", "ATL201904010")] == {"k": 12, "g": 1}
    assert series.seasons() == {"2019"}


def test_series_from_rows_rejects_duplicate_keys_and_bad_columns():
    facts = ["k"]
    with pytest.raises(TieOutError, match="duplicate key"):
        series_from_rows("s", "season", facts, ["season", "k"], [("2019", 1), ("2019", 2)])
    with pytest.raises(TieOutError, match="leading columns"):
        series_from_rows("s", "game", facts, ["game_id", "season", "k"], [])
    with pytest.raises(TieOutError, match="undeclared facts"):
        series_from_rows("s", "season", facts, ["season", "k", "hr"], [("2019", 1, 2)])


def test_a_blank_fact_is_kept_as_none_and_skipped_not_read_as_zero():
    blank = series_from_rows("a", "season", ["k"], ["season", "k"], [("1910", None)])
    other = series_from_rows("b", "season", ["k"], ["season", "k"], [("1910", 7)])
    assert blank.counts[("1910",)] == {"k": None}
    result = tieout.compare(blank, other, seasons={"1910"})
    assert result.differences == ()
    assert result.unrecorded == 1


# --- report -----------------------------------------------------------------


def test_a_problem_recorded_outside_the_comparisons_fails_the_report():
    a = _season("event", {"2019": {"hr": 5}})
    b = _season("batting", {"2019": {"hr": 5}})
    report = Report()
    report.add(_run(a, b))
    assert report.passed

    report.problems.append("core.play is missing 3 events")

    assert not report.passed
    assert any("core.play is missing 3 events" in line for line in report.lines())


def test_report_lines_name_the_season_counts_and_failures():
    a = _season("event", {"2018": {"k": 1}, "2019": {"k": 2}, "2020": {"k": 9}})
    b = _season("batting", {"2018": {"k": 1}, "2019": {"k": 3}})
    report = Report()
    report.add(_run(a, b))

    text = "\n".join(report.lines())

    assert "1 match" in text and "1 unexplained" in text and "1 not comparable" in text
    assert "FAIL" in text and "season 2019 k: event 2 vs batting 3" in text
    assert "not comparable: 2020 covered only by event" in text


# --- read-only access: argument validation (no database needed) --------------


def test_open_readonly_requires_an_explicit_database_name_and_url():
    with pytest.raises(TieOutError, match="explicit database name"):
        tieout.open_readonly("postgresql:///x", expect_db="")
    with pytest.raises(TieOutError, match="database URL"):
        tieout.open_readonly("", expect_db="mlb")


# --- merging per-season comparisons and the difference cap -------------------


def _season_pair(season, a_k, b_k):
    return (
        _game("event", {(season, "G1"): {"k": a_k}}, facts=("k",)),
        _game("batting", {(season, "G1"): {"k": b_k}}, facts=("k",)),
    )


def test_merged_per_season_comparisons_are_assessed_once_over_all_seasons():
    parts = []
    for season, a_k, b_k in (("2018", 1, 1), ("2019", 2, 3)):
        a, b = _season_pair(season, a_k, b_k)
        parts.append(compare(a, b, seasons=[season]))

    merged = tieout.merge_comparisons(parts)
    result = assess(merged, NO_ENTRIES, {})

    assert merged.keys_compared == 2
    assert merged.seasons == {"2018", "2019"}
    assert [d.key[0] for d in result.unexplained] == ["2019"]
    assert {r.season: r.status for r in result.seasons} == {"2018": "match", "2019": "unexplained"}


def test_merging_different_pairs_is_a_programming_error():
    a, b = _season_pair("2019", 1, 1)
    other = compare(a, _game("gamelog", {("2019", "G1"): {"k": 1}}, facts=("k",)), seasons=["2019"])

    with pytest.raises(ValueError, match="different pairs"):
        tieout.merge_comparisons([compare(a, b, seasons=["2019"]), other])
    with pytest.raises(ValueError, match="nothing to merge"):
        tieout.merge_comparisons([])


def test_differences_beyond_the_cap_are_counted_and_fail_the_comparison():
    a = _game("event", {("2019", f"G{i}"): {"k": 1} for i in range(10)}, facts=("k",))
    b = _game("batting", {("2019", f"G{i}"): {"k": 2} for i in range(10)}, facts=("k",))

    comparison = compare(a, b, seasons=["2019"], max_differences=3)
    result = assess(comparison, NO_ENTRIES, {})

    assert len(comparison.differences) == 3
    assert comparison.overflow == 7
    assert not result.passed
    report = Report()
    report.add(result)
    assert any("7 further differences" in line for line in report.lines())


def test_overflow_alone_fails_even_when_every_kept_difference_is_explained():
    events = _season("event", {"2019": {"hr": 6873}})
    regular = _season("gamelog", {"2019": {"hr": 6767}})
    ctx = _e1_context({"2019": {"hr": 106}})
    comparison = compare(events, regular, seasons=["2019"])
    with_overflow = tieout.Comparison(**{**comparison.__dict__, "overflow": 1})

    result = assess(with_overflow, INITIAL_REGISTER, ctx)

    assert not result.unexplained and not result.stale
    assert not result.passed


def test_check_columns_passes_a_table_matching_its_contract_exactly():
    contract = {"raw.retrosheet_roster": frozenset({"player_id", "team_id", "_season"})}
    actual = {"raw.retrosheet_roster": frozenset({"player_id", "team_id", "_season"})}

    assert check_columns(actual, contract) == []


def test_check_columns_reports_a_missing_and_an_extra_column():
    contract = {"raw.retrosheet_roster": frozenset({"player_id", "team_id", "_season"})}
    actual = {"raw.retrosheet_roster": frozenset({"player_id", "_season", "bats"})}

    problems = check_columns(actual, contract)

    assert any("raw.retrosheet_roster is missing column(s) team_id" in p for p in problems)
    assert any("raw.retrosheet_roster has unexpected column(s) bats" in p for p in problems)


def test_check_columns_reports_a_table_absent_from_the_database():
    contract = {"raw.retrosheet_roster": frozenset({"player_id"})}

    problems = check_columns(actual={}, contract=contract)

    assert problems == ["schema contract: raw.retrosheet_roster does not exist in this database"]


# --- E1 with a blank season total, E4/E6/E7 box-score games, E8 ---------------


def test_e1_predicts_nothing_where_the_regular_season_total_is_blank():
    events = _season("event", {"1910": {"k": 9400}})
    regular = _season("gamelog", {"1910": {"k": None}})
    ctx = _e1_context({"1910": {"k": 55}})
    ctx[("gamelog", "season")] = regular

    result = _run(events, regular, register=INITIAL_REGISTER, ctx=ctx)

    assert result.passed, (result.unexplained, result.stale)


def _level(source, level, rows, facts):
    return Series(
        source=source,
        level=level,
        facts=frozenset(facts),
        counts={tuple(key): dict(values) for key, values in rows.items()},
    )


def _box_context(*, event_games, info_games, plays_games, box_games):
    facts = ("r", "g")
    return {
        ("event", "game"): _level("event", "game", event_games, facts),
        ("gameinfo", "game"): _level("gameinfo", "game", info_games, facts),
        ("csv_plays", "game"): _level("csv_plays", "game", plays_games, facts),
        ("box", "game"): _level("box", "game", box_games, facts),
    }


_ANCHOR = {
    ("1943", "NYA194307010"): {"r": 3, "g": 1},
    ("1926", "CHN192601015"): {"r": 4, "g": 1},
}


def test_e4_explains_a_box_score_game_that_no_play_by_play_holds():
    box_games = {**_ANCHOR, ("1943", "HSL194307111"): {"r": 5, "g": 1}}
    ctx = _box_context(
        event_games=_ANCHOR, info_games=_ANCHOR, plays_games=_ANCHOR, box_games=box_games
    )

    result = _run(
        _game("event", _ANCHOR, ("r", "g")),
        _game("box", box_games, ("r", "g")),
        register=INITIAL_REGISTER,
        ctx=ctx,
    )

    assert result.passed, (result.unexplained, result.stale)
    assert {entry for _, entry in result.explained} == {"E4"}


def test_e6_explains_a_game_only_the_box_scores_hold_and_nothing_else_does():
    box_games = {**_ANCHOR, ("1943", "HSL194307111"): {"r": 5, "g": 1}}
    ctx = _box_context(
        event_games=_ANCHOR, info_games=_ANCHOR, plays_games=_ANCHOR, box_games=box_games
    )

    result = _run(
        _game("gameinfo", _ANCHOR, ("r", "g")),
        _game("box", box_games, ("r", "g")),
        register=INITIAL_REGISTER,
        ctx=ctx,
    )

    assert result.passed, (result.unexplained, result.stale)
    assert {entry for _, entry in result.explained} == {"E6"}


def test_e6_does_not_excuse_a_game_that_game_info_holds_under_another_season():
    info = {**_ANCHOR, ("1925", "PRG192601010"): {"r": 12, "g": 1}}
    box_games = {**_ANCHOR, ("1926", "PRG192601010"): {"r": 12, "g": 1}}
    ctx = _box_context(
        event_games=_ANCHOR, info_games=info, plays_games=_ANCHOR, box_games=box_games
    )
    ctx[("csv_plays", "game")] = _level(
        "csv_plays", "game", {**_ANCHOR, ("1926", "X"): {"r": 0, "g": 1}}, ("r", "g")
    )

    result = _run(
        _game("gameinfo", info, ("r", "g")),
        _game("box", box_games, ("r", "g")),
        register=Register(entries=(tieout.E6,)),
        ctx=ctx,
    )

    assert not result.passed


def test_e7_explains_the_second_season_copy_of_a_new_year_game():
    event = {
        **_ANCHOR,
        ("1925", "PRG192601010"): {"r": 12, "g": 1},
    }
    box_games = {
        **_ANCHOR,
        ("1925", "PRG192601010"): {"r": 12, "g": 1},
        ("1926", "PRG192601010"): {"r": 12, "g": 1},
    }
    ctx = _box_context(event_games=event, info_games=event, plays_games=event, box_games=box_games)

    result = _run(
        _game("event", event, ("r", "g")),
        _game("box", box_games, ("r", "g")),
        register=INITIAL_REGISTER,
        ctx=ctx,
    )

    assert result.passed, (result.unexplained, result.stale)
    assert {entry for _, entry in result.explained} == {"E7"}


def test_e7_does_not_excuse_a_game_the_box_lists_in_one_season_only():
    event = {**_ANCHOR, ("1925", "PRG192601010"): {"r": 12, "g": 1}}
    box_games = {**_ANCHOR, ("1926", "PRG192601010"): {"r": 12, "g": 1}}
    ctx = _box_context(event_games=event, info_games=event, plays_games=event, box_games=box_games)

    result = _run(
        _game("event", event, ("r", "g")),
        _game("box", box_games, ("r", "g")),
        register=Register(entries=(tieout.E7,)),
        ctx=ctx,
    )

    assert not result.passed


_E8_KEY = ("1947", "BRO194707200")


def _pa_games(event_pa, csv_pa):
    return (
        _game("event", {_E8_KEY: {"pa": event_pa}}, ("pa",)),
        _game("csv_plays", {_E8_KEY: {"pa": csv_pa}}, ("pa",)),
    )


def test_e8_explains_the_one_plate_appearance_in_the_1947_game():
    event, plays = _pa_games(69, 68)

    result = _run(event, plays, register=Register(entries=(tieout.E8,)))

    assert result.passed, (result.unexplained, result.stale)
    assert {entry for _, entry in result.explained} == {"E8"}


def test_e8_does_not_excuse_a_bigger_gap_and_is_stale_when_the_sources_agree():
    event, plays = _pa_games(70, 68)
    bigger = _run(event, plays, register=Register(entries=(tieout.E8,)))
    assert not bigger.passed

    event, plays = _pa_games(68, 68)
    agree = _run(event, plays, register=Register(entries=(tieout.E8,)))
    assert [item.entry_id for item in agree.stale] == ["E8"]


def test_e4_and_e7_explain_a_player_the_box_holds_even_when_the_game_total_is_left_out():
    # The box game total leaves out a game with a -1 count (BLS...), but its player
    # rows stay; PRG... is listed under both seasons in the box game totals.
    event_games = {**_ANCHOR, ("1925", "PRG192601020"): {"r": 5, "g": 1}}
    box_games = {
        **_ANCHOR,
        ("1925", "PRG192601020"): {"r": 5, "g": 1},
        ("1926", "PRG192601020"): {"r": 5, "g": 1},
    }
    ctx = _box_context(
        event_games=event_games,
        info_games=event_games,
        plays_games=event_games,
        box_games=box_games,
    )
    event_players = _level(
        "event",
        "player_game",
        {("1925", "PRG192601020", "a1"): {"k": 1}, ("1926", "CHN192601015", "c1"): {"k": 2}},
        ("k",),
    )
    box_players = _level(
        "box",
        "player_game",
        {
            ("1925", "PRG192601020", "a1"): {"k": 1},
            ("1926", "PRG192601020", "a1"): {"k": 1},
            ("1925", "BLS192510111", "b1"): {"k": 3},
            ("1926", "CHN192601015", "c1"): {"k": 2},
        },
        ("k",),
    )

    result = _run(event_players, box_players, register=INITIAL_REGISTER, ctx=ctx)

    assert result.passed, (result.unexplained, result.stale)
    assert {entry for _, entry in result.explained} == {"E4", "E7"}
