import pytest
from retrosheetpy import Product, resolve

B = "https://www.retrosheet.org"


def test_yearly_csv():
    r = resolve(Product.YEARLY_CSV, season=2023)
    assert r.url == f"{B}/downloads/2023/2023csvs.zip"
    assert (r.product, r.season, r.filename) == (Product.YEARLY_CSV, 2023, "2023csvs.zip")


@pytest.mark.parametrize(
    "year,name",
    [
        (1910, "1910seve.zip"),
        (1919, "1910seve.zip"),
        (1999, "1990seve.zip"),
        (2024, "2020seve.zip"),
    ],
)
def test_event_decade(year, name):
    r = resolve(Product.EVENTS_DECADE, season=year)
    assert r.url == f"{B}/events/{name}"
    assert r.group == name.removesuffix(".zip")


def test_event_decade_before_1910_is_rejected():
    with pytest.raises(ValueError):
        resolve(Product.EVENTS_DECADE, season=1909)


@pytest.mark.parametrize(
    "product,name",
    [
        (Product.EVENTS_POSTSEASON, "allpost.zip"),
        (Product.EVENTS_ALLSTAR, "allas.zip"),
        (Product.EVENTS_NEGRO_LEAGUE, "allevr.zip"),
        (Product.BOX_NEGRO_LEAGUE, "allebr.zip"),
    ],
)
def test_events_whole_archives(product, name):
    assert resolve(product).url == f"{B}/events/{name}"


@pytest.mark.parametrize(
    "year,name",
    [(1871, "1871box.zip"), (1874, "1874box.zip"), (1898, "1890sbox.zip"), (1905, "1900sbox.zip")],
)
def test_box_archive_families(year, name):
    assert resolve(Product.BOX_ARCHIVE, season=year).url == f"{B}/events/{name}"


def test_box_archive_unknown_year_rejected():
    with pytest.raises(ValueError):
        resolve(Product.BOX_ARCHIVE, season=1873)


def test_roster_resources():
    assert resolve(Product.ROSTERS).url == f"{B}/rosters.zip"
    assert resolve(Product.BIODATA).url == f"{B}/downloads/biodata.zip"
    assert resolve(Product.TEAM_ABBREVIATIONS).url == f"{B}/TEAMABR.TXT"


def test_season_required_where_needed():
    with pytest.raises(ValueError):
        resolve(Product.YEARLY_CSV)
