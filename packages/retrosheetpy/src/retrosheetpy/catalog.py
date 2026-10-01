"""Deterministic official Retrosheet URL resolution."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

BASE = "https://www.retrosheet.org"


class Product(StrEnum):
    YEARLY_CSV = "yearly_csv"
    EVENTS_DECADE = "events_decade"
    EVENTS_POSTSEASON = "events_postseason"
    EVENTS_ALLSTAR = "events_allstar"
    EVENTS_NEGRO_LEAGUE = "events_negro_league"
    BOX_ARCHIVE = "box_archive"
    BOX_NEGRO_LEAGUE = "box_negro_league"
    ROSTERS = "rosters"
    BIODATA = "biodata"
    TEAM_ABBREVIATIONS = "team_abbreviations"


@dataclass(frozen=True)
class Resource:
    """An official Retrosheet file the client knows how to fetch."""

    product: Product
    url: str
    filename: str
    season: int | None = None
    group: str | None = None

    @property
    def is_zip(self) -> bool:
        return self.filename.lower().endswith(".zip")


_WHOLE = {
    Product.EVENTS_POSTSEASON: f"{BASE}/events/allpost.zip",
    Product.EVENTS_ALLSTAR: f"{BASE}/events/allas.zip",
    Product.EVENTS_NEGRO_LEAGUE: f"{BASE}/events/allevr.zip",
    Product.BOX_NEGRO_LEAGUE: f"{BASE}/events/allebr.zip",
    Product.ROSTERS: f"{BASE}/rosters.zip",
    Product.BIODATA: f"{BASE}/downloads/biodata.zip",
    Product.TEAM_ABBREVIATIONS: f"{BASE}/TEAMABR.TXT",
}

_BOX_SINGLE_SEASONS = {1871, 1872, 1874}
# Retrosheet's "1890sbox.zip" holds 1898-1899 only; "1900sbox.zip" holds 1900-1909.
_BOX_ERA = {range(1898, 1900): "1890sbox.zip", range(1900, 1910): "1900sbox.zip"}


def _need_season(product: Product, season: int | None) -> int:
    if season is None:
        raise ValueError(f"{product.value} requires a season")
    return season


def resolve(product: Product, season: int | None = None) -> Resource:
    """Return the official Resource for ``product`` (and ``season`` if needed)."""
    if product is Product.YEARLY_CSV:
        y = _need_season(product, season)
        name = f"{y}csvs.zip"
        return Resource(product, f"{BASE}/downloads/{y}/{name}", name, season=y)
    if product is Product.EVENTS_DECADE:
        y = _need_season(product, season)
        if not 1910 <= y <= date.today().year:
            raise ValueError(f"no event decade archive for {y}")
        name = f"{y // 10 * 10}seve.zip"
        return Resource(product, f"{BASE}/events/{name}", name, season=y, group=name[:-4])
    if product is Product.BOX_ARCHIVE:
        y = _need_season(product, season)
        if y in _BOX_SINGLE_SEASONS:
            name = f"{y}box.zip"
        else:
            name = next((n for r, n in _BOX_ERA.items() if y in r), "")
            if not name:
                raise ValueError(f"no box-score archive for {y}")
        return Resource(product, f"{BASE}/events/{name}", name, season=y, group=name[:-4])
    url = _WHOLE.get(product)
    if url is None:
        raise ValueError(f"unsupported product {product!r}")
    return Resource(product, url, url.rsplit("/", 1)[1])
