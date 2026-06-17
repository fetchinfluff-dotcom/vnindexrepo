from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class AlertType(str, Enum):
    DAILY_SIGNAL = "daily_signal"
    POSITION_OPEN = "position_open"
    POSITION_CLOSE = "position_close"
    STOP_LOSS_HIT = "stop_loss_hit"
    TAKE_PROFIT_HIT = "take_profit_hit"
    DRAWDOWN_WARNING = "drawdown_warning"
    DRAWDOWN_STOP = "drawdown_stop"
    SECTOR_EXPOSURE = "sector_exposure"
    FOREIGN_ROOM = "foreign_room"
    TECHNICAL = "technical"


class AlertSystem:
    """
    Alert channels: Telegram, Email
    Alert types: signal, position, risk, technical
    """

    def __init__(self, config: dict):
        self.config = config
        self.telegram_token = config.get("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = config.get("TELEGRAM_CHAT_ID", "")
        self.email_host = config.get("EMAIL_HOST", "smtp.gmail.com")
        self.email_user = config.get("EMAIL_USER", "")
        self.email_pass = config.get("EMAIL_PASS", "")
        self.initial_capital = config.get("initial_capital", 1_000_000_000)

    async def send_alert(self, alert_type: AlertType, data: dict):
        message = self._format_message(alert_type, data)

        if self.telegram_token and self.telegram_chat_id:
            await self._send_telegram(message)

        if self.email_user and self.email_pass:
            await self._send_email(alert_type.value, message)

        logger.info("alert_sent", type=alert_type.value, channel=self._active_channels())

    def _active_channels(self) -> list:
        channels = []
        if self.telegram_token:
            channels.append("telegram")
        if self.email_user:
            channels.append("email")
        return channels or ["none"]

    def _format_message(self, alert_type: AlertType, data: dict) -> str:
        formatters = {
            AlertType.DAILY_SIGNAL: self._format_daily_signal,
            AlertType.POSITION_OPEN: self._format_position_open,
            AlertType.POSITION_CLOSE: self._format_position_close,
            AlertType.STOP_LOSS_HIT: self._format_stop_loss,
            AlertType.TAKE_PROFIT_HIT: self._format_take_profit,
            AlertType.DRAWDOWN_WARNING: self._format_drawdown_warning,
            AlertType.DRAWDOWN_STOP: self._format_drawdown_stop,
            AlertType.SECTOR_EXPOSURE: self._format_sector_exposure,
            AlertType.FOREIGN_ROOM: self._format_foreign_room,
            AlertType.TECHNICAL: self._format_technical,
        }
        formatter = formatters.get(alert_type, lambda d: str(d))
        return formatter(data)

    def _format_daily_signal(self, data: dict) -> str:
        lines = [f"VN100 Strategy Signals - {data.get('date', '')}", ""]
        for o in data.get("orders", []):
            icon = "BUY" if o.get("action") == "BUY" else "SELL"
            lines.append(f"{icon} {o['ticker']}: {o['action']} {o['quantity']} shares")
            lines.append(f"   Reason: {o.get('reason', 'N/A')}")
        lines.append("")
        lines.append(f"NAV: {data.get('nav', 'N/A'):,} VND")
        lines.append(f"Cash: {data.get('cash', 'N/A'):,} VND")
        lines.append(f"Positions: {data.get('positions', 0)}")
        return "\n".join(lines)

    def _format_position_open(self, data: dict) -> str:
        return (
            f"Position Opened\n"
            f"Ticker: {data.get('ticker', 'N/A')}\n"
            f"Qty: {data.get('quantity', 0)}\n"
            f"Price: {data.get('price', 0):,} VND\n"
            f"Notional: {data.get('notional', 0):,} VND\n"
            f"Reason: {data.get('reason', 'N/A')}"
        )

    def _format_position_close(self, data: dict) -> str:
        pnl = data.get("pnl", 0)
        pnl_icon = "+" if pnl >= 0 else ""
        return (
            f"Position Closed\n"
            f"Ticker: {data.get('ticker', 'N/A')}\n"
            f"Qty: {data.get('quantity', 0)}\n"
            f"Exit Price: {data.get('exit_price', 0):,} VND\n"
            f"PnL: {pnl_icon}{pnl:,.0f} VND ({data.get('pnl_pct', 0):+.2f}%)\n"
            f"Reason: {data.get('reason', 'N/A')}\n"
            f"Holding Days: {data.get('holding_days', 0)}"
        )

    def _format_stop_loss(self, data: dict) -> str:
        return (
            f"Stop Loss Triggered\n"
            f"Ticker: {data.get('ticker', 'N/A')}\n"
            f"Entry: {data.get('entry_price', 0):,} VND\n"
            f"Exit: {data.get('exit_price', 0):,} VND\n"
            f"Loss: {data.get('pnl_pct', 0):+.2f}%\n"
            f"Stop Level: {data.get('stop_loss', 0):,} VND"
        )

    def _format_take_profit(self, data: dict) -> str:
        return (
            f"Take Profit Hit (TP{data.get('tp_level', 1)})\n"
            f"Ticker: {data.get('ticker', 'N/A')}\n"
            f"Entry: {data.get('entry_price', 0):,} VND\n"
            f"Exit: {data.get('exit_price', 0):,} VND\n"
            f"Profit: {data.get('pnl_pct', 0):+.2f}%\n"
            f"Reduced by {data.get('reduce_pct', 0)*100:.0f}%"
        )

    def _format_drawdown_warning(self, data: dict) -> str:
        return (
            f"Drawdown Warning\n"
            f"Current DD: {data.get('drawdown_pct', 0):.2f}%\n"
            f"Warning Threshold: {data.get('warning_threshold', 10):.0f}%\n"
            f"NAV: {data.get('nav', 0):,} VND\n"
            f"Peak: {data.get('peak', 0):,} VND"
        )

    def _format_drawdown_stop(self, data: dict) -> str:
        return (
            f"Trading Halted - Max Drawdown\n"
            f"Current DD: {data.get('drawdown_pct', 0):.2f}%\n"
            f"Stop Threshold: {data.get('stop_threshold', 15):.0f}%\n"
            f"NAV: {data.get('nav', 0):,} VND\n"
            f"Peak: {data.get('peak', 0):,} VND\n"
            f"All new positions are blocked."
        )

    def _format_sector_exposure(self, data: dict) -> str:
        return (
            f"Sector Exposure Warning\n"
            f"Sector: {data.get('sector', 'N/A')}\n"
            f"Current Exposure: {data.get('current_pct', 0):.2f}%\n"
            f"Limit: {data.get('limit_pct', 20):.0f}%\n"
            f"Positions: {', '.join(data.get('tickers', []))}"
        )

    def _format_foreign_room(self, data: dict) -> str:
        return (
            f"Foreign Room Warning\n"
            f"Ticker: {data.get('ticker', 'N/A')}\n"
            f"Remaining Room: {data.get('room_pct', 0):.2f}%\n"
            f"Threshold: 5%"
        )

    def _format_technical(self, data: dict) -> str:
        return (
            f"Technical Alert\n"
            f"Component: {data.get('component', 'N/A')}\n"
            f"Error: {data.get('error', 'N/A')}\n"
            f"Time: {data.get('time', 'N/A')}"
        )

    async def _send_telegram(self, message: str):
        if not self.telegram_token or not self.telegram_chat_id:
            return
        try:
            import httpx
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            async with httpx.AsyncClient() as client:
                await client.post(url, json={
                    "chat_id": self.telegram_chat_id,
                    "text": message,
                    "parse_mode": "Markdown",
                })
        except ImportError:
            logger.warning("httpx not available, telegram alert skipped")
        except Exception as e:
            logger.error("telegram_send_failed", error=str(e))

    async def _send_email(self, subject: str, body: str):
        if not self.email_user or not self.email_pass:
            return
        try:
            msg = MIMEMultipart()
            msg["From"] = self.email_user
            msg["To"] = self.email_user
            msg["Subject"] = f"[VN100 Strategy] {subject}"
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(self.email_host, 587) as server:
                server.starttls()
                server.login(self.email_user, self.email_pass)
                server.send_message(msg)
        except Exception as e:
            logger.error("email_send_failed", error=str(e))

    async def send_daily_signal_alert(self, orders: list, nav: float, cash: float, pos_count: int):
        await self.send_alert(AlertType.DAILY_SIGNAL, {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "orders": orders,
            "nav": nav,
            "cash": cash,
            "positions": pos_count,
        })

    async def send_drawdown_alert(self, nav: float, peak: float):
        dd_pct = (peak - nav) / peak * 100
        alert_type = AlertType.DRAWDOWN_STOP if dd_pct >= 15 else AlertType.DRAWDOWN_WARNING

        await self.send_alert(alert_type, {
            "drawdown_pct": round(dd_pct, 2),
            "warning_threshold": 10.0,
            "stop_threshold": 15.0,
            "nav": nav,
            "peak": peak,
        })

    async def send_technical_alert(self, component: str, error: str):
        await self.send_alert(AlertType.TECHNICAL, {
            "component": component,
            "error": error,
            "time": datetime.now().isoformat(),
        })


from datetime import datetime
