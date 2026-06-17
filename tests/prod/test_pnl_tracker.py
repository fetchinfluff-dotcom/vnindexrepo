from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.prod.pnl_tracker import PnLTracker


@pytest.fixture
def mock_supabase():
    client = MagicMock()
    table = MagicMock()
    table.select = MagicMock(return_value=table)
    table.order = MagicMock(return_value=table)
    table.limit = MagicMock(return_value=table)
    table.insert = MagicMock(return_value=table)
    table.eq = MagicMock(return_value=table)
    table.execute = AsyncMock()
    client.table = MagicMock(return_value=table)
    return client


@pytest.fixture
def config():
    return {
        "initial_capital": 1_000_000_000,
        "sector_map": {"VCB": "Banking", "HPG": "Steel", "FPT": "Technology"},
    }


@pytest.fixture
def tracker(mock_supabase, config, tmp_path):
    return PnLTracker(mock_supabase, config, output_dir=str(tmp_path))


class TestPnLTracker:
    async def test_compute_daily_pnl(self, tracker, mock_supabase):
        mock_supabase.table().execute.return_value = MagicMock(data=[{
            "available_cash": 700_000_000,
            "current_nav": 1_000_000_000,
            "positions": [
                {"ticker": "VCB", "quantity": 5000, "entry_price": 25000,
                 "entry_date": "2026-06-01T00:00:00"},
            ],
            "peak_value": 1_000_000_000,
        }])
        prices = {"VCB": 26200}
        result = await tracker.compute_daily_pnl(prices)
        assert "nav" in result
        assert result["position_count"] == 1

    async def test_empty_portfolio(self, tracker, mock_supabase):
        mock_supabase.table().execute.return_value = MagicMock(data=[{
            "available_cash": 1_000_000_000,
            "current_nav": 1_000_000_000,
            "positions": [],
            "peak_value": 1_000_000_000,
        }])
        result = await tracker.compute_daily_pnl({})
        assert result["position_count"] == 0
        assert result["nav"] == 1_000_000_000

    async def test_holding_bucket(self, tracker):
        assert tracker._holding_bucket(3) == "0-5d"
        assert tracker._holding_bucket(10) == "5-20d"
        assert tracker._holding_bucket(30) == "20-60d"
        assert tracker._holding_bucket(100) == "60+d"

    async def test_attribution(self, tracker, mock_supabase):
        mock_supabase.table().execute.return_value = MagicMock(data=[{
            "available_cash": 700_000_000,
            "current_nav": 1_000_000_000,
            "positions": [
                {"ticker": "VCB", "quantity": 5000, "entry_price": 25000,
                 "entry_date": "2026-06-01T00:00:00"},
                {"ticker": "HPG", "quantity": 3000, "entry_price": 20000,
                 "entry_date": "2026-06-10T00:00:00"},
            ],
            "peak_value": 1_000_000_000,
        }])
        result = await tracker.compute_attribution({"VCB": 26200, "HPG": 19500})
        assert "by_sector" in result
        assert "Banking" in result["by_sector"]

    async def test_generate_weekly_summary(self, tracker, mock_supabase):
        mock_supabase.table().execute.return_value = MagicMock(data=[
            {"date": "2026-06-16", "nav": 1_000_000_000, "daily_pnl": 5_000_000,
             "unrealized_pnl": 3_000_000, "realized_pnl": 2_000_000,
             "cash": 700_000_000, "total_cost": 300_000_000, "position_count": 3},
            {"date": "2026-06-15", "nav": 995_000_000, "daily_pnl": -2_000_000,
             "unrealized_pnl": -1_000_000, "realized_pnl": -1_000_000,
             "cash": 700_000_000, "total_cost": 300_000_000, "position_count": 3},
        ])
        summary = await tracker.generate_weekly_summary()
        assert "total_pnl" in summary
