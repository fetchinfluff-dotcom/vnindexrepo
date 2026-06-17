from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from src.backtest.walkforward import WalkForwardOptimizer, PARAM_GRID, WindowResult
from src.strategy.config import StrategyConfig


@pytest.fixture
def sample_data_wf():
    np.random.seed(42)
    n_dates = 600
    dates = pd.bdate_range("2020-01-02", periods=n_dates)
    tickers = ["VCB", "ACB"]
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
                "current_foreign_own": 0.15, "foreign_room_pct": 20.0},
        "ACB": {"ticker": "ACB", "sector": "Banking", "foreign_room_limit": 0.3,
                "current_foreign_own": 0.15, "foreign_room_pct": 20.0},
    }
    benchmark = pd.DataFrame({"close": 1000 * np.cumprod(1.0 + np.random.normal(0.0003, 0.008, n_dates))}, index=dates)
    config = StrategyConfig(ticker_universe=tickers, sector_map={t: info["sector"] for t, info in ticker_info.items()})
    return config, features, ticker_info, benchmark


def test_param_grid_structure():
    assert "pullback_threshold" in PARAM_GRID
    assert "volume_ratio_min" in PARAM_GRID
    assert "max_loss_pct" in PARAM_GRID
    assert "weekly_rsi_max" in PARAM_GRID
    assert "foreign_ratio_min" in PARAM_GRID


def test_window_result_dataclass():
    wr = WindowResult(
        window_idx=0,
        train_start=datetime(2020, 1, 1),
        train_end=datetime(2021, 12, 31),
        test_start=datetime(2022, 1, 1),
        test_end=datetime(2022, 6, 30),
        best_params={"pullback_threshold": 0.01},
        is_sharpe=1.5,
        oos_sharpe=1.2,
        is_return=0.25,
        oos_return=0.18,
        is_maxdd=-0.12,
        oos_maxdd=-0.10,
        is_win_rate=0.55,
        oos_win_rate=0.52,
    )
    assert wr.window_idx == 0
    assert wr.is_sharpe == 1.5
    assert wr.oos_sharpe == 1.2


def test_walkforward_initialization(sample_data_wf):
    config, features, ticker_info, benchmark = sample_data_wf
    from src.backtest.engine import VN100Backtester

    optimizer = WalkForwardOptimizer(
        backtester_factory=lambda c, fd, ti, bd: VN100Backtester(c, fd, ti, bd),
        config=config,
        features_data=features,
        ticker_info=ticker_info,
        benchmark_data=benchmark,
    )
    assert optimizer.param_grid is not None
    assert "pullback_threshold" in optimizer.param_grid


def test_walkforward_optimize_small(sample_data_wf):
    config, features, ticker_info, benchmark = sample_data_wf
    from src.backtest.engine import VN100Backtester

    optimizer = WalkForwardOptimizer(
        backtester_factory=lambda c, fd, ti, bd: VN100Backtester(c, fd, ti, bd),
        config=config,
        features_data=features,
        ticker_info=ticker_info,
        benchmark_data=benchmark,
        param_grid={"pullback_threshold": [0.01], "volume_ratio_min": [1.2]},
    )
    results, summary_df = optimizer.optimize(
        mode="buy_atc_sell_atc",
        train_months=12,
        test_months=3,
        roll_months=6,
        embargo_days=2,
    )
    assert isinstance(results, list)
    assert isinstance(summary_df, pd.DataFrame)


def test_walkforward_is_oos_ratio(sample_data_wf):
    config, features, ticker_info, benchmark = sample_data_wf
    from src.backtest.engine import VN100Backtester

    optimizer = WalkForwardOptimizer(
        backtester_factory=lambda c, fd, ti, bd: VN100Backtester(c, fd, ti, bd),
        config=config,
        features_data=features,
        ticker_info=ticker_info,
        benchmark_data=benchmark,
        param_grid={"pullback_threshold": [0.01]},
    )
    results, _ = optimizer.optimize(
        mode="buy_atc_sell_atc",
        train_months=12,
        test_months=3,
        roll_months=6,
        embargo_days=2,
    )
    ratio = optimizer._compute_is_oos_ratio(results)
    assert isinstance(ratio, float)
    assert ratio >= 0.0


def test_add_months():
    dt = datetime(2023, 1, 15)
    result = WalkForwardOptimizer._add_months(dt, 3)
    assert result.month == 4
    assert result.year == 2023
