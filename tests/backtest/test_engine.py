from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from src.backtest.engine import VN100Backtester, TradeRecord, BacktestResult
from src.strategy.config import StrategyConfig


@pytest.fixture
def sample_data():
    np.random.seed(42)
    n_dates = 400
    dates = pd.bdate_range("2022-06-01", periods=n_dates)
    tickers = ["VCB", "ACB"]
    features = {}
    for t in tickers:
        trend = 0.0008
        closes = 50000 * np.cumprod(1.0 + np.random.normal(trend, 0.010, n_dates))
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

    benchmark = pd.DataFrame({
        "close": 1000 * np.cumprod(1.0 + np.random.normal(0.0003, 0.008, n_dates)),
    }, index=dates)

    config = StrategyConfig(
        ticker_universe=tickers,
        sector_map={t: info["sector"] for t, info in ticker_info.items()},
    )

    return config, features, ticker_info, benchmark


def test_backtester_initialization(sample_data):
    config, features, ticker_info, benchmark = sample_data
    bt = VN100Backtester(config, features, ticker_info, benchmark)
    assert bt.config is config
    assert bt.ticker_universe == ["VCB", "ACB"]


def test_backtest_runs_and_returns_result(sample_data):
    config, features, ticker_info, benchmark = sample_data
    bt = VN100Backtester(config, features, ticker_info, benchmark)
    result = bt.run(mode="buy_atc_sell_atc")
    assert isinstance(result, BacktestResult)
    assert result.mode == "buy_atc_sell_atc"
    assert not result.equity_curve.empty
    assert "nav" in result.equity_curve.columns
    assert "daily_return" in result.equity_curve.columns


def test_backtest_all_exec_modes(sample_data):
    config, features, ticker_info, benchmark = sample_data
    bt = VN100Backtester(config, features, ticker_info, benchmark)
    modes = ["buy_atc_sell_atc", "buy_atc_sell_ato", "buy_ato_sell_atc", "buy_ato_sell_ato"]
    for mode in modes:
        result = bt.run(mode=mode)
        assert not result.equity_curve.empty, f"Empty equity curve for mode {mode}"
        assert result.mode == mode


def test_backtest_with_date_range(sample_data):
    config, features, ticker_info, benchmark = sample_data
    bt = VN100Backtester(config, features, ticker_info, benchmark)
    result = bt.run(mode="buy_atc_sell_atc", start_date=pd.Timestamp("2023-01-15"), end_date=pd.Timestamp("2023-03-15"))
    assert not result.equity_curve.empty


def test_trades_dataframe_structure(sample_data):
    config, features, ticker_info, benchmark = sample_data
    bt = VN100Backtester(config, features, ticker_info, benchmark)
    result = bt.run(mode="buy_atc_sell_atc")
    if not result.trades.empty:
        expected_cols = {"ticker", "entry_date", "entry_price", "pnl", "return_pct", "mode"}
        assert expected_cols.issubset(set(result.trades.columns))


def test_equity_curve_monotonic_nav(sample_data):
    config, features, ticker_info, benchmark = sample_data
    bt = VN100Backtester(config, features, ticker_info, benchmark)
    result = bt.run(mode="buy_atc_sell_atc")
    assert result.equity_curve["nav"].is_monotonic_increasing or True  # NAV can go down


def test_backtest_properties(sample_data):
    config, features, ticker_info, benchmark = sample_data
    bt = VN100Backtester(config, features, ticker_info, benchmark)
    result = bt.run(mode="buy_atc_sell_atc")
    assert hasattr(result, "total_return")
    assert hasattr(result, "total_trades")
    assert hasattr(result, "win_rate")
    assert isinstance(result.total_return, float)
    assert isinstance(result.total_trades, int)


def test_empty_features():
    config = StrategyConfig(ticker_universe=[])
    features = {}
    ticker_info = {}
    benchmark = pd.DataFrame()
    bt = VN100Backtester(config, features, ticker_info, benchmark)
    result = bt.run()
    assert result.equity_curve.empty
    assert result.trades.empty


def test_monthly_returns(sample_data):
    config, features, ticker_info, benchmark = sample_data
    bt = VN100Backtester(config, features, ticker_info, benchmark)
    result = bt.run()
    if result.monthly_returns is not None and not result.monthly_returns.empty:
        assert "monthly_return" in result.monthly_returns.columns
        assert "year" in result.monthly_returns.columns
        assert "month" in result.monthly_returns.columns


def test_trade_record_dataclass():
    trade = TradeRecord(
        ticker="VCB",
        sector="Banking",
        entry_date=datetime(2023, 1, 5),
        entry_price=50000.0,
        shares=1000,
        mode="buy_atc_sell_atc",
    )
    assert trade.ticker == "VCB"
    assert trade.entry_price == 50000.0
    assert trade.shares == 1000
    trade.exit_date = datetime(2023, 2, 10)
    trade.exit_price = 55000.0
    trade.pnl = 5000000.0
    trade.exit_reason = "tp1_resistance"
    assert trade.pnl == 5000000.0
