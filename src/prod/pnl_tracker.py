from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger(__name__)


class PnLTracker:
    """
    Daily mark-to-market PnL:
    - Unrealized PnL = sum((current_price - avg_cost) * shares)
    - Realized PnL = sum(sell_price * shares - buy_price * shares)

    Attribution: by sector, by holding period, by exit reason.
    """

    def __init__(self, supabase_client, config: dict, output_dir: str = "data/pnl"):
        self.supabase = supabase_client
        self.config = config
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    async def compute_daily_pnl(self, current_prices: Dict[str, float]) -> dict:
        state = await self._load_portfolio_state()
        if not state:
            return {}

        positions = state.get("positions", [])
        cash = state.get("available_cash", 0)
        total_cost = 0.0
        unrealized_pnl = 0.0
        position_details = []

        for pos in positions:
            ticker = pos["ticker"]
            qty = pos.get("quantity", 0)
            entry = pos.get("entry_price", 0)
            current = current_prices.get(ticker, entry)
            notional = qty * current
            cost = qty * entry
            total_cost += cost
            upnl = (current - entry) * qty
            upnl_pct = (current - entry) / entry if entry > 0 else 0.0

            unrealized_pnl += upnl
            sector = self.config.get("sector_map", {}).get(ticker, "Others")
            holding_days = self._holding_days(pos.get("entry_date"))
            holding_bucket = self._holding_bucket(holding_days)

            position_details.append({
                "ticker": ticker,
                "sector": sector,
                "quantity": qty,
                "entry_price": entry,
                "current_price": current,
                "notional": round(notional, 2),
                "cost": round(cost, 2),
                "unrealized_pnl": round(upnl, 2),
                "unrealized_pnl_pct": round(upnl_pct * 100, 4),
                "holding_days": holding_days,
                "holding_bucket": holding_bucket,
            })

        nav = cash + sum(p["notional"] for p in position_details)
        day_pnl = await self._compute_realized_pnl(datetime.now().date())

        record = {
            "date": datetime.now().date().isoformat(),
            "nav": round(nav, 2),
            "cash": round(cash, 2),
            "total_cost": round(total_cost, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "realized_pnl": round(day_pnl, 2),
            "daily_pnl": round(unrealized_pnl + day_pnl, 2),
            "position_count": len(position_details),
            "details": position_details,
        }

        await self._save_daily_pnl(record)
        self._export_csv(record)

        return record

    async def compute_attribution(self, current_prices: Dict[str, float]) -> dict:
        pnl = await self.compute_daily_pnl(current_prices)
        details = pnl.get("details", [])

        sector_pnl = {}
        bucket_pnl = {}
        for d in details:
            sec = d["sector"]
            bucket = d["holding_bucket"]
            sector_pnl[sec] = sector_pnl.get(sec, 0) + d["unrealized_pnl"]
            bucket_pnl[bucket] = bucket_pnl.get(bucket, 0) + d["unrealized_pnl"]

        return {
            "date": pnl["date"],
            "by_sector": sector_pnl,
            "by_holding_bucket": bucket_pnl,
            "total_unrealized": pnl["unrealized_pnl"],
            "total_realized": pnl["realized_pnl"],
        }

    async def compute_realized_pnl_by_exit(self) -> pd.DataFrame:
        try:
            result = await self.supabase.table("closed_trades").select("*").execute()
            trades = result.data or []
        except Exception:
            trades = []

        records = []
        for t in trades:
            exit_reason = t.get("exit_reason", "manual")
            records.append({
                "ticker": t["ticker"],
                "entry_price": t.get("entry_price", 0),
                "exit_price": t.get("exit_price", 0),
                "quantity": t.get("quantity", 0),
                "pnl": (t.get("exit_price", 0) - t.get("entry_price", 0)) * t.get("quantity", 0),
                "pnl_pct": (t.get("exit_price", 0) - t.get("entry_price", 0)) / t.get("entry_price", 0)
                if t.get("entry_price", 0) > 0 else 0,
                "exit_reason": exit_reason,
                "exit_date": t.get("exit_date", ""),
                "sector": self.config.get("sector_map", {}).get(t["ticker"], "Others"),
            })

        return pd.DataFrame(records)

    def _holding_days(self, entry_date_str: Optional[str]) -> int:
        if not entry_date_str:
            return 0
        try:
            entry = datetime.fromisoformat(entry_date_str)
            return (datetime.now() - entry).days
        except Exception:
            return 0

    def _holding_bucket(self, days: int) -> str:
        if days <= 5:
            return "0-5d"
        elif days <= 20:
            return "5-20d"
        elif days <= 60:
            return "20-60d"
        return "60+d"

    async def _load_portfolio_state(self) -> dict:
        try:
            result = await self.supabase.table("portfolio_state").select("*").order(
                "created_at", desc=True
            ).limit(1).execute()
            return result.data[0] if result.data else {}
        except Exception:
            return {}

    async def _compute_realized_pnl(self, date) -> float:
        try:
            result = await self.supabase.table("orders").select("*").eq("status", "filled").execute()
            total = 0.0
            for o in result.data or []:
                if o.get("action") in ("SELL", "SELL_ALL", "REDUCE"):
                    total += o.get("quantity", 0) * o.get("fill_price", 0)
            return total
        except Exception:
            return 0.0

    async def _save_daily_pnl(self, record: dict):
        try:
            await self.supabase.table("daily_pnl").insert(record).execute()
        except Exception as e:
            logger.error("failed_to_save_daily_pnl", error=str(e))

    def _export_csv(self, record: dict):
        date_str = record["date"]
        path = os.path.join(self.output_dir, f"daily_pnl_{date_str}.csv")
        details = record.pop("details", [])
        pd.DataFrame([record]).to_csv(path, index=False)
        if details:
            detail_path = os.path.join(self.output_dir, f"positions_{date_str}.csv")
            pd.DataFrame(details).to_csv(detail_path, index=False)
        record["details"] = details

    async def generate_weekly_summary(self) -> dict:
        try:
            result = await self.supabase.table("daily_pnl").select("*").order("date", desc=True).limit(7).execute()
            records = result.data or []
        except Exception:
            records = []

        if not records:
            return {}

        df = pd.DataFrame(records)
        summary = {
            "period": f"{records[-1]['date']} to {records[0]['date']}",
            "total_pnl": round(df["daily_pnl"].sum(), 2),
            "avg_nav": round(df["nav"].mean(), 2),
            "avg_unrealized": round(df["unrealized_pnl"].mean(), 2),
            "avg_realized": round(df["realized_pnl"].mean(), 2),
            "days": len(records),
        }
        week_path = os.path.join(self.output_dir, "weekly_summary.csv")
        pd.DataFrame([summary]).to_csv(week_path, index=False)
        return summary

    async def generate_monthly_summary(self) -> dict:
        try:
            result = await self.supabase.table("daily_pnl").select("*").order("date", desc=True).limit(30).execute()
            records = result.data or []
        except Exception:
            records = []

        if not records:
            return {}

        df = pd.DataFrame(records)
        summary = {
            "period": f"{records[-1]['date']} to {records[0]['date']}",
            "total_pnl": round(df["daily_pnl"].sum(), 2),
            "avg_nav": round(df["nav"].mean(), 2),
            "final_nav": round(df["nav"].iloc[0], 2),
            "return_pct": round((df["nav"].iloc[0] - df["nav"].iloc[-1]) / df["nav"].iloc[-1] * 100, 4),
            "days": len(records),
        }
        month_path = os.path.join(self.output_dir, "monthly_summary.csv")
        pd.DataFrame([summary]).to_csv(month_path, index=False)
        return summary
