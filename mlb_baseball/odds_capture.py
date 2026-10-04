"""Frequent price-only capture of Kalshi and Polymarket odds (cron, every 15
minutes). See openspec/changes/odds-history-capture. Only runs when MLB games
are scheduled around today, so the off-season does not pile up identical
futures prices; the nightly update() still keeps the catalogs current."""

import logging
from datetime import UTC, date, datetime, timedelta

import psycopg

from mlb_baseball.connectors import kalshi, polymarket
from mlb_baseball.db import get_connection

logger = logging.getLogger(__name__)


def games_scheduled(conn: psycopg.Connection, today: date) -> bool:
    """True when raw.mlb_schedule (refreshed every 5 minutes) lists a game from
    yesterday to tomorrow. The one-day margin each side covers US evening games
    that are already "tomorrow" in UTC and late games that end "yesterday".
    Fails open (True) when the schedule table does not exist yet: not knowing is
    a reason to capture, not to lose data."""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_schedule')")
        if cur.fetchone()[0] is None:
            return True
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM raw.mlb_schedule WHERE game_date BETWEEN %s AND %s)",
            ((today - timedelta(days=1)).isoformat(), (today + timedelta(days=1)).isoformat()),
        )
        return bool(cur.fetchone()[0])


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
