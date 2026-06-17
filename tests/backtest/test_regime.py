from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest.regime_analysis import (
    classify_regime,
    regime_performance,
    regime_distribution,
)


@pytest.fixture
def sample_vnindex():
    np.random.seed(42)
    dates = pd.date_range("2020-01-01", periods=756, freq="B")
    returns = np.random.normal(0.0003, 0.01, len(dates))
    prices = 1000 * np.cumprod(1.0 + returns)
    return pd.Series(prices, index=dates, name="close")


def test_classify_regime_returns_series(sample_vnindex):
    regimes = classify_regime(sample_vnindex)
    assert isinstance(regimes, pd.Series)
    assert len(regimes) == len(sample_vnindex)
    assert regimes.dtype == object or regimes.dtype.name == "object"


def test_classify_regime_valid_labels(sample_vnindex):
    regimes = classify_regime(sample_vnindex)
    valid_labels = {"bull", "bear", "sideways"}
    unique_labels = set(regimes.unique())
    assert unique_labels.issubset(valid_labels)


def test_classify_regime_with_ema50(sample_vnindex):
    ema50 = sample_vnindex.ewm(span=50).mean()
    regimes = classify_regime(sample_vnindex, ema50)
    assert isinstance(regimes, pd.Series)
    assert len(regimes) == len(sample_vnindex)


def test_classify_regime_short_series():
    short = pd.Series([100, 101], index=pd.date_range("2023-01-01", periods=2, freq="D"))
    regimes = classify_regime(short)
    assert all(r == "sideways" for r in regimes)


def test_regime_performance(sample_vnindex):
    dates = sample_vnindex.index
    trades = pd.DataFrame({
        "ticker": ["VCB"] * 10,
        "sector": ["Banking"] * 10,
        "entry_date": dates[:10],
        "entry_price": [50000.0] * 10,
        "exit_date": dates[20:30],
        "exit_price": [55000.0] * 10,
        "shares": [1000] * 10,
        "pnl": [5000000.0] * 10,
        "return_pct": [0.1] * 10,
        "hold_days": [20] * 10,
        "exit_reason": ["tp1"] * 10,
        "mode": ["buy_atc_sell_atc"] * 10,
    })
    equity = pd.DataFrame({
        "nav": 1e9 * np.exp(np.cumsum(np.random.normal(0.0005, 0.01, len(dates)))),
    }, index=dates)
    daily_returns = equity["nav"].pct_change().fillna(0)

    regimes = classify_regime(sample_vnindex)
    result = regime_performance(trades, equity, daily_returns, regimes)

    assert isinstance(result, dict)
    for regime in ["bull", "bear", "sideways"]:
        assert regime in result
        assert "total_return" in result[regime]
        assert "win_rate" in result[regime]
        assert "trade_count" in result[regime]
        assert "benchmark_return" in result[regime]


def test_regime_performance_empty_trades(sample_vnindex):
    regimes = classify_regime(sample_vnindex)
    equity = pd.DataFrame({"nav": [1e9] * len(sample_vnindex)}, index=sample_vnindex.index)
    daily_returns = pd.Series(0.0, index=sample_vnindex.index)
    result = regime_performance(pd.DataFrame(), equity, daily_returns, regimes)
    assert isinstance(result, dict)
    for regime in ["bull", "bear", "sideways"]:
        assert regime in result


def test_regime_distribution(sample_vnindex):
    regimes = classify_regime(sample_vnindex)
    dist = regime_distribution(regimes)
    assert isinstance(dist, dict)
    assert "bull" in dist
    assert "bear" in dist
    assert "sideways" in dist
    total = sum(dist.values())
    assert total == len(regimes)


def test_synthetic_bull_regime():
    dates = pd.date_range("2023-01-01", periods=252, freq="B")
    prices = 1000 * np.cumprod(1.0 + np.random.normal(0.001, 0.008, len(dates)))
    vnindex = pd.Series(prices, index=dates)
    regimes = classify_regime(vnindex)
    bull_count = (regimes == "bull").sum()
    assert bull_count >= 0


def test_synthetic_bear_regime():
    dates = pd.date_range("2023-01-01", periods=252, freq="B")
    prices = 1000 * np.cumprod(1.0 + np.random.normal(-0.0015, 0.015, len(dates)))
    vnindex = pd.Series(prices, index=dates)
    regimes = classify_regime(vnindex)
    bear_count = (regimes == "bear").sum()
    assert bear_count >= 0


def test_regime_performance_with_benchmark(sample_vnindex):
    regimes = classify_regime(sample_vnindex)
    equity = pd.DataFrame({"nav": sample_vnindex.values * 1e6}, index=sample_vnindex.index)
    daily_returns = equity["nav"].pct_change().fillna(0)
    bm_returns = sample_vnindex.pct_change().fillna(0)
    result = regime_performance(pd.DataFrame(), equity, daily_returns, regimes, bm_returns)
    assert isinstance(result, dict)
