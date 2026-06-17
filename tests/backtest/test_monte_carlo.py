from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest.monte_carlo import MonteCarloSimulator, MonteCarloResult, STRESS_PERIODS
from src.strategy.config import StrategyConfig


@pytest.fixture
def sample_mc_data():
    np.random.seed(42)
    n_dates = 400
    dates = pd.bdate_range("2022-06-01", periods=n_dates)
    tickers = ["VCB"]
    features = {}
    for t in tickers:
        closes = 50000 * np.cumprod(1.0 + np.random.normal(0.0008, 0.010, n_dates))
        closes = np.maximum(closes, 10000)
        opens = closes * np.random.uniform(0.97, 0.98, n_dates)
        highs = closes * np.random.uniform(1.003, 1.008, n_dates)
        lows = opens * np.random.uniform(0.99, 0.997, n_dates)
        closes_series = pd.Series(closes)
        df = pd.DataFrame({
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": np.full(n_dates, 2_000_000.0),
            "ema20": closes_series.ewm(span=20).mean().values,
            "ema50": closes_series.ewm(span=50).mean().values,
            "ema200": closes_series.ewm(span=200).mean().values,
            "swing_high": closes_series.rolling(20).max().values,
            "swing_low": closes_series.rolling(20).min().values,
            "vol_ma20": np.full(n_dates, 1_500_000.0),
            "vol_ratio": np.full(n_dates, 1.5),
            "rsi_weekly": np.full(n_dates, 55.0),
            "foreign_net_buy_5d": np.full(n_dates, 500_000_000.0),
            "foreign_ratio_5d": np.full(n_dates, 0.45),
            "ceiling": closes * 1.07,
            "ceiling_buffer": np.full(n_dates, 0.98),
            "dist_ema20": np.full(n_dates, 0.005),
            "atr14": np.full(n_dates, 1500.0),
            "foreign_net_sell_streak": np.zeros(n_dates),
        }, index=dates)
        features[t] = df

    ticker_info = {
        "VCB": {"ticker": "VCB", "sector": "Banking", "foreign_room_limit": 0.3,
                "current_foreign_own": 0.15, "foreign_room_pct": 25.0},
    }
    benchmark = pd.DataFrame({"close": 1000 * np.cumprod(1.0 + np.random.normal(0.0003, 0.008, n_dates))}, index=dates)
    config = StrategyConfig(ticker_universe=tickers, sector_map={"VCB": "Banking"})
    return config, features, ticker_info, benchmark


def test_monte_carlo_result_dataclass():
    result = MonteCarloResult(n_runs=100)
    result.cagr_values = list(np.random.normal(0.12, 0.05, 100))
    result.maxdd_values = list(np.random.normal(-0.15, 0.05, 100))
    result.sharpe_values = list(np.random.normal(1.5, 0.3, 100))
    result.win_rate_values = list(np.random.normal(0.55, 0.05, 100))
    result.profit_factor_values = list(np.random.normal(1.8, 0.3, 100))

    pt = result.percentile_table()
    assert isinstance(pt, pd.DataFrame)
    assert "Metric" in pt.columns
    assert "50%" in pt.columns

    ci = result.ci_90()
    assert "cagr" in ci
    assert "sharpe" in ci
    assert "maxdd" in ci
    assert len(ci["cagr"]) == 2


def test_monte_carlo_simulator_initialization(sample_mc_data):
    config, features, ticker_info, benchmark = sample_mc_data
    from src.backtest.engine import VN100Backtester

    simulator = MonteCarloSimulator(
        backtester_factory=lambda c, fd, ti, bd: VN100Backtester(c, fd, ti, bd),
        config=config,
        features_data=features,
        ticker_info=ticker_info,
        benchmark_data=benchmark,
        n_runs=5,
        random_seed=42,
    )
    assert simulator.n_runs == 5
    assert simulator.random_seed == 42


def test_monte_carlo_run_small(sample_mc_data):
    config, features, ticker_info, benchmark = sample_mc_data
    from src.backtest.engine import VN100Backtester

    simulator = MonteCarloSimulator(
        backtester_factory=lambda c, fd, ti, bd: VN100Backtester(c, fd, ti, bd),
        config=config,
        features_data=features,
        ticker_info=ticker_info,
        benchmark_data=benchmark,
        n_runs=3,
        random_seed=42,
    )
    result = simulator.run(mode="buy_atc_sell_atc")
    assert result.n_runs == 3
    assert len(result.cagr_values) == 3
    assert len(result.sharpe_values) == 3
    assert len(result.maxdd_values) == 3


def test_stress_periods_defined():
    assert "covid_2020" in STRESS_PERIODS
    assert "rate_hike_2022" in STRESS_PERIODS
    assert "vn_correction_2024" in STRESS_PERIODS


def test_stress_test_returns_metrics(sample_mc_data):
    config, features, ticker_info, benchmark = sample_mc_data
    from src.backtest.engine import VN100Backtester

    simulator = MonteCarloSimulator(
        backtester_factory=lambda c, fd, ti, bd: VN100Backtester(c, fd, ti, bd),
        config=config,
        features_data=features,
        ticker_info=ticker_info,
        benchmark_data=benchmark,
        n_runs=2,
    )
    result = simulator.stress_test(mode="buy_atc_sell_atc", period_name="covid_2020")
    assert isinstance(result, dict)
    assert "period" in result
    assert result["period"] == "covid_2020"


def test_simulate_equity_from_trades(sample_mc_data):
    config, features, ticker_info, benchmark = sample_mc_data
    from src.backtest.engine import VN100Backtester

    simulator = MonteCarloSimulator(
        backtester_factory=lambda c, fd, ti, bd: VN100Backtester(c, fd, ti, bd),
        config=config,
        features_data=features,
        ticker_info=ticker_info,
        benchmark_data=benchmark,
    )
    base_bt = VN100Backtester(config, features, ticker_info, benchmark)
    base_result = base_bt.run()
    sim_equity = simulator._simulate_equity_from_trades(base_result.trades, base_result.equity_curve)
    assert isinstance(sim_equity, pd.DataFrame)
    assert "nav" in sim_equity.columns
