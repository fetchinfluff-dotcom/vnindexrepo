from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class EntryConfig(BaseModel):
    macro_bull_required: bool = True
    pullback_threshold: float = 0.01
    foreign_net_buy_min: float = 0.0
    foreign_ratio_min: float = 0.40
    volume_ratio_min: float = 1.2
    candle_body_ratio_min: float = 0.50
    ceiling_buffer_pct: float = 0.97
    weekly_rsi_max: float = 70.0
    foreign_room_max_pct: float = 0.95
    sector_exposure_max_pct: float = 0.20


class ExitConfig(BaseModel):
    death_cross_reduce_pct: float = 0.50
    foreign_sell_streak_days: int = 5
    foreign_sell_streak_reduce_pct: float = 0.30
    tp1_reduce_pct: float = 0.40
    tp1_swing_high_threshold: float = 0.99
    tp2_reduce_pct: float = 0.30
    tp2_r_multiple: float = 2.5
    ema20_trail_reduce_pct: float = 1.0


class PositionSizingConfig(BaseModel):
    kelly_fraction: float = 0.25
    max_position_pct: float = 0.10
    max_sector_pct: float = 0.20
    min_cash_pct: float = 0.30
    foreign_room_reduce_threshold: float = 10.0
    foreign_room_block_threshold: float = 5.0
    ceiling_buffer_reduce_threshold: float = 2.0
    ceiling_buffer_min_factor: float = 0.30


class RiskConfig(BaseModel):
    max_loss_pct: float = 0.92
    tp1_reduce_pct: float = 0.40
    tp2_r_multiple: float = 2.5
    trail_reduce_pct: float = 0.30


class PortfolioConfig(BaseModel):
    initial_cash: float = 1_000_000_000.0
    max_positions: int = 10
    max_sector_pct: float = 0.20
    min_cash_pct: float = 0.30
    max_drawdown_pct: float = 0.15
    rebalance_frequency_days: int = 21


class ExecutionConfig(BaseModel):
    slippage_ato: float = 0.001
    slippage_atc: float = 0.0005
    default_mode: str = "buy_atc_sell_atc"


class StrategyConfig(BaseModel):
    entry: EntryConfig = Field(default_factory=EntryConfig)
    exit: ExitConfig = Field(default_factory=ExitConfig)
    sizing: PositionSizingConfig = Field(default_factory=PositionSizingConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    portfolio: PortfolioConfig = Field(default_factory=PortfolioConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    ticker_universe: List[str] = Field(default_factory=lambda: [])
    sector_map: Dict[str, str] = Field(default_factory=dict)
