"""Unit tests for Sabermetric Research Catalog & Citation Registry (RESEARCH-01, ADR-117)."""

from mlb_baseball.research import LiteratureCatalog, ResearchDomain, health_check


def test_literature_catalog_indexing_and_search():
    """Verify literature catalog indexes foundational books and supports multi-field search."""
    catalog = LiteratureCatalog()

    # 1. List all
    all_pubs = catalog.list_all()
    assert len(all_pubs) >= 6

    # 2. Search by author
    tango_results = catalog.search("Tom Tango")
    assert len(tango_results) >= 1
    assert "The Book" in tango_results[0].title

    # 3. Search by concept (Pythagorean)
    pyth_results = catalog.search("Pythagorean")
    assert len(pyth_results) >= 1
    assert "Bill James" in pyth_results[0].authors[0]

    # 4. Search by domain (Home Field Advantage)
    hfa_results = catalog.search("home_field_advantage")
    assert len(hfa_results) >= 1
    assert hfa_results[0].domain == ResearchDomain.HOME_FIELD_ADVANTAGE

    # 5. Search by citation key
    pub = catalog.get_by_citation_id("tango2006thebook")
    assert pub is not None
    assert pub.year == 2006
    assert any("wOBA" in f for f in pub.key_formulas)


def test_research_health_check():
    """Verify research health check passes cleanly."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "peer-reviewed" in checks[0].detail
