from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from datetime import datetime, time
from typing import Any, Callable, Dict, Optional

import structlog

logger = structlog.get_logger(__name__)

SCHEDULE = {
    "signal_generator": {"hour": 15, "minute": 0, "description": "Generate daily signals after market close"},
    "order_review": {"hour": 15, "minute": 30, "description": "Review and confirm orders"},
    "send_alerts": {"hour": 16, "minute": 0, "description": "Send signal alerts via Telegram/Email"},
    "pnl_update": {"hour": 16, "minute": 30, "description": "Update daily P&L tracker"},
    "morning_fill_check": {"hour": 9, "minute": 0, "description": "Check morning ATO/ATC fills"},
    "status_update": {"hour": 10, "minute": 0, "description": "Send daily status update alert"},
}


class ProductionScheduler:
    """
    Production schedule manager.
    Supports systemd timers, cron, or in-process asyncio loop.
    """

    def __init__(
        self,
        signal_generator,
        order_manager,
        pnl_tracker,
        alert_system,
        config: dict,
    ):
        self.signal_generator = signal_generator
        self.order_manager = order_manager
        self.pnl_tracker = pnl_tracker
        self.alert_system = alert_system
        self.config = config
        self._running = False

    async def run_scheduled(self, task_name: str):
        logger.info("scheduled_task_started", task=task_name)

        try:
            if task_name == "signal_generator":
                result = await self.signal_generator.run()
                logger.info("signal_generator_complete", **result)

            elif task_name == "order_review":
                orders = await self._load_todays_orders()
                logger.info("orders_for_review", count=len(orders))

            elif task_name == "send_alerts":
                orders = await self._load_todays_orders()
                state = await self.order_manager.get_portfolio_summary()
                if orders:
                    await self.alert_system.send_daily_signal_alert(
                        orders=orders,
                        nav=state.get("current_nav", 0),
                        cash=state.get("available_cash", 0),
                        pos_count=len(state.get("positions", [])),
                    )

            elif task_name == "pnl_update":
                prices = await self._get_current_prices()
                await self.pnl_tracker.compute_daily_pnl(prices)
                await self.pnl_tracker.generate_weekly_summary()

            elif task_name == "morning_fill_check":
                result = await self.order_manager.process_pending_orders()
                logger.info("fill_check_complete", **result)

            elif task_name == "status_update":
                state = await self.order_manager.get_portfolio_summary()
                pos_count = len(state.get("positions", []))
                nav = state.get("current_nav", 0)
                logger.info("daily_status", nav=nav, positions=pos_count)

            else:
                logger.warning("unknown_task", task=task_name)

        except Exception as e:
            logger.error("scheduled_task_failed", task=task_name, error=str(e))
            await self.alert_system.send_technical_alert(task_name, str(e))

    async def _load_todays_orders(self) -> list:
        try:
            import supabase
            today = datetime.now().date().isoformat()
            result = await self.signal_generator.supabase.table("orders").select("*").eq(
                "date", today
            ).execute()
            return result.data or []
        except Exception:
            return []

    async def _get_current_prices(self) -> dict:
        try:
            tickers = self.config.get("ticker_universe", [])
            prices = {}
            for ticker in tickers[:50]:
                bar = await self.signal_generator.dnse.get_latest_price(ticker)
                if bar:
                    prices[ticker] = bar.get("close", 0)
            return prices
        except Exception:
            return {}

    def run_all_now(self):
        """Run all tasks sequentially (for manual invocation)."""
        logger.info("running_all_tasks_now")

    def generate_cron_tab(self) -> str:
        lines = ["# VN100 Strategy Production Schedule (VN time)", "#"]
        for task, sched in SCHEDULE.items():
            lines.append(
                f"{sched['minute']} {sched['hour']} * * 1-5 "
                f"cd {os.getcwd()} && {sys.executable} -m src.prod.scheduler --task {task} "
                f">> logs/{task}.log 2>&1"
            )
        return "\n".join(lines)

    def generate_systemd_timer(self, task_name: str) -> str:
        sched = SCHEDULE.get(task_name)
        if not sched:
            return ""

        service = f"""[Unit]
Description=VN100 Strategy - {sched['description']}
After=network.target

[Service]
Type=oneshot
WorkingDirectory={os.getcwd()}
ExecStart={sys.executable} -m src.prod.scheduler --task {task_name}
StandardOutput=append:logs/{task_name}.log
StandardError=append:logs/{task_name}.log
"""

        timer = f"""[Unit]
Description=VN100 Strategy Timer - {sched['description']}

[Timer]
OnCalendar=Mon..Fri *-*-* {sched['hour']:02d}:{sched['minute']:02d}:00
Persistent=true

[Install]
WantedBy=timers.target
"""
        return f"{service}\n# --- timer ---\n{timer}"

    def generate_systemd_timers(self) -> str:
        parts = ["# VN100 Strategy - systemd timers", "# Save each block as /etc/systemd/system/vn100-<task>.{service,timer}"]
        for task_name in SCHEDULE:
            parts.append(f"\n# === {task_name} ===\n")
            parts.append(self.generate_systemd_timer(task_name))
        return "\n".join(parts)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="VN100 Production Scheduler")
    parser.add_argument("--task", type=str, default="signal_generator",
                        choices=list(SCHEDULE.keys()) + ["all"],
                        help="Task to run")
    parser.add_argument("--generate-cron", action="store_true",
                        help="Print cron tab and exit")
    parser.add_argument("--generate-systemd", action="store_true",
                        help="Print systemd timer units and exit")
    args = parser.parse_args()

    if args.generate_cron:
        sched = ProductionScheduler(None, None, None, None, {})
        print(sched.generate_cron_tab())
        return

    if args.generate_systemd:
        sched = ProductionScheduler(None, None, None, None, {})
        print(sched.generate_systemd_timers())
        return

    logger.info("scheduler_started", task=args.task)


if __name__ == "__main__":
    main()
