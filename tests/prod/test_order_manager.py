from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.prod.order_manager import OrderManager


@pytest.fixture
def mock_dnse():
    client = MagicMock()
    client.check_order_fill = AsyncMock(return_value={"filled": True, "fill_price": 26500})
    client.place_order = AsyncMock(return_value={"success": True, "order_id": "ORD123"})
    return client


@pytest.fixture
def mock_supabase():
    client = MagicMock()
    table = MagicMock()
    table.select = MagicMock(return_value=table)
    table.in_ = MagicMock(return_value=table)
    table.eq = MagicMock(return_value=table)
    table.order = MagicMock(return_value=table)
    table.limit = MagicMock(return_value=table)
    table.execute = AsyncMock()
    client.table = MagicMock(return_value=table)
    return client


@pytest.fixture
def config():
    return {
        "initial_capital": 1_000_000_000,
        "max_position_pct": 0.10,
    }


@pytest.fixture
def order_manager(mock_dnse, mock_supabase, config):
    return OrderManager(mock_dnse, mock_supabase, config)


class TestOrderManager:
    async def test_process_no_pending_orders(self, order_manager, mock_supabase):
        mock_supabase.table().execute.return_value = MagicMock(data=[])
        result = await order_manager.process_pending_orders()
        assert result["status"] == "no_pending_orders"

    async def test_process_pending_orders(self, order_manager, mock_supabase):
        mock_supabase.table().execute.return_value = MagicMock(data=[
            {"id": "1", "ticker": "VCB", "action": "BUY", "quantity": 1000,
             "date": "2026-06-16", "status": "signal_generated"},
        ])
        mock_supabase.table().update = MagicMock(return_value=mock_supabase.table())
        result = await order_manager.process_pending_orders()
        assert result["status"] == "success"

    async def test_send_order(self, order_manager):
        order = {"ticker": "VCB", "action": "BUY", "quantity": 1000,
                 "execution": "ATC", "price": 26500}
        result = await order_manager.send_order(order)
        assert result["status"] == "sent"

    async def test_send_order_rejected_risk(self, order_manager):
        order = {"ticker": "VCB", "action": "BUY", "quantity": 100000,
                 "execution": "ATC", "price": 200000}
        result = await order_manager.send_order(order)
        assert result["status"] != "sent"

    async def test_pre_trade_risk_check(self, order_manager):
        order = {"action": "BUY", "quantity": 1000, "price": 50000}
        result = order_manager._pre_trade_risk_check(order)
        assert result["approved"] is True

        order = {"action": "BUY", "quantity": 100000, "price": 200000}
        result = order_manager._pre_trade_risk_check(order)
        assert result["approved"] is False

    async def test_get_portfolio_summary(self, order_manager, mock_supabase):
        mock_supabase.table().execute.return_value = MagicMock(data=[{
            "available_cash": 700_000_000,
            "current_nav": 1_000_000_000,
            "positions": [],
        }])
        summary = await order_manager.get_portfolio_summary()
        assert summary["available_cash"] == 700_000_000
