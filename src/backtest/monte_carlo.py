from __future__ import annotations

import random
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import structlog

from src.strategy.config import StrategyConfig

logger = structlog.get_logger(__name__)

STRESS_PERIODS = {
    "covid_2020": ("2020-01-01", "2020-06-30"),
    "rate_hike_2022": ("2022-04-01", "2022-12-31"),
    "vn_correction_2024": ("2024-04-01", "2024-12-31"),
}


@dataclass
class MonteCarloResult:
    n_runs: int = 0
    cagr_values: List[float] = field(default_factory=list)
    maxdd_values: List[float] = field(default_factory=list)
    sharpe_values: List[float] = field(default_factory=list)
    win_rate_values: List[float] = field(default_factory=list)
    profit_factor_values: List[float] = field(default_factory=list)

    def percentile_table(self) -> pd.DataFrame:
        data = {
            "Metric": ["CAGR", "Max DD", "Sharpe", "Win Rate", "Profit Factor"],
            "5%": [
                np.percentile(self.cagr_values, 5) if self.cagr_values else 0,
                np.percentile(self.maxdd_values, 5) if self.maxdd_values else 0,
                np.percentile(self.sharpe_values, 5) if self.sharpe_values else 0,
                np.percentile(self.win_rate_values, 5) if self.win_rate_values else 0,
                np.percentile(self.profit_factor_values, 5) if self.profit_factor_values else 0,
            ],
            "25%": [
                np.percentile(self.cagr_values, 25) if self.cagr_values else 0,
                np.percentile(self.maxdd_values, 25) if self.maxdd_values else 0,
                np.percentile(self.sharpe_values, 25) if self.sharpe_values else 0,
                np.percentile(self.win_rate_values, 25) if self.win_rate_values else 0,
                np.percentile(self.profit_factor_values, 25) if self.profit_factor_values else 0,
            ],
            "50%": [
                np.percentile(self.cagr_values, 50) if self.cagr_values else 0,
                np.percentile(self.maxdd_values, 50) if self.maxdd_values else 0,
                np.percentile(self.sharpe_values, 50) if self.sharpe_values else 0,
                np.percentile(self.win_rate_values, 50) if self.win_rate_values else 0,
                np.percentile(self.profit_factor_values, 50) if self.profit_factor_values else 0,
            ],
            "75%": [
                np.percentile(self.cagr_values, 75) if self.cagr_values else 0,
                np.percentile(self.maxdd_values, 75) if self.maxdd_values else 0,
                np.percentile(self.sharpe_values, 75) if self.sharpe_values else 0,
                np.percentile(self.win_rate_values, 75) if self.win_rate_values else 0,
                np.percentile(self.profit_factor_values, 75) if self.profit_factor_values else 0,
            ],
            "95%": [
                np.percentile(self.cagr_values, 95) if self.cagr_values else 0,
                np.percentile(self.maxdd_values, 95) if self.maxdd_values else 0,
                np.percentile(self.sharpe_values, 95) if self.sharpe_values else 0,
                np.percentile(self.win_rate_values, 95) if self.win_rate_values else 0,
                np.percentile(self.profit_factor_values, 95) if self.profit_factor_values else 0,
            ],
        }
        df = pd.DataFrame(data)
        for col in ["5%", "25%", "50%", "75%", "95%"]:
            df[col] = df[col].apply(lambda x: f"{x:.4f}")
        return df

    def ci_90(self) -> Dict[str, Tuple[float, float]]:
        return {
            "cagr": (
                np.percentile(self.cagr_values, 5) if self.cagr_values else 0,
                np.percentile(self.cagr_values, 95) if self.cagr_values else 0,
            ),
            "maxdd": (
                np.percentile(self.maxdd_values, 5) if self.maxdd_values else 0,
                np.percentile(self.maxdd_values, 95) if self.maxdd_values else 0,
            ),
            "sharpe": (
                np.percentile(self.sharpe_values, 5) if self.sharpe_values else 0,
                np.percentile(self.sharpe_values, 95) if self.sharpe_values else 0,
            ),
            "win_rate": (
                np.percentile(self.win_rate_values, 5) if self.win_rate_values else 0,
                np.percentile(self.win_rate_values, 95) if self.win_rate_values else 0,
            ),
        }


class MonteCarloSimulator:

    def __init__(
        self,
        backtester_factory: callable,
        config: StrategyConfig,
        features_data: Dict[str, pd.DataFrame],
        ticker_info: Dict[str, Dict[str, Any]],
        benchmark_data: Optional[pd.DataFrame] = None,
        n_runs: int = 1000,
        random_seed: int = 42,
        noise_pct: float = 0.10,
    ):
        self.backtester_factory = backtester_factory
        self.config = config
        self.features_data = features_data
        self.ticker_info = ticker_info
        self.benchmark_data = benchmark_data
        self.n_runs = n_runs
        self.random_seed = random_seed
        self.noise_pct = noise_pct

    def run(
        self,
        mode: str = "buy_atc_sell_atc",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        progress_callback: Optional[callable] = None,
    ) -> MonteCarloResult:
        np.random.seed(self.random_seed)
        random.seed(self.random_seed)

        bt = self.backtester_factory(
            self.config, self.features_data, self.ticker_info, self.benchmark_data
        )
        base_result = bt.run(mode=mode, start_date=start_date, end_date=end_date)

        if base_result.trades.empty:
            logger.warning("monte_carlo_base_trades_empty")
            return MonteCarloResult()

        base_trades = base_result.trades.copy()

        result = MonteCarloResult(n_runs=self.n_runs)

        for run_idx in range(self.n_runs):
            if progress_callback:
                progress_callback(run_idx / self.n_runs)

            shuffled_trades = base_trades.sample(
                frac=1.0, replace=False, random_state=self.random_seed + run_idx
            ).reset_index(drop=True)

            noise = 1.0 + np.random.uniform(
                -self.noise_pct, self.noise_pct, size=len(shuffled_trades)
            )
            noisy_trades = shuffled_trades.copy()
            if "entry_price" in noisy_trades.columns:
                noisy_trades["entry_price"] = noisy_trades["entry_price"] * noise
            if "exit_price" in noisy_trades.columns:
                noisy_exit = shuffled_trades["exit_price"].copy()
                valid_exit = noisy_exit > 0
                if valid_exit.any():
                    noisy_exit.loc[valid_exit] = (
                        noisy_exit.loc[valid_exit] * noise[valid_exit]
                    )
                noisy_trades["exit_price"] = noisy_exit
            if "pnl" in noisy_trades.columns and "shares" in noisy_trades.columns:
                noisy_trades["pnl"] = (
                    noisy_trades["exit_price"] - noisy_trades["entry_price"]
                ) * noisy_trades["shares"]
                noisy_trades["return_pct"] = (
                    noisy_trades["exit_price"] / noisy_trades["entry_price"] - 1.0
                )

            sim_equity = self._simulate_equity_from_trades(
                noisy_trades, base_result.equity_curve
            )
            sim_daily = sim_equity["nav"].pct_change().fillna(0.0)

            from src.backtest.analytics import (
                compute_cagr,
                compute_max_drawdown,
                compute_sharpe,
            )

            cagr_val = compute_cagr(sim_equity["nav"])
            maxdd = compute_max_drawdown(sim_equity["nav"])
            sharpe = compute_sharpe(sim_daily)

            result.cagr_values.append(cagr_val)
            result.maxdd_values.append(maxdd)
            result.sharpe_values.append(sharpe)

            if not noisy_trades.empty and "pnl" in noisy_trades.columns:
                wins = (noisy_trades["pnl"] > 0).sum()
                wr = wins / len(noisy_trades) if len(noisy_trades) > 0 else 0
                result.win_rate_values.append(wr)
                gross_profit = noisy_trades.loc[noisy_trades["pnl"] > 0, "pnl"].sum()
                gross_loss = abs(noisy_trades.loc[noisy_trades["pnl"] < 0, "pnl"].sum())
                pf = gross_profit / gross_loss if gross_loss > 0 else (np.inf if gross_profit > 0 else 0)
                result.profit_factor_values.append(pf)

        return result

    def _simulate_equity_from_trades(
        self, trades: pd.DataFrame, base_equity: pd.DataFrame
    ) -> pd.DataFrame:
        if trades.empty or base_equity.empty:
            return base_equity.copy()

        sim = base_equity.copy()
        initial_nav = sim["nav"].iloc[0]
        total_pnl = trades["pnl"].sum()
        cum_pnl = 0.0
        trade_idx = 0

        for i in range(1, len(sim)):
            cum_pnl = trades.iloc[:trade_idx]["pnl"].sum() if trade_idx > 0 else 0.0
            sim.iloc[i, sim.columns.get_loc("nav")] = initial_nav + cum_pnl

            while (trade_idx < len(trades)
                   and trades.iloc[trade_idx].get("exit_date", sim.index[i]) <= sim.index[i]):
                trade_idx += 1

        final_pnl = trades["pnl"].sum()
        sim["nav"] = initial_nav + np.linspace(0, final_pnl, len(sim))
        return sim

    def stress_test(
        self,
        mode: str = "buy_atc_sell_atc",
        period_name: str = "covid_2020",
    ) -> Dict[str, Any]:
        if period_name not in STRESS_PERIODS:
            logger.warning("unknown_stress_period", period=period_name)
            return {"error": f"Unknown period: {period_name}"}

        start_str, end_str = STRESS_PERIODS[period_name]
        start_date = pd.Timestamp(start_str)
        end_date = pd.Timestamp(end_str)

        bt = self.backtester_factory(
            self.config, self.features_data, self.ticker_info, self.benchmark_data
        )
        result = bt.run(mode=mode, start_date=start_date, end_date=end_date)

        from src.backtest.analytics import compute_metrics
        metrics = compute_metrics(
            result.trades, result.equity_curve, result.daily_returns
        )
        metrics["period"] = period_name
        return metrics

    def run_all_stress_tests(self, mode: str = "buy_atc_sell_atc") -> Dict[str, Any]:
        results = {}
        for period_name in STRESS_PERIODS:
            results[period_name] = self.stress_test(mode, period_name)
        return results


def generate_monte_carlo_report(result: MonteCarloResult) -> str:
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        return _text_monte_carlo_report(result)

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=("CAGR Distribution", "Max DD Distribution", "Sharpe Distribution", "Win Rate Distribution"),
    )

    if result.cagr_values:
        fig.add_trace(
            go.Histogram(x=result.cagr_values, nbinsx=50, name="CAGR", marker_color="blue", opacity=0.7),
            row=1, col=1,
        )
        ci_lo, ci_hi = np.percentile(result.cagr_values, 5), np.percentile(result.cagr_values, 95)
        fig.add_vline(x=ci_lo, line_dash="dash", line_color="red", row=1, col=1)
        fig.add_vline(x=ci_hi, line_dash="dash", line_color="red", row=1, col=1)

    if result.maxdd_values:
        fig.add_trace(
            go.Histogram(x=result.maxdd_values, nbinsx=50, name="Max DD", marker_color="red", opacity=0.7),
            row=1, col=2,
        )

    if result.sharpe_values:
        fig.add_trace(
            go.Histogram(x=result.sharpe_values, nbinsx=50, name="Sharpe", marker_color="green", opacity=0.7),
            row=2, col=1,
        )

    if result.win_rate_values:
        fig.add_trace(
            go.Histogram(x=result.win_rate_values, nbinsx=50, name="Win Rate", marker_color="orange", opacity=0.7),
            row=2, col=2,
        )

    fig.update_layout(
        title="Monte Carlo Simulation Results",
        height=800,
        showlegend=False,
        template="plotly_white",
    )

    pt = result.percentile_table()
    table_html = pt.to_html(index=False, classes="table table-striped")

    full_html = fig.to_html(include_plotlyjs="cdn", full_html=False)
    html = f"""<html><head><title>Monte Carlo Report</title></head><body>
    {full_html}
    <h2>Percentile Table</h2>
    {table_html}
    </body></html>"""
    return html


def _text_monte_carlo_report(result: MonteCarloResult) -> str:
    lines = ["=== Monte Carlo Simulation ===", ""]
    lines.append(f"Runs: {result.n_runs}")
    lines.append("")
    pt = result.percentile_table()
    lines.append(pt.to_string(index=False))
    lines.append("")
    ci = result.ci_90()
    lines.append("90% Confidence Intervals:")
    for k, (lo, hi) in ci.items():
        lines.append(f"  {k}: [{lo:.4f}, {hi:.4f}]")
    return "\n".join(lines)
