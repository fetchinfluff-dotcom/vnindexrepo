from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.prod.alerts import AlertSystem, AlertType


@pytest.fixture
def config():
    return {
        "TELEGRAM_BOT_TOKEN": "test_token",
        "TELEGRAM_CHAT_ID": "test_chat",
        "EMAIL_HOST": "smtp.gmail.com",
        "EMAIL_USER": "test@gmail.com",
        "EMAIL_PASS": "test_pass",
        "initial_capital": 1_000_000_000,
    }


@pytest.fixture
def alert_system(config):
    return AlertSystem(config)


class TestAlertSystem:
    async def test_send_daily_signal_alert(self, alert_system):
        orders = [
            {"ticker": "VCB", "action": "BUY", "quantity": 1000, "reason": "entry_signal"},
            {"ticker": "HPG", "action": "SELL_ALL", "quantity": 2000, "reason": "trend_break"},
        ]
        with patch.object(alert_system, "_send_telegram", AsyncMock()) as mock_tg:
            await alert_system.send_daily_signal_alert(orders, nav=1_000_000_000, cash=700_000_000, pos_count=3)
            mock_tg.assert_called_once()
            message = mock_tg.call_args[0][0]
            assert "VCB" in message
            assert "HPG" in message

    async def test_drawdown_warning(self, alert_system):
        with patch.object(alert_system, "_send_telegram", AsyncMock()) as mock_tg:
            await alert_system.send_drawdown_alert(nav=880_000_000, peak=1_000_000_000)
            mock_tg.assert_called_once()
            message = mock_tg.call_args[0][0]
            assert "Drawdown Warning" in message or "Trading Halted" in message

    async def test_drawdown_stop(self, alert_system):
        with patch.object(alert_system, "_send_telegram", AsyncMock()) as mock_tg:
            await alert_system.send_drawdown_alert(nav=800_000_000, peak=1_000_000_000)
            mock_tg.assert_called_once()
            message = mock_tg.call_args[0][0]
            assert "Trading Halted" in message

    async def test_technical_alert(self, alert_system):
        with patch.object(alert_system, "_send_telegram", AsyncMock()) as mock_tg:
            await alert_system.send_technical_alert("DNSE API", "Connection timeout")
            mock_tg.assert_called_once()

    async def test_no_telegram_token(self):
        sys = AlertSystem({"initial_capital": 1_000_000})
        await sys.send_daily_signal_alert([], 0, 0, 0)

    async def test_format_alert_types(self, alert_system):
        msg = alert_system._format_message(AlertType.POSITION_OPEN, {
            "ticker": "VCB", "quantity": 1000, "price": 25000, "notional": 25_000_000, "reason": "entry_signal",
        })
        assert "VCB" in msg

        msg = alert_system._format_message(AlertType.POSITION_CLOSE, {
            "ticker": "HPG", "quantity": 2000, "exit_price": 28000,
            "pnl": 6_000_000, "pnl_pct": 0.12, "reason": "take_profit", "holding_days": 10,
        })
        assert "HPG" in msg

    async def test_active_channels(self, alert_system):
        channels = alert_system._active_channels()
        assert "telegram" in channels
        assert "email" in channels

    async def test_send_alert_without_email(self):
        sys = AlertSystem({"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "c", "initial_capital": 1_000_000})
        with patch.object(sys, "_send_telegram", AsyncMock()) as mock_tg:
            await sys.send_alert(AlertType.TECHNICAL, {"error": "test"})
            mock_tg.assert_called_once()

    async def test_format_stop_loss(self, alert_system):
        msg = alert_system._format_message(AlertType.STOP_LOSS_HIT, {
            "ticker": "VNM", "entry_price": 72000, "exit_price": 66240,
            "pnl_pct": -0.08, "stop_loss": 66240,
        })
        assert "Stop Loss" in msg

    async def test_format_take_profit(self, alert_system):
        msg = alert_system._format_message(AlertType.TAKE_PROFIT_HIT, {
            "ticker": "MWG", "entry_price": 58000, "exit_price": 63000,
            "pnl_pct": 0.086, "reduce_pct": 0.4, "tp_level": 1,
        })
        assert "Take Profit" in msg

    async def test_format_foreign_room(self, alert_system):
        msg = alert_system._format_message(AlertType.FOREIGN_ROOM, {
            "ticker": "VCB", "room_pct": 3.2,
        })
        assert "Foreign Room" in msg
