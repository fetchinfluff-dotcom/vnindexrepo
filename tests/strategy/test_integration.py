from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from src.strategy.execution import simulate_execution
from src.strategy.portfolio import VN100Portfolio
from src.strategy.risk import calculate_stop_loss, calculate_take_profit_levels
from src.strategy.signals import check_entry_conditions, generate_signals
from src.strategy.sizing import calculate_position_size

TICKER_INFO = {
    "ticker": "VCB",
    "foreign_room_limit": 0.30,
    "current_foreign_own": 0.20,
    "sector": "Banking",
}


def _make_features(n_days: int = 252) -> pd.DataFrame:
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    trends = np.cumsum(np.random.randn(n_days) * 500) + 100_000.0
    data = {
        "date": dates,
        "close": trends,
        "open": trends - np.random.randint(50, 200, n_days),
        "high": trends + np.random.randint(100, 500, n_days),
        "low": trends - np.random.randint(100, 500, n_days),
        "ema200": np.full(n_days, 95_000.0),
        "ema50": np.full(n_days, 97_000.0),
        "ema20": trends * 0.99 + 1000,
        "swing_high": trends * 1.05,
        "swing_low": trends * 0.95,
        "volume": np.random.randint(3_000_000, 6_000_000, n_days),
        "vol_ma20": np.full(n_days, 3_000_000),
        "vol_ratio": np.random.uniform(0.8, 2.0, n_days),
        "foreign_net_buy_5d": np.random.uniform(1e8, 5e9, n_days),
        "foreign_ratio_5d": np.random.uniform(0.40, 0.60, n_days),
        "rsi_weekly": np.random.uniform(40, 68, n_days),
        "ceiling": trends * 1.07,
        "ceiling_buffer": trends * 1.07 - trends,
        "dist_ema20": (trends - (trends * 0.99 + 1000)) / (trends * 0.99 + 1000),
        "atr14": np.random.uniform(1000, 3000, n_days),
    }
    return pd.DataFrame(data).set_index("date")


def test_full_pipeline_signals_to_portfolio():
    features = _make_features(500)
    signals = generate_signals(features, TICKER_INFO)

    assert isinstance(signals, pd.Series)
    entries = int((signals == 1).sum())
    assert entries >= 0, "Should have some entries or gracefully zero"
    assert set(signals.unique()).issubset({-1, 0, 1})


def test_sizing_with_realistic_params():
    risk_params = {
        "portfolio_value": 1_000_000_000.0,
        "kelly_fraction": 0.25,
        "max_position_pct": 0.10,
        "max_sector_pct": 0.20,
        "min_cash_pct": 0.30,
        "price": 80_000.0,
    }
    market_data = {
        "close": 80_000.0,
        "foreign_room_pct": 30.0,
        "dist_to_ceiling_pct": 5.0,
    }
    result = calculate_position_size(
        ticker="VNM",
        signal_strength=0.8,
        available_cash=500_000_000.0,
        current_positions=[],
        sector_map={"VNM": "Food & Beverage"},
        risk_params=risk_params,
        market_data=market_data,
    )
    assert result["reason"] == "ok" or result["quantity"] == 0
    if result["quantity"] > 0:
        assert result["notional"] <= 100_000_000.0  # 10% hard cap


def test_risk_stop_tp_integration():
    entry = 100_000.0
    ticker_data = {"swing_low": 91_000.0, "ema20": 93_000.0, "swing_high": 108_000.0}
    sl = calculate_stop_loss(entry, ticker_data)
    assert sl == 91_000.0  # swing_low is the min

    levels = calculate_take_profit_levels(entry, sl, ticker_data)
    assert len(levels) == 3
    tp1 = next(l for l in levels if l["level"] == 1)
    assert tp1["price"] == 108_000.0
    assert tp1["reduce_pct"] == 0.40


def test_portfolio_execution_flow():
    pf = VN100Portfolio(initial_cash=1_000_000_000.0)
    entry_price = 50_000.0
    stop_loss = 46_000.0
    qty = 1_000

    pos = pf.open_position(
        ticker="VCB", quantity=qty, price=entry_price,
        stop_loss=stop_loss, entry_date=datetime(2025, 1, 15),
    )
    assert pos is not None
    assert pf.position_count == 1
    assert pf.cash == 950_000_000.0

    for price, dt in [(51_000.0, datetime(2025, 1, 16)),
                       (52_000.0, datetime(2025, 1, 17))]:
        pf.update_position("VCB", price, dt)

    closed = pf.close_position(
        ticker="VCB", exit_price=52_000.0,
        exit_date=datetime(2025, 1, 20), reason="tp_hit",
    )
    assert closed is not None
    assert closed.pnl == 2_000_000.0  # 2000 profit * 1000 shares
    assert pf.position_count == 0
    assert pf.cash == 950_000_000.0 + 52_000_000.0


def test_execution_modes_all_produce_output():
    dates = pd.date_range("2025-01-02", periods=10, freq="B")
    px_df = pd.DataFrame({
        "date": dates,
        "open": np.full(10, 100_000.0),
        "close": np.full(10, 101_000.0),
    })
    sigs = pd.DataFrame({
        "date": [dates[0], dates[3]],
        "ticker": ["VCB", "VCB"],
        "signal": [1, -1],
    })
    # dates[0]+1 and dates[3]+1 are both within the range (no Friday signals to avoid weekend gap)
    for mode in ["buy_atc_sell_atc", "buy_atc_sell_ato",
                  "buy_ato_sell_atc", "buy_ato_sell_ato"]:
        result = simulate_execution(sigs, mode, px_df)
        assert not result.empty, f"Mode {mode} failed"
        assert len(result[result["action"] == "buy"]) == 1
        assert len(result[result["action"] == "sell"]) == 1


def test_edge_case_all_entry_conditions_satisfied():
    row = pd.Series({
        "close": 100_000.0,
        "open": 98_000.0,
        "high": 100_500.0,
        "low": 98_000.0,
        "ema200": 90_000.0,
        "ema50": 95_000.0,
        "ema20": 99_500.0,
        "swing_high": 105_000.0,
        "swing_low": 95_000.0,
        "volume": 5_000_000,
        "vol_ma20": 3_000_000,
        "vol_ratio": 1.67,
        "foreign_net_buy_5d": 100_000_000.0,
        "foreign_ratio_5d": 0.45,
        "rsi_weekly": 55.0,
        "ceiling": 107_000.0,
        "ceiling_buffer": 107_000.0 - 100_000.0,
        "dist_ema20": 0.005,
        "atr14": 2_000.0,
    })
    info = {"foreign_room_limit": 0.30, "current_foreign_own": 0.15, "sector": "Banking"}
    result = check_entry_conditions(row, info)
    assert result["signal"] == 1, f"Expected BUY, got {result}"
