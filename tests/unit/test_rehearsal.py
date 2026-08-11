import pytest

from mlb_baseball.rehearsal import assert_safe_urls, clear_sample


def test_rehearsal_requires_distinct_source_and_test_target():
    with pytest.raises(ValueError, match="must differ"):
        assert_safe_urls("postgresql:///mlb", "postgresql:///mlb")


def test_rehearsal_refuses_a_non_test_target():
    with pytest.raises(ValueError, match="must contain 'test'"):
        assert_safe_urls("postgresql:///mlb", "postgresql:///research")


def test_rehearsal_accepts_a_distinct_test_target():
    assert_safe_urls("postgresql:///mlb", "postgresql:///mlb_test")


def test_clear_rehearsal_refuses_a_non_test_target():
    with pytest.raises(ValueError, match="must contain 'test'"):
        clear_sample("postgresql:///mlb")
