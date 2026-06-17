from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest.analytics import (
    compute_cagr,
    compute_max_drawdown,
    compute_sharpe,
    compute_sortino,
    compute_volatility,
    compute_calmar,
    compute_profit_factor,
    compute_expectancy,
    compute_avg_win_loss,
    compute_benchmark_metrics,
    compute_drawdowns_detail,
    compute_metrics,
)


@pytest.fixture
def sample_equity():
    dates = pd.date_range("2023-01-01", periods=252, freq="B")
    nav = 1e9 * np.exp(np.cumsum(np.random.normal(0.0005, 0.01, len(dates))))
    return pd.DataFrame({"nav": nav, "daily_return": pd.Series(nav).pct_change().fillna(0)}, index=dates)


@pytest.fixture
def sample_trades():
    np.random.seed(42)
    n = 50
    pnls = np.random.normal(500000, 2000000, n)
    pnls[::3] = pnls[::3] * -1
    return pd.DataFrame({
        "ticker": ["VCB"] * n,
        "sector": ["Banking"] * n,
        "pnl": pnls,
        "return_pct": pnls / 50000 / 1000,
        "entry_date": pd.date_range("2023-01-01", periods=n, freq="W"),
        "exit_date": pd.date_range("2023-02-15", periods=n, freq="W"),
        "shares": [1000] * n,
        "hold_days": [30] * n,
        "exit_reason": ["tp1_resistance"] * n,
        "mode": ["buy_atc_sell_atc"] * n,
        "entry_price": [50000.0] * n,
        "commission_entry": [75000.0] * n,
        "commission_exit": [75000.0] * n,
    })


class TestComputeCAGR:
    def test_positive_return(self):
        nav = pd.Series([100, 150])
        assert compute_cagr(nav, trading_days=1) == pytest.approx(0.5, rel=1e-3)

    def test_zero_return(self):
        nav = pd.Series([100, 100])
        assert compute_cagr(nav, trading_days=1) == 0.0

    def test_negative_return(self):
        nav = pd.Series([100, 50])
        assert compute_cagr(nav, trading_days=1) == pytest.approx(-0.5, rel=1e-3)

    def test_short_series(self):
        assert compute_cagr(pd.Series([100])) == 0.0


class TestComputeMaxDrawdown:
    def test_no_drawdown(self):
        nav = pd.Series([100, 110, 120])
        assert compute_max_drawdown(nav) == pytest.approx(0.0, abs=1e-6)

    def test_with_drawdown(self):
        nav = pd.Series([100, 120, 90, 110])
        dd = compute_max_drawdown(nav)
        assert dd < 0
        assert dd == pytest.approx(-0.25, rel=1e-2)

    def test_short_series(self):
        assert compute_max_drawdown(pd.Series([100])) == 0.0


class TestComputeSharpe:
    def test_positive_sharpe(self):
        returns = pd.Series(np.random.normal(0.001, 0.01, 252))
        sharpe = compute_sharpe(returns)
        assert isinstance(sharpe, float)

    def test_no_volatility(self):
        returns = pd.Series([0.001] * 10)
        result = compute_sharpe(returns)
        assert result == 0.0 or abs(result) < 1e-6

    def test_short_series(self):
        assert compute_sharpe(pd.Series([0.001])) == 0.0


class TestComputeProfitFactor:
    def test_basic_pf(self):
        trades = pd.DataFrame({"pnl": [100, -50, 200, -30]})
        pf = compute_profit_factor(trades)
        assert pf == pytest.approx(300 / 80, rel=1e-3)

    def test_all_winners(self):
        trades = pd.DataFrame({"pnl": [100, 200]})
        assert compute_profit_factor(trades) == np.inf

    def test_all_losers(self):
        trades = pd.DataFrame({"pnl": [-100, -200]})
        assert compute_profit_factor(trades) == 0.0

    def test_empty(self):
        assert compute_profit_factor(pd.DataFrame()) == 0.0


class TestComputeMetrics:
    def test_full_metrics(self, sample_equity, sample_trades):
        metrics = compute_metrics(sample_trades, sample_equity, sample_equity["daily_return"])
        assert "total_return" in metrics
        assert "cagr" in metrics
        assert "sharpe" in metrics
        assert "max_drawdown" in metrics
        assert "win_rate" in metrics
        assert "profit_factor" in metrics
        assert "total_trades" in metrics

    def test_benchmark_metrics(self, sample_equity, sample_trades):
        bm_returns = pd.Series(np.random.normal(0.0003, 0.008, len(sample_equity)), index=sample_equity.index)
        metrics = compute_metrics(sample_trades, sample_equity, sample_equity["daily_return"], bm_returns)
        assert "benchmark_alpha" in metrics or any("benchmark" in k for k in metrics)

    def test_empty_equity(self):
        metrics = compute_metrics(pd.DataFrame(), pd.DataFrame(), pd.Series(dtype=float))
        assert "error" in metrics


class TestDrawdownDetail:
    def test_basic_drawdowns(self):
        nav = pd.Series([100, 110, 95, 105, 90, 100], index=pd.date_range("2023-01-01", periods=6, freq="D"))
        dd = compute_drawdowns_detail(nav)
        assert not dd.empty
        assert "depth_pct" in dd.columns
        assert "recovery_days" in dd.columns


class TestBenchmarkMetrics:
    def test_correlation(self):
        strat = pd.Series(np.random.normal(0.001, 0.01, 100))
        bench = strat * 0.8 + np.random.normal(0, 0.005, 100)
        result = compute_benchmark_metrics(strat, bench)
        assert "beta" in result
        assert "alpha" in result
        assert "correlation" in result
