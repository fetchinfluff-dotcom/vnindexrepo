from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

MAX_POSITIONS = 10
MAX_SECTOR_PCT = 0.20
MIN_CASH_PCT = 0.30
MAX_DRAWDOWN_PCT = 0.15
REQUIRED_SECTOR_KEYS = ["sector", "notional", "ticker"]

SECTOR_GROUPS = {
    "Banking": ["VCB", "CTG", "BID", "VPB", "MBB", "TCB", "ACB", "HDB", "STB", "MSB", "OCB", "NAB", "LPB", "TPB", "VIB", "SHB", "EIB"],
    "Real Estate": ["VIC", "VHM", "VRE", "NVL", "DXG", "KDH", "PDR", "NLG", "HDG", "HPX", "DIG", "HQC", "LDG", "QCG"],
    "Securities": ["SSI", "VND", "VCI", "HCM", "FTS", "MBS", "SHS", "BVS", "VIX", "ORS", "EVF", "AGR", "TVS"],
    "Steel": ["HPG", "NKG", "HSG", "TLH", "POM", "VIS", "DTL"],
    "Oil & Gas": ["GAS", "PLX", "PVD", "PVS", "PVC", "PVB", "POW"],
    "Retail": ["MWG", "FPT", "PNJ", "PET", "DGW", "SJG"],
    "Food & Beverage": ["SAB", "BHN", "VNM", "MSN", "KDC", "QNS", "LSS", "NSC"],
    "Construction": ["CTD", "HBC", "VGC", "HHV", "C4G", "CTI"],
    "Technology": ["FPT", "CMG", "ELC"],
    "Logistics": ["GMD", "SCS", "VSC", "VOS", "HUT", "HAH", "VJC", "HVN"],
    "Insurance": ["BVH", "PVI", "BMI", "MIG", "PTI"],
    "Others": [],
}


@dataclass
class Position:
    ticker: str
    sector: str
    entry_price: float
    quantity: int
    notional: float
    stop_loss: float
    entry_date: datetime
    current_price: float = 0.0
    take_profit_levels: List[Dict[str, Any]] = field(default_factory=list)
    exit_price: Optional[float] = None
    exit_date: Optional[datetime] = None
    exit_reason: Optional[str] = None
    pnl: float = 0.0
    pnl_pct: float = 0.0


class VN100Portfolio:

    def __init__(
        self,
        initial_cash: float = 1_000_000_000.0,
        max_positions: int = MAX_POSITIONS,
        max_sector_pct: float = MAX_SECTOR_PCT,
        min_cash_pct: float = MIN_CASH_PCT,
        max_drawdown_pct: float = MAX_DRAWDOWN_PCT,
    ):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.positions: Dict[str, Position] = {}
        self.closed_positions: List[Position] = []
        self.max_positions = max_positions
        self.max_sector_pct = max_sector_pct
        self.min_cash_pct = min_cash_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.peak_value = initial_cash
        self.current_value = initial_cash
        self.trading_paused = False
        self._sector_map: Dict[str, str] = self._build_sector_map()
        logger.info(
            "portfolio_initialized",
            initial_cash=initial_cash,
            max_positions=max_positions,
        )

    @staticmethod
    def _build_sector_map() -> Dict[str, str]:
        mapping = {}
        for sector, tickers in SECTOR_GROUPS.items():
            for t in tickers:
                mapping[t] = sector
        return mapping

    # ── queries ──────────────────────────────────────────────────

    def get_sector_exposure(self, sector: str) -> float:
        return sum(
            p.notional for p in self.positions.values()
            if p.sector == sector
        )

    def get_sector_pct(self, sector: str) -> float:
        tv = self.total_value
        return self.get_sector_exposure(sector) / tv if tv > 0 else 0.0

    @property
    def total_value(self) -> float:
        pos_value = sum(p.notional for p in self.positions.values())
        return self.cash + pos_value

    @property
    def position_count(self) -> int:
        return len(self.positions)

    @property
    def cash_pct(self) -> float:
        tv = self.total_value
        return self.cash / tv if tv > 0 else 1.0

    @property
    def drawdown(self) -> float:
        tv = self.total_value
        return (self.peak_value - tv) / self.peak_value if self.peak_value > 0 else 0.0

    # ── validation ───────────────────────────────────────────────

    def can_open_position(
        self,
        ticker: str,
        sector: str,
        notional: float,
    ) -> Dict[str, Any]:
        result = {"allowed": True, "reasons": []}

        if self.trading_paused:
            result["allowed"] = False
            result["reasons"].append("trading_paused_drawdown")
            return result

        if self.position_count >= self.max_positions:
            result["allowed"] = False
            result["reasons"].append(f"max_positions_{self.max_positions}")
            return result

        if ticker in self.positions:
            result["allowed"] = False
            result["reasons"].append("already_held")
            return result

        sector_exposure = self.get_sector_exposure(sector)
        sector_after = sector_exposure + notional
        tv = self.total_value
        if tv > 0 and (sector_after / tv) > self.max_sector_pct:
            result["allowed"] = False
            result["reasons"].append(f"sector_cap_{self.max_sector_pct:.0%}")
            return result

        cash_after = self.cash - notional
        tv_after = cash_after + sum(p.notional for p in self.positions.values()) + notional
        if tv_after > 0 and (cash_after / tv_after) < self.min_cash_pct:
            result["allowed"] = False
            result["reasons"].append(f"min_cash_{self.min_cash_pct:.0%}")
            return result

        return result

    # ── actions ──────────────────────────────────────────────────

    def open_position(
        self,
        ticker: str,
        quantity: int,
        price: float,
        stop_loss: float,
        entry_date: datetime,
        reason: str = "entry_signal",
    ) -> Optional[Position]:
        sector = self._sector_map.get(ticker, "Others")
        notional = quantity * price

        check = self.can_open_position(ticker, sector, notional)
        if not check["allowed"]:
            logger.warning("position_rejected", ticker=ticker, reasons=check["reasons"])
            return None

        if notional > self.cash:
            logger.warning("insufficient_cash", ticker=ticker, required=notional, cash=self.cash)
            return None

        pos = Position(
            ticker=ticker,
            sector=sector,
            entry_price=price,
            quantity=quantity,
            notional=notional,
            stop_loss=stop_loss,
            entry_date=entry_date,
            current_price=price,
        )
        self.positions[ticker] = pos
        self.cash -= notional
        self._update_peak()
        logger.info(
            "position_opened",
            ticker=ticker,
            quantity=quantity,
            price=price,
            notional=round(notional, 2),
            sector=sector,
            reason=reason,
        )
        return pos

    def update_position(
        self,
        ticker: str,
        current_price: float,
        date: datetime,
    ) -> None:
        pos = self.positions.get(ticker)
        if pos is None:
            return
        pos.current_price = current_price
        new_notional = current_price * pos.quantity
        delta = new_notional - pos.notional
        pos.notional = new_notional
        self._update_peak()

    def close_position(
        self,
        ticker: str,
        exit_price: float,
        exit_date: datetime,
        reason: str = "manual_exit",
    ) -> Optional[Position]:
        pos = self.positions.pop(ticker, None)
        if pos is None:
            return None

        pos.exit_price = exit_price
        pos.exit_date = exit_date
        pos.exit_reason = reason
        pos.pnl = (exit_price - pos.entry_price) * pos.quantity
        pos.pnl_pct = (exit_price - pos.entry_price) / pos.entry_price
        pos.notional = 0.0

        proceeds = exit_price * pos.quantity
        self.cash += proceeds

        self.closed_positions.append(pos)
        self._update_peak()
        logger.info(
            "position_closed",
            ticker=ticker,
            exit_price=exit_price,
            pnl=round(pos.pnl, 2),
            pnl_pct=round(pos.pnl_pct * 100, 2),
            reason=reason,
        )
        return pos

    def reduce_position(
        self,
        ticker: str,
        reduce_pct: float,
        exit_price: float,
        exit_date: datetime,
        reason: str = "partial_reduce",
    ) -> Optional[float]:
        pos = self.positions.get(ticker)
        if pos is None:
            return None

        reduce_qty = int(pos.quantity * reduce_pct)
        if reduce_qty <= 0:
            return 0.0

        pos.quantity -= reduce_qty
        pos.notional = pos.quantity * exit_price
        proceeds = reduce_qty * exit_price
        self.cash += proceeds
        self._update_peak()
        logger.info(
            "position_reduced",
            ticker=ticker,
            reduced_qty=reduce_qty,
            remaining_qty=pos.quantity,
            price=exit_price,
            reason=reason,
        )
        return float(proceeds)

    # ── maintenance ──────────────────────────────────────────────

    def _update_peak(self) -> None:
        tv = self.total_value
        if tv > self.peak_value:
            self.peak_value = tv
        dd = self.drawdown
        if dd >= self.max_drawdown_pct:
            self.trading_paused = True
            logger.warning(
                "drawdown_limit_breached",
                drawdown=round(dd * 100, 2),
                limit=round(self.max_drawdown_pct * 100, 2),
            )

    def rebalance(self, current_date: datetime) -> List[Dict[str, Any]]:
        actions: List[Dict[str, Any]] = []
        tv = self.total_value

        for sector in set(p.sector for p in self.positions.values()):
            sector_exposure = self.get_sector_exposure(sector)
            sector_pct = sector_exposure / tv if tv > 0 else 0
            if sector_pct > self.max_sector_pct:
                excess = sector_exposure - (tv * self.max_sector_pct)
                positions_in_sector = [
                    p for p in self.positions.values() if p.sector == sector
                ]
                if positions_in_sector:
                    reduce_by = excess / len(positions_in_sector)
                    for p in positions_in_sector:
                        reduce_qty = int(reduce_by / p.current_price) if p.current_price > 0 else 0
                        if reduce_qty > 0 and reduce_qty < p.quantity:
                            p.quantity -= reduce_qty
                            p.notional = p.quantity * p.current_price
                            self.cash += reduce_qty * p.current_price
                            actions.append({
                                "action": "reduce_sector",
                                "ticker": p.ticker,
                                "qty": reduce_qty,
                                "reason": f"sector_rebalance_{sector}",
                            })

        excess_cash = self.cash - (tv * self.min_cash_pct)
        if excess_cash > 0:
            pass

        self._update_peak()
        logger.info("rebalance_complete", actions=len(actions))
        return actions

    def get_state(self) -> Dict[str, Any]:
        return {
            "cash": round(self.cash, 2),
            "total_value": round(self.total_value, 2),
            "position_count": self.position_count,
            "cash_pct": round(self.cash_pct * 100, 2),
            "drawdown": round(self.drawdown * 100, 2),
            "trading_paused": self.trading_paused,
            "positions": [
                {
                    "ticker": p.ticker,
                    "sector": p.sector,
                    "entry_price": p.entry_price,
                    "quantity": p.quantity,
                    "notional": round(p.notional, 2),
                    "current_price": p.current_price,
                    "unrealized_pnl": round(
                        (p.current_price - p.entry_price) * p.quantity, 2
                    ),
                    "stop_loss": p.stop_loss,
                }
                for p in self.positions.values()
            ],
            "sector_exposure": {
                sector: round(self.get_sector_exposure(sector), 2)
                for sector in set(
                    list(self._sector_map.values())
                    + [p.sector for p in self.positions.values()]
                )
            },
        }
