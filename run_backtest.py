#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import logging
import structlog

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.INFO, format="%(message)s")
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

ALL_MODES = [
    "buy_atc_sell_atc",
    "buy_atc_sell_ato",
    "buy_ato_sell_atc",
    "buy_ato_sell_ato",
]


def load_sample_data() -> Dict[str, Any]:
    np.random.seed(42)
    n_dates = 1260
    dates = pd.bdate_range("2018-01-02", periods=n_dates)
    tickers = ["VCB", "ACB", "BID", "CTG", "VPB", "MBB", "TCB", "HDB", "STB", "VNM",
               "HPG", "FPT", "MWG", "VIC", "VHM", "SSI", "VND", "GAS", "PLX", "SAB"]

    sectors = {
        "VCB": "Banking", "ACB": "Banking", "BID": "Banking", "CTG": "Banking",
        "VPB": "Banking", "MBB": "Banking", "TCB": "Banking", "HDB": "Banking",
        "STB": "Banking", "VNM": "Food & Beverage", "HPG": "Steel", "FPT": "Technology",
        "MWG": "Retail", "VIC": "Real Estate", "VHM": "Real Estate",
        "SSI": "Securities", "VND": "Securities", "GAS": "Oil & Gas",
        "PLX": "Oil & Gas", "SAB": "Food & Beverage",
    }

    features_data = {}
    ticker_info = {}

    for ticker in tickers:
        base_price = np.random.uniform(20000, 120000)
        prices = base_price * np.cumprod(1.0 + np.random.normal(0.0005, 0.015, n_dates))
        prices = np.maximum(prices, 5000)
        closes = prices
        opens = closes * (1.0 + np.random.normal(0, 0.005, n_dates))
        highs = np.maximum(closes, opens) * (1.0 + np.abs(np.random.normal(0, 0.003, n_dates)))
        lows = np.minimum(closes, opens) * (1.0 - np.abs(np.random.normal(0, 0.003, n_dates)))
        volumes = np.random.randint(500000, 5000000, n_dates).astype(float)

        df = pd.DataFrame({
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
            "ema20": pd.Series(closes).ewm(span=20).mean().values,
            "ema50": pd.Series(closes).ewm(span=50).mean().values,
            "ema200": pd.Series(closes).ewm(span=200).mean().values,
            "swing_high": pd.Series(closes).rolling(20).max().values,
            "swing_low": pd.Series(closes).rolling(20).min().values,
            "vol_ma20": pd.Series(volumes).rolling(20).mean().values,
            "vol_ratio": volumes / pd.Series(volumes).rolling(20).mean().values,
            "rsi_weekly": np.random.uniform(30, 80, n_dates),
            "foreign_net_buy_5d": np.random.uniform(-1e9, 1e9, n_dates),
            "foreign_ratio_5d": np.random.uniform(0.2, 0.6, n_dates),
            "foreign_net_sell_streak": np.random.randint(0, 7, n_dates).astype(float),
            "ceiling": closes * 1.07,
            "ceiling_buffer": closes / (closes * 1.07),
            "dist_ema20": (closes - pd.Series(closes).ewm(span=20).mean().values) / pd.Series(closes).ewm(span=20).mean().values,
            "atr14": np.random.uniform(500, 2000, n_dates),
        }, index=dates)
        df["ceiling_buffer"] = np.clip(df["ceiling_buffer"], 0.90, 1.0)
        df["vol_ratio"] = np.clip(df["vol_ratio"], 0.3, 5.0)
        features_data[ticker] = df

        ticker_info[ticker] = {
            "ticker": ticker,
            "sector": sectors.get(ticker, "Others"),
            "foreign_room_limit": np.random.uniform(0.2, 0.49),
            "current_foreign_own": np.random.uniform(0.05, 0.25),
            "foreign_room_pct": np.random.uniform(5, 30),
        }

    vnindex_close = 1000 * np.cumprod(1.0 + np.random.normal(0.0003, 0.008, n_dates))
    benchmark = pd.DataFrame({
        "close": vnindex_close,
        "vn30_close": vnindex_close * np.random.uniform(0.8, 1.2, n_dates),
        "vn100_close": vnindex_close * np.random.uniform(0.7, 1.1, n_dates),
    }, index=dates)

    return {
        "features_data": features_data,
        "ticker_info": ticker_info,
        "benchmark_data": benchmark,
        "tickers": tickers,
    }


def run_single_mode(
    config,
    features_data,
    ticker_info,
    benchmark_data,
    mode: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    from src.backtest.engine import VN100Backtester
    from src.backtest.analytics import generate_tearsheet, compute_metrics

    logger.info("running_backtest", mode=mode)

    bt = VN100Backtester(config, features_data, ticker_info, benchmark_data)
    result = bt.run(mode=mode, start_date=start_date, end_date=end_date)

    benchmark_returns = None
    if benchmark_data is not None and "close" in benchmark_data.columns:
        benchmark_returns = benchmark_data["close"].pct_change().dropna()

    metrics = compute_metrics(
        result.trades, result.equity_curve, result.daily_returns,
        benchmark_returns, config,
    )

    tearsheet_html = generate_tearsheet(
        result.trades, result.equity_curve, result.daily_returns,
        result.monthly_returns, benchmark_data, config,
        title=f"Backtest Tearsheet - {mode}",
    )

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "tearsheet.html"), "w", encoding="utf-8") as f:
            f.write(tearsheet_html)
        if not result.trades.empty:
            result.trades.to_csv(os.path.join(output_dir, "trades.csv"), index=False)
        if not result.equity_curve.empty:
            result.equity_curve.to_csv(os.path.join(output_dir, "equity_curve.csv"))
        if result.monthly_returns is not None and not result.monthly_returns.empty:
            result.monthly_returns.to_csv(os.path.join(output_dir, "monthly_returns.csv"))
        logger.info("results_saved", mode=mode, output=output_dir)

    return {
        "result": result,
        "metrics": metrics,
        "tearsheet_html": tearsheet_html,
    }


def run_comparison(
    config,
    features_data,
    ticker_info,
    benchmark_data,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    output_dir: str = "backtest_results",
):
    from src.backtest.analytics import generate_comparison_report

    results = {}
    for mode in ALL_MODES:
        mode_dir = os.path.join(output_dir, mode)
        out = run_single_mode(
            config, features_data, ticker_info, benchmark_data,
            mode, start_date, end_date, mode_dir,
        )
        results[mode] = out["result"]

    benchmark_returns = None
    if benchmark_data is not None and "close" in benchmark_data.columns:
        benchmark_returns = benchmark_data["close"].pct_change().dropna()

    report_html = generate_comparison_report(results, benchmark_returns)
    comparison_path = os.path.join(output_dir, "comparison_report.html")
    with open(comparison_path, "w", encoding="utf-8") as f:
        f.write(report_html)

    logger.info("comparison_report_saved", path=comparison_path)

    print("\n" + "=" * 80)
    print(f"{'Execution Mode Comparison':^80}")
    print("=" * 80)
    header = f"{'Mode':<25} {'Return':<10} {'CAGR':<10} {'Sharpe':<10} {'MaxDD':<10} {'WinRate':<10} {'Trades':<8}"
    print(header)
    print("-" * 80)
    for mode in ALL_MODES:
        r = results[mode]
        from src.backtest.analytics import compute_metrics
        m = compute_metrics(r.trades, r.equity_curve, r.daily_returns, benchmark_returns)
        print(
            f"{mode:<25} {m.get('total_return', 0):<10.2%} {m.get('cagr', 0):<10.2%} "
            f"{m.get('sharpe', 0):<10.2f} {m.get('max_drawdown', 0):<10.2%} "
            f"{m.get('win_rate', 0):<10.2%} {m.get('total_trades', 0):<8}"
        )
    print("=" * 80)

    return results


def main():
    parser = argparse.ArgumentParser(description="VN100 Close-to-Close Backtest Engine")
    parser.add_argument("--mode", type=str, default="buy_atc_sell_atc",
                        choices=ALL_MODES + ["all"],
                        help="Execution mode")
    parser.add_argument("--compare_all", action="store_true",
                        help="Compare all 4 execution modes")
    parser.add_argument("--start", type=str, default="2018-01-01",
                        help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="2024-12-31",
                        help="End date (YYYY-MM-DD)")
    parser.add_argument("--output", type=str, default="backtest_results",
                        help="Output directory")
    parser.add_argument("--walkforward", action="store_true",
                        help="Run walk-forward optimization")
    parser.add_argument("--monte-carlo", action="store_true",
                        help="Run Monte Carlo simulation")
    parser.add_argument("--regime", action="store_true",
                        help="Run regime analysis")
    parser.add_argument("--use-sample-data", action="store_true", default=True,
                        help="Use generated sample data (default: True)")

    args = parser.parse_args()

    start_date = pd.Timestamp(args.start) if args.start else None
    end_date = pd.Timestamp(args.end) if args.end else None

    logger.info("loading_data")
    data = load_sample_data()
    features_data = data["features_data"]
    ticker_info = data["ticker_info"]
    benchmark_data = data["benchmark_data"]
    tickers = data["tickers"]

    from src.strategy.config import StrategyConfig, EntryConfig, ExitConfig, PositionSizingConfig, RiskConfig, PortfolioConfig, ExecutionConfig

    config = StrategyConfig(
        entry=EntryConfig(
            macro_bull_required=True,
            pullback_threshold=0.01,
            foreign_net_buy_min=0.0,
            foreign_ratio_min=0.40,
            volume_ratio_min=1.2,
            candle_body_ratio_min=0.50,
            ceiling_buffer_pct=0.97,
            weekly_rsi_max=70.0,
            foreign_room_max_pct=0.95,
            sector_exposure_max_pct=0.20,
        ),
        exit=ExitConfig(
            death_cross_reduce_pct=0.50,
            foreign_sell_streak_days=5,
            foreign_sell_streak_reduce_pct=0.30,
            tp1_reduce_pct=0.40,
            tp1_swing_high_threshold=0.99,
            tp2_reduce_pct=0.30,
            tp2_r_multiple=2.5,
            ema20_trail_reduce_pct=1.0,
        ),
        sizing=PositionSizingConfig(
            kelly_fraction=0.25,
            max_position_pct=0.10,
            max_sector_pct=0.20,
            min_cash_pct=0.30,
            foreign_room_reduce_threshold=10.0,
            foreign_room_block_threshold=5.0,
            ceiling_buffer_reduce_threshold=2.0,
            ceiling_buffer_min_factor=0.30,
        ),
        risk=RiskConfig(
            max_loss_pct=0.92,
            tp1_reduce_pct=0.40,
            tp2_r_multiple=2.5,
            trail_reduce_pct=0.30,
        ),
        portfolio=PortfolioConfig(
            initial_cash=1_000_000_000.0,
            max_positions=10,
            max_sector_pct=0.20,
            min_cash_pct=0.30,
            max_drawdown_pct=0.15,
        ),
        execution=ExecutionConfig(
            slippage_ato=0.001,
            slippage_atc=0.0005,
            default_mode="buy_atc_sell_atc",
        ),
        ticker_universe=tickers,
        sector_map={t: info["sector"] for t, info in ticker_info.items()},
    )

    if args.compare_all:
        run_comparison(config, features_data, ticker_info, benchmark_data,
                       start_date, end_date, args.output)
        return

    if args.mode == "all":
        for mode in ALL_MODES:
            run_single_mode(
                config, features_data, ticker_info, benchmark_data,
                mode, start_date, end_date,
                os.path.join(args.output, mode),
            )
        return

    result = run_single_mode(
        config, features_data, ticker_info, benchmark_data,
        args.mode, start_date, end_date,
        os.path.join(args.output, args.mode),
    )

    if args.walkforward:
        logger.info("running_walkforward")
        from src.backtest.walkforward import WalkForwardOptimizer, generate_walkforward_report

        optimizer = WalkForwardOptimizer(
            backtester_factory=lambda c, fd, ti, bd: __import__(
                "src.backtest.engine", fromlist=["VN100Backtester"]
            ).VN100Backtester(c, fd, ti, bd),
            config=config,
            features_data=features_data,
            ticker_info=ticker_info,
            benchmark_data=benchmark_data,
        )
        window_results, summary_df = optimizer.optimize(
            mode=args.mode,
            train_months=24,
            test_months=6,
            roll_months=3,
            embargo_days=5,
        )
        wf_html = generate_walkforward_report(window_results, summary_df)
        wf_path = os.path.join(args.output, args.mode, "walkforward.html")
        os.makedirs(os.path.dirname(wf_path), exist_ok=True)
        with open(wf_path, "w", encoding="utf-8") as f:
            f.write(wf_html)
        logger.info("walkforward_saved", path=wf_path)

    if args.monte_carlo:
        logger.info("running_monte_carlo")
        from src.backtest.monte_carlo import MonteCarloSimulator, generate_monte_carlo_report

        simulator = MonteCarloSimulator(
            backtester_factory=lambda c, fd, ti, bd: __import__(
                "src.backtest.engine", fromlist=["VN100Backtester"]
            ).VN100Backtester(c, fd, ti, bd),
            config=config,
            features_data=features_data,
            ticker_info=ticker_info,
            benchmark_data=benchmark_data,
            n_runs=200,
            random_seed=42,
        )
        mc_result = simulator.run(
            mode=args.mode,
            start_date=start_date,
            end_date=end_date,
        )
        mc_html = generate_monte_carlo_report(mc_result)
        mc_path = os.path.join(args.output, args.mode, "monte_carlo.html")
        os.makedirs(os.path.dirname(mc_path), exist_ok=True)
        with open(mc_path, "w", encoding="utf-8") as f:
            f.write(mc_html)

        ci = mc_result.ci_90()
        logger.info("monte_carlo_ci", ci_90=ci)
        print("\nMonte Carlo 90% CI:")
        for k, (lo, hi) in ci.items():
            print(f"  {k}: [{lo:.4f}, {hi:.4f}]")
        print(f"\nPercentile Table:")
        print(mc_result.percentile_table().to_string(index=False))

    if args.regime:
        logger.info("running_regime_analysis")
        from src.backtest.regime_analysis import (
            classify_regime, regime_performance, generate_regime_report,
        )

        if benchmark_data is not None:
            vnindex = benchmark_data["close"]
            ema50 = vnindex.ewm(span=50).mean()
            regimes = classify_regime(vnindex, ema50)
        else:
            logger.warning("no_benchmark_data_for_regime")
            return

        benchmark_returns = None
        if benchmark_data is not None:
            benchmark_returns = benchmark_data["close"].pct_change().dropna()

        regime_results = regime_performance(
            result["result"].trades,
            result["result"].equity_curve,
            result["result"].daily_returns,
            regimes,
            benchmark_returns,
        )

        regime_html = generate_regime_report(regime_results, regimes)
        regime_path = os.path.join(args.output, args.mode, "regime_analysis.html")
        os.makedirs(os.path.dirname(regime_path), exist_ok=True)
        with open(regime_path, "w", encoding="utf-8") as f:
            f.write(regime_html)

        print("\nRegime Analysis:")
        print("-" * 60)
        for regime in ["bull", "bear", "sideways"]:
            r = regime_results.get(regime, {})
            print(f"{regime.upper():<12} Return: {r.get('total_return', 0):>8.2%}  "
                  f"WinRate: {r.get('win_rate', 0):>6.2%}  "
                  f"Trades: {r.get('trade_count', 0):>4d}  "
                  f"PF: {r.get('profit_factor', 0):>6.2f}")


if __name__ == "__main__":
    main()
