from __future__ import annotations

import itertools
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import structlog

from src.strategy.config import StrategyConfig

logger = structlog.get_logger(__name__)


PARAM_GRID = {
    "pullback_threshold": [0.005, 0.01, 0.015],
    "volume_ratio_min": [1.0, 1.2, 1.5, 2.0],
    "max_loss_pct": [0.90, 0.92, 0.94],
    "weekly_rsi_max": [65.0, 70.0, 75.0],
    "foreign_ratio_min": [0.3, 0.4, 0.5],
}


@dataclass
class WindowResult:
    window_idx: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    best_params: Dict[str, Any]
    is_sharpe: float
    oos_sharpe: float
    is_return: float
    oos_return: float
    is_maxdd: float
    oos_maxdd: float
    is_win_rate: float
    oos_win_rate: float
    stability: float = 0.0


class WalkForwardOptimizer:

    def __init__(
        self,
        backtester_factory: callable,
        config: StrategyConfig,
        features_data: Dict[str, pd.DataFrame],
        ticker_info: Dict[str, Dict[str, Any]],
        benchmark_data: Optional[pd.DataFrame] = None,
        param_grid: Optional[Dict[str, List[Any]]] = None,
    ):
        self.backtester_factory = backtester_factory
        self.config = config
        self.features_data = features_data
        self.ticker_info = ticker_info
        self.benchmark_data = benchmark_data
        self.param_grid = param_grid or PARAM_GRID

    def _apply_params(self, bt: Any, params: Dict[str, Any], is_training: bool = True) -> Any:
        bt._pullback_threshold_override = params.get("pullback_threshold")
        bt._volume_ratio_override = params.get("volume_ratio_min")
        bt._max_loss_pct_override = params.get("max_loss_pct")
        bt._weekly_rsi_override = params.get("weekly_rsi_max")
        bt._foreign_ratio_override = params.get("foreign_ratio_min")
        return bt

    def _check_entry_with_overrides(
        self, row: pd.Series, ticker_info: dict
    ) -> dict:
        from src.strategy.signals import check_entry_conditions
        result = check_entry_conditions(row, ticker_info)
        if result["signal"] != 1:
            return result

        pb = getattr(self, "_pullback_threshold_override", None)
        vr = getattr(self, "_volume_ratio_override", None)
        wr = getattr(self, "_weekly_rsi_override", None)
        fr = getattr(self, "_foreign_ratio_override", None)

        if pb is not None:
            dist_pct = abs(row.get("dist_ema20", 0))
            if dist_pct > pb:
                return {"signal": 0, "reasons": ["pullback_override"]}
        if vr is not None:
            vol_ratio = row.get("vol_ratio", 1.0)
            if vol_ratio <= vr:
                return {"signal": 0, "reasons": ["volume_override"]}
        if wr is not None:
            rsi = row.get("rsi_weekly", 0)
            if rsi >= wr:
                return {"signal": 0, "reasons": ["rsi_override"]}
        if fr is not None:
            foreign_ratio = row.get("foreign_ratio_5d", 0)
            if foreign_ratio <= fr:
                return {"signal": 0, "reasons": ["foreign_ratio_override"]}
        return result

    def _get_stop_loss_with_overrides(
        self, entry_price: float, ticker_data: dict
    ) -> float:
        from src.strategy.risk import calculate_stop_loss
        mlp = getattr(self, "_max_loss_pct_override", None)
        params = {}
        if mlp is not None:
            params["max_loss_pct"] = mlp
        return calculate_stop_loss(entry_price, ticker_data, params)

    def _create_backtester_with_overrides(self, params: Dict[str, Any]) -> Any:
        bt = self.backtester_factory(
            self.config, self.features_data, self.ticker_info, self.benchmark_data
        )
        self._apply_params(bt, params)
        bt._check_entry_conditions = lambda row, info: self._check_entry_with_overrides(row, info)
        orig_get = bt._get_ticker_data

        def _get_ticker_data_override(ticker, date):
            data = orig_get(ticker, date)
            mlp = getattr(bt, "_max_loss_pct_override", None)
            if mlp is not None:
                data["_max_loss_pct"] = mlp
            return data

        bt._get_ticker_data = _get_ticker_data_override
        return bt

    def _compute_is_oos_ratio(self, window_results: List[WindowResult]) -> float:
        if not window_results:
            return 0.0
        ratios = []
        for wr in window_results:
            if wr.is_sharpe != 0:
                ratios.append(abs(wr.oos_sharpe / wr.is_sharpe))
            elif wr.is_return != 0:
                ratios.append(abs(wr.oos_return / wr.is_return))
            else:
                ratios.append(0.0)
        return float(np.mean(ratios)) if ratios else 0.0

    def _evaluate_params(
        self,
        bt: Any,
        params: Dict[str, Any],
        train_dates: Tuple[datetime, datetime],
        test_dates: Tuple[datetime, datetime],
        mode: str,
    ) -> Tuple[Dict[str, float], Dict[str, float]]:
        from src.backtest.analytics import compute_metrics

        train_result = bt.run(
            mode=mode,
            start_date=train_dates[0],
            end_date=train_dates[1],
        )
        is_metrics = compute_metrics(
            train_result.trades, train_result.equity_curve, train_result.daily_returns
        )

        test_result = bt.run(
            mode=mode,
            start_date=test_dates[0],
            end_date=test_dates[1],
        )
        oos_metrics = compute_metrics(
            test_result.trades, test_result.equity_curve, test_result.daily_returns
        )

        return is_metrics, oos_metrics

    def _select_best_params(
        self,
        results: List[Tuple[Dict[str, Any], Dict[str, float], Dict[str, float]]],
    ) -> Tuple[Dict[str, Any], Dict[str, float], Dict[str, float]]:
        best = None
        best_score = -np.inf
        for params, is_m, oos_m in results:
            score = is_m.get("sharpe", 0) * 0.6 + oos_m.get("sharpe", 0) * 0.4
            if score > best_score:
                best_score = score
                best = (params, is_m, oos_m)
        return best if best else (list(results)[0] if results else ({}, {}, {}))

    def optimize(
        self,
        mode: str = "buy_atc_sell_atc",
        train_months: int = 24,
        test_months: int = 6,
        roll_months: int = 3,
        embargo_days: int = 5,
        max_workers: int = 1,
        progress_callback: Optional[callable] = None,
    ) -> Tuple[List[WindowResult], pd.DataFrame]:
        all_dates = sorted(set(
            dt
            for df in self.features_data.values()
            for dt in df.index
        ))
        all_dates = pd.DatetimeIndex(all_dates)
        if len(all_dates) == 0:
            logger.warning("no_dates_for_walkforward")
            return [], pd.DataFrame()

        start_date = all_dates[0]
        end_date = all_dates[-1]

        windows = self._build_windows(
            start_date, end_date, train_months, test_months, roll_months, embargo_days
        )

        if not windows:
            logger.warning("no_windows_constructed")
            return [], pd.DataFrame()

        window_results: List[WindowResult] = []
        all_param_results: List[Dict[str, Any]] = []

        param_keys = list(self.param_grid.keys())
        param_values = list(self.param_grid.values())
        param_combinations = list(itertools.product(*param_values))

        logger.info(
            "walkforward_started",
            windows=len(windows),
            param_combos=len(param_combinations),
            mode=mode,
        )

        for w_idx, (train_dates, test_dates) in enumerate(windows):
            logger.info(
                "walkforward_window",
                window=w_idx + 1,
                train_start=train_dates[0].strftime("%Y-%m-%d") if isinstance(train_dates[0], (datetime, pd.Timestamp)) else str(train_dates[0]),
                train_end=train_dates[1].strftime("%Y-%m-%d") if isinstance(train_dates[1], (datetime, pd.Timestamp)) else str(train_dates[1]),
                test_start=test_dates[0].strftime("%Y-%m-%d") if isinstance(test_dates[0], (datetime, pd.Timestamp)) else str(test_dates[0]),
                test_end=test_dates[1].strftime("%Y-%m-%d") if isinstance(test_dates[1], (datetime, pd.Timestamp)) else str(test_dates[1]),
            )

            window_param_results: List[Tuple[Dict[str, Any], Dict[str, float], Dict[str, float]]] = []

            for p_combo in param_combinations:
                params = dict(zip(param_keys, p_combo))
                bt = self._create_backtester_with_overrides(params)
                try:
                    is_m, oos_m = self._evaluate_params(
                        bt, params, train_dates, test_dates, mode
                    )
                    window_param_results.append((params, is_m, oos_m))
                except Exception as e:
                    logger.warning("param_eval_failed", params=params, error=str(e))
                    continue

                if progress_callback:
                    progress_callback(
                        (w_idx * len(param_combinations) + len(window_param_results))
                        / (len(windows) * len(param_combinations))
                    )

            best_params, best_is, best_oos = self._select_best_params(window_param_results)

            wr = WindowResult(
                window_idx=w_idx,
                train_start=train_dates[0] if isinstance(train_dates[0], datetime) else train_dates[0].to_pydatetime() if isinstance(train_dates[0], (pd.Timestamp,)) else datetime.combine(train_dates[0], datetime.min.time()) if isinstance(train_dates[0], pd.Timestamp) else train_dates[0],
                train_end=train_dates[1],
                test_start=test_dates[0],
                test_end=test_dates[1],
                best_params=best_params,
                is_sharpe=best_is.get("sharpe", 0),
                oos_sharpe=best_oos.get("sharpe", 0),
                is_return=best_is.get("total_return", 0),
                oos_return=best_oos.get("total_return", 0),
                is_maxdd=best_is.get("max_drawdown", 0),
                oos_maxdd=best_oos.get("max_drawdown", 0),
                is_win_rate=best_is.get("win_rate", 0),
                oos_win_rate=best_oos.get("win_rate", 0),
            )
            window_results.append(wr)

            for params, is_m, oos_m in window_param_results:
                all_param_results.append({
                    "window": w_idx,
                    **params,
                    "is_sharpe": is_m.get("sharpe", 0),
                    "is_return": is_m.get("total_return", 0),
                    "oos_sharpe": oos_m.get("sharpe", 0),
                    "oos_return": oos_m.get("total_return", 0),
                })

            if progress_callback:
                progress_callback((w_idx + 1) / len(windows))

        summary_df = pd.DataFrame(all_param_results) if all_param_results else pd.DataFrame()
        logger.info(
            "walkforward_completed",
            windows=len(window_results),
            avg_oos_ratio=round(self._compute_is_oos_ratio(window_results), 4),
        )

        return window_results, summary_df

    def _build_windows(
        self,
        start_date: datetime,
        end_date: datetime,
        train_months: int,
        test_months: int,
        roll_months: int,
        embargo_days: int,
    ) -> List[Tuple[Tuple[datetime, datetime], Tuple[datetime, datetime]]]:
        windows = []
        current_start = start_date

        while True:
            train_end = self._add_months(current_start, train_months)
            if train_end > end_date:
                break

            test_start = train_end + pd.Timedelta(days=embargo_days)
            test_end = self._add_months(test_start, test_months)
            if test_end > end_date:
                test_end = end_date

            if test_start >= test_end:
                break

            windows.append(
                ((current_start, train_end), (test_start, test_end))
            )

            current_start = self._add_months(current_start, roll_months)

        return windows

    @staticmethod
    def _add_months(dt: datetime, months: int) -> datetime:
        if isinstance(dt, pd.Timestamp):
            dt = dt.to_pydatetime()
        month = dt.month - 1 + months
        year = dt.year + month // 12
        month = month % 12 + 1
        day = min(dt.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                            31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
        return datetime(year, month, day, dt.hour, dt.minute, dt.second)


def generate_walkforward_report(
    window_results: List[WindowResult],
    summary_df: pd.DataFrame,
) -> str:
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        return _text_walkforward_report(window_results, summary_df)

    if not window_results:
        return "<p>No walk-forward results.</p>"

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=(
            "IS vs OOS Sharpe by Window",
            "IS vs OOS Return by Window",
            "Optimal Parameters Stability",
            "IS/OOS Ratio",
        ),
        vertical_spacing=0.12,
    )

    windows = list(range(len(window_results)))
    is_sharpes = [wr.is_sharpe for wr in window_results]
    oos_sharpes = [wr.oos_sharpe for wr in window_results]
    is_returns = [wr.is_return for wr in window_results]
    oos_returns = [wr.oos_return for wr in window_results]

    fig.add_trace(
        go.Bar(x=windows, y=is_sharpes, name="IS Sharpe", marker_color="blue", opacity=0.7),
        row=1, col=1,
    )
    fig.add_trace(
        go.Bar(x=windows, y=oos_sharpes, name="OOS Sharpe", marker_color="orange", opacity=0.7),
        row=1, col=1,
    )

    fig.add_trace(
        go.Bar(x=windows, y=is_returns, name="IS Return", marker_color="blue", opacity=0.7),
        row=1, col=2,
    )
    fig.add_trace(
        go.Bar(x=windows, y=oos_returns, name="OOS Return", marker_color="orange", opacity=0.7),
        row=1, col=2,
    )

    if not summary_df.empty and len(window_results) > 0:
        param_cols = [c for c in summary_df.columns if c not in ("window", "is_sharpe", "is_return", "oos_sharpe", "oos_return")]
        param_stability = {}
        for col in param_cols:
            if col in summary_df.columns:
                unique_vals = summary_df.groupby("window")[col].first()
                param_stability[col] = unique_vals.tolist() if len(unique_vals) == len(window_results) else []

        if param_stability:
            for param_name, values in param_stability.items():
                if values and len(values) == len(windows):
                    fig.add_trace(
                        go.Scatter(
                            x=windows, y=values,
                            mode="lines+markers",
                            name=param_name,
                        ),
                        row=2, col=1,
                    )

    ratios = []
    for wr in window_results:
        if wr.is_sharpe != 0:
            ratios.append(abs(wr.oos_sharpe / wr.is_sharpe))
        elif wr.is_return != 0:
            ratios.append(abs(wr.oos_return / wr.is_return))
        else:
            ratios.append(0.0)

    fig.add_trace(
        go.Bar(x=windows, y=ratios, name="IS/OOS Ratio", marker_color="green"),
        row=2, col=2,
    )
    fig.add_hline(y=0.7, line_dash="dash", line_color="red", row=2, col=2)

    fig.update_layout(
        title="Walk-Forward Analysis",
        height=800,
        showlegend=True,
        template="plotly_white",
    )

    return fig.to_html(include_plotlyjs="cdn", full_html=True)


def _text_walkforward_report(
    window_results: List[WindowResult],
    summary_df: pd.DataFrame,
) -> str:
    lines = ["=== Walk-Forward Analysis ===", ""]
    for wr in window_results:
        lines.append(f"Window {wr.window_idx + 1}:")
        lines.append(f"  Train: {wr.train_start.date()} - {wr.train_end.date()}")
        lines.append(f"  Test:  {wr.test_start.date()} - {wr.test_end.date()}")
        lines.append(f"  Best Params: {wr.best_params}")
        lines.append(f"  IS Sharpe: {wr.is_sharpe:.3f} | OOS Sharpe: {wr.oos_sharpe:.3f}")
        lines.append(f"  IS Return: {wr.is_return:.2%} | OOS Return: {wr.oos_return:.2%}")
        lines.append("")
    return "\n".join(lines)
