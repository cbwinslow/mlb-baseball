"""Sabermetric Literature, Research Papers, and Citation Registry (RESEARCH-01, ADR-117).

Maintains a structured, searchable catalog of peer-reviewed research, books,
and mathematical formulations that govern the MLB platform's models and algorithms.

Adheres strictly to object-oriented encapsulation and polymorphic query interfaces.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Sequence

from mlb_baseball.health import Check


class ResearchDomain(enum.Enum):
    """Categorization of sabermetric research topics."""

    RUN_EXPECTANCY = "run_expectancy"
    PROJECTIONS = "projections"
    HOME_FIELD_ADVANTAGE = "home_field_advantage"
    PITCHING_ESTIMATORS = "pitching_estimators"
    GAME_THEORY_STRATEGY = "game_theory_strategy"
    PROBABILITY_CALIBRATION = "probability_calibration"
    PORTFOLIO_RISK = "portfolio_risk"


@dataclasses.dataclass(frozen=True)
class ResearchPublication:
    """Encapsulates a foundational research paper, book, or monograph."""

    citation_id: str
    title: str
    authors: tuple[str, ...]
    year: int
    publisher_or_journal: str
    domain: ResearchDomain
    abstract: str
    key_formulas: tuple[str, ...]
    project_implementations: tuple[str, ...]


# Foundational sabermetric research catalog
FOUNDATIONAL_RESEARCH: tuple[ResearchPublication, ...] = (
    ResearchPublication(
        citation_id="tango2006thebook",
        title="The Book: Playing the Percentages in Baseball",
        authors=("Tom M. Tango", "Mitchel G. Lichtman", "Andrew E. Dolphin"),
        year=2006,
        publisher_or_journal="Potomac Books / Skyhorse Publishing",
        domain=ResearchDomain.RUN_EXPECTANCY,
        abstract=(
            "Foundational sabermetric text defining 24-state base/out run expectancy (RE24), "
            "Weighted On-Base Average (wOBA), Fielding Independent Pitching (FIP), "
            "Times-Through-The-Order (TTO) degradation, and home field advantage decomposition."
        ),
        key_formulas=(
            "wOBA = (0.69*uBB + 0.72*HBP + 0.89*1B + 1.27*2B + 1.62*3B + 2.10*HR) / PA",
            "FIP = (13*HR + 3*(BB + HBP) - 2*K) / IP + FIP_constant",
            "RE(Base, Outs) = Expected runs from state until 3 outs",
            "TTO_3rd_look wOBA penalty = +0.015 to +0.020 wOBA (~ +0.18 runs/game)",
        ),
        project_implementations=(
            "mlb_baseball/model/markov.py",
            "mlb_baseball/model/simulate.py",
            "mlb_baseball/model/wpa.py",
            "gold.game_feature",
        ),
    ),
    ResearchPublication(
        citation_id="james1981abstract",
        title="The Bill James Baseball Abstract & Log5 Matchup Method",
        authors=("Bill James",),
        year=1981,
        publisher_or_journal="Ballantine Books",
        domain=ResearchDomain.PROJECTIONS,
        abstract=(
            "Introduced Pythagorean Win Expectation relating runs scored and allowed to team "
            "win percentage, the Log5 odds ratio formula for head-to-head probability estimation, "
            "and the Marcel 3-year regression projection system."
        ),
        key_formulas=(
            "Pythagorean Win% = RS^1.83 / (RS^1.83 + RA^1.83)",
            "Log5 Matchup Win Prob = (P_A - P_A * P_B) / (P_A + P_B - 2 * P_A * P_B)",
            "Marcel 3-Yr Rate = (5*t1 + 4*t2 + 3*t3 + 1200*LgMean) / (5*n1 + 4*n2 + 3*n3 + 1200)",
        ),
        project_implementations=(
            "mlb_baseball/model/log5.py",
            "mlb_baseball/model/season.py",
            "mlb_baseball/model/props.py",
        ),
    ),
    ResearchPublication(
        citation_id="palmer1984hidden",
        title=(
            "The Hidden Game of Baseball: A Revolutionary Approach to Baseball and Its Statistics"
        ),
        authors=("Pete Palmer", "John Thorn"),
        year=1984,
        publisher_or_journal="Doubleday / University of Chicago Press",
        domain=ResearchDomain.RUN_EXPECTANCY,
        abstract=(
            "Pioneered linear weights valuation of batting and pitching events, Linear Weights "
            "Batting Runs (LWTS), and multi-year park factor adjustments."
        ),
        key_formulas=(
            "Linear Weights Run Value = Delta RE(Event)",
            "Park Factor = ((Home_RS + Home_RA) / Home_G) / ((Road_RS + Road_RA) / Road_G)",
        ),
        project_implementations=(
            "mlb_baseball/model/markov.py",
            "gold.game_feature",
        ),
    ),
    ResearchPublication(
        citation_id="platt1999calibration",
        title=("Probabilistic Outputs for SVMs and Comparisons to Regularized Likelihood Methods"),
        authors=("John C. Platt",),
        year=1999,
        publisher_or_journal="Advances in Large Margin Classifiers, MIT Press",
        domain=ResearchDomain.PROBABILITY_CALIBRATION,
        abstract=(
            "Formulates sigmoid logistic scaling (Platt Scaling) to transform uncalibrated "
            "margin/tree outputs into well-calibrated posterior probabilities."
        ),
        key_formulas=(
            "P(y=1 | f) = 1 / (1 + exp(A * f + B))",
            "Expected Calibration Error (ECE) = sum_b (|B_b| / N) * |acc(B_b) - conf(B_b)|",
        ),
        project_implementations=(
            "mlb_baseball/model/calibration.py",
            "mlb_baseball/model/evaluation.py",
        ),
    ),
    ResearchPublication(
        citation_id="moskowitz2011scorecasting",
        title="Scorecasting: The Hidden Influences Behind How Sports Are Played and Games Are Won",
        authors=("Tobias J. Moskowitz", "L. Jon Wertheim"),
        year=2011,
        publisher_or_journal="Crown Archetype",
        domain=ResearchDomain.HOME_FIELD_ADVANTAGE,
        abstract=(
            "Rigorous empirical decomposition of Home Field Advantage across sports. Demonstrates "
            "that MLB home win advantage (~53.5%) is driven primarily by umpire strike-zone bias, "
            "tactical last-bat advantage in extra innings, and visiting travel fatigue."
        ),
        key_formulas=(
            "Home Win Log-Odds = beta_0 + sum(beta_i * Delta_X_i)",
            "beta_0 (Baseline HFA) = ln(0.535 / 0.465) approx +0.1405",
            "Road Favorite Inversion: Home Win Prob < 0.50 when sum(beta_i * Delta_X_i) < -0.1405",
        ),
        project_implementations=(
            "mlb_baseball/model/calibration.py",
            "mlb_baseball/model/gbm.py",
            "mlb_baseball/model/season.py",
        ),
    ),
    ResearchPublication(
        citation_id="kelly1956criterion",
        title="A New Interpretation of Information Rate",
        authors=("John L. Kelly Jr.",),
        year=1956,
        publisher_or_journal="Bell System Technical Journal, 35(4), 917-926",
        domain=ResearchDomain.PORTFOLIO_RISK,
        abstract=(
            "Pioneered the Kelly Criterion for maximizing the asymptotic geometric growth rate "
            "of wealth over repeated favorable gambles under logarithmic utility."
        ),
        key_formulas=(
            "f* = (p * b - q) / b = (p * (b + 1) - 1) / b",
            "Fractional Kelly = c * f* (typically c = 0.25 for quarter-Kelly)",
            "Growth Rate g(f) = sum_i [p_i * ln(1 + f_i * b_i) + (1 - p_i) * ln(1 - f_i)]",
        ),
        project_implementations=("mlb_baseball/model/portfolio.py",),
    ),
)


class LiteratureCatalog:
    """Searchable catalog and retrieval system for platform research foundations."""

    def __init__(self, publications: Sequence[ResearchPublication] = FOUNDATIONAL_RESEARCH) -> None:
        self._publications = tuple(publications)

    def search(self, query: str) -> list[ResearchPublication]:
        """Search publications by title, author, keyword, or citation key."""
        q = query.lower().strip()
        words = q.split()
        results: list[ResearchPublication] = []
        for pub in self._publications:
            full_text = (
                f"{pub.title} {pub.citation_id} {' '.join(pub.authors)} "
                f"{pub.abstract} {pub.domain.value} {' '.join(pub.key_formulas)} "
                f"{' '.join(pub.project_implementations)}"
            ).lower()
            if all(w in full_text for w in words):
                results.append(pub)
        return results

    def get_by_citation_id(self, key: str) -> ResearchPublication | None:
        """Retrieve a specific publication by its citation key."""
        for pub in self._publications:
            if pub.citation_id.lower() == key.lower():
                return pub
        return None

    def list_all(self) -> list[ResearchPublication]:
        """Return all indexed foundational publications."""
        return list(self._publications)


def health_check() -> list[Check]:
    """Operational health check for the research and knowledge catalog (RESEARCH-01)."""
    checks: list[Check] = []
    try:
        catalog = LiteratureCatalog()
        all_pubs = catalog.list_all()
        if len(all_pubs) >= 6:
            checks.append(
                Check(
                    "research knowledge catalog",
                    True,
                    f"{len(all_pubs)} peer-reviewed sabermetric publications indexed",
                )
            )
        else:
            checks.append(
                Check(
                    "research knowledge catalog",
                    False,
                    f"Expected >= 6 publications, got {len(all_pubs)}",
                )
            )
    except Exception as exc:
        checks.append(Check("research knowledge catalog", False, str(exc)))
    return checks
