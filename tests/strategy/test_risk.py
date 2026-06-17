from __future__ import annotations

from typing import Any, Dict

import pytest

from src.strategy.risk import (
    calculate_position_risk,
    calculate_stop_loss,
    calculate_take_profit_levels,
)


def test_stop_loss_swing_low_is_lowest():
    entry = 100_000.0
    ticker_data = {"swing_low": 90_000.0, "ema20": 95_000.0}
    sl = calculate_stop_loss(entry, ticker_data)
    # swing_low 90k < ema20 95k < fixed 92k → 90k
    assert sl == 90_000.0


def test_stop_loss_ema20_is_lowest():
    entry = 100_000.0
    ticker_data = {"swing_low": 93_000.0, "ema20": 91_000.0}
    sl = calculate_stop_loss(entry, ticker_data)
    assert sl == 91_000.0


def test_stop_loss_fixed_is_lowest():
    entry = 100_000.0
    ticker_data = {"swing_low": 97_000.0, "ema20": 96_000.0}
    sl = calculate_stop_loss(entry, ticker_data)
    # Fixed: 100k * 0.92 = 92k < 96k ema20 < 97k swing_low
    assert sl == 92_000.0


def test_stop_loss_no_swing_low():
    entry = 100_000.0
    ticker_data = {"ema20": 91_000.0}
    sl = calculate_stop_loss(entry, ticker_data)
    # candidates: [92000 (fixed), 91000 (ema20)]
    assert sl == 91_000.0


def test_stop_loss_no_ema20():
    entry = 100_000.0
    ticker_data = {"swing_low": 93_000.0}
    sl = calculate_stop_loss(entry, ticker_data)
    assert sl == 92_000.0  # fixed 92k < swing_low 93k


def test_stop_loss_empty_data():
    entry = 100_000.0
    sl = calculate_stop_loss(entry, {})
    assert sl == 92_000.0  # default fallback


def test_stop_loss_custom_max_loss():
    entry = 100_000.0
    sl = calculate_stop_loss(entry, {}, params={"max_loss_pct": 0.95})
    assert sl == 95_000.0


def test_take_profit_swing_high_level():
    entry = 100_000.0
    sl = 92_000.0
    ticker_data = {"swing_high": 108_000.0}
    levels = calculate_take_profit_levels(entry, sl, ticker_data)
    assert len(levels) == 3
    assert levels[0]["level"] == 1
    assert levels[0]["price"] == 108_000.0
    assert levels[0]["reduce_pct"] == 0.40
    assert levels[0]["reason"] == "tp1_resistance"


def test_take_profit_fib_level():
    entry = 100_000.0
    sl = 92_000.0
    ticker_data = {"swing_high": 108_000.0}
    levels = calculate_take_profit_levels(entry, sl, ticker_data)
    # 2.5R = 2.5 * (100k - 92k) = 20k → entry + 20k = 120k
    assert levels[1]["level"] == 2
    assert levels[1]["price"] == 120_000.0
    assert levels[1]["reduce_pct"] == 0.30
    assert levels[1]["reason"] == "tp2_fib"


def test_take_profit_trail_level():
    entry = 100_000.0
    sl = 92_000.0
    levels = calculate_take_profit_levels(entry, sl, None)
    assert len(levels) == 2  # no swing_high → only fib + trail
    assert levels[-1]["method"] == "ema20_trail"
    assert levels[-1]["reduce_pct"] == 0.30


def test_take_profit_no_data():
    entry = 100_000.0
    sl = 92_000.0
    levels = calculate_take_profit_levels(entry, sl)
    assert len(levels) == 2
    assert levels[0]["method"] == "fib_2.5r"
    assert levels[0]["price"] == 120_000.0


def test_position_risk_basic():
    entry = 100_000.0
    sl = 92_000.0
    qty = 1000
    result = calculate_position_risk(entry, sl, qty, 1_000_000_000.0)
    assert result["risk_per_share"] == 8_000.0
    assert result["total_risk"] == 8_000_000.0
    assert result["risk_pct"] == 0.8


def test_position_risk_zero_portfolio():
    result = calculate_position_risk(100_000.0, 92_000.0, 100, 0.0)
    assert result["risk_pct"] == 0.0


def test_position_risk_zero_quantity():
    result = calculate_position_risk(100_000.0, 92_000.0, 0, 1_000_000_000.0)
    assert result["total_risk"] == 0.0
