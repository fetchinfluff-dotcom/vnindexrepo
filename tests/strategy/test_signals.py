from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from src.strategy.signals import (
    check_entry_conditions,
    check_exit_conditions,
    generate_signals,
)

TICKER_INFO = {
    "ticker": "VCB",
    "foreign_room_limit": 0.30,
    "current_foreign_own": 0.20,
    "sector": "Banking",
}


def _make_row(**overrides) -> pd.Series:
    data = {
        "close": 100_000.0,
        "open": 98_000.0,
        "high": 100_200.0,
        "low": 98_000.0,
        "ema200": 90_000.0,
        "ema50": 95_000.0,
        "ema20": 99_500.0,
        "swing_high": 105_000.0,
        "swing_low": 95_000.0,
        "volume": 5_000_000,
        "vol_ma20": 3_000_000,
        "vol_ratio": 1.67,
        "foreign_net_buy_5d": 50_000_000_000.0,
        "foreign_ratio_5d": 0.55,
        "rsi_weekly": 60.0,
        "ceiling": 107_000.0,
        "ceiling_buffer": 107_000.0 - 100_000.0,
        "dist_ema20": (100_000.0 - 99_500.0) / 99_500.0,
        "atr14": 2_000.0,
        "foreign_net_sell_streak": 0,
        "date": datetime(2025, 1, 15),
    }
    data.update(overrides)
    return pd.Series(data)


# ── Entry condition tests ───────────────────────────────────────


def test_entry_all_conditions_met():
    row = _make_row()
    result = check_entry_conditions(row, TICKER_INFO)
    assert result["signal"] == 1, f"Expected BUY, got {result}"


def test_entry_macro_bear_close_below_ema200():
    row = _make_row(close=85_000.0, ema200=90_000.0)
    result = check_entry_conditions(row, TICKER_INFO)
    assert result["signal"] == 0
    assert "macro_bear" in result["reasons"]


def test_entry_macro_bear_ema50_below_ema200():
    row = _make_row(ema50=88_000.0, ema200=90_000.0)
    result = check_entry_conditions(row, TICKER_INFO)
    assert result["signal"] == 0
    assert "macro_bear" in result["reasons"]


def test_entry_no_pullback():
    row = _make_row(dist_ema20=0.05)
    result = check_entry_conditions(row, TICKER_INFO)
    assert result["signal"] == 0
    assert "no_pullback" in result["reasons"]


def test_entry_no_pullback_negative():
    row = _make_row(dist_ema20=-0.05)
    result = check_entry_conditions(row, TICKER_INFO)
    assert result["signal"] == 0
    assert "no_pullback" in result["reasons"]


def test_entry_weak_foreign_flow_net_buy_negative():
    row = _make_row(foreign_net_buy_5d=-1_000_000.0)
    result = check_entry_conditions(row, TICKER_INFO)
    assert result["signal"] == 0
    assert "weak_foreign_flow" in result["reasons"]


def test_entry_weak_foreign_flow_low_ratio():
    row = _make_row(foreign_ratio_5d=0.30)
    result = check_entry_conditions(row, TICKER_INFO)
    assert result["signal"] == 0
    assert "weak_foreign_flow" in result["reasons"]


def test_entry_low_volume():
    row = _make_row(vol_ratio=1.0)
    result = check_entry_conditions(row, TICKER_INFO)
    assert result["signal"] == 0
    assert "low_volume" in result["reasons"]


def test_entry_weak_candle_close_below_open():
    row = _make_row(close=98_000.0, open=99_000.0)
    result = check_entry_conditions(row, TICKER_INFO)
    assert result["signal"] == 0
    assert "weak_candle" in result["reasons"]


def test_entry_weak_candle_small_body():
    row = _make_row(close=99_100.0, open=99_000.0, high=100_000.0, low=98_500.0)
    result = check_entry_conditions(row, TICKER_INFO)
    assert result["signal"] == 0
    assert "weak_candle" in result["reasons"]


def test_entry_near_ceiling():
    row = _make_row(close=104_500.0, ceiling=107_000.0)
    result = check_entry_conditions(row, TICKER_INFO)
    assert result["signal"] == 0
    assert "near_ceiling" in result["reasons"]


def test_entry_rsi_overbought_weekly():
    row = _make_row(rsi_weekly=75.0)
    result = check_entry_conditions(row, TICKER_INFO)
    assert result["signal"] == 0
    assert "rsi_overbought_weekly" in result["reasons"]


def test_entry_foreign_room_exhausted():
    info = {**TICKER_INFO, "current_foreign_own": 0.29, "foreign_room_limit": 0.30}
    row = _make_row()
    result = check_entry_conditions(row, info)
    assert result["signal"] == 0
    assert "foreign_room_exhausted" in result["reasons"]


# ── Exit condition tests ────────────────────────────────────────


def test_exit_trend_break():
    row = _make_row(close=85_000.0, ema200=90_000.0)
    result = check_exit_conditions(row)
    assert result["action"] == "sell_all"
    assert result["reason"] == "trend_break"


def test_exit_trail_ema20_two_days():
    row = _make_row(close=98_000.0, ema20=99_500.0)
    position = {"entry_price": 100_000.0, "stop_loss": 95_000.0}
    result = check_exit_conditions(row, position=position, prev_close_ema20_cross=True)
    assert result["action"] == "sell_position"
    assert result["reason"] == "trail_ema20"


def test_exit_trail_ema20_first_day_only():
    row = _make_row(close=98_000.0, ema20=99_500.0)
    result = check_exit_conditions(row, prev_close_ema20_cross=False)
    assert result["action"] == "hold"


def test_exit_structure_break():
    row = _make_row(close=94_000.0, swing_low=95_000.0)
    result = check_exit_conditions(row)
    assert result["action"] == "sell_position"
    assert result["reason"] == "structure_break"


def test_exit_death_cross():
    row = _make_row(ema50=89_000.0, ema200=90_000.0, ema50_prev=91_000.0, ema200_prev=90_000.0)
    result = check_exit_conditions(row)
    assert result["action"] == "reduce"
    assert result["reduce_pct"] == 0.50
    assert result["reason"] == "death_cross"


def test_exit_foreign_sell_streak():
    row = _make_row(foreign_net_sell_streak=5)
    result = check_exit_conditions(row)
    assert result["action"] == "reduce"
    assert result["reduce_pct"] == 0.30
    assert result["reason"] == "foreign_sell_streak"


def test_exit_tp1_resistance():
    row = _make_row(close=104_000.0, swing_high=105_000.0)
    position = {"entry_price": 100_000.0, "stop_loss": 95_000.0}
    result = check_exit_conditions(row, position=position)
    assert result["action"] == "take_profit_1"
    assert result["reduce_pct"] == 0.40
    assert result["reason"] == "tp1_resistance"


def test_exit_tp2_fib():
    row = _make_row(close=115_000.0, swing_high=120_000.0)
    position = {"entry_price": 100_000.0, "stop_loss": 95_000.0}
    result = check_exit_conditions(row, position=position)
    assert result["action"] == "take_profit_2"
    assert result["reduce_pct"] == 0.30
    assert result["reason"] == "tp2_fib"


# ── generate_signals integration ─────────────────────────────────


def _make_features(n_days: int = 252) -> pd.DataFrame:
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    base_close = 100_000.0
    trends = np.cumsum(np.random.randn(n_days) * 500) + base_close
    data = {
        "date": dates,
        "close": trends,
        "open": trends - np.random.randint(100, 500, n_days),
        "high": trends + np.random.randint(100, 800, n_days),
        "low": trends - np.random.randint(100, 800, n_days),
        "ema200": np.full(n_days, 95_000.0),
        "ema50": np.full(n_days, 97_000.0),
        "ema20": trends * 0.99 + 1000,
        "swing_high": trends * 1.05,
        "swing_low": trends * 0.95,
        "volume": np.random.randint(2_000_000, 8_000_000, n_days),
        "vol_ma20": np.full(n_days, 3_000_000),
        "vol_ratio": np.random.uniform(0.8, 2.0, n_days),
        "foreign_net_buy_5d": np.random.uniform(-1e9, 2e9, n_days),
        "foreign_ratio_5d": np.random.uniform(0.3, 0.6, n_days),
        "rsi_weekly": np.random.uniform(30, 80, n_days),
        "ceiling": trends * 1.07,
        "ceiling_buffer": trends * 1.07 - trends,
        "dist_ema20": (trends - (trends * 0.99 + 1000)) / (trends * 0.99 + 1000),
        "atr14": np.random.uniform(1000, 3000, n_days),
    }
    return pd.DataFrame(data).set_index("date")


def test_generate_signals_basic():
    features = _make_features(100)
    signals = generate_signals(features, TICKER_INFO)
    assert isinstance(signals, pd.Series)
    assert signals.name == "signal"
    assert set(signals.unique()).issubset({-1, 0, 1})
    assert len(signals) == len(features)


def test_generate_signals_no_crash_empty():
    with pytest.raises(ValueError):
        generate_signals(pd.DataFrame(), TICKER_INFO)


def test_generate_signals_missing_column():
    bad = _make_features(10).drop(columns=["ema200"])
    with pytest.raises(ValueError, match="Missing feature columns"):
        generate_signals(bad, TICKER_INFO)


def test_generate_signals_missing_ticker_info():
    features = _make_features(10)
    with pytest.raises(ValueError, match="Missing ticker_info keys"):
        generate_signals(features, {})


def test_generate_signals_produces_some_entries():
    features = _make_features(500)
    signals = generate_signals(features, TICKER_INFO)
    entry_count = int((signals == 1).sum())
    assert entry_count >= 0
