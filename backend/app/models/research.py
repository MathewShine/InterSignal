from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExecutionMode(StrEnum):
    INTRADAY = "INTRADAY"
    SWING = "SWING"


class MomentumClassification(StrEnum):
    EMERGING = "EMERGING"
    CONFIRMED = "CONFIRMED"


class CandidateStatus(StrEnum):
    DISCOVERED = "DISCOVERED"
    WATCH = "WATCH"
    BREAKOUT_DETECTED = "BREAKOUT_DETECTED"
    CONFIRMING = "CONFIRMING"
    ENTRY_ELIGIBLE = "ENTRY_ELIGIBLE"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class SignalStatus(StrEnum):
    GENERATED = "GENERATED"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


class StrategyConfigurationStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class OutcomeLabel(StrEnum):
    STRONG_WIN = "STRONG_WIN"
    WIN = "WIN"
    SMALL_WIN = "SMALL_WIN"
    BREAKEVEN = "BREAKEVEN"
    LOSS = "LOSS"
    STRONG_LOSS = "STRONG_LOSS"
    NO_FOLLOW_THROUGH = "NO_FOLLOW_THROUGH"
    FALSE_BREAKOUT = "FALSE_BREAKOUT"
    MISSED_WINNER = "MISSED_WINNER"
    GOOD_REJECTION = "GOOD_REJECTION"


class DomainModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Instrument(DomainModel):
    id: UUID | None = None
    provider_symbol: str | None = None
    exchange: str
    trading_symbol: str
    company_name: str
    isin: str | None = None
    sector: str | None = None
    industry: str | None = None
    instrument_type: str
    nifty500_member: bool = False
    active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Candle(DomainModel):
    id: UUID | None = None
    instrument_id: UUID
    trading_date: date | None = None
    candle_timestamp: datetime | None = None
    interval_code: str | None = None
    open: Decimal = Field(max_digits=18, decimal_places=4)
    high: Decimal = Field(max_digits=18, decimal_places=4)
    low: Decimal = Field(max_digits=18, decimal_places=4)
    close: Decimal = Field(max_digits=18, decimal_places=4)
    adjusted_close: Decimal | None = Field(default=None, max_digits=18, decimal_places=4)
    volume: int
    traded_value: Decimal | None = Field(default=None, max_digits=20, decimal_places=2)
    vwap: Decimal | None = Field(default=None, max_digits=18, decimal_places=4)
    source: str
    created_at: datetime | None = None

    @model_validator(mode="after")
    def validate_candle_shape(self) -> "Candle":
        if self.high < self.low:
            raise ValueError("high must be greater than or equal to low")
        if self.volume < 0:
            raise ValueError("volume must be non-negative")
        if self.trading_date is None and self.candle_timestamp is None:
            raise ValueError("either trading_date or candle_timestamp is required")
        return self


class MarketRegimeSnapshot(DomainModel):
    id: UUID | None = None
    calculated_at: datetime
    regime: str
    subtype: str | None = None
    score: Decimal
    confidence: Decimal | None = None
    nifty_trend_score: Decimal | None = None
    breadth_score: Decimal | None = None
    sector_score: Decimal | None = None
    global_gift_score: Decimal | None = None
    vix_score: Decimal | None = None
    intraday_confirmation_score: Decimal | None = None
    configuration_version_id: UUID | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class FeatureSnapshot(DomainModel):
    id: UUID | None = None
    instrument_id: UUID
    calculated_at: datetime
    timeframe: str
    feature_version: str
    features: dict[str, Any] = Field(default_factory=dict)
    relative_volume: Decimal | None = None
    relative_strength_nifty: Decimal | None = None
    relative_strength_sector: Decimal | None = None
    atr: Decimal | None = None
    atr_percent: Decimal | None = None
    vwap: Decimal | None = None
    distance_from_vwap: Decimal | None = None
    breakout_level: Decimal | None = None
    breakout_type: str | None = None
    breakout_quality: Decimal | None = None
    momentum_score: Decimal | None = None
    extension_score: Decimal | None = None
    created_at: datetime | None = None


class StrategyCandidate(DomainModel):
    id: UUID | None = None
    instrument_id: UUID
    detected_at: datetime
    strategy_name: str
    strategy_version: str
    execution_mode: ExecutionMode
    momentum_classification: MomentumClassification
    status: CandidateStatus = CandidateStatus.DISCOVERED
    feature_snapshot_id: UUID | None = None
    market_regime_snapshot_id: UUID | None = None
    news_event_id: UUID | None = None
    catalyst_context: dict[str, Any] | None = None
    base_score: Decimal | None = None
    adjusted_score: Decimal | None = None
    rejection_reason: str | None = None
    configuration_version_id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_rejection_reason(self) -> "StrategyCandidate":
        if self.status == CandidateStatus.REJECTED and not self.rejection_reason:
            raise ValueError("rejection_reason is required when status is REJECTED")
        return self


class SignalPenalty(DomainModel):
    id: UUID | None = None
    candidate_id: UUID
    penalty_type: str
    penalty_value: Decimal
    reason: str
    metadata: dict[str, Any] | None = None
    created_at: datetime | None = None


class TradeSignal(DomainModel):
    id: UUID | None = None
    candidate_id: UUID
    generated_at: datetime
    signal_type: str
    execution_mode: ExecutionMode
    entry_price: Decimal | None = None
    entry_price_low: Decimal | None = None
    entry_price_high: Decimal | None = None
    stop_price: Decimal
    target_price: Decimal | None = None
    risk_reward_ratio: Decimal | None = None
    planned_risk_amount: Decimal | None = None
    planned_position_size: Decimal | None = None
    signal_score: Decimal
    status: SignalStatus = SignalStatus.GENERATED
    configuration_version_id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_entry_range(self) -> "TradeSignal":
        if (
            self.entry_price_low is not None
            and self.entry_price_high is not None
            and self.entry_price_high < self.entry_price_low
        ):
            raise ValueError("entry_price_high must be greater than or equal to entry_price_low")
        return self


class StrategyConfiguration(DomainModel):
    id: UUID | None = None
    strategy_name: str
    version: str
    status: StrategyConfigurationStatus = StrategyConfigurationStatus.DRAFT
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    configuration: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CandidateOutcome(DomainModel):
    id: UUID | None = None
    candidate_id: UUID
    evaluation_completed_at: datetime
    return_5m: Decimal | None = None
    return_15m: Decimal | None = None
    return_30m: Decimal | None = None
    return_60m: Decimal | None = None
    return_eod: Decimal | None = None
    return_1d: Decimal | None = None
    return_2d: Decimal | None = None
    return_3d: Decimal | None = None
    return_4d: Decimal | None = None
    mfe: Decimal | None = None
    mae: Decimal | None = None
    mfe_r: Decimal | None = None
    mae_r: Decimal | None = None
    hit_0_5r: bool | None = None
    hit_1r: bool | None = None
    hit_1_5r: bool | None = None
    hit_2r: bool | None = None
    hit_3r: bool | None = None
    stop_hit: bool | None = None
    hit_1r_before_stop: bool | None = None
    hit_2r_before_stop: bool | None = None
    outcome_label: OutcomeLabel
    metadata: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

