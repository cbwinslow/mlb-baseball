"""Per-team and league-wide MLB news/RSS ingestion -- headlines, links, and
summaries only, deliberately not full article bodies (license-clean, and
sufficient for the signal extraction -- injuries/trades/rumors -- this is
meant to feed later; that extraction is Phase 2, not built here). Accrues
into raw.news for later NLP feature encoding.

Three feed sources, each verified working via a real fetch before being
hardcoded (see docs/DATA_SOURCES.md "News/RSS" and docs/DECISIONS.md
ADR-047):
- **MLB.com** (`https://www.mlb.com/{slug}/feeds/news/rss.xml`) -- league-wide
  plus all 30 teams. A wrong slug 404s (confirmed directly), so the 30
  slugs in MLB_COM_SLUGS are all real, not guessed.
- **MLB Trade Rumors** (`https://www.mlbtraderumors.com/{slug}/feed`) --
  league-wide plus all 30 teams. A wrong slug 200s but returns a genuinely
  empty (0-item) feed (confirmed directly), so the 30 slugs in
  MLBTR_SLUGS are all real too, not inferred from the 200 status alone.
- **ESPN** (`https://www.espn.com/espn/rss/mlb/news`) -- league-wide only;
  no working per-team variant found, so not built (a static dict of
  team->feed URLs is fine per this project's own bias against
  speculative structure -- not worth inventing an unverified URL pattern
  for one source when two others already give full per-team coverage).

bootstrap() == update(): confirmed directly that none of the three
sources paginate or expose an archive -- each feed only ever returns its
own most recent ~15-25 items, so there is no separate "full historical
load" to do differently. History accrues from whenever polling starts,
not before -- a real, documented limitation (see docs/DATA_SOURCES.md),
not an oversight.

Idempotency is the reason this connector doesn't use load.py's shared
helpers: feeds re-serve the same items on every single poll, and neither
load_dataframe (replace-a-chunk) nor append_dataframe (pure insert, no
conflict handling) can express "insert this item only if we haven't seen
it before." raw.news is therefore the one raw table with a real UNIQUE
constraint (migration 0027) -- dedup_key is the feed's own guid, falling
back to a sha256 of the link for the rare entry missing one -- and this
module writes its own small `INSERT ... ON CONFLICT (dedup_key) DO
NOTHING` path directly, rather than growing load.py into a fourth,
more-general pattern for a need only this connector has so far (see
docs/ARCHITECTURE.md "Loading patterns" and CLAUDE.md "don't build
abstractions for sources we don't have yet").
"""

import hashlib
from calendar import timegm
from datetime import UTC, datetime, timedelta

import feedparser
import psycopg

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import Check, check_last_run, check_table_has_rows
from mlb_baseball.ingest import track_run
from mlb_baseball.net import get_with_retry

SOURCE = "news"
TABLE = "raw.news"

# Identifies this project to the servers it polls, in place of the default
# "python-requests/x.y" -- cheap etiquette, and insurance against a future
# UA-based blocking rule even though none of the three sources below
# actually require it today (confirmed: all three 200 with no UA sent).
USER_AGENT = "mlb-baseball-news-connector/1.0 (+https://github.com/cbwinslow/mlb-baseball)"

# Canonical team key -> MLB.com's own one-word team slug (already unique
# across all 30 teams, so used as the canonical key both sources' rows
# are tagged with). Every value here was confirmed with a real fetch
# returning team-specific content (channel <title> e.g. "Red Sox News",
# "Athletics News" -- distinct from the league feed's "MLB News") before
# being hardcoded -- not guessed from a naming convention.
MLB_COM_SLUGS: dict[str, str] = {
    "angels": "angels",
    "astros": "astros",
    "athletics": "athletics",
    "bluejays": "bluejays",
    "braves": "braves",
    "brewers": "brewers",
    "cardinals": "cardinals",
    "cubs": "cubs",
    "dbacks": "dbacks",
    "dodgers": "dodgers",
    "giants": "giants",
    "guardians": "guardians",
    "mariners": "mariners",
    "marlins": "marlins",
    "mets": "mets",
    "nationals": "nationals",
    "orioles": "orioles",
    "padres": "padres",
    "phillies": "phillies",
    "pirates": "pirates",
    "rangers": "rangers",
    "rays": "rays",
    "redsox": "redsox",
    "reds": "reds",
    "rockies": "rockies",
    "royals": "royals",
    "tigers": "tigers",
    "twins": "twins",
    "whitesox": "whitesox",
    "yankees": "yankees",
}

# Canonical team key (matching MLB_COM_SLUGS above) -> MLB Trade Rumors'
# own city+nickname slug. Every value confirmed with a real fetch (15
# items, channel <title> naming the team) before being hardcoded.
MLBTR_SLUGS: dict[str, str] = {
    "angels": "los-angeles-angels",
    "astros": "houston-astros",
    "athletics": "oakland-athletics",
    "bluejays": "toronto-blue-jays",
    "braves": "atlanta-braves",
    "brewers": "milwaukee-brewers",
    "cardinals": "st-louis-cardinals",
    "cubs": "chicago-cubs",
    "dbacks": "arizona-diamondbacks",
    "dodgers": "los-angeles-dodgers",
    "giants": "san-francisco-giants",
    "guardians": "cleveland-guardians",
    "mariners": "seattle-mariners",
    "marlins": "miami-marlins",
    "mets": "new-york-mets",
    "nationals": "washington-nationals",
    "orioles": "baltimore-orioles",
    "padres": "san-diego-padres",
    "phillies": "philadelphia-phillies",
    "pirates": "pittsburgh-pirates",
    "rangers": "texas-rangers",
    "rays": "tampa-bay-rays",
    "redsox": "boston-red-sox",
    "reds": "cincinnati-reds",
    "rockies": "colorado-rockies",
    "royals": "kansas-city-royals",
    "tigers": "detroit-tigers",
    "twins": "minnesota-twins",
    "whitesox": "chicago-white-sox",
    "yankees": "new-york-yankees",
}


def _feeds() -> list[tuple[str, str | None, str]]:
    """Returns (source, team, url) for every feed polled -- league-wide once
    per source, plus all 30 teams for the two sources that offer per-team
    feeds. team is None for a league-wide feed."""
    feeds: list[tuple[str, str | None, str]] = [
        ("mlb_com", None, "https://www.mlb.com/feeds/news/rss.xml"),
        ("mlb_trade_rumors", None, "https://www.mlbtraderumors.com/feed"),
        ("espn", None, "https://www.espn.com/espn/rss/mlb/news"),
    ]
    feeds.extend(
        ("mlb_com", team, f"https://www.mlb.com/{slug}/feeds/news/rss.xml")
        for team, slug in MLB_COM_SLUGS.items()
    )
    feeds.extend(
        ("mlb_trade_rumors", team, f"https://www.mlbtraderumors.com/{slug}/feed")
        for team, slug in MLBTR_SLUGS.items()
    )
    return feeds


def _published(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed is None:
        return None
    return datetime.fromtimestamp(timegm(parsed), tz=UTC)


def _dedup_key(guid: str | None, link: str | None) -> str | None:
    """The feed's own guid where present (already a unique, source-issued
    identifier -- no need to hash it), falling back to a sha256 of the
    link for the rare entry with neither <guid> nor <id>. Returns None
    only when an entry has neither -- confirmed not to happen on any of
    the real feeds this connector polls, but handled explicitly rather
    than crashing the whole feed over one malformed entry."""
    if guid:
        return guid
    if link:
        return hashlib.sha256(link.encode()).hexdigest()
    return None


def parse_entries(source: str, team: str | None, raw_bytes: bytes) -> list[dict]:
    """Parses one feed's raw RSS/Atom bytes into row dicts ready for
    _insert_rows. Pure function (no network, no DB) -- this is what
    tests/unit exercises directly against fixture XML."""
    parsed = feedparser.parse(raw_bytes)
    fetched_at = datetime.now(UTC)
    rows = []
    for entry in parsed.entries:
        link = entry.get("link") or None
        guid = entry.get("id") or None
        dedup_key = _dedup_key(guid, link)
        if dedup_key is None:
            print(
                f"news: {source}/{team or 'league'} entry with neither guid nor "
                f"link, skipping ({entry.get('title', '?')!r})"
            )
            continue
        rows.append(
            {
                "source": source,
                "team": team,
                "title": entry.get("title"),
                "link": link,
                "guid": guid,
                "dedup_key": dedup_key,
                "published": _published(entry),
                "summary": entry.get("summary"),
                "fetched_at": fetched_at,
            }
        )
    return rows


def _fetch_feed(source: str, team: str | None, url: str) -> list[dict]:
    response = get_with_retry(url, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return parse_entries(source, team, response.content)


def _insert_rows(conn: psycopg.Connection, rows: list[dict]) -> int:
    """INSERT ... ON CONFLICT (dedup_key) DO NOTHING -- the dedicated,
    hand-written insert path raw.news needs (see module docstring). Loops
    row-by-row rather than a single multi-row INSERT so cur.rowcount
    reports exactly how many rows this call actually landed (skipped
    conflicts don't count), which is what bootstrap()/update() report as
    this run's row count."""
    inserted = 0
    with conn.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO raw.news
                    (source, team, title, link, guid, dedup_key, published, summary, fetched_at)
                VALUES
                    (%(source)s, %(team)s, %(title)s, %(link)s, %(guid)s, %(dedup_key)s,
                     %(published)s, %(summary)s, %(fetched_at)s)
                ON CONFLICT (dedup_key) DO NOTHING
                """,
                row,
            )
            inserted += cur.rowcount
    return inserted


def _run(conn: psycopg.Connection) -> dict[str, int]:
    """Fetches every feed in turn, tolerating any single feed's failure --
    a connection error/timeout/HTTP error on one team's feed must not
    lose data already landed from every other feed already processed this
    run, nor block the rest. Each feed's insert is committed immediately
    after it succeeds (rather than one commit at the very end) for the
    same reason: a later feed's failure triggers a rollback of only that
    feed's own (never-inserted) attempt, not everything landed so far.
    """
    feeds = _feeds()
    total_rows = 0
    failed = 0
    for source, team, url in feeds:
        try:
            rows = _fetch_feed(source, team, url)
            total_rows += _insert_rows(conn, rows)
            conn.commit()
        except Exception as exc:
            failed += 1
            conn.rollback()
            print(f"news: {source}/{team or 'league'} feed failed ({url}): {exc}; skipping")
    if failed:
        print(f"news: {failed}/{len(feeds)} feeds failed this run")
    return {TABLE: total_rows}


def bootstrap() -> dict[str, int]:
    with get_connection() as conn, track_run(conn, SOURCE, "bootstrap") as result:
        counts = _run(conn)
        result["rows"] = sum(counts.values())
    return counts


def update() -> dict[str, int]:
    with get_connection() as conn, track_run(conn, SOURCE, "update") as result:
        counts = _run(conn)
        result["rows"] = sum(counts.values())
    return counts


def _freshness_check() -> Check:
    """No genuinely new item across every feed combined in 48h is
    suspicious during a live MLB season -- teams play (and get covered)
    daily. Distinct from check_last_run, which only confirms update() ran
    without raising: _run's per-feed try/except means update() never
    raises just because every single feed happened to return zero new
    items, so a connector that's silently blocked/broken on every feed
    could still show a clean check_last_run indefinitely. fetched_at is
    only set on rows actually inserted (ON CONFLICT DO NOTHING leaves an
    already-seen row's fetched_at untouched from its first insert), so
    MAX(fetched_at) answers "when did a genuinely new item last land,"
    not just "when did update() last execute.\""""
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("SELECT max(fetched_at) FROM raw.news")
            except psycopg.errors.UndefinedTable:
                conn.rollback()
                return Check("news freshness", False, "raw.news does not exist — run `mlb migrate`")
            (latest,) = fetch_one(cur)
    if latest is None:
        return Check("news freshness", False, "no items ingested yet")
    age = datetime.now(UTC) - latest
    if age > timedelta(hours=48):
        return Check(
            "news freshness",
            False,
            f"newest item landed {age} ago (older than 48h) — feeds may be broken/blocked",
        )
    return Check("news freshness", True, f"newest item landed {age} ago")


def health_check() -> list[Check]:
    return [check_table_has_rows(TABLE), check_last_run(SOURCE), _freshness_check()]
