from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


def calculate_position_size(
    ticker: str,
    signal_strength: float,
    available_cash: float,
    current_positions: List[Dict[str, Any]],
    sector_map: Dict[str, str],
    risk_params: Dict[str, Any],
    market_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    portfolio_value = risk_params.get("portfolio_value", available_cash)
    kelly_fraction = risk_params.get("kelly_fraction", 0.25)
    max_position_pct = risk_params.get("max_position_pct", 0.10)
    max_sector_pct = risk_params.get("max_sector_pct", 0.20)
    min_cash_pct = risk_params.get("min_cash_pct", 0.30)
    price = risk_params.get("price", market_data.get("close", 0) if market_data else 0)
    if price <= 0:
        return {
            "ticker": ticker,
            "quantity": 0,
            "notional": 0.0,
            "signal_strength": signal_strength,
            "reason": "invalid_price",
            "reduced_by": {},
        }

    base_notional = kelly_fraction * available_cash * signal_strength
    reduced_by: Dict[str, float] = {}

    hard_cap_notional = portfolio_value * max_position_pct
    if base_notional > hard_cap_notional:
        reduced_by["hard_cap"] = base_notional - hard_cap_notional
        base_notional = hard_cap_notional

    sector = sector_map.get(ticker, "Unknown")
    current_sector_value = sum(
        p["notional"] for p in current_positions
        if sector_map.get(p["ticker"], "Unknown") == sector
    )
    sector_room = (portfolio_value * max_sector_pct) - current_sector_value
    if sector_room <= 0:
        return {
            "ticker": ticker,
            "quantity": 0,
            "notional": 0.0,
            "signal_strength": signal_strength,
            "reason": f"sector_cap_reached:{sector}",
            "reduced_by": reduced_by,
        }
    if base_notional > sector_room:
        reduced_by["sector_cap"] = base_notional - sector_room
        base_notional = sector_room

    total_positions_notional = sum(p["notional"] for p in current_positions)
    cash_after = available_cash - base_notional
    total_value_after = total_positions_notional + cash_after
    cash_pct_after = cash_after / total_value_after if total_value_after > 0 else 1.0
    if cash_pct_after < min_cash_pct:
        max_allowed_for_cash = available_cash - (portfolio_value * min_cash_pct)
        if max_allowed_for_cash <= 0:
            return {
                "ticker": ticker,
                "quantity": 0,
                "notional": 0.0,
                "signal_strength": signal_strength,
                "reason": "cash_reserve",
                "reduced_by": reduced_by,
            }
        if base_notional > max_allowed_for_cash:
            reduced_by["cash_reserve"] = base_notional - max_allowed_for_cash
            base_notional = max_allowed_for_cash

    if market_data:
        foreign_room_pct = market_data.get("foreign_room_pct", 100.0)
        if 5.0 < foreign_room_pct < 10.0:
            reduction_factor = foreign_room_pct / 10.0
            reduced_notional = base_notional * reduction_factor
            reduced_by["foreign_room"] = base_notional - reduced_notional
            base_notional = reduced_notional
        elif foreign_room_pct <= 5.0:
            return {
                "ticker": ticker,
                "quantity": 0,
                "notional": 0.0,
                "signal_strength": signal_strength,
                "reason": "foreign_room_exhausted",
                "reduced_by": reduced_by,
            }

        dist_from_ceiling = market_data.get("dist_to_ceiling_pct", 100.0)
        if dist_from_ceiling < 2.0:
            reduction_factor = dist_from_ceiling / 3.0
            reduced_notional = base_notional * max(reduction_factor, 0.3)
            reduced_by["ceiling_buffer"] = base_notional - reduced_notional
            base_notional = reduced_notional

    sector_position_count = sum(
        1 for p in current_positions
        if sector_map.get(p["ticker"], "Unknown") == sector
    )
    if sector_position_count > 0:
        sector_reduction = 1.0 / (1.0 + sector_position_count)
        reduced_notional = base_notional * sector_reduction
        reduced_by["sector_open_interest"] = base_notional - reduced_notional
        base_notional = reduced_notional

    base_notional = max(base_notional, 0.0)
    quantity = int(base_notional / price) if price > 0 else 0
    actual_notional = quantity * price

    return {
        "ticker": ticker,
        "quantity": quantity,
        "price": price,
        "notional": round(actual_notional, 2),
        "signal_strength": signal_strength,
        "reason": "ok",
        "reduced_by": reduced_by,
    }
