"""Phase 2 modeling (ADR-032, docs/RESEARCH.md). Deliberately not a plugin
framework -- two models exist so far (features is a shared build step, log5
is the first model); this just calls each directly. Extract real structure
once a third model actually needs it, not before -- same reasoning as this
project's connector registry, which came after multiple real connectors,
not in anticipation of one.
"""

from mlb_baseball.health import Check
from mlb_baseball.model import features, log5


def run() -> dict[str, int]:
    counts = features.run()
    counts.update(log5.run())
    return counts


def health_check() -> list[Check]:
    return features.health_check() + log5.health_check()
