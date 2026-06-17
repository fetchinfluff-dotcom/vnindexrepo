from __future__ import annotations

from datetime import datetime

import pytest

from src.strategy.portfolio import VN100Portfolio


@pytest.fixture
def pf() -> VN100Portfolio:
    return VN100Portfolio(initial_cash=1_000_000_000.0)


def test_initial_state(pf):
    state = pf.get_state()
    assert state["cash"] == 1_000_000_000.0
    assert state["position_count"] == 0
    assert state["cash_pct"] == 100.0
    assert state["drawdown"] == 0.0
    assert state["trading_paused"] is False


def test_open_position(pf):
    pos = pf.open_position(
        ticker="VCB",
        quantity=1000,
        price=50_000.0,
        stop_loss=46_000.0,
        entry_date=datetime(2025, 1, 15),
    )
    assert pos is not None
    assert pos.ticker == "VCB"
    assert pos.sector == "Banking"
    assert pos.quantity == 1000
    assert pos.notional == 50_000_000.0
    assert pf.cash == 950_000_000.0
    assert pf.position_count == 1


def test_open_position_insufficient_cash(pf):
    pos = pf.open_position(
        ticker="VCB",
        quantity=100_000,
        price=500_000.0,
        stop_loss=460_000.0,
        entry_date=datetime(2025, 1, 15),
    )
    assert pos is None  # 50B notional > 1B cash


def test_max_positions_enforced(pf):
    for i, ticker in enumerate(["VCB", "CTG", "BID", "VPB", "MBB", "TCB", "ACB", "HDB", "STB", "MSB"]):
        pf.open_position(
            ticker=ticker,
            quantity=100,
            price=50_000.0,
            stop_loss=46_000.0,
            entry_date=datetime(2025, 1, 15),
        )
    assert pf.position_count == 10
    # 11th should fail
    pos = pf.open_position(
        ticker="TPB",
        quantity=100,
        price=50_000.0,
        stop_loss=46_000.0,
        entry_date=datetime(2025, 1, 16),
    )
    assert pos is None


def test_sector_cap_enforced(pf):
    pf.open_position(
        ticker="VCB", quantity=4000, price=50_000.0,
        stop_loss=46_000.0, entry_date=datetime(2025, 1, 15),
    )
    # VCB notional = 200M, sector = Banking
    # 200M / 1B = 20% → at limit
    pos2 = pf.open_position(
        ticker="CTG", quantity=100, price=50_000.0,
        stop_loss=46_000.0, entry_date=datetime(2025, 1, 16),
    )
    assert pos2 is None  # would exceed 20% sector cap


def test_close_position(pf):
    pf.open_position(
        ticker="VCB", quantity=1000, price=50_000.0,
        stop_loss=46_000.0, entry_date=datetime(2025, 1, 15),
    )
    closed = pf.close_position(
        ticker="VCB", exit_price=55_000.0,
        exit_date=datetime(2025, 1, 30), reason="tp_hit",
    )
    assert closed is not None
    assert closed.pnl == 5_000_000.0  # (55k - 50k) * 1000
    assert closed.pnl_pct == 0.10
    assert closed.exit_reason == "tp_hit"
    assert pf.position_count == 0
    assert pf.cash == 950_000_000.0 + 55_000_000.0  # initial - entry + proceeds


def test_reduce_position(pf):
    pf.open_position(
        ticker="VCB", quantity=1000, price=50_000.0,
        stop_loss=46_000.0, entry_date=datetime(2025, 1, 15),
    )
    pf.reduce_position(
        ticker="VCB", reduce_pct=0.50,
        exit_price=52_000.0, exit_date=datetime(2025, 1, 20),
        reason="tp1_hit",
    )
    pos = pf.positions["VCB"]
    assert pos.quantity == 500
    assert pos.notional == 500 * 52_000.0
    assert pf.cash == 950_000_000.0 + (500 * 52_000.0)


def test_drawdown_halts_trading(pf):
    pf.open_position(
        ticker="VCB", quantity=2_000, price=50_000.0,
        stop_loss=46_000.0, entry_date=datetime(2025, 1, 15),
    )
    pf.open_position(
        ticker="HPG", quantity=2_000, price=50_000.0,
        stop_loss=46_000.0, entry_date=datetime(2025, 1, 15),
    )
    pf.open_position(
        ticker="FPT", quantity=2_000, price=50_000.0,
        stop_loss=46_000.0, entry_date=datetime(2025, 1, 15),
    )
    # 3 positions × 100M each = 300M; cash = 700M
    # Simulate price crash to 25k → each position = 50M, total = 150M
    # Total value = 700M + 150M = 850M, DD = (1B - 850M) / 1B = 15%
    pf.update_position("VCB", 25_000.0, datetime(2025, 1, 20))
    pf.update_position("HPG", 25_000.0, datetime(2025, 1, 20))
    pf.update_position("FPT", 25_000.0, datetime(2025, 1, 20))
    assert pf.trading_paused is True
    check = pf.can_open_position("CTG", "Banking", 10_000_000.0)
    assert check["allowed"] is False
    assert "trading_paused_drawdown" in check["reasons"]


def test_get_sector_exposure(pf):
    pf.open_position(
        ticker="VCB", quantity=1000, price=50_000.0,
        stop_loss=46_000.0, entry_date=datetime(2025, 1, 15),
    )
    pf.open_position(
        ticker="CTG", quantity=500, price=40_000.0,
        stop_loss=37_000.0, entry_date=datetime(2025, 1, 16),
    )
    exposure = pf.get_sector_exposure("Banking")
    assert exposure == 50_000_000.0 + 20_000_000.0


def test_rebalance(pf):
    pf.open_position(
        ticker="VCB", quantity=3_000, price=50_000.0,
        stop_loss=46_000.0, entry_date=datetime(2025, 1, 15),
    )
    pf.open_position(
        ticker="CTG", quantity=1_000, price=50_000.0,
        stop_loss=46_000.0, entry_date=datetime(2025, 1, 15),
    )
    # Banking = (3k+1k)*50k = 200M, 20% of 1B = 200M → at limit
    # After price increase to 55k, Banking = 220M → 22% > 20%
    pf.update_position("VCB", 55_000.0, datetime(2025, 1, 31))
    pf.update_position("CTG", 55_000.0, datetime(2025, 1, 31))
    actions = pf.rebalance(datetime(2025, 1, 31))
    assert len(actions) > 0
    sector_pct = pf.get_sector_pct("Banking")
    assert sector_pct <= 0.21


def test_unknown_ticker_sector(pf):
    pos = pf.open_position(
        ticker="XYZ", quantity=100, price=50_000.0,
        stop_loss=46_000.0, entry_date=datetime(2025, 1, 15),
    )
    assert pos is not None
    assert pos.sector == "Others"


def test_can_open_position_already_held(pf):
    pf.open_position(
        ticker="VCB", quantity=100, price=50_000.0,
        stop_loss=46_000.0, entry_date=datetime(2025, 1, 15),
    )
    check = pf.can_open_position("VCB", "Banking", 10_000_000.0)
    assert check["allowed"] is False
    assert "already_held" in check["reasons"]


def test_state_includes_positions_and_sector(pf):
    pf.open_position(
        ticker="VCB", quantity=100, price=50_000.0,
        stop_loss=46_000.0, entry_date=datetime(2025, 1, 15),
    )
    state = pf.get_state()
    assert len(state["positions"]) == 1
    assert state["positions"][0]["ticker"] == "VCB"
    assert "Banking" in state["sector_exposure"]


def test_update_position_updates_value(pf):
    pf.open_position(
        ticker="VCB", quantity=1000, price=50_000.0,
        stop_loss=46_000.0, entry_date=datetime(2025, 1, 15),
    )
    pf.update_position("VCB", 55_000.0, datetime(2025, 1, 20))
    pos = pf.positions["VCB"]
    assert pos.current_price == 55_000.0
    assert pos.notional == 55_000_000.0


def test_close_nonexistent_position(pf):
    closed = pf.close_position("NONEXIST", 50_000.0, datetime(2025, 1, 15))
    assert closed is None


def test_reduce_nonexistent_position(pf):
    result = pf.reduce_position("NONEXIST", 0.5, 50_000.0, datetime(2025, 1, 15))
    assert result is None
