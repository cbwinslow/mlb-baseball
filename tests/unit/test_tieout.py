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
    compare,
    coverage,
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


def test_series_from_rows_rejects_duplicate_keys_null_facts_and_bad_columns():
    facts = ["k"]
    with pytest.raises(TieOutError, match="duplicate key"):
        series_from_rows("s", "season", facts, ["season", "k"], [("2019", 1), ("2019", 2)])
    with pytest.raises(TieOutError, match="NULL k"):
        series_from_rows("s", "season", facts, ["season", "k"], [("2019", None)])
    with pytest.raises(TieOutError, match="leading columns"):
        series_from_rows("s", "game", facts, ["game_id", "season", "k"], [])
    with pytest.raises(TieOutError, match="undeclared facts"):
        series_from_rows("s", "season", facts, ["season", "k", "hr"], [("2019", 1, 2)])


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
