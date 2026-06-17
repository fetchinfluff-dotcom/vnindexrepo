from __future__ import annotations

from typing import Any, Dict, List

import pytest

from src.strategy.sizing import calculate_position_size


def _default_risk_params(**overrides) -> Dict[str, Any]:
    params = {
        "portfolio_value": 1_000_000_000.0,
        "kelly_fraction": 0.25,
        "max_position_pct": 0.10,
        "max_sector_pct": 0.20,
        "min_cash_pct": 0.30,
        "price": 50_000.0,
    }
    params.update(overrides)
    return params


def _default_market_data(**overrides) -> Dict[str, Any]:
    data = {
        "close": 50_000.0,
        "foreign_room_pct": 50.0,
        "dist_to_ceiling_pct": 10.0,
    }
    data.update(overrides)
    return data


def test_basic_position_size():
    result = calculate_position_size(
        ticker="VCB",
        signal_strength=1.0,
        available_cash=500_000_000.0,
        current_positions=[],
        sector_map={"VCB": "Banking"},
        risk_params=_default_risk_params(),
        market_data=_default_market_data(),
    )
    assert result["reason"] == "ok"
    assert result["quantity"] > 0
    assert result["notional"] > 0
    assert result["ticker"] == "VCB"


def test_hard_cap_respected():
    params = _default_risk_params(portfolio_value=1_000_000_000.0, max_position_pct=0.10)
    result = calculate_position_size(
        ticker="VCB",
        signal_strength=1.0,
        available_cash=1_000_000_000.0,
        current_positions=[],
        sector_map={"VCB": "Banking"},
        risk_params=params,
        market_data=_default_market_data(),
    )
    max_notional = 1_000_000_000.0 * 0.10
    assert result["notional"] <= max_notional, f"{result['notional']} > {max_notional}"


def test_sector_cap_rejects():
    params = _default_risk_params(max_sector_pct=0.20)
    existing = [
        {"ticker": "CTG", "notional": 300_000_000.0},
    ]
    sector_map = {"VCB": "Banking", "CTG": "Banking"}
    result = calculate_position_size(
        ticker="VCB",
        signal_strength=1.0,
        available_cash=500_000_000.0,
        current_positions=existing,
        sector_map=sector_map,
        risk_params=params,
        market_data=_default_market_data(),
    )
    portfolio_value = params["portfolio_value"]
    max_sector = portfolio_value * 0.20
    # Existing sector value = 300M, max sector = 200M, already exceeded
    assert result["reason"].startswith("sector_cap_reached"), f"Got {result['reason']}"
    assert result["quantity"] == 0


def test_cash_reserve_respected():
    params = _default_risk_params(min_cash_pct=0.30, portfolio_value=1_000_000_000.0)
    result = calculate_position_size(
        ticker="VCB",
        signal_strength=1.0,
        available_cash=500_000_000.0,
        current_positions=[{"ticker": "HPG", "notional": 500_000_000.0, "ticker_sector": "Steel"}],
        sector_map={"VCB": "Banking", "HPG": "Steel"},
        risk_params=params,
        market_data=_default_market_data(),
    )
    # 500M cash - position must leave at least 30% of 1B = 300M
    # If position is > 200M, it would violate cash reserve
    if result["quantity"] > 0:
        assert (result["notional"] <= 200_000_000.0) or ("cash_reserve" in result.get("reduced_by", {}))


def test_foreign_room_reduces_size():
    md = _default_market_data(foreign_room_pct=7.0)
    result = calculate_position_size(
        ticker="VCB",
        signal_strength=1.0,
        available_cash=500_000_000.0,
        current_positions=[],
        sector_map={"VCB": "Banking"},
        risk_params=_default_risk_params(),
        market_data=md,
    )
    assert "foreign_room" in result.get("reduced_by", {})


def test_foreign_room_blocks_trade():
    md = _default_market_data(foreign_room_pct=3.0)
    result = calculate_position_size(
        ticker="VCB",
        signal_strength=1.0,
        available_cash=500_000_000.0,
        current_positions=[],
        sector_map={"VCB": "Banking"},
        risk_params=_default_risk_params(),
        market_data=md,
    )
    assert result["reason"] == "foreign_room_exhausted"
    assert result["quantity"] == 0


def test_ceiling_buffer_reduces_size():
    md = _default_market_data(dist_to_ceiling_pct=1.0)
    result = calculate_position_size(
        ticker="VCB",
        signal_strength=1.0,
        available_cash=500_000_000.0,
        current_positions=[],
        sector_map={"VCB": "Banking"},
        risk_params=_default_risk_params(),
        market_data=md,
    )
    assert "ceiling_buffer" in result.get("reduced_by", {})


def test_sector_open_interest_reduces():
    result = calculate_position_size(
        ticker="VCB",
        signal_strength=1.0,
        available_cash=500_000_000.0,
        current_positions=[{"ticker": "CTG", "notional": 100_000_000.0}],
        sector_map={"VCB": "Banking", "CTG": "Banking"},
        risk_params=_default_risk_params(),
        market_data=_default_market_data(),
    )
    assert "sector_open_interest" in result.get("reduced_by", {})
    assert result["quantity"] > 0


def test_zero_signal_strength():
    result = calculate_position_size(
        ticker="VCB",
        signal_strength=0.0,
        available_cash=500_000_000.0,
        current_positions=[],
        sector_map={"VCB": "Banking"},
        risk_params=_default_risk_params(),
        market_data=_default_market_data(),
    )
    assert result["quantity"] == 0


def test_zero_price():
    params = _default_risk_params(price=0.0)
    result = calculate_position_size(
        ticker="VCB",
        signal_strength=1.0,
        available_cash=500_000_000.0,
        current_positions=[],
        sector_map={"VCB": "Banking"},
        risk_params=params,
        market_data=_default_market_data(close=0),
    )
    assert result["quantity"] == 0
    assert result["reason"] == "invalid_price"


def test_signal_strength_scaling():
    full = calculate_position_size(
        ticker="VCB",
        signal_strength=1.0,
        available_cash=500_000_000.0,
        current_positions=[],
        sector_map={"VCB": "Banking"},
        risk_params=_default_risk_params(),
        market_data=_default_market_data(),
    )
    half = calculate_position_size(
        ticker="VCB",
        signal_strength=0.5,
        available_cash=500_000_000.0,
        current_positions=[],
        sector_map={"VCB": "Banking"},
        risk_params=_default_risk_params(),
        market_data=_default_market_data(),
    )
    assert full["notional"] >= half["notional"]
