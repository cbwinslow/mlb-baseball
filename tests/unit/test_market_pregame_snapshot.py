"""Unit coverage for conform.py's _latest_before -- the pure bisect logic
behind core.market.implied_probability's pre-game snapshot resolution
(ADR-052, issue #1). No I/O: pre-sorted (timestamp, value) lists in,
one value or None out.
"""

from datetime import datetime
from decimal import Decimal

from mlb_baseball.conform import _latest_before


def test_returns_the_latest_entry_strictly_before_cutoff():
    entries = [
        (datetime(2026, 8, 1, 6, 0), Decimal("0.55")),
        (datetime(2026, 8, 2, 6, 0), Decimal("0.60")),
        (datetime(2026, 8, 3, 6, 0), Decimal("0.99")),
    ]
    # Game starts 2026-08-02 19:05 -- the 08-02 06:00 snapshot qualifies
    # (before), the 08-03 06:00 one does not (after).
    assert _latest_before(entries, datetime(2026, 8, 2, 19, 5)) == Decimal("0.60")


def test_a_snapshot_exactly_at_cutoff_does_not_qualify():
    # Strictly before, not before-or-equal -- a snapshot captured at the
    # exact moment of first pitch is not safely "pre-game."
    entries = [(datetime(2026, 8, 2, 19, 5), Decimal("0.60"))]
    assert _latest_before(entries, datetime(2026, 8, 2, 19, 5)) is None


def test_no_entries_before_cutoff_returns_none():
    entries = [(datetime(2026, 8, 3, 6, 0), Decimal("0.99"))]
    assert _latest_before(entries, datetime(2026, 8, 2, 19, 5)) is None


def test_empty_entries_returns_none():
    assert _latest_before([], datetime(2026, 8, 2, 19, 5)) is None


def test_picks_the_most_recent_of_several_qualifying_entries():
    entries = [
        (datetime(2026, 8, 1, 6, 0), Decimal("0.50")),
        (datetime(2026, 8, 2, 6, 0), Decimal("0.55")),
        (datetime(2026, 8, 2, 12, 0), Decimal("0.58")),
    ]
    assert _latest_before(entries, datetime(2026, 8, 2, 19, 5)) == Decimal("0.58")
