from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from src.strategy.execution import (
    ExecMode,
    compute_execution_stats,
    simulate_execution,
)


def _price_df() -> pd.DataFrame:
    dates = pd.date_range("2025-01-02", periods=20, freq="B")
    np.random.seed(42)
    return pd.DataFrame({
        "date": dates,
        "open": np.random.uniform(95_000, 105_000, len(dates)),
        "close": np.random.uniform(96_000, 106_000, len(dates)),
        "high": np.random.uniform(100_000, 110_000, len(dates)),
        "low": np.random.uniform(93_000, 99_000, len(dates)),
    }).set_index("date")


def _signal_df(buy_dates, sell_dates) -> pd.DataFrame:
    rows = []
    for d in buy_dates:
        rows.append({"date": d, "ticker": "VCB", "signal": 1})
    for d in sell_dates:
        rows.append({"date": d, "ticker": "VCB", "signal": -1})
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def test_exec_mode_values():
    assert ExecMode.BUY_ATC_SELL_ATC.value == "buy_atc_sell_atc"
    assert ExecMode.BUY_ATC_SELL_ATO.value == "buy_atc_sell_ato"
    assert ExecMode.BUY_ATO_SELL_ATC.value == "buy_ato_sell_atc"
    assert ExecMode.BUY_ATO_SELL_ATO.value == "buy_ato_sell_ato"


def test_simulate_empty_signal():
    result = simulate_execution(
        pd.DataFrame(columns=["date", "ticker", "signal"]),
        "buy_atc_sell_atc",
        _price_df(),
    )
    assert result.empty


def test_simulate_buy_atc_sell_atc():
    dates = _price_df().index[:5]
    sigs = _signal_df(buy_dates=[dates[0]], sell_dates=[dates[3]])
    px_df = _price_df().reset_index()
    result = simulate_execution(sigs, "buy_atc_sell_atc", px_df)
    assert not result.empty
    assert len(result) >= 1  # at least buy, maybe sell
    buy = result[result["action"] == "buy"]
    if not buy.empty:
        assert "exec_date" in buy.columns
        assert buy.iloc[0]["mode"] == "buy_atc_sell_atc"


def test_all_four_modes_run():
    dates = pd.date_range("2025-01-02", periods=10, freq="B")
    px_df = pd.DataFrame({
        "date": dates,
        "open": np.full(len(dates), 100_000.0),
        "close": np.full(len(dates), 101_000.0),
    })
    sigs = pd.DataFrame({
        "date": [dates[1], dates[5]],
        "ticker": ["VCB", "VCB"],
        "signal": [1, -1],
    })
    for mode in ["buy_atc_sell_atc", "buy_atc_sell_ato", "buy_ato_sell_atc", "buy_ato_sell_ato"]:
        result = simulate_execution(sigs, mode, px_df)
        assert not result.empty, f"Mode {mode} produced empty results"
        assert "fill_price" in result.columns
        assert result["fill_price"].iloc[0] > 0


def test_execution_slippage_direction():
    dates = pd.date_range("2025-01-02", periods=5, freq="B")
    px_df = pd.DataFrame({
        "date": dates,
        "open": [100_000.0] * 5,
        "close": [101_000.0] * 5,
    })
    sigs = pd.DataFrame({
        "date": [dates[1]],
        "ticker": ["VCB"],
        "signal": [1],
    })
    atc_result = simulate_execution(sigs, "buy_atc_sell_atc", px_df)
    ato_result = simulate_execution(sigs, "buy_ato_sell_atc", px_df)
    if not atc_result.empty and not ato_result.empty:
        atc_fill = atc_result[atc_result["action"] == "buy"]["fill_price"].iloc[0]
        ato_fill = ato_result[ato_result["action"] == "buy"]["fill_price"].iloc[0]
        # ATC = close * 1.0005, ATO = open * 1.001
        expected_atc = round(101_000.0 * 1.0005, 2)
        expected_ato = round(100_000.0 * 1.001, 2)
        assert atc_fill == expected_atc
        assert ato_fill == expected_ato


def test_missing_price_data_skips():
    dates = pd.date_range("2025-01-02", periods=3, freq="B")
    px_df = pd.DataFrame({
        "date": [dates[0]],
        "open": [100_000.0],
        "close": [101_000.0],
    })
    sigs = pd.DataFrame({
        "date": [dates[1]],
        "ticker": ["VCB"],
        "signal": [1],
    })
    result = simulate_execution(sigs, "buy_atc_sell_atc", px_df)
    assert result.empty  # no next-day price for dates[1]


def test_compute_stats():
    df = pd.DataFrame({
        "action": ["buy", "sell"],
        "fill_price": [100_000.0, 105_000.0],
        "signal_date": [datetime(2025, 1, 2), datetime(2025, 1, 10)],
        "exec_date": [datetime(2025, 1, 3), datetime(2025, 1, 11)],
        "ticker": ["VCB", "VCB"],
        "signal": [1, -1],
        "mode": ["buy_atc_sell_atc", "buy_atc_sell_atc"],
    })
    stats = compute_execution_stats(df)
    assert stats["total_fills"] == 2
    assert stats["buys"] == 1
    assert stats["sells"] == 1


def test_compute_stats_empty():
    assert compute_execution_stats(pd.DataFrame()) == {"total_fills": 0}


def test_missing_close_or_open_raises():
    dates = pd.date_range("2025-01-02", periods=5, freq="B")
    px_df = pd.DataFrame({"date": dates, "close": np.full(5, 100_000.0)})
    sigs = pd.DataFrame({
        "date": [dates[1]],
        "ticker": ["VCB"],
        "signal": [1],
    })
    with pytest.raises(ValueError, match="price_df must have 'open' and 'close' columns"):
        simulate_execution(sigs, "buy_atc_sell_atc", px_df)


def test_missing_signal_columns_raises():
    dates = pd.date_range("2025-01-02", periods=5, freq="B")
    px_df = pd.DataFrame({"date": dates, "open": np.full(5, 100_000.0), "close": np.full(5, 101_000.0)})
    bad_sig = pd.DataFrame({"date": [dates[1]], "ticker": ["VCB"]})  # no signal column
    with pytest.raises(ValueError, match="signal_df missing column"):
        simulate_execution(bad_sig, "buy_atc_sell_atc", px_df)
