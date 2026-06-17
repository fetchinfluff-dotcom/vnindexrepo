from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import structlog

from src.strategy.config import StrategyConfig
from src.strategy.execution import ExecMode, _get_entry_price, _get_exit_price
from src.strategy.portfolio import VN100Portfolio
from src.strategy.risk import calculate_stop_loss, calculate_take_profit_levels
from src.strategy.signals import check_entry_conditions, check_exit_conditions
from src.strategy.sizing import calculate_position_size

logger = structlog.get_logger(__name__)

COMMISSION_RATE = 0.0015
PRICE_LIMIT_PCT = 0.07
T2_SETTLEMENT_DAYS = 2


@dataclass
class TradeRecord:
    ticker: str
    sector: str
    entry_date: datetime
    entry_price: float
    exit_date: Optional[datetime] = None
    exit_price: Optional[float] = None
    shares: int = 0
    pnl: float = 0.0
    return_pct: float = 0.0
    hold_days: int = 0
    exit_reason: Optional[str] = None
    mode: str = ""
    commission_entry: float = 0.0
    commission_exit: float = 0.0
    slippage_entry_bps: float = 0.0
    slippage_exit_bps: float = 0.0


@dataclass
class BacktestResult:
    mode: str
    trades: pd.DataFrame
    equity_curve: pd.DataFrame
    monthly_returns: pd.DataFrame
    daily_returns: pd.Series
    config: StrategyConfig
    execution_metrics: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_return(self) -> float:
        if self.equity_curve.empty:
            return 0.0
        return (
            self.equity_curve["nav"].iloc[-1]
            / self.equity_curve["nav"].iloc[0]
            - 1.0
        )

    @property
    def total_trades(self) -> int:
        return len(self.trades) if not self.trades.empty else 0

    @property
    def win_rate(self) -> float:
        if self.trades.empty:
            return 0.0
        wins = (self.trades["pnl"] > 0).sum()
        return wins / len(self.trades) if len(self.trades) > 0 else 0.0


class VN100Backtester:

    def __init__(
        self,
        config: StrategyConfig,
        features_data: Dict[str, pd.DataFrame],
        ticker_info: Dict[str, Dict[str, Any]],
        benchmark_data: Optional[pd.DataFrame] = None,
    ):
        self.config = config
        self.features_data = features_data
        self.ticker_info = ticker_info
        self.benchmark_data = benchmark_data

        self.ticker_universe = config.ticker_universe or list(features_data.keys())
        self.sector_map: Dict[str, str] = {
            tid: info.get("sector", "Others")
            for tid, info in ticker_info.items()
        }

        self._precompute_entry_signals()

    def _precompute_entry_signals(self) -> None:
        self._entry_signal_dates: Dict[str, pd.DatetimeIndex] = {}
        for ticker in self.ticker_universe:
            if ticker not in self.features_data:
                continue
            features = self.features_data[ticker]
            info = self.ticker_info.get(ticker, {})
            signal_dates = []
            for dt, row in features.iterrows():
                result = check_entry_conditions(row, info)
                if result["signal"] == 1:
                    signal_dates.append(dt)
            self._entry_signal_dates[ticker] = pd.DatetimeIndex(
                sorted(signal_dates)
            )

    def _check_exit_for_position(
        self,
        ticker: str,
        position: Any,
        row: pd.Series,
        date: datetime,
        prev_cross: bool,
    ) -> Optional[Dict[str, Any]]:
        pos_dict = {
            "entry_price": position.entry_price,
            "stop_loss": position.stop_loss,
        }
        exit_result = check_exit_conditions(row, pos_dict, prev_cross)
        if exit_result["action"] != "hold":
            return exit_result
        stop_loss = position.stop_loss
        if row.get("close", np.inf) <= stop_loss:
            return {"action": "sell_position", "reduce_pct": 1.0, "reason": "stop_loss"}
        return None

    def _get_fill_price(
        self,
        ticker: str,
        date: datetime,
        is_buy: bool,
        mode: ExecMode,
    ) -> Optional[float]:
        if ticker not in self.features_data:
            return None
        features = self.features_data[ticker]
        if date not in features.index:
            return None
        row = features.loc[date]

        if is_buy:
            base_price = _get_entry_price(row, mode)
        else:
            base_price = _get_exit_price(row, mode)

        if base_price is None:
            return None

        prev_date = features.index[features.index.get_loc(date) - 1] if features.index.get_loc(date) > 0 else None
        if prev_date is not None and prev_date in features.index:
            prev_close = features.loc[prev_date, "close"]
            ceiling = prev_close * (1.0 + PRICE_LIMIT_PCT)
            floor = prev_close * (1.0 - PRICE_LIMIT_PCT)
            base_price = max(min(base_price, ceiling), floor)

        return round(base_price, 2)

    def _compute_commission(self, price: float, shares: int) -> float:
        return price * shares * COMMISSION_RATE

    def run(
        self,
        mode: str = "buy_atc_sell_atc",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        progress_callback: Optional[callable] = None,
    ) -> BacktestResult:
        _mode = ExecMode(mode)
        logger.info("backtest_started", mode=mode)

        all_dates = sorted(set(
            dt
            for ticker in self.ticker_universe
            if ticker in self.features_data
            for dt in self.features_data[ticker].index
        ))
        all_dates = pd.DatetimeIndex(all_dates)
        if start_date:
            all_dates = all_dates[all_dates >= start_date]
        if end_date:
            all_dates = all_dates[all_dates <= end_date]

        if len(all_dates) == 0:
            logger.warning("no_trading_dates")
            return BacktestResult(
                mode=mode,
                trades=pd.DataFrame(),
                equity_curve=pd.DataFrame(),
                monthly_returns=pd.DataFrame(),
                daily_returns=pd.Series(dtype=float),
                config=self.config,
            )

        portfolio = VN100Portfolio(
            initial_cash=self.config.portfolio.initial_cash,
            max_positions=self.config.portfolio.max_positions,
            max_sector_pct=self.config.portfolio.max_sector_pct,
            min_cash_pct=self.config.portfolio.min_cash_pct,
            max_drawdown_pct=self.config.portfolio.max_drawdown_pct,
        )

        pending_buys: List[Dict[str, Any]] = []
        pending_sells: List[Dict[str, Any]] = []
        settlement_queue: List[Tuple[datetime, float]] = []
        trades: List[TradeRecord] = []
        equity_rows: List[Dict[str, Any]] = []
        open_trade_map: Dict[str, Optional[TradeRecord]] = {
            t: None for t in self.ticker_universe
        }

        n_dates = len(all_dates)
        for idx, date in enumerate(all_dates):
            if progress_callback and idx % 50 == 0:
                progress_callback(idx / n_dates)

            cash_released = sum(
                amt for settle_date, amt in settlement_queue if settle_date <= date
            )
            if cash_released > 0:
                portfolio.cash += cash_released
                settlement_queue = [
                    (d, a) for d, a in settlement_queue if d > date
                ]

            for order in pending_buys:
                ticker = order["ticker"]
                exec_date = date
                fill_price = self._get_fill_price(ticker, exec_date, True, _mode)
                if fill_price is None:
                    continue

                qty = order["quantity"]
                notional = qty * fill_price
                if notional > portfolio.cash + cash_released:
                    max_qty = int((portfolio.cash + cash_released) / fill_price)
                    max_qty = (max_qty // 100) * 100
                    if max_qty <= 0:
                        continue
                    qty = max_qty
                    notional = qty * fill_price

                commission = self._compute_commission(fill_price, qty)
                total_cost = notional + commission

                if total_cost > portfolio.cash:
                    continue

                slippage_bps = 0.0
                if mode in ("buy_atc_sell_atc", "buy_atc_sell_ato"):
                    slippage_bps = 0.05
                    expected = order.get("signal_price", fill_price)
                    if expected > 0:
                        slippage_bps = (fill_price / expected - 1.0) * 10000
                else:
                    slippage_bps = 0.1

                sector = self.sector_map.get(ticker, "Others")
                params = {
                    "portfolio_value": portfolio.total_value,
                    "price": fill_price,
                }
                stop_loss = calculate_stop_loss(
                    fill_price,
                    ticker_data=self._get_ticker_data(ticker, exec_date),
                    params=params,
                )

                pos = portfolio.open_position(
                    ticker=ticker,
                    quantity=qty,
                    price=fill_price,
                    stop_loss=stop_loss,
                    entry_date=exec_date,
                    reason="entry_signal",
                )
                if pos is not None:
                    portfolio.cash -= commission
                    trade_rec = TradeRecord(
                        ticker=ticker,
                        sector=sector,
                        entry_date=exec_date,
                        entry_price=fill_price,
                        shares=qty,
                        mode=mode,
                        commission_entry=commission,
                        slippage_entry_bps=slippage_bps,
                    )
                    open_trade_map[ticker] = trade_rec
                    trades.append(trade_rec)

            for order in pending_sells:
                ticker = order["ticker"]
                if ticker not in portfolio.positions:
                    continue

                exec_date = date
                fill_price = self._get_fill_price(ticker, exec_date, False, _mode)
                if fill_price is None:
                    continue

                reduce_pct = order.get("reduce_pct", 1.0)
                reason = order.get("reason", "exit_signal")

                if reduce_pct >= 1.0:
                    commission = self._compute_commission(
                        fill_price, portfolio.positions[ticker].quantity
                    )
                    closed = portfolio.close_position(
                        ticker=ticker,
                        exit_price=fill_price,
                        exit_date=exec_date,
                        reason=reason,
                    )
                    if closed is not None:
                        portfolio.cash -= commission
                        settlement_queue.append(
                            (exec_date + pd.Timedelta(days=T2_SETTLEMENT_DAYS), closed.quantity * fill_price)
                        )
                        trade_rec = open_trade_map.get(ticker)
                        if trade_rec is not None:
                            trade_rec.exit_date = exec_date
                            trade_rec.exit_price = fill_price
                            trade_rec.pnl = closed.pnl
                            hold_days = (exec_date - trade_rec.entry_date).days if trade_rec.entry_date else 0
                            trade_rec.hold_days = hold_days
                            trade_rec.exit_reason = reason
                            trade_rec.commission_exit = commission
                            if trade_rec.entry_price > 0:
                                trade_rec.return_pct = (
                                    fill_price / trade_rec.entry_price - 1.0
                                )
                            slippage_bps = 0.0
                            if mode in ("buy_atc_sell_atc", "buy_ato_sell_atc"):
                                slippage_bps = 0.05
                            else:
                                slippage_bps = 0.1
                            trade_rec.slippage_exit_bps = slippage_bps
                        open_trade_map[ticker] = None
                else:
                    commission = self._compute_commission(
                        fill_price,
                        int(portfolio.positions[ticker].quantity * reduce_pct),
                    )
                    portfolio.reduce_position(
                        ticker=ticker,
                        reduce_pct=reduce_pct,
                        exit_price=fill_price,
                        exit_date=exec_date,
                        reason=reason,
                    )
                    portfolio.cash -= commission

            pending_buys.clear()
            pending_sells.clear()

            for tic in list(portfolio.positions.keys()):
                if tic not in self.features_data or date not in self.features_data[tic].index:
                    continue
                row = self.features_data[tic].loc[date]
                portfolio.update_position(tic, row["close"], date)

            for tic in list(portfolio.positions.keys()):
                if tic not in self.features_data or date not in self.features_data[tic].index:
                    continue
                row = self.features_data[tic].loc[date]

                prev_date = all_dates[all_dates.get_loc(date) - 1] if all_dates.get_loc(date) > 0 else None
                prev_cross = False
                if prev_date is not None:
                    if tic in self.features_data and prev_date in self.features_data[tic].index:
                        prev_row = self.features_data[tic].loc[prev_date]
                        prev_close_val = prev_row.get("close", 0)
                        prev_ema20 = prev_row.get("ema20", 0)
                        prev_cross = bool(
                            prev_close_val > prev_ema20
                            and row.get("close", 0) < row.get("ema20", 0)
                        )

                exit_result = self._check_exit_for_position(
                    tic, portfolio.positions[tic], row, date, prev_cross
                )
                if exit_result is not None:
                    pending_sells.append({
                        "ticker": tic,
                        "reduce_pct": exit_result["reduce_pct"],
                        "reason": exit_result["reason"],
                    })

            for tic in self.ticker_universe:
                if tic in portfolio.positions:
                    continue
                if tic not in self._entry_signal_dates:
                    continue
                if date not in self._entry_signal_dates[tic]:
                    continue
                if tic not in self.features_data or date not in self.features_data[tic].index:
                    continue

                row = self.features_data[tic].loc[date]
                info = self.ticker_info.get(tic, {})
                current_positions_list = [
                    {"ticker": p.ticker, "notional": p.notional, "sector": p.sector}
                    for p in portfolio.positions.values()
                ]
                risk_params = {
                    "portfolio_value": portfolio.total_value,
                    "kelly_fraction": self.config.sizing.kelly_fraction,
                    "max_position_pct": self.config.sizing.max_position_pct,
                    "max_sector_pct": self.config.sizing.max_sector_pct,
                    "min_cash_pct": self.config.sizing.min_cash_pct,
                    "price": row["close"],
                }
                market_data = {
                    "close": row["close"],
                    "foreign_room_pct": info.get("foreign_room_pct", 100.0),
                    "dist_to_ceiling_pct": row.get("ceiling_buffer", 100.0),
                }

                size_result = calculate_position_size(
                    ticker=tic,
                    signal_strength=1.0,
                    available_cash=portfolio.cash,
                    current_positions=current_positions_list,
                    sector_map=self.sector_map,
                    risk_params=risk_params,
                    market_data=market_data,
                )

                if size_result["quantity"] > 0:
                    pending_buys.append({
                        "ticker": tic,
                        "quantity": size_result["quantity"],
                        "signal_price": row["close"],
                    })

            nav = portfolio.total_value
            pos_value = sum(p.notional for p in portfolio.positions.values())
            equity_rows.append({
                "date": date,
                "cash": round(portfolio.cash, 2),
                "positions_value": round(pos_value, 2),
                "nav": round(nav, 2),
                "drawdown": round(portfolio.drawdown, 6),
                "position_count": portfolio.position_count,
                "trading_paused": int(portfolio.trading_paused),
            })

        trades_df = self._build_trades_df(trades)
        equity_df = pd.DataFrame(equity_rows)
        if not equity_df.empty:
            equity_df["date"] = pd.to_datetime(equity_df["date"])
            equity_df.set_index("date", inplace=True)
            equity_df["daily_return"] = equity_df["nav"].pct_change().fillna(0.0)
            equity_df["cumulative_return"] = (1.0 + equity_df["daily_return"]).cumprod() - 1.0

        monthly_returns = self._build_monthly_returns(equity_df)
        daily_returns = equity_df["daily_return"] if not equity_df.empty else pd.Series(dtype=float)

        exec_metrics = {
            "total_trades": len(trades),
            "total_commission": sum(
                t.commission_entry + t.commission_exit for t in trades
            ),
            "avg_slippage_entry_bps": np.mean([t.slippage_entry_bps for t in trades]) if trades else 0.0,
            "avg_slippage_exit_bps": np.mean([t.slippage_exit_bps for t in trades if t.exit_date is not None]) if trades else 0.0,
        }

        logger.info(
            "backtest_completed",
            mode=mode,
            trades=len(trades),
            final_nav=round(equity_df["nav"].iloc[-1], 2) if not equity_df.empty else 0,
        )

        return BacktestResult(
            mode=mode,
            trades=trades_df,
            equity_curve=equity_df,
            monthly_returns=monthly_returns,
            daily_returns=daily_returns,
            config=self.config,
            execution_metrics=exec_metrics,
        )

    def _get_ticker_data(self, ticker: str, date: datetime) -> Dict[str, Any]:
        if ticker not in self.features_data:
            return {}
        features = self.features_data[ticker]
        if date not in features.index:
            return {}
        row = features.loc[date]
        return {
            "close": row.get("close", 0),
            "swing_low": row.get("swing_low", 0),
            "ema20": row.get("ema20", 0),
            "swing_high": row.get("swing_high", 0),
        }

    def _build_trades_df(self, trades: List[TradeRecord]) -> pd.DataFrame:
        if not trades:
            return pd.DataFrame(columns=[
                "ticker", "sector", "entry_date", "entry_price",
                "exit_date", "exit_price", "shares", "pnl", "return_pct",
                "hold_days", "exit_reason", "mode",
            ])
        records = []
        for t in trades:
            records.append({
                "ticker": t.ticker,
                "sector": t.sector,
                "entry_date": t.entry_date,
                "entry_price": t.entry_price,
                "exit_date": t.exit_date,
                "exit_price": t.exit_price if t.exit_price else 0.0,
                "shares": t.shares,
                "pnl": t.pnl,
                "return_pct": t.return_pct,
                "hold_days": t.hold_days,
                "exit_reason": t.exit_reason,
                "mode": t.mode,
                "commission_entry": t.commission_entry,
                "commission_exit": t.commission_exit,
                "slippage_entry_bps": t.slippage_entry_bps,
                "slippage_exit_bps": t.slippage_exit_bps,
            })
        df = pd.DataFrame(records)
        if not df.empty and "entry_date" in df.columns:
            df["entry_date"] = pd.to_datetime(df["entry_date"])
        if not df.empty and "exit_date" in df.columns:
            df["exit_date"] = pd.to_datetime(df["exit_date"])
        return df

    def _build_monthly_returns(self, equity_df: pd.DataFrame) -> pd.DataFrame:
        if equity_df.empty or "daily_return" not in equity_df.columns:
            return pd.DataFrame()
        monthly = equity_df["daily_return"].resample("ME").apply(
            lambda x: (1 + x).prod() - 1
        )
        result = monthly.to_frame(name="monthly_return")
        result["year"] = result.index.year
        result["month"] = result.index.month
        return result
