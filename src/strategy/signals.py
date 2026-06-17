from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger(__name__)

REQUIRED_FEATURES = [
    "close", "ema200", "ema50", "ema20",
    "swing_high", "swing_low",
    "vol_ma20", "vol_ratio",
    "foreign_net_buy_5d", "foreign_ratio_5d",
    "rsi_weekly",
    "ceiling", "ceiling_buffer",
    "dist_ema20", "atr14",
    "open",
]

REQUIRED_TICKER_INFO = [
    "foreign_room_limit",
    "current_foreign_own",
    "sector",
]


def _validate_inputs(features: pd.DataFrame, ticker_info: dict) -> None:
    missing_cols = [c for c in REQUIRED_FEATURES if c not in features.columns]
    if missing_cols:
        raise ValueError(f"Missing feature columns: {missing_cols}")
    missing_keys = [k for k in REQUIRED_TICKER_INFO if k not in ticker_info]
    if missing_keys:
        raise ValueError(f"Missing ticker_info keys: {missing_keys}")
    if "date" not in features.columns and not isinstance(features.index, pd.DatetimeIndex):
        logger.warning("features has no 'date' column; assuming index is datetime")


def check_entry_conditions(row: pd.Series, ticker_info: dict) -> dict:
    result = {"signal": 0, "reasons": []}

    macro_bull = bool(row["close"] > row["ema200"] and row["ema50"] > row["ema200"])
    if not macro_bull:
        result["reasons"].append("macro_bear")
        return result

    dist_pct = abs(row["dist_ema20"]) if "dist_ema20" in row else abs(row["close"] - row["ema20"]) / row["ema20"]
    pullback = bool(dist_pct <= 0.01)
    if not pullback:
        result["reasons"].append("no_pullback")
        return result

    foreign_flow = bool(
        row["foreign_net_buy_5d"] > 0
        and row["foreign_ratio_5d"] > 0.40
    )
    if not foreign_flow:
        result["reasons"].append("weak_foreign_flow")
        return result

    volume_ok = bool(row["vol_ratio"] > 1.2) if "vol_ratio" in row else bool(row["volume"] > row["vol_ma20"] * 1.2)
    if not volume_ok:
        result["reasons"].append("low_volume")
        return result

    body = abs(row["close"] - row["open"])
    total_range = row["high"] - row["low"] if "high" in row and "low" in row else body * 1.5
    if total_range == 0:
        total_range = body
    candle_bull = bool(row["close"] > row["open"] and body / total_range > 0.50)
    if not candle_bull:
        result["reasons"].append("weak_candle")
        return result

    ceiling_buffer_ok = bool(row["close"] < row["ceiling"] * 0.97)
    if not ceiling_buffer_ok:
        result["reasons"].append("near_ceiling")
        return result

    weekly_rsi_ok = bool(row["rsi_weekly"] < 70)
    if not weekly_rsi_ok:
        result["reasons"].append("rsi_overbought_weekly")
        return result

    foreign_room_ok = bool(
        ticker_info.get("current_foreign_own", 0)
        < ticker_info["foreign_room_limit"] * 0.95
    )
    if not foreign_room_ok:
        result["reasons"].append("foreign_room_exhausted")
        return result

    result["signal"] = 1
    return result


def check_exit_conditions(
    row: pd.Series,
    position: Optional[dict] = None,
    prev_close_ema20_cross: bool = False,
) -> dict:
    result = {"action": "hold", "reduce_pct": 0, "reason": None}

    if row["close"] < row["ema200"]:
        return {"action": "sell_all", "reduce_pct": 1.0, "reason": "trend_break"}

    close_below_ema20 = bool(row["close"] < row["ema20"])
    if prev_close_ema20_cross and close_below_ema20:
        if position is not None:
            return {"action": "sell_position", "reduce_pct": 1.0, "reason": "trail_ema20"}

    if row["close"] < row["swing_low"]:
        return {"action": "sell_position", "reduce_pct": 1.0, "reason": "structure_break"}

    if "ema50" in row and "ema200" in row:
        prev_ema50 = row.get("ema50_prev", row["ema50"])
        prev_ema200 = row.get("ema200_prev", row["ema200"])
        if prev_ema50 > prev_ema200 and row["ema50"] < row["ema200"]:
            return {"action": "reduce", "reduce_pct": 0.50, "reason": "death_cross"}

    foreign_sell_5d = row.get("foreign_net_sell_streak", 0)
    if foreign_sell_5d >= 5:
        return {"action": "reduce", "reduce_pct": 0.30, "reason": "foreign_sell_streak"}

    if position is not None and "entry_price" in position:
        entry = position["entry_price"]
        swing_high = row.get("swing_high", np.inf)
        if row["close"] >= swing_high * 0.99:
            result = {"action": "take_profit_1", "reduce_pct": 0.40, "reason": "tp1_resistance"}
            result["tp_level"] = 1
            return result

        stop_loss = position.get("stop_loss", entry * 0.92)
        r_multiple = 2.5 * (entry - stop_loss)
        if r_multiple > 0 and row["close"] >= entry + r_multiple:
            result = {"action": "take_profit_2", "reduce_pct": 0.30, "reason": "tp2_fib"}
            result["tp_level"] = 2
            return result

    return result


def generate_signals(
    features: pd.DataFrame,
    ticker_info: dict,
    prev_close_ema20_cross_series: Optional[pd.Series] = None,
    position_info: Optional[dict] = None,
) -> pd.Series:
    _validate_inputs(features, ticker_info)

    if prev_close_ema20_cross_series is None:
        prev_close_ema20_cross_series = pd.Series(False, index=features.index)

    signals = pd.Series(0, index=features.index, dtype=int, name="signal")

    for i in range(len(features)):
        row = features.iloc[i]
        dt = features.index[i] if isinstance(features.index, pd.DatetimeIndex) else row.get("date", i)

        entry = check_entry_conditions(row, ticker_info)
        if entry["signal"] == 1:
            signals.iloc[i] = 1
            continue

        prev_cross = bool(
            prev_close_ema20_cross_series.iloc[i - 1]
            if i > 0 and i < len(prev_close_ema20_cross_series)
            else False
        )
        exit_result = check_exit_conditions(row, position_info, prev_cross)
        if exit_result["action"] != "hold":
            signals.iloc[i] = -1

    entry_count = int((signals == 1).sum())
    exit_count = int((signals == -1).sum())
    logger.info(
        "signals_generated",
        ticker=ticker_info.get("ticker", "unknown"),
        entries=entry_count,
        exits=exit_count,
        total_rows=len(features),
    )

    return signals
