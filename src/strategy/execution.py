from __future__ import annotations

from enum import Enum
from typing import Dict, Optional

import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger(__name__)

SLIPPAGE_ATO = 0.001
SLIPPAGE_ATC = 0.0005


class ExecMode(str, Enum):
    BUY_ATC_SELL_ATC = "buy_atc_sell_atc"
    BUY_ATC_SELL_ATO = "buy_atc_sell_ato"
    BUY_ATO_SELL_ATC = "buy_ato_sell_atc"
    BUY_ATO_SELL_ATO = "buy_ato_sell_ato"


def _get_entry_price(
    row: pd.Series,
    mode: ExecMode,
) -> Optional[float]:
    if mode in (ExecMode.BUY_ATC_SELL_ATC, ExecMode.BUY_ATC_SELL_ATO):
        fill = row.get("close", None)
        if fill is None or pd.isna(fill):
            return None
        return fill * (1.0 + SLIPPAGE_ATC)
    else:
        fill = row.get("open", None)
        if fill is None or pd.isna(fill):
            return None
        return fill * (1.0 + SLIPPAGE_ATO)


def _get_exit_price(
    row: pd.Series,
    mode: ExecMode,
) -> Optional[float]:
    if mode in (ExecMode.BUY_ATC_SELL_ATC, ExecMode.BUY_ATO_SELL_ATC):
        fill = row.get("close", None)
        if fill is None or pd.isna(fill):
            return None
        return fill * (1.0 - SLIPPAGE_ATC)
    else:
        fill = row.get("open", None)
        if fill is None or pd.isna(fill):
            return None
        return fill * (1.0 - SLIPPAGE_ATO)


def _resolve_price_df(
    price_df: pd.DataFrame,
    signal_date,
) -> Optional[pd.Series]:
    if price_df.index.name == "date" or isinstance(price_df.index, pd.DatetimeIndex):
        if signal_date in price_df.index:
            return price_df.loc[signal_date]
        return None
    if "date" in price_df.columns:
        match = price_df[price_df["date"] == signal_date]
        if not match.empty:
            return match.iloc[0]
        return None
    return None


def simulate_execution(
    signal_df: pd.DataFrame,
    mode: str,
    price_df: pd.DataFrame,
    portfolio_value: float = 1_000_000_000.0,
) -> pd.DataFrame:
    _mode = ExecMode(mode)
    required_cols = ["date", "ticker", "signal"]
    for c in required_cols:
        if c not in signal_df.columns:
            raise ValueError(f"signal_df missing column: {c}")
    if "open" not in price_df.columns or "close" not in price_df.columns:
        raise ValueError("price_df must have 'open' and 'close' columns")

    if signal_df.empty:
        return pd.DataFrame()

    signal_df = signal_df.sort_values("date").reset_index(drop=True)
    price_cols = ["open", "close", "high", "low"] if all(c in price_df.columns for c in ["high", "low"]) else ["open", "close"]

    results = []
    for idx, sig_row in signal_df.iterrows():
        sig_date = sig_row["date"]
        signal = sig_row["signal"]
        ticker = sig_row.get("ticker", "UNKNOWN")

        px_signal = _resolve_price_df(price_df, sig_date)
        if px_signal is None:
            logger.warning("price_not_found", date=sig_date, ticker=ticker)
            continue

        px_next = _resolve_price_df(price_df, sig_date + pd.Timedelta(days=1))
        if px_next is None:
            logger.debug("no_next_day_price", date=sig_date, ticker=ticker)
            continue

        if signal == 1:
            entry_px = _get_entry_price(px_next, _mode)
            if entry_px is None:
                continue
            results.append({
                "signal_date": sig_date,
                "exec_date": sig_date + pd.Timedelta(days=1),
                "ticker": ticker,
                "action": "buy",
                "signal": 1,
                "fill_price": round(entry_px, 2),
                "mode": mode,
            })

        elif signal == -1:
            exit_px = _get_exit_price(px_next, _mode)
            if exit_px is None:
                continue
            results.append({
                "signal_date": sig_date,
                "exec_date": sig_date + pd.Timedelta(days=1),
                "ticker": ticker,
                "action": "sell",
                "signal": -1,
                "fill_price": round(exit_px, 2),
                "mode": mode,
            })

    result_df = pd.DataFrame(results)
    if result_df.empty:
        return result_df

    logger.info(
        "execution_simulated",
        mode=mode,
        fills=len(result_df),
        buys=int((result_df["action"] == "buy").sum()),
        sells=int((result_df["action"] == "sell").sum()),
    )
    return result_df


def compute_execution_stats(exec_df: pd.DataFrame) -> Dict[str, float]:
    if exec_df.empty:
        return {"total_fills": 0}

    stats: Dict[str, float] = {
        "total_fills": float(len(exec_df)),
        "buys": float((exec_df["action"] == "buy").sum()),
        "sells": float((exec_df["action"] == "sell").sum()),
    }

    slippage_col = "slippage"
    if slippage_col in exec_df.columns:
        stats["avg_slippage_bps"] = float(exec_df[slippage_col].mean() * 10000)

    return stats
