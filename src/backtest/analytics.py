from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger(__name__)

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False
    logger.warning("plotly not installed; HTML tearsheet will be unavailable")


def compute_cagr(equity_curve: pd.Series, trading_days: int = 252) -> float:
    if len(equity_curve) < 2:
        return 0.0
    total_return = equity_curve.iloc[-1] / equity_curve.iloc[0] - 1.0
    n_periods = len(equity_curve) - 1
    years = n_periods / trading_days
    if years <= 0:
        return 0.0
    return (1.0 + total_return) ** (1.0 / years) - 1.0


def compute_max_drawdown(equity_curve: pd.Series) -> float:
    if len(equity_curve) < 2:
        return 0.0
    rolling_max = equity_curve.expanding().max()
    drawdowns = (equity_curve - rolling_max) / rolling_max
    return float(drawdowns.min())


def compute_drawdowns_detail(equity_curve: pd.Series) -> pd.DataFrame:
    if len(equity_curve) < 2:
        return pd.DataFrame()
    rolling_max = equity_curve.expanding().max()
    drawdowns = (equity_curve - rolling_max) / rolling_max
    is_dd = drawdowns < 0
    dd_starts = []
    dd_ends = []
    dd_bottoms = []
    in_dd = False
    start_idx = None
    bottom_val = 0.0
    bottom_idx = None
    for i in range(len(drawdowns)):
        if is_dd.iloc[i] and not in_dd:
            in_dd = True
            start_idx = i
            bottom_val = drawdowns.iloc[i]
            bottom_idx = i
        elif is_dd.iloc[i] and in_dd:
            if drawdowns.iloc[i] < bottom_val:
                bottom_val = drawdowns.iloc[i]
                bottom_idx = i
        elif not is_dd.iloc[i] and in_dd:
            dd_starts.append(equity_curve.index[start_idx])
            dd_ends.append(equity_curve.index[i])
            dd_bottoms.append(bottom_val)
            in_dd = False
            start_idx = None
    if in_dd:
        dd_starts.append(equity_curve.index[start_idx])
        dd_ends.append(equity_curve.index[-1])
        dd_bottoms.append(bottom_val)

    results = []
    for s, e, b in zip(dd_starts, dd_ends, dd_bottoms):
        recovery_days = (e - s).days if e > s else 0
        results.append({
            "start": s,
            "end": e,
            "depth_pct": round(b * 100, 2),
            "recovery_days": recovery_days,
        })
    results.sort(key=lambda x: x["depth_pct"])
    return pd.DataFrame(results)


def compute_sharpe(daily_returns: pd.Series, rf: float = 0.0, periods: int = 252) -> float:
    if len(daily_returns) < 2:
        return 0.0
    excess = daily_returns - rf / periods
    excess_std = excess.std()
    if excess_std < 1e-10:
        return 0.0
    return float(np.sqrt(periods) * excess.mean() / excess_std)


def compute_sortino(daily_returns: pd.Series, rf: float = 0.0, periods: int = 252) -> float:
    if len(daily_returns) < 2:
        return 0.0
    excess = daily_returns - rf / periods
    downside = excess[excess < 0]
    if len(downside) < 2 or downside.std() == 0:
        return 0.0
    return float(np.sqrt(periods) * excess.mean() / downside.std())


def compute_volatility(daily_returns: pd.Series, periods: int = 252) -> float:
    if len(daily_returns) < 2:
        return 0.0
    return float(daily_returns.std() * np.sqrt(periods))


def compute_calmar(cagr_val: float, max_dd: float) -> float:
    if max_dd == 0:
        return 0.0
    return abs(cagr_val / max_dd)


def compute_ulcer(equity_curve: pd.Series) -> float:
    if len(equity_curve) < 2:
        return 0.0
    rolling_max = equity_curve.expanding().max()
    pct_dd = (equity_curve - rolling_max) / rolling_max * 100
    squared = pct_dd ** 2
    return float(np.sqrt(squared.mean()))


def compute_mar(cagr_val: float, max_dd: float) -> float:
    return compute_calmar(cagr_val, max_dd)


def compute_sterling(cagr_val: float, max_dd: float, avg_dd: float = 0.0) -> float:
    if avg_dd == 0:
        avg_dd = abs(max_dd)
    denom = abs(avg_dd) + 0.1
    return cagr_val / denom


def compute_profit_factor(trades_df: pd.DataFrame) -> float:
    if trades_df.empty:
        return 0.0
    gross_profit = trades_df.loc[trades_df["pnl"] > 0, "pnl"].sum()
    gross_loss = abs(trades_df.loc[trades_df["pnl"] < 0, "pnl"].sum())
    if gross_loss == 0:
        return np.inf if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def compute_expectancy(trades_df: pd.DataFrame) -> float:
    if trades_df.empty:
        return 0.0
    return trades_df["pnl"].mean()


def compute_avg_win_loss(trades_df: pd.DataFrame) -> Tuple[float, float]:
    if trades_df.empty:
        return 0.0, 0.0
    avg_win = trades_df.loc[trades_df["pnl"] > 0, "pnl"].mean() if (trades_df["pnl"] > 0).any() else 0.0
    avg_loss = trades_df.loc[trades_df["pnl"] < 0, "pnl"].mean() if (trades_df["pnl"] < 0).any() else 0.0
    return float(avg_win), float(abs(avg_loss))


def compute_benchmark_metrics(
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
    rf: float = 0.0,
    periods: int = 252,
) -> Dict[str, float]:
    valid = strategy_returns.dropna().align(benchmark_returns.dropna(), join="inner")
    strat, bench = valid
    if len(strat) < 2:
        return {"alpha": 0.0, "beta": 0.0, "correlation": 0.0, "tracking_error": 0.0, "info_ratio": 0.0}
    cov = np.cov(strat, bench)
    beta = cov[0, 1] / cov[1, 1] if cov[1, 1] > 0 else 0.0
    alpha = (strat.mean() - beta * bench.mean()) * periods
    corr = strat.corr(bench)
    te = (strat - bench).std() * np.sqrt(periods)
    ir = (strat.mean() - bench.mean()) * periods / te if te > 0 else 0.0
    return {
        "alpha": round(alpha, 4),
        "beta": round(beta, 4),
        "correlation": round(corr, 4),
        "tracking_error": round(te, 4),
        "info_ratio": round(ir, 4),
    }


def compute_metrics(
    trades_df: pd.DataFrame,
    equity_curve: pd.DataFrame,
    daily_returns: pd.Series,
    benchmark_returns: Optional[pd.Series] = None,
    config: Any = None,
) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}

    if equity_curve.empty or "nav" not in equity_curve.columns:
        return {"error": "empty_equity_curve"}

    nav = equity_curve["nav"]
    total_return = nav.iloc[-1] / nav.iloc[0] - 1.0
    cagr_val = compute_cagr(nav)
    max_dd = compute_max_drawdown(nav)
    vol = compute_volatility(daily_returns)
    sharpe = compute_sharpe(daily_returns)
    sortino = compute_sortino(daily_returns)
    calmar = compute_calmar(cagr_val, max_dd)
    ulcer = compute_ulcer(nav)
    mar = compute_mar(cagr_val, max_dd)
    sterling = compute_sterling(cagr_val, max_dd)
    pf = compute_profit_factor(trades_df)
    expectancy = compute_expectancy(trades_df)
    avg_win, avg_loss = compute_avg_win_loss(trades_df)
    dd_detail = compute_drawdowns_detail(nav)
    yearly_returns = _compute_yearly_returns(daily_returns)
    monthly_heatmap = _compute_monthly_heatmap(daily_returns)
    sector_pnl = _compute_sector_attribution(trades_df)
    trade_stats = _compute_trade_stats(trades_df)

    metrics["total_return"] = round(total_return, 4)
    metrics["cagr"] = round(cagr_val, 4)
    metrics["volatility"] = round(vol, 4)
    metrics["max_drawdown"] = round(max_dd, 4)
    metrics["calmar"] = round(calmar, 4)
    metrics["sharpe"] = round(sharpe, 4)
    metrics["sortino"] = round(sortino, 4)
    metrics["ulcer"] = round(ulcer, 4)
    metrics["mar"] = round(mar, 4)
    metrics["sterling"] = round(sterling, 4)
    metrics["profit_factor"] = round(pf, 4) if pf != np.inf else "inf"
    metrics["expectancy"] = round(expectancy, 2)
    metrics["avg_win"] = round(avg_win, 2)
    metrics["avg_loss"] = round(avg_loss, 2)
    metrics["win_rate"] = round(trade_stats["win_rate"], 4)
    metrics["avg_hold_days"] = round(trade_stats["avg_hold_days"], 1)
    metrics["max_position"] = round(trade_stats["max_position"], 2)
    metrics["avg_position_size"] = round(trade_stats["avg_position_size"], 2)
    metrics["total_trades"] = trade_stats["total_trades"]
    metrics["sector_pnl"] = sector_pnl
    metrics["yearly_returns"] = yearly_returns
    metrics["monthly_heatmap"] = monthly_heatmap
    metrics["drawdowns"] = dd_detail

    if benchmark_returns is not None:
        bm_metrics = compute_benchmark_metrics(daily_returns, benchmark_returns)
        metrics.update({f"benchmark_{k}": v for k, v in bm_metrics.items()})

    return metrics


def _compute_yearly_returns(daily_returns: pd.Series) -> Dict[int, float]:
    if daily_returns.empty:
        return {}
    yearly = daily_returns.groupby(daily_returns.index.year).apply(lambda x: (1 + x).prod() - 1)
    return {int(k): round(v, 4) for k, v in yearly.items()}


def _compute_monthly_heatmap(daily_returns: pd.Series) -> pd.DataFrame:
    if daily_returns.empty:
        return pd.DataFrame()
    monthly = daily_returns.groupby([daily_returns.index.year, daily_returns.index.month]).apply(
        lambda x: (1 + x).prod() - 1
    )
    result = monthly.unstack(level=0)
    result.columns = [int(c) for c in result.columns]
    result.index = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]
    return result


def _compute_sector_attribution(trades_df: pd.DataFrame) -> pd.DataFrame:
    if trades_df.empty or "sector" not in trades_df.columns:
        return pd.DataFrame()
    grouped = trades_df.groupby("sector").agg(
        total_pnl=("pnl", "sum"),
        trade_count=("pnl", "count"),
        win_count=("pnl", lambda x: (x > 0).sum()),
        avg_return=("return_pct", "mean"),
    ).reset_index()
    grouped["hit_rate"] = grouped["win_count"] / grouped["trade_count"]
    grouped = grouped.sort_values("total_pnl", ascending=False)
    return grouped


def _compute_trade_stats(trades_df: pd.DataFrame) -> Dict[str, float]:
    if trades_df.empty:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "avg_hold_days": 0.0,
            "max_position": 0.0,
            "avg_position_size": 0.0,
        }
    total = len(trades_df)
    wins = (trades_df["pnl"] > 0).sum()
    win_rate = wins / total if total > 0 else 0.0
    avg_hold = trades_df["hold_days"].mean() if "hold_days" in trades_df.columns else 0.0
    max_pos = trades_df["shares"].max() if "shares" in trades_df.columns else 0.0
    avg_size = trades_df["shares"].mean() if "shares" in trades_df.columns else 0.0
    return {
        "total_trades": total,
        "win_rate": float(win_rate),
        "avg_hold_days": float(avg_hold),
        "max_position": float(max_pos),
        "avg_position_size": float(avg_size),
    }


def generate_tearsheet(
    trades_df: pd.DataFrame,
    equity_curve: pd.DataFrame,
    daily_returns: pd.Series,
    monthly_returns: pd.DataFrame,
    benchmark_data: Optional[pd.DataFrame] = None,
    config: Any = None,
    title: str = "Backtest Tearsheet",
) -> str:
    metrics = compute_metrics(trades_df, equity_curve, daily_returns, None, config)
    if not HAS_PLOTLY:
        return _text_tearsheet(metrics, trades_df, equity_curve)
    return _plotly_tearsheet(metrics, trades_df, equity_curve, daily_returns, monthly_returns, benchmark_data, title)


def _text_tearsheet(metrics: Dict, trades_df: pd.DataFrame, equity_curve: pd.DataFrame) -> str:
    lines = ["=== Backtest Tearsheet (Text) ===", ""]
    lines.append(f"Total Return: {metrics.get('total_return', 0):.2%}")
    lines.append(f"CAGR: {metrics.get('cagr', 0):.2%}")
    lines.append(f"Volatility: {metrics.get('volatility', 0):.2%}")
    lines.append(f"Max Drawdown: {metrics.get('max_drawdown', 0):.2%}")
    lines.append(f"Sharpe: {metrics.get('sharpe', 0):.2f}")
    lines.append(f"Sortino: {metrics.get('sortino', 0):.2f}")
    lines.append(f"Calmar: {metrics.get('calmar', 0):.2f}")
    lines.append(f"Profit Factor: {metrics.get('profit_factor', 0)}")
    lines.append(f"Win Rate: {metrics.get('win_rate', 0):.2%}")
    lines.append(f"Total Trades: {metrics.get('total_trades', 0)}")
    lines.append("")
    if not trades_df.empty:
        lines.append("Top 5 Trades:")
        top = trades_df.nlargest(5, "pnl")[["ticker", "pnl", "return_pct", "exit_reason"]]
        lines.append(top.to_string(index=False))
    return "\n".join(lines)


def _plotly_tearsheet(
    metrics: Dict,
    trades_df: pd.DataFrame,
    equity_curve: pd.DataFrame,
    daily_returns: pd.Series,
    monthly_returns: pd.DataFrame,
    benchmark_data: Optional[pd.DataFrame] = None,
    title: str = "Backtest Tearsheet",
) -> str:
    fig = make_subplots(
        rows=5, cols=3,
        specs=[
            [{"colspan": 3}, None, None],
            [{"colspan": 3}, None, None],
            [{"colspan": 2}, {"type": "table"}, None],
            [{"colspan": 3}, None, None],
            [{"colspan": 3}, None, None],
        ],
        subplot_titles=(
            "Equity Curve", None, None,
            "Drawdown", None, None,
            "Monthly Returns", "Key Metrics", None,
            "Sector Attribution", None, None,
            "Yearly Returns", None, None,
        ),
        vertical_spacing=0.08,
        horizontal_spacing=0.05,
        row_heights=[0.2, 0.15, 0.25, 0.2, 0.2],
    )

    if not equity_curve.empty and "nav" in equity_curve.columns:
        fig.add_trace(
            go.Scatter(
                x=equity_curve.index, y=equity_curve["nav"],
                mode="lines", name="NAV",
                line=dict(color="blue", width=2),
            ),
            row=1, col=1,
        )
        if benchmark_data is not None and "close" in benchmark_data.columns:
            bm_norm = benchmark_data["close"] / benchmark_data["close"].iloc[0] * equity_curve["nav"].iloc[0]
            fig.add_trace(
                go.Scatter(
                    x=bm_norm.index, y=bm_norm,
                    mode="lines", name="Benchmark",
                    line=dict(color="gray", width=1, dash="dash"),
                ),
                row=1, col=1,
            )

    if not equity_curve.empty and "drawdown" in equity_curve.columns:
        fig.add_trace(
            go.Scatter(
                x=equity_curve.index,
                y=equity_curve["drawdown"] * 100,
                mode="lines", name="Drawdown %",
                fill="tozeroy",
                line=dict(color="red", width=1),
            ),
            row=2, col=1,
        )

    monthly_vals = metrics.get("monthly_heatmap", pd.DataFrame())
    if not monthly_vals.empty:
        z_data = monthly_vals.values * 100
        fig.add_trace(
            go.Heatmap(
                z=z_data,
                x=[str(c) for c in monthly_vals.columns],
                y=monthly_vals.index,
                colorscale="RdYlGn",
                zmid=0,
                text=np.round(z_data, 1),
                texttemplate="%{text}%",
                name="Monthly Returns %",
                colorbar=dict(title="%"),
            ),
            row=3, col=1,
        )

    metric_rows = []
    metric_rows.append([f"Total Return", f"{metrics.get('total_return', 0):.2%}"])
    metric_rows.append([f"CAGR", f"{metrics.get('cagr', 0):.2%}"])
    metric_rows.append([f"Volatility", f"{metrics.get('volatility', 0):.2%}"])
    metric_rows.append([f"Max DD", f"{metrics.get('max_drawdown', 0):.2%}"])
    metric_rows.append([f"Sharpe", f"{metrics.get('sharpe', 0):.2f}"])
    metric_rows.append([f"Sortino", f"{metrics.get('sortino', 0):.2f}"])
    metric_rows.append([f"Calmar", f"{metrics.get('calmar', 0):.2f}"])
    metric_rows.append([f"Profit Factor", f"{metrics.get('profit_factor', 'N/A')}"])
    metric_rows.append([f"Win Rate", f"{metrics.get('win_rate', 0):.2%}"])
    metric_rows.append([f"Total Trades", f"{metrics.get('total_trades', 0)}"])
    fig.add_trace(
        go.Table(
            header=dict(values=["Metric", "Value"], align="left"),
            cells=dict(values=list(zip(*metric_rows)) if metric_rows else [[], []], align="left"),
        ),
        row=3, col=2,
    )

    sector_data = metrics.get("sector_pnl", pd.DataFrame())
    if not sector_data.empty:
        fig.add_trace(
            go.Bar(
                x=sector_data["sector"],
                y=sector_data["total_pnl"],
                name="Sector PnL",
                marker_color=["green" if v > 0 else "red" for v in sector_data["total_pnl"]],
            ),
            row=4, col=1,
        )

    yearly = metrics.get("yearly_returns", {})
    if yearly:
        years = list(yearly.keys())
        returns = list(yearly.values())
        colors = ["green" if v > 0 else "red" for v in returns]
        fig.add_trace(
            go.Bar(x=years, y=returns, name="Yearly Return", marker_color=colors),
            row=5, col=1,
        )

    fig.update_layout(
        title=dict(text=title, x=0.5),
        height=1400,
        showlegend=True,
        template="plotly_white",
    )
    fig.update_xaxes(title_text="Date", row=1, col=1)
    fig.update_yaxes(title_text="NAV (VND)", row=1, col=1)
    fig.update_xaxes(title_text="Date", row=2, col=1)
    fig.update_yaxes(title_text="Drawdown %", row=2, col=1)
    fig.update_xaxes(title_text="Year", row=5, col=1)
    fig.update_yaxes(title_text="Return %", row=5, col=1)

    html = fig.to_html(include_plotlyjs="cdn", full_html=True)
    return html


def generate_comparison_report(
    results: Dict[str, BacktestResult],
    benchmark_returns: Optional[pd.Series] = None,
) -> str:


    if not HAS_PLOTLY:
        lines = ["=== Execution Mode Comparison ===", ""]
        header = f"{'Mode':<25} {'Return':<10} {'CAGR':<10} {'Sharpe':<10} {'MaxDD':<10} {'WinRate':<10} {'Trades':<8}"
        lines.append(header)
        lines.append("-" * len(header))
        for mode, result in results.items():
            metrics = compute_metrics(result.trades, result.equity_curve, result.daily_returns, benchmark_returns)
            lines.append(
                f"{mode:<25} {metrics.get('total_return', 0):<10.2%} {metrics.get('cagr', 0):<10.2%} "
                f"{metrics.get('sharpe', 0):<10.2f} {metrics.get('max_drawdown', 0):<10.2%} "
                f"{metrics.get('win_rate', 0):<10.2%} {metrics.get('total_trades', 0):<8}"
            )
        return "\n".join(lines)

    modes = list(results.keys())
    all_metrics = {}
    for mode in modes:
        all_metrics[mode] = compute_metrics(
            results[mode].trades, results[mode].equity_curve,
            results[mode].daily_returns, benchmark_returns,
        )

    fig = make_subplots(
        rows=3, cols=2,
        specs=[
            [{"colspan": 2}, None],
            [{"type": "table"}, {"type": "table"}],
            [{"type": "table"}, {"type": "table"}],
        ],
        subplot_titles=("Equity Curve Comparison", None, "Key Metrics", "Risk Metrics", "Trade Stats", "Sector Attribution"),
        vertical_spacing=0.08,
        row_heights=[0.3, 0.25, 0.25],
    )
    fig.update_layout(height=1200)

    colors = ["blue", "red", "green", "orange"]
    for i, mode in enumerate(modes):
        eq = results[mode].equity_curve
        if not eq.empty and "nav" in eq.columns:
            fig.add_trace(
                go.Scatter(
                    x=eq.index, y=eq["nav"],
                    mode="lines", name=mode,
                    line=dict(color=colors[i % len(colors)], width=1.5),
                ),
                row=1, col=1,
            )

    metric_keys = ["total_return", "cagr", "sharpe", "sortino", "calmar", "profit_factor", "win_rate", "total_trades"]
    metric_labels = ["Total Return", "CAGR", "Sharpe", "Sortino", "Calmar", "Profit Factor", "Win Rate", "Trades"]
    metric_rows = [["Metric"] + [m.replace("_", " ").title() for m in metric_keys]]
    for mode in modes:
        row = [mode]
        for k in metric_keys:
            v = all_metrics[mode].get(k, 0)
            if k in ("total_return", "cagr", "win_rate"):
                row.append(f"{v:.2%}" if isinstance(v, float) else str(v))
            elif k in ("sharpe", "sortino", "calmar"):
                row.append(f"{v:.2f}" if isinstance(v, float) else str(v))
            else:
                row.append(f"{v:,.0f}" if isinstance(v, (int, float)) else str(v))
        metric_rows.append(row)
    if len(metric_rows) > 1:
        fig.add_trace(
            go.Table(
                header=dict(values=metric_rows[0], align="center"),
                cells=dict(values=list(zip(*metric_rows[1:])) if len(metric_rows) > 1 else [[], []], align="center"),
            ),
            row=2, col=1,
        )

    risk_keys = ["volatility", "max_drawdown", "ulcer", "sterling", "mar", "expectancy", "avg_win", "avg_loss"]
    risk_rows = [["Metric"] + [k.replace("_", " ").title() for k in risk_keys]]
    for mode in modes:
        row = [mode]
        for k in risk_keys:
            v = all_metrics[mode].get(k, 0)
            if k in ("volatility", "max_drawdown"):
                row.append(f"{v:.2%}" if isinstance(v, float) else str(v))
            elif k in ("ulcer", "sterling", "mar"):
                row.append(f"{v:.4f}" if isinstance(v, float) else str(v))
            else:
                row.append(f"{v:,.0f}" if isinstance(v, (int, float)) else str(v))
        risk_rows.append(row)
    if len(risk_rows) > 1:
        fig.add_trace(
            go.Table(
                header=dict(values=risk_rows[0], align="center"),
                cells=dict(values=list(zip(*risk_rows[1:])) if len(risk_rows) > 1 else [[], []], align="center"),
            ),
            row=2, col=2,
        )

    trade_rows = [["Metric"] + ["Avg Hold Days", "Max Position", "Avg Position"]]
    for mode in modes:
        v = all_metrics[mode]
        row = [mode, f"{v.get('avg_hold_days', 0):.1f}", f"{v.get('max_position', 0):,.0f}", f"{v.get('avg_position_size', 0):,.0f}"]
        trade_rows.append(row)
    if len(trade_rows) > 1:
        fig.add_trace(
            go.Table(
                header=dict(values=trade_rows[0], align="center"),
                cells=dict(values=list(zip(*trade_rows[1:])) if len(trade_rows) > 1 else [[], []], align="center"),
            ),
            row=3, col=1,
        )

    sector_rows = [["Sector"] + modes]
    all_sectors = set()
    for mode in modes:
        sec_df = all_metrics[mode].get("sector_pnl", pd.DataFrame())
        if not sec_df.empty:
            all_sectors.update(sec_df["sector"].tolist())
    all_sectors = sorted(all_sectors)
    if all_sectors:
        for sec in all_sectors:
            row = [sec]
            for mode in modes:
                sec_df = all_metrics[mode].get("sector_pnl", pd.DataFrame())
                if not sec_df.empty and sec in sec_df["sector"].values:
                    pnl_val = sec_df[sec_df["sector"] == sec]["total_pnl"].iloc[0]
                    row.append(f"{pnl_val:,.0f}")
                else:
                    row.append("N/A")
            sector_rows.append(row)
        fig.add_trace(
            go.Table(
                header=dict(values=sector_rows[0], align="center"),
                cells=dict(values=list(zip(*sector_rows[1:])) if len(sector_rows) > 1 else [[], []], align="center"),
            ),
            row=3, col=2,
        )

    fig.update_layout(
        title=dict(text="Execution Mode Comparison", x=0.5),
        height=1200,
        showlegend=True,
        template="plotly_white",
    )

    return fig.to_html(include_plotlyjs="cdn", full_html=True)


from src.backtest.engine import BacktestResult
