from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger(__name__)


def classify_regime(
    vnindex_daily: pd.Series,
    ema50_daily: Optional[pd.Series] = None,
) -> pd.Series:
    if len(vnindex_daily) < 2:
        return pd.Series("sideways", index=vnindex_daily.index)

    monthly = vnindex_daily.resample("ME").last().dropna()
    monthly_returns = monthly.pct_change()

    if ema50_daily is not None:
        monthly_ema50 = ema50_daily.resample("ME").last().dropna()
        common_idx = monthly.index.intersection(monthly_ema50.index)
        monthly = monthly.loc[common_idx]
        monthly_returns = monthly_returns.loc[common_idx]
        monthly_ema50 = monthly_ema50.loc[common_idx]
    else:
        monthly_ema50 = pd.Series(np.nan, index=monthly.index)

    regimes = pd.Series("sideways", index=monthly.index, dtype=object)

    for idx in monthly.index:
        if idx not in monthly_returns.index:
            continue
        ret = monthly_returns.loc[idx]
        if pd.isna(ret):
            continue

        above_ema50 = True
        if idx in monthly_ema50.index and not pd.isna(monthly_ema50.loc[idx]):
            above_ema50 = monthly.loc[idx] > monthly_ema50.loc[idx]

        if ret > 0.02 and above_ema50:
            regimes.loc[idx] = "bull"
        elif ret < -0.02 and not above_ema50:
            regimes.loc[idx] = "bear"
        else:
            regimes.loc[idx] = "sideways"

    daily_regimes = pd.Series("sideways", index=vnindex_daily.index, dtype=object)
    for idx in vnindex_daily.index:
        month_end = idx.replace(day=28) + pd.DateOffset(days=4)
        month_end = month_end.replace(day=1) - pd.DateOffset(days=1)
        month_end = month_end.date() if hasattr(month_end, "date") else month_end
        month_end_ts = pd.Timestamp(month_end)

        if month_end_ts in regimes.index:
            daily_regimes[idx] = regimes.loc[month_end_ts]

    return daily_regimes


def regime_performance(
    trades_df: pd.DataFrame,
    equity_curve: pd.DataFrame,
    daily_returns: pd.Series,
    regimes: pd.Series,
    benchmark_returns: Optional[pd.Series] = None,
) -> Dict[str, Dict[str, Any]]:
    results: Dict[str, Dict[str, Any]] = {}

    regime_labels = ["bull", "bear", "sideways"]
    for regime in regime_labels:
        regime_mask = regimes == regime
        regime_dates = regimes[regime_mask].index

        regime_returns = daily_returns.loc[regime_dates] if not daily_returns.empty else pd.Series(dtype=float)
        regime_trades = trades_df[
            trades_df["entry_date"].apply(
                lambda x: x in regime_dates if hasattr(x, "__iter__") else False
            )
        ] if not trades_df.empty else pd.DataFrame()

        if hasattr(regime_dates, "__iter__") and len(regime_dates) > 0:
            trade_mask = trades_df["entry_date"].isin(regime_dates) if not trades_df.empty else pd.Series(False)
            regime_trades = trades_df[trade_mask] if not trades_df.empty else pd.DataFrame()
        else:
            regime_trades = pd.DataFrame()

        if not regime_returns.empty:
            total_ret = (1.0 + regime_returns).prod() - 1.0
            avg_ret = regime_returns.mean()
            std_ret = regime_returns.std()
        else:
            total_ret = 0.0
            avg_ret = 0.0
            std_ret = 0.0

        win_rate = 0.0
        pf = 0.0
        avg_trade = 0.0
        trade_count = 0
        if not regime_trades.empty and "pnl" in regime_trades.columns:
            trade_count = len(regime_trades)
            wins = (regime_trades["pnl"] > 0).sum()
            win_rate = wins / trade_count if trade_count > 0 else 0.0
            gross_profit = regime_trades.loc[regime_trades["pnl"] > 0, "pnl"].sum()
            gross_loss = abs(regime_trades.loc[regime_trades["pnl"] < 0, "pnl"].sum())
            pf = gross_profit / gross_loss if gross_loss > 0 else (np.inf if gross_profit > 0 else 0.0)
            avg_trade = regime_trades["pnl"].mean()

        bm_ret = 0.0
        if benchmark_returns is not None:
            bm_regime = benchmark_returns.loc[regime_dates] if not benchmark_returns.empty else pd.Series(dtype=float)
            if not bm_regime.empty:
                bm_ret = (1.0 + bm_regime).prod() - 1.0

        foreign_corr = 0.0
        sector_attribution: Dict[str, float] = {}
        if not regime_trades.empty and "sector" in regime_trades.columns:
            sec_pnl = regime_trades.groupby("sector")["pnl"].sum()
            sector_attribution = sec_pnl.to_dict()

        results[regime] = {
            "total_return": total_ret,
            "avg_return": avg_ret,
            "std_return": std_ret,
            "win_rate": win_rate,
            "profit_factor": pf,
            "avg_trade_pnl": avg_trade,
            "trade_count": trade_count,
            "benchmark_return": bm_ret,
            "excess_return": total_ret - bm_ret,
            "foreign_correlation": foreign_corr,
            "sector_attribution": sector_attribution,
            "date_count": len(regime_dates) if hasattr(regime_dates, "__iter__") else 0,
        }

    return results


def generate_regime_report(
    regime_results: Dict[str, Dict[str, Any]],
    regimes: pd.Series,
) -> str:
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        return _text_regime_report(regime_results)

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=(
            "Strategy Return by Regime",
            "Win Rate by Regime",
            "Trade Count by Regime",
            "Benchmark Comparison",
        ),
        vertical_spacing=0.12,
    )

    labels = ["Bull", "Bear", "Sideways"]
    returns = [regime_results.get(r, {}).get("total_return", 0) for r in ["bull", "bear", "sideways"]]
    win_rates = [regime_results.get(r, {}).get("win_rate", 0) for r in ["bull", "bear", "sideways"]]
    trade_counts = [regime_results.get(r, {}).get("trade_count", 0) for r in ["bull", "bear", "sideways"]]
    bm_returns = [regime_results.get(r, {}).get("benchmark_return", 0) for r in ["bull", "bear", "sideways"]]

    fig.add_trace(
        go.Bar(x=labels, y=returns, name="Strategy Return", marker_color=["green", "red", "gray"]),
        row=1, col=1,
    )
    fig.add_trace(
        go.Bar(x=labels, y=bm_returns, name="Benchmark Return", marker_color=["lightgreen", "lightcoral", "lightgray"]),
        row=1, col=1,
    )

    fig.add_trace(
        go.Bar(x=labels, y=win_rates, name="Win Rate", marker_color=["blue", "orange", "purple"]),
        row=1, col=2,
    )

    fig.add_trace(
        go.Bar(x=labels, y=trade_counts, name="Trade Count", marker_color=["cyan", "magenta", "yellow"]),
        row=2, col=1,
    )

    fig.add_trace(
        go.Bar(x=labels, y=returns, name="Excess Return",
               marker_color=["darkgreen", "darkred", "darkgray"]),
        row=2, col=2,
    )
    fig.add_trace(
        go.Bar(x=labels, y=bm_returns, name="Benchmark",
               marker_color=["lightgreen", "lightcoral", "lightgray"]),
        row=2, col=2,
    )

    fig.update_layout(
        title="Regime Analysis",
        height=700,
        showlegend=True,
        template="plotly_white",
        barmode="group",
    )

    return fig.to_html(include_plotlyjs="cdn", full_html=True)


def _text_regime_report(regime_results: Dict[str, Dict[str, Any]]) -> str:
    lines = ["=== Regime Analysis ===", ""]
    for regime in ["bull", "bear", "sideways"]:
        r = regime_results.get(regime, {})
        lines.append(f"{regime.upper()}:")
        lines.append(f"  Total Return: {r.get('total_return', 0):.2%}")
        lines.append(f"  Win Rate: {r.get('win_rate', 0):.2%}")
        lines.append(f"  Profit Factor: {r.get('profit_factor', 0):.2f}")
        lines.append(f"  Trade Count: {r.get('trade_count', 0)}")
        lines.append(f"  Benchmark Return: {r.get('benchmark_return', 0):.2%}")
        lines.append(f"  Excess Return: {r.get('excess_return', 0):.2%}")
        lines.append("")
    return "\n".join(lines)


def regime_distribution(regimes: pd.Series) -> Dict[str, int]:
    counts = regimes.value_counts()
    return {
        "bull": int(counts.get("bull", 0)),
        "bear": int(counts.get("bear", 0)),
        "sideways": int(counts.get("sideways", 0)),
    }
