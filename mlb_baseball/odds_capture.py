"""Frequent price-only capture of Kalshi and Polymarket odds (cron, every 15
minutes). See openspec/changes/odds-history-capture. Only runs when MLB games
are scheduled around today, so the off-season does not pile up identical
futures prices; the nightly update() still keeps the catalogs current."""

import logging
from datetime import UTC, datetime

from mlb_baseball.connectors import kalshi, polymarket
from mlb_baseball.db import get_connection
from mlb_baseball.health import games_scheduled

logger = logging.getLogger(__name__)


def _games_scheduled_now() -> bool:
    with get_connection() as conn:
        return games_scheduled(conn, datetime.now(UTC).date())


def run() -> dict[str, int]:
    """Capture both sources. One source failing must not cost the other its
    observation, so every source is attempted and the failure is raised after."""
    if not _games_scheduled_now():
        logger.info("odds capture: no MLB games scheduled around today; skipping")
        return {}
    counts: dict[str, int] = {}
    failures: list[str] = []
    for name, snapshot in (("kalshi", kalshi.snapshot), ("polymarket", polymarket.snapshot)):
        try:
            counts.update(snapshot())
        except Exception as exc:
            logger.error("odds capture: %s failed (%s)", name, exc)
            failures.append(f"{name}: {exc}")
    if failures:
        raise RuntimeError("odds capture failed — " + "; ".join(failures))
    return counts
