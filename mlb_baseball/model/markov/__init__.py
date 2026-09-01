"""Base/out Markov chain: `core` is pure computation, `estimate` reads the DB.

This package was one 1,150-line module (`markov.py`). The split (ADR-275
follow-up) puts every database read in `estimate.py` and every pure
computation in `core.py`, so `core` can be imported and unit-tested without
touching SQL. (A fully DB-driver-free import of the whole process is a
separate concern -- `mlb_baseball/model/__init__.py` eagerly imports psycopg;
see issue #111.) The public surface is unchanged -- every name that was `markov.X`
is re-exported here.
"""

from mlb_baseball.model.markov.core import *  # noqa: F401,F403
from mlb_baseball.model.markov.core import __all__ as _core_all
from mlb_baseball.model.markov.estimate import *  # noqa: F401,F403
from mlb_baseball.model.markov.estimate import __all__ as _estimate_all

__all__ = [*_core_all, *_estimate_all]
