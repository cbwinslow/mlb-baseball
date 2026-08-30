"""Base/out Markov chain: `core` is pure computation, `estimate` reads the DB.

This package was one 1,150-line module (`markov.py`). The split (ADR-275
follow-up) lets `core` be imported and unit-tested with no database, which
the plate-appearance matchup model needs. The public surface is unchanged --
every name that used to be `markov.X` is re-exported here.

`estimate` is re-exported lazily (PEP 562 ``__getattr__``): it imports
``psycopg`` at module load, so eager-importing it here would defeat the
split's goal of ``markov.core`` importing with no DB driver present.
``markov.<estimator>`` still resolves on first access.
"""

from typing import TYPE_CHECKING

from mlb_baseball.model.markov.core import *  # noqa: F401,F403
from mlb_baseball.model.markov.core import __all__ as _core_all

if TYPE_CHECKING:
    # Give type-checkers the real estimator signatures; at runtime these
    # resolve lazily through __getattr__ below (see module docstring).
    from mlb_baseball.model.markov.estimate import *  # noqa: F401,F403

_estimate_all = [
    "estimate_transition_matrix",
    "estimate_run_expectancy",
    "estimate_outcome_distribution",
    "fetch_matchup_transition_counts",
    "estimate_matchup_distribution",
    "real_half_inning_runs",
    "real_game_scores",
    "fetch_pitcher_arsenal",
    "fetch_batter_arsenal",
]

__all__ = [*_core_all, *_estimate_all]


def __getattr__(name: str) -> object:
    if name in _estimate_all:
        from mlb_baseball.model.markov import estimate

        return getattr(estimate, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
