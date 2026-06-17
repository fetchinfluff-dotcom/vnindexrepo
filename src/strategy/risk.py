from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


def calculate_stop_loss(
    entry_price: float,
    ticker_data: Dict[str, Any],
    params: Optional[Dict[str, Any]] = None,
) -> float:
    if params is None:
        params = {}

    candidates: List[float] = []

    pivot_low = ticker_data.get("swing_low", None)
    if pivot_low is not None and pivot_low > 0 and pivot_low < entry_price:
        candidates.append(pivot_low)

    fixed_pct = entry_price * params.get("max_loss_pct", 0.92)
    candidates.append(fixed_pct)

    ema20 = ticker_data.get("ema20", None)
    if ema20 is not None and ema20 > 0 and ema20 < entry_price:
        candidates.append(ema20)

    if not candidates:
        candidates.append(entry_price * 0.92)

    stop_loss = min(candidates)
    logger.debug(
        "stop_loss_calculated",
        entry_price=entry_price,
        stop_loss=round(stop_loss, 2),
        candidates=[round(c, 2) for c in candidates],
    )
    return stop_loss


def calculate_take_profit_levels(
    entry_price: float,
    stop_loss: float,
    ticker_data: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    levels = []

    if ticker_data:
        swing_high = ticker_data.get("swing_high", None)
        if swing_high is not None and swing_high > entry_price:
            levels.append({
                "level": 1,
                "price": swing_high,
                "reduce_pct": 0.40,
                "method": "swing_high",
                "reason": "tp1_resistance",
            })

    risk_per_unit = entry_price - stop_loss
    if risk_per_unit > 0:
        r2_price = entry_price + risk_per_unit * 2.5
        if not levels or r2_price != levels[0]["price"]:
            levels.append({
                "level": 2 if levels else 1,
                "price": r2_price,
                "reduce_pct": 0.30,
                "method": "fib_2.5r",
                "reason": "tp2_fib",
            })

    levels.append({
        "level": len(levels) + 1,
        "price": None,
        "reduce_pct": 0.30,
        "method": "ema20_trail",
        "reason": "trail_ema20",
    })

    return levels


def calculate_position_risk(
    entry_price: float,
    stop_loss: float,
    quantity: int,
    portfolio_value: float,
) -> Dict[str, Any]:
    risk_per_share = abs(entry_price - stop_loss)
    total_risk = risk_per_share * quantity
    risk_pct = (total_risk / portfolio_value * 100) if portfolio_value > 0 else 0.0

    return {
        "risk_per_share": round(risk_per_share, 2),
        "total_risk": round(total_risk, 2),
        "risk_pct": round(risk_pct, 4),
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "quantity": quantity,
    }
