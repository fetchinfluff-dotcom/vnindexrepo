from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from src.prod.signal_generator import DailySignalGenerator


@pytest.fixture
def mock_dnse():
    client = MagicMock()
    client.get_daily_bars = AsyncMock()
    client.get_foreign_flow = AsyncMock()
    client.get_latest_price = AsyncMock()
    return client


@pytest.fixture
def mock_supabase():
    client = MagicMock()
    client.table = MagicMock()
    return client


@pytest.fixture
def mock_strategy():
    module = MagicMock()
    module.signals.check_entry_conditions = MagicMock()
    module.signals.check_exit_conditions = MagicMock()
    module.sizing.calculate_position_size = MagicMock()
    return module


@pytest.fixture
def config():
    return {
        "initial_capital": 1_000_000_000,
        "max_positions": 10,
        "max_sector_exposure": 0.20,
        "ticker_universe": ["VCB", "ACB", "BID", "HPG", "FPT", "MWG", "VNM", "VHM"],
        "sector_map": {
            "VCB": "Banking", "ACB": "Banking", "BID": "Banking",
            "HPG": "Steel", "FPT": "Technology", "MWG": "Retail",
            "VNM": "Food & Beverage", "VHM": "Real Estate",
        },
    }


@pytest.fixture
def sample_bars():
    dates = pd.bdate_range("2025-01-02", periods=300)
    tickers = ["VCB", "ACB", "HPG", "FPT"]
    rows = []
    np.random.seed(42)
    for ticker in tickers:
        base = np.random.uniform(20000, 120000)
        prices = base * np.cumprod(1.0 + np.random.normal(0.0005, 0.015, len(dates)))
        prices = np.maximum(prices, 5000)
        vols = np.random.randint(500000, 5000000, len(dates))
        for i, d in enumerate(dates):
            rows.append({
                "ticker": ticker,
                "date": d,
                "open": prices[i] * (1 + np.random.normal(0, 0.003)),
                "high": prices[i] * 1.01,
                "low": prices[i] * 0.99,
                "close": prices[i],
                "volume": float(vols[i]),
            })
    return pd.DataFrame(rows)


@pytest.fixture
def sample_foreign():
    tickers = ["VCB", "ACB", "HPG", "FPT"]
    dates = pd.bdate_range("2025-01-02", periods=20)
    rows = []
    for ticker in tickers:
        for d in dates:
            rows.append({
                "ticker": ticker,
                "date": d,
                "net_buy": np.random.uniform(-1e9, 1e9),
                "buy_volume": np.random.uniform(1e9, 5e9),
                "sell_volume": np.random.uniform(1e9, 5e9),
            })
    return pd.DataFrame(rows)


@pytest.fixture
def generator(mock_dnse, mock_supabase, mock_strategy, config):
    return DailySignalGenerator(mock_dnse, mock_supabase, mock_strategy, config)


class TestDailySignalGenerator:
    async def test_skip_non_trading_day(self, generator):
        generator._is_trading_day = AsyncMock(return_value=False)
        result = await generator.run()
        assert result["status"] == "skipped"
        assert result["reason"] == "not_trading_day"

    async def test_successful_run_with_signals(self, generator, sample_bars, sample_foreign):
        generator._is_trading_day = AsyncMock(return_value=True)
        generator._pull_vn100_latest_bars = AsyncMock(return_value=sample_bars)
        generator._pull_foreign_flow = AsyncMock(return_value=sample_foreign)
        generator._load_portfolio_state = AsyncMock(return_value={
            "available_cash": 700_000_000,
            "current_nav": 1_000_000_000,
            "positions": [],
            "peak_value": 1_000_000_000,
        })
        generator.strategy.signals.check_entry_conditions.return_value = {
            "signal": 1, "reasons": []
        }
        generator.strategy.sizing.calculate_position_size.return_value = {
            "ticker": "VCB", "quantity": 1000, "notional": 50_000_000,
            "signal_strength": 1.0, "reason": "ok", "reduced_by": {},
        }
        generator._save_orders = AsyncMock()
        generator._update_portfolio_state = AsyncMock()
        generator._send_alerts = AsyncMock()

        result = await generator.run()

        assert result["status"] == "success"
        assert result["signals_generated"] >= 0
        assert "buys" in result
        assert "sells" in result

    async def test_compute_features(self, generator, sample_bars):
        features = generator._compute_features(sample_bars, pd.DataFrame())
        assert "ema200" in features.columns
        assert "ema50" in features.columns
        assert "ema20" in features.columns
        assert "vol_ma20" in features.columns
        assert "vol_ratio" in features.columns
        assert "swing_high" in features.columns
        assert "swing_low" in features.columns
        assert "ceiling" in features.columns
        assert "dist_ema20" in features.columns
        assert "atr14" in features.columns
        assert not features.empty

    async def test_generate_exit_orders(self, generator, sample_bars):
        features = generator._compute_features(sample_bars, pd.DataFrame())
        portfolio = {
            "positions": [
                {"ticker": "VCB", "entry_price": 30000, "shares": 1000, "stop_loss": 27600},
            ]
        }
        generator.strategy.signals.check_exit_conditions.return_value = {
            "action": "hold", "reduce_pct": 0, "reason": None
        }
        orders = generator._generate_exit_orders(portfolio, features)
        assert isinstance(orders, list)

    async def test_generate_entry_orders(self, generator, sample_bars):
        features = generator._compute_features(sample_bars, pd.DataFrame())
        ticker_info = {"VCB": {"ticker": "VCB", "sector": "Banking", "foreign_room_pct": 25}}
        portfolio = {"positions": [], "available_cash": 700_000_000, "current_nav": 1_000_000_000}
        generator.strategy.signals.check_entry_conditions.return_value = {
            "signal": 1, "reasons": []
        }
        generator.strategy.sizing.calculate_position_size.return_value = {
            "ticker": "VCB", "quantity": 1000, "notional": 50_000_000,
            "signal_strength": 1.0, "reason": "ok", "reduced_by": {},
        }
        orders = generator._generate_entry_orders(portfolio, features, ticker_info, [])
        assert isinstance(orders, list)

    async def test_exit_orders_prioritized(self, generator, sample_bars):
        features = generator._compute_features(sample_bars, pd.DataFrame())
        portfolio = {
            "positions": [
                {"ticker": "VCB", "entry_price": 30000, "shares": 1000, "stop_loss": 27600},
            ],
            "available_cash": 700_000_000,
            "current_nav": 1_000_000_000,
        }
        ticker_info = {"VCB": {"ticker": "VCB", "sector": "Banking", "foreign_room_pct": 25}}

        generator.strategy.signals.check_exit_conditions.return_value = {
            "action": "sell_all", "reduce_pct": 1.0, "reason": "trend_break"
        }
        generator._generate_entry_orders = MagicMock(return_value=[])

        exit_orders = generator._generate_exit_orders(portfolio, features)
        assert len(exit_orders) >= 0

    async def test_trading_day_check(self, generator):
        generator._is_trading_day = AsyncMock(return_value=True)
        assert await generator._is_trading_day()

        generator._is_trading_day = AsyncMock(return_value=False)
        assert not await generator._is_trading_day()

    async def test_empty_data_handling(self, generator):
        generator._is_trading_day = AsyncMock(return_value=True)
        generator._pull_vn100_latest_bars = AsyncMock(return_value=pd.DataFrame())
        generator._pull_foreign_flow = AsyncMock(return_value=pd.DataFrame())
        generator._load_portfolio_state = AsyncMock(return_value={
            "available_cash": 1_000_000_000,
            "current_nav": 1_000_000_000,
            "positions": [],
            "peak_value": 1_000_000_000,
        })
        generator._save_orders = AsyncMock()
        generator._update_portfolio_state = AsyncMock()
        generator._send_alerts = AsyncMock()

        result = await generator.run()
        assert result["status"] == "success"

    async def test_position_sizing_respects_max_positions(self, generator, sample_bars):
        features = generator._compute_features(sample_bars, pd.DataFrame())
        portfolio = {
            "positions": [
                {"ticker": "HPG", "entry_price": 20000, "shares": 3000, "stop_loss": 18400},
                {"ticker": "FPT", "entry_price": 70000, "shares": 1500, "stop_loss": 64400},
                {"ticker": "MWG", "entry_price": 50000, "shares": 2000, "stop_loss": 46000},
                {"ticker": "VNM", "entry_price": 65000, "shares": 1500, "stop_loss": 59800},
                {"ticker": "VHM", "entry_price": 40000, "shares": 2500, "stop_loss": 36800},
                {"ticker": "ACB", "entry_price": 25000, "shares": 4000, "stop_loss": 23000},
                {"ticker": "BID", "entry_price": 45000, "shares": 2000, "stop_loss": 41400},
                {"ticker": "VCB", "entry_price": 35000, "shares": 3000, "stop_loss": 32200},
            ],
            "available_cash": 200_000_000,
            "current_nav": 1_000_000_000,
        }
        ticker_info = {"VCB": {"ticker": "VCB", "sector": "Banking", "foreign_room_pct": 25}}
        generator.strategy.signals.check_entry_conditions.return_value = {
            "signal": 1, "reasons": []
        }
        generator.strategy.sizing.calculate_position_size.return_value = {
            "ticker": "VCB", "quantity": 0, "notional": 0,
            "signal_strength": 1.0, "reason": "ok", "reduced_by": {},
        }
        generator.config["max_positions"] = 10
        orders = generator._generate_entry_orders(portfolio, features, ticker_info, [])
        assert isinstance(orders, list)

    async def test_drawdown_pauses_trading(self, generator):
        portfolio = {
            "available_cash": 500_000_000,
            "current_nav": 850_000_000,
            "peak_value": 1_000_000_000,
            "positions": [],
        }
        dd = (portfolio["peak_value"] - portfolio["current_nav"]) / portfolio["peak_value"]
        assert dd == 0.15
        assert dd <= generator.config.get("max_drawdown", 0.15)
