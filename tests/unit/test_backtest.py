"""Unit tests for Historical Walk-Forward Backtesting Engine (BACKTEST-01, ADR-119)."""

from unittest.mock import MagicMock

from mlb_baseball.model.backtest import (
    BacktestSummary,
    BetRecord,
    WalkForwardBacktester,
    health_check,
)
from mlb_baseball.model.portfolio import KellyAllocator


def test_backtest_summary_dataclass():
    """Verify BacktestSummary encapsulation and metrics integrity."""
    rec = BetRecord(
        game_instance_key="mlb:1001",
        game_date="2024-04-05",
        matchup="BOS @ NYA (HOME)",
        model_prob=0.6200,
        market_prob=0.5000,
        decimal_odds=2.000,
        wager_usd=250.0,
        won_bet=True,
        pnl_usd=250.0,
        bankroll_after_usd=10250.0,
    )

    summary = BacktestSummary(
        start_date="2024-04-01",
        end_date="2024-04-30",
        model_version="gbm-v1",
        initial_bankroll_usd=10000.0,
        final_bankroll_usd=10250.0,
        total_wagers=1,
        winning_wagers=1,
        losing_wagers=0,
        win_rate_pct=100.0,
        total_wagered_usd=250.0,
        total_pnl_usd=250.0,
        roi_pct=100.0,
        annualized_sharpe_ratio=3.50,
        max_drawdown_pct=0.0,
        mean_clv_pct=24.0,
        brier_score=0.1444,
        wager_history=[rec],
    )

    assert summary.total_wagers == 1
    assert summary.win_rate_pct == 100.0
    assert summary.total_pnl_usd == 250.0
    assert len(summary.wager_history) == 1


def test_walk_forward_backtest_mock_run():
    """Verify walk-forward backtesting execution and portfolio compounding on mock data."""
    # 2 games: Game 1 won (+EV home bet), Game 2 lost (+EV away bet)
    mock_rows = [
        {
            "game_instance_key": "game_1",
            "game_date": "2024-05-01",
            "home_team": "NYA",
            "away_team": "BAL",
            "home_win_prob": 0.65,
            "market_home_prob": 0.50,
            "home_score": 5,
            "away_score": 3,
        },
        {
            "game_instance_key": "game_2",
            "game_date": "2024-05-02",
            "home_team": "BOS",
            "away_team": "TOR",
            "home_win_prob": 0.35,
            "market_home_prob": 0.55,
            "home_score": 4,
            "away_score": 2,
        },
    ]

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchall.return_value = mock_rows

    allocator = KellyAllocator(fraction=0.25, max_single_bet_pct=0.025, max_total_exposure_pct=0.15)
    tester = WalkForwardBacktester(allocator=allocator, min_edge_pct=0.05)

    summary = tester.run_backtest(
        start_date="2024-05-01",
        end_date="2024-05-02",
        model_version="gbm-v1",
        initial_bankroll=10000.0,
        conn=mock_conn,
    )

    assert summary.total_wagers == 2
    assert summary.winning_wagers == 1
    assert summary.losing_wagers == 1
    assert summary.win_rate_pct == 50.0
    assert len(summary.wager_history) == 2
    assert summary.wager_history[0].won_bet is True
    assert summary.wager_history[1].won_bet is False


def test_backtest_health_check():
    """Verify backtesting engine health check returns clean pass."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Quarter-Kelly" in checks[0].detail
