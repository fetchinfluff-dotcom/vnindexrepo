from __future__ import annotations

import asyncio
import os
from datetime import datetime, time
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger(__name__)


class DailySignalGenerator:
    """
    Cron job: runs daily at 15:00-15:30 VN time.
    Pulls data, computes features, generates entry/exit signals,
    calculates position sizes, saves orders to Supabase, and sends alerts.
    """

    def __init__(self, dnse_client, supabase_client, strategy_module, config: dict):
        self.dnse = dnse_client
        self.supabase = supabase_client
        self.strategy = strategy_module
        self.config = config

    async def run(self) -> dict:
        """Main execution pipeline."""
        if not await self._is_trading_day():
            return {"status": "skipped", "reason": "not_trading_day"}

        latest_bars = await self._pull_vn100_latest_bars()
        foreign_flow = await self._pull_foreign_flow()
        portfolio_state = await self._load_portfolio_state()

        features = self._compute_features(latest_bars, foreign_flow)
        ticker_info = self._build_ticker_info(latest_bars)

        exit_orders = self._generate_exit_orders(portfolio_state, features)
        entry_orders = self._generate_entry_orders(portfolio_state, features, ticker_info, exit_orders)

        all_orders = exit_orders + entry_orders
        await self._save_orders(all_orders)
        await self._update_portfolio_state(portfolio_state, all_orders)

        if all_orders:
            await self._send_alerts(all_orders, portfolio_state)

        return {
            "status": "success",
            "date": str(datetime.now().date()),
            "signals_generated": len(all_orders),
            "buys": len([o for o in all_orders if o["action"] == "BUY"]),
            "sells": len([o for o in all_orders if o["action"] in ("SELL", "SELL_ALL", "REDUCE")]),
            "nav": portfolio_state.get("current_nav"),
            "cash": portfolio_state.get("available_cash"),
            "positions": len(portfolio_state.get("positions", [])),
        }

    async def _is_trading_day(self) -> bool:
        try:
            result = await self.supabase.table("calendar").select("is_trading_day").eq(
                "date", datetime.now().date().isoformat()
            ).execute()
            return result.data[0]["is_trading_day"] if result.data else False
        except Exception:
            logger.warning("calendar_check_failed, defaulting to weekday")
            return datetime.now().weekday() < 5

    async def _pull_vn100_latest_bars(self) -> pd.DataFrame:
        tickers = await self._get_vn100_tickers()
        all_data = []
        for i in range(0, len(tickers), 10):
            batch = tickers[i:i + 10]
            tasks = [self.dnse.get_daily_bars(t, 260) for t in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    logger.error("data_pull_error", error=str(r))
                    continue
                all_data.append(r)
        return pd.concat(all_data) if all_data else pd.DataFrame()

    async def _pull_foreign_flow(self) -> pd.DataFrame:
        tickers = await self._get_vn100_tickers()
        records = []
        for i in range(0, len(tickers), 10):
            batch = tickers[i:i + 10]
            tasks = [self.dnse.get_foreign_flow(t, 20) for t in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    continue
                records.append(r)
        return pd.concat(records) if records else pd.DataFrame()

    async def _get_vn100_tickers(self) -> List[str]:
        try:
            result = await self.supabase.table("vn100_constituents").select("ticker").execute()
            return [r["ticker"] for r in result.data]
        except Exception:
            return self.config.get("ticker_universe", [])

    async def _load_portfolio_state(self) -> dict:
        try:
            result = await self.supabase.table("portfolio_state").select("*").order("created_at", desc=True).limit(1).execute()
            if result.data:
                return result.data[0]
        except Exception:
            logger.warning("failed_to_load_portfolio_state")
        return {
            "available_cash": self.config.get("initial_capital", 1_000_000_000),
            "current_nav": self.config.get("initial_capital", 1_000_000_000),
            "positions": [],
            "peak_value": self.config.get("initial_capital", 1_000_000_000),
        }

    def _build_ticker_info(self, bars: pd.DataFrame) -> Dict[str, dict]:
        info = {}
        for ticker in bars["ticker"].unique() if "ticker" in bars.columns else []:
            info[ticker] = {
                "ticker": ticker,
                "sector": self.config.get("sector_map", {}).get(ticker, "Others"),
                "foreign_room_limit": 0.49,
                "current_foreign_own": 0.0,
                "foreign_room_pct": 100.0,
            }
        return info

    def _compute_features(self, bars: pd.DataFrame, foreign: pd.DataFrame) -> pd.DataFrame:
        if bars.empty:
            return bars

        for span in (200, 50, 20):
            bars[f"ema{span}"] = bars.groupby("ticker")["close"].transform(
                lambda x: x.ewm(span=span).mean()
            )

        bars["vol_ma20"] = bars.groupby("ticker")["volume"].transform(
            lambda x: x.rolling(20).mean()
        )
        bars["vol_ratio"] = bars["volume"] / bars["vol_ma20"].replace(0, np.nan)

        def find_swing_highs(g):
            vals = g["high"].values
            result = np.full(len(vals), np.nan)
            for i in range(10, len(vals) - 5):
                if vals[i] == max(vals[i - 10:i + 6]):
                    result[i] = vals[i]
            return pd.Series(result, index=g.index)

        def find_swing_lows(g):
            vals = g["low"].values
            result = np.full(len(vals), np.nan)
            for i in range(10, len(vals) - 5):
                if vals[i] == min(vals[i - 10:i + 6]):
                    result[i] = vals[i]
            return pd.Series(result, index=g.index)

        bars["swing_high"] = bars.groupby("ticker", group_keys=False).apply(find_swing_highs)
        bars["swing_low"] = bars.groupby("ticker", group_keys=False).apply(find_swing_lows)
        bars["swing_high"] = bars.groupby("ticker")["swing_high"].transform(lambda x: x.ffill())
        bars["swing_low"] = bars.groupby("ticker")["swing_low"].transform(lambda x: x.ffill())

        if not foreign.empty and "ticker" in foreign.columns:
            foreign_agg = foreign.groupby("ticker").agg({
                "net_buy": lambda x: x.tail(5).sum(),
                "buy_volume": lambda x: x.tail(5).sum(),
                "sell_volume": lambda x: x.tail(5).sum(),
            }).reset_index()
            foreign_agg["foreign_ratio_5d"] = foreign_agg["buy_volume"] / (
                foreign_agg["buy_volume"] + foreign_agg["sell_volume"]
            ).replace(0, np.nan)
            foreign_agg["foreign_net_buy_5d"] = foreign_agg["net_buy"]
            bars = bars.merge(
                foreign_agg[["ticker", "foreign_net_buy_5d", "foreign_ratio_5d"]],
                on="ticker", how="left"
            )
        else:
            bars["foreign_net_buy_5d"] = 0.0
            bars["foreign_ratio_5d"] = 0.5

        bars["ceiling"] = bars["close"] * 1.07
        bars["ceiling_buffer"] = bars["close"] / bars["ceiling"]
        bars["dist_ema20"] = (bars["close"] - bars["ema20"]) / bars["ema20"].replace(0, np.nan)
        bars["atr14"] = bars.groupby("ticker")["close"].transform(
            lambda x: (x.diff().abs()).rolling(14).mean()
        )
        bars["rsi_weekly"] = 50.0

        return bars

    def _generate_exit_orders(self, portfolio: dict, features: pd.DataFrame) -> List[dict]:
        orders = []
        today = datetime.now().date().isoformat()

        for pos in portfolio.get("positions", []):
            ticker = pos["ticker"]
            ticker_feat = features[features["ticker"] == ticker]
            if ticker_feat.empty:
                continue
            row = ticker_feat.iloc[-1]

            pos_info = {
                "entry_price": pos.get("entry_price", 0),
                "shares": pos.get("shares", pos.get("quantity", 0)),
                "stop_loss": pos.get("stop_loss", pos.get("entry_price", 0) * 0.92),
            }
            prev_row = ticker_feat.iloc[-2] if len(ticker_feat) >= 2 else None

            exit_result = self.strategy.signals.check_exit_conditions(row, pos_info)

            if exit_result["action"] == "sell_all":
                qty = pos_info["shares"]
                if qty > 0:
                    orders.append({
                        "ticker": ticker,
                        "action": "SELL_ALL",
                        "quantity": qty,
                        "execution": "ATC",
                        "reason": exit_result["reason"],
                        "signal_strength": 1.0,
                        "date": today,
                    })
            elif exit_result["action"] == "sell_position":
                qty = pos_info["shares"]
                if qty > 0:
                    orders.append({
                        "ticker": ticker,
                        "action": "SELL_ALL",
                        "quantity": qty,
                        "execution": "ATC",
                        "reason": exit_result["reason"],
                        "signal_strength": 1.0,
                        "date": today,
                    })
            elif exit_result["action"] == "reduce":
                reduce_pct = exit_result.get("reduce_pct", 0.5)
                qty = int(pos_info["shares"] * reduce_pct)
                if qty > 0:
                    orders.append({
                        "ticker": ticker,
                        "action": "REDUCE",
                        "quantity": qty,
                        "execution": "ATC",
                        "reason": exit_result["reason"],
                        "signal_strength": 0.5,
                        "date": today,
                    })
            elif exit_result["action"] in ("take_profit_1", "take_profit_2"):
                reduce_pct = exit_result.get("reduce_pct", 0.4)
                qty = int(pos_info["shares"] * reduce_pct)
                if qty > 0:
                    action = "REDUCE"
                    orders.append({
                        "ticker": ticker,
                        "action": action,
                        "quantity": qty,
                        "execution": "ATC",
                        "reason": exit_result["reason"],
                        "signal_strength": 0.8,
                        "date": today,
                    })

        return orders

    def _generate_entry_orders(
        self, portfolio: dict, features: pd.DataFrame, ticker_info: dict, exit_orders: List[dict]
    ) -> List[dict]:
        orders = []
        today = datetime.now().date().isoformat()
        existing_tickers = {p["ticker"] for p in portfolio.get("positions", [])}
        exiting_tickers = {o["ticker"] for o in exit_orders}
        max_pos = self.config.get("max_positions", 10)

        if features.empty or "ticker" not in features.columns:
            return orders

        current_count = len(existing_tickers - exiting_tickers)
        if current_count >= max_pos:
            return orders

        slots_available = max_pos - current_count
        candidates = []

        for ticker in features["ticker"].unique():
            if ticker in existing_tickers or ticker in exiting_tickers:
                continue
            ticker_feat = features[features["ticker"] == ticker]
            if ticker_feat.empty:
                continue
            row = ticker_feat.iloc[-1]
            info = ticker_info.get(ticker, {})
            if not info:
                continue

            entry = self.strategy.signals.check_entry_conditions(row, info)
            if entry["signal"] != 1:
                continue

            candidates.append({
                "ticker": ticker,
                "signal_strength": 1.0,
                "price": row["close"],
                "row": row,
                "info": info,
                "sector": info.get("sector", "Others"),
                "reasons": entry["reasons"],
            })

        candidates.sort(key=lambda c: c["signal_strength"], reverse=True)
        candidates = candidates[:slots_available]

        for cand in candidates:
            sizing_result = self.strategy.sizing.calculate_position_size(
                ticker=cand["ticker"],
                signal_strength=cand["signal_strength"],
                available_cash=portfolio.get("available_cash", 0),
                current_positions=[
                    {"ticker": p["ticker"], "notional": p.get("notional", 0)}
                    for p in portfolio.get("positions", [])
                    if p["ticker"] not in exiting_tickers
                ],
                sector_map=self.config.get("sector_map", {}),
                risk_params={
                    "portfolio_value": portfolio.get("current_nav", 1_000_000_000),
                    "kelly_fraction": 0.25,
                    "max_position_pct": 0.10,
                    "max_sector_pct": 0.20,
                    "min_cash_pct": 0.30,
                    "price": cand["price"],
                },
                market_data={
                    "close": cand["price"],
                    "foreign_room_pct": cand["info"].get("foreign_room_pct", 100),
                },
            )

            if sizing_result["quantity"] <= 0:
                continue

            orders.append({
                "ticker": cand["ticker"],
                "action": "BUY",
                "quantity": sizing_result["quantity"],
                "execution": "ATC",
                "reason": "entry_signal",
                "signal_strength": cand["signal_strength"],
                "date": today,
                "price": cand["price"],
                "notional": sizing_result["notional"],
            })

        return orders

    async def _save_orders(self, orders: List[dict]):
        if not orders:
            return
        try:
            await self.supabase.table("orders").insert(orders).execute()
            logger.info("orders_saved", count=len(orders))
        except Exception as e:
            logger.error("failed_to_save_orders", error=str(e))

    async def _update_portfolio_state(self, portfolio: dict, orders: List[dict]):
        nav = portfolio.get("current_nav", 1_000_000_000)
        cash = portfolio.get("available_cash", 1_000_000_000)
        positions = list(portfolio.get("positions", []))
        peak = portfolio.get("peak_value", nav)
        exiting = {}
        buying = []

        for o in orders:
            if o["action"] in ("SELL_ALL", "SELL"):
                exiting[o["ticker"]] = o["quantity"]
            elif o["action"] == "REDUCE":
                exiting[o["ticker"]] = exiting.get(o["ticker"], 0) + o["quantity"]
            elif o["action"] == "BUY":
                buying.append(o)

        new_positions = []
        for p in positions:
            ticker = p["ticker"]
            qty = p.get("shares", p.get("quantity", 0))
            if ticker in exiting:
                qty -= exiting[ticker]
            if qty > 0:
                p["quantity"] = qty
                new_positions.append(p)

        for o in buying:
            new_positions.append({
                "ticker": o["ticker"],
                "quantity": o["quantity"],
                "entry_price": o.get("price", 0),
                "notional": o.get("notional", 0),
                "stop_loss": o.get("price", 0) * 0.92,
                "entry_date": o["date"],
            })

        try:
            state = {
                "available_cash": cash,
                "current_nav": nav,
                "positions": new_positions,
                "peak_value": peak,
                "updated_at": datetime.now().isoformat(),
            }
            await self.supabase.table("portfolio_state").insert(state).execute()
        except Exception as e:
            logger.error("failed_to_update_portfolio_state", error=str(e))

    async def _send_alerts(self, orders: List[dict], portfolio: dict):
        logger.info("alerts_queued", order_count=len(orders))
