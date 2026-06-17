from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

ORDER_STATUSES = ("signal_generated", "order_sent", "filled", "settled", "cancelled", "rejected")


class OrderManager:
    """
    Tracks order lifecycle:
    signal_generated -> order_sent -> filled -> settled (T+2)

    Daily:
    - Load pending orders from Supabase
    - Check fill status via DNSE API
    - Update position state
    - Update NAV
    """

    def __init__(self, dnse_client, supabase_client, config: dict):
        self.dnse = dnse_client
        self.supabase = supabase_client
        self.config = config

    async def process_pending_orders(self) -> dict:
        orders = await self._load_pending_orders()
        if not orders:
            return {"status": "no_pending_orders", "processed": 0}

        filled = []
        for order in orders:
            fill_status = await self._check_fill(order)
            if fill_status["filled"]:
                order["status"] = "filled"
                order["fill_price"] = fill_status["fill_price"]
                order["filled_at"] = datetime.now().isoformat()
                await self._update_order(order)
                await self._update_positions(order)
                filled.append(order)

        await self._settle_t_plus_2()

        return {
            "status": "success",
            "total_pending": len(orders),
            "filled": len(filled),
            "order_ids": [o.get("id") for o in filled],
        }

    async def _load_pending_orders(self) -> List[dict]:
        try:
            result = await self.supabase.table("orders").select("*").in_(
                "status", ("signal_generated", "order_sent")
            ).execute()
            return result.data or []
        except Exception as e:
            logger.error("failed_to_load_pending_orders", error=str(e))
            return []

    async def _check_fill(self, order: dict) -> dict:
        try:
            exec_date = order.get("date", datetime.now().date().isoformat())
            ticker = order["ticker"]
            side = "buy" if order["action"] == "BUY" else "sell"
            qty = order["quantity"]

            fill_info = await self.dnse.check_order_fill(
                ticker=ticker,
                side=side,
                quantity=qty,
                date=exec_date,
            )
            return {"filled": fill_info.get("filled", False), "fill_price": fill_info.get("fill_price", 0)}
        except Exception as e:
            logger.warning("fill_check_failed", ticker=order["ticker"], error=str(e))
            return {"filled": False, "fill_price": 0}

    async def _update_order(self, order: dict):
        try:
            await self.supabase.table("orders").update(order).eq("id", order["id"]).execute()
        except Exception as e:
            logger.error("failed_to_update_order", order_id=order.get("id"), error=str(e))

    async def _update_positions(self, order: dict):
        ticker = order["ticker"]
        action = order["action"]
        qty = order["quantity"]
        fill_price = order.get("fill_price", 0)

        try:
            state_result = await self.supabase.table("portfolio_state").select("*").order(
                "created_at", desc=True
            ).limit(1).execute()
            state = state_result.data[0] if state_result.data else {}

            positions = list(state.get("positions", []))
            if action == "BUY":
                positions.append({
                    "ticker": ticker,
                    "quantity": qty,
                    "entry_price": fill_price,
                    "notional": qty * fill_price,
                    "stop_loss": fill_price * 0.92,
                    "entry_date": datetime.now().isoformat(),
                })
                state["available_cash"] = state.get("available_cash", 0) - (qty * fill_price)
            else:
                for p in positions:
                    if p["ticker"] == ticker:
                        if action in ("SELL_ALL", "SELL"):
                            p["quantity"] = 0
                            state["available_cash"] = state.get("available_cash", 0) + (qty * fill_price)
                        elif action == "REDUCE":
                            p["quantity"] -= qty
                            state["available_cash"] = state.get("available_cash", 0) + (qty * fill_price)
                        break

            state["positions"] = [p for p in positions if p.get("quantity", 0) > 0]
            state["updated_at"] = datetime.now().isoformat()
            await self.supabase.table("portfolio_state").insert(state).execute()
        except Exception as e:
            logger.error("failed_to_update_positions", ticker=ticker, error=str(e))

    async def _settle_t_plus_2(self):
        settle_date = (datetime.now() - timedelta(days=2)).date().isoformat()
        try:
            result = await self.supabase.table("orders").select("*").eq("status", "filled").execute()
            for order in result.data or []:
                order_date = order.get("filled_at", "")[:10]
                if order_date == settle_date:
                    order["status"] = "settled"
                    await self._update_order(order)
        except Exception as e:
            logger.error("t_plus_2_settlement_failed", error=str(e))

    async def send_order(self, order: dict) -> dict:
        risk_check = self._pre_trade_risk_check(order)
        if not risk_check["approved"]:
            return {"status": "rejected", "reason": risk_check["reason"]}

        try:
            response = await self.dnse.place_order(
                ticker=order["ticker"],
                side="buy" if order["action"] == "BUY" else "sell",
                quantity=order["quantity"],
                order_type=order.get("execution", "ATC"),
            )
            if response.get("success"):
                order["status"] = "order_sent"
                order["order_id"] = response.get("order_id")
                await self._update_order(order)
                return {"status": "sent", "order_id": order["order_id"]}
            return {"status": "failed", "reason": response.get("message", "unknown")}
        except Exception as e:
            logger.error("order_send_failed", ticker=order["ticker"], error=str(e))
            return {"status": "error", "reason": str(e)}

    def _pre_trade_risk_check(self, order: dict) -> dict:
        action = order["action"]
        qty = order["quantity"]
        price = order.get("price", 0)

        if action == "BUY":
            max_notional = self.config.get("max_position_pct", 0.10) * self.config.get("initial_capital", 1_000_000_000)
            if qty * price > max_notional:
                return {"approved": False, "reason": "exceeds_max_position_size"}

        return {"approved": True, "reason": "ok"}

    async def get_portfolio_summary(self) -> dict:
        try:
            result = await self.supabase.table("portfolio_state").select("*").order(
                "created_at", desc=True
            ).limit(1).execute()
            return result.data[0] if result.data else {}
        except Exception:
            return {}
