from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


INTERSIGNAL_PORTFOLIO_OS_V1 = "INTERSIGNAL_PORTFOLIO_OS_V1"


class PortfolioApiModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @field_validator("generated_at", "valuation_timestamp", check_fields=False)
    @classmethod
    def require_aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Portfolio API timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)


class PortfolioAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class PortfolioMeta(PortfolioApiModel):
    read_only: bool = True
    source_contract: str = "INTERSIGNAL_PORTFOLIO_OS_SNAPSHOT_V1"
    auth_enforcement: str = "NOT_IMPLEMENTED"
    broker_integration: str = "NOT_IMPLEMENTED"
    live_market_integration: str = "NOT_CONFIGURED"
    internal_paths_exposed: bool = False
    unavailable_sections: tuple[str, ...] = ()


class PortfolioOptionView(PortfolioApiModel):
    portfolio_id: str
    name: str
    portfolio_type: str
    source_type: str


class PortfolioView(PortfolioOptionView):
    currency: str
    status: str


class PortfolioSummaryView(PortfolioApiModel):
    portfolio_value: Decimal
    invested: Decimal
    cash: Decimal
    invested_pct: Decimal | None = None
    cash_pct: Decimal | None = None
    cost_basis: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    valuation_timestamp: datetime


class LotView(PortfolioApiModel):
    lot_id: str
    acquisition_date: date
    quantity: Decimal
    entry_price: Decimal
    cost_basis: Decimal
    remaining_quantity: Decimal
    realized_status: str


class HoldingView(PortfolioApiModel):
    holding_id: str
    security_id: str
    symbol: str
    name: str
    instrument_type: str
    quantity: Decimal
    average_cost: Decimal
    current_price: Decimal
    market_value: Decimal
    cost_basis: Decimal
    weight: Decimal | None = None
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal | None = None
    sector: str | None = None
    industry: str | None = None
    currency: str
    as_of: datetime
    lots: tuple[LotView, ...] = ()


class ExposureItemView(PortfolioApiModel):
    label: str
    weight: Decimal


class AllocationView(PortfolioApiModel):
    invested_pct: Decimal | None = None
    cash_pct: Decimal | None = None
    gross_exposure: Decimal | None = None
    net_exposure: Decimal | None = None
    sectors: tuple[ExposureItemView, ...] = ()


class ConcentrationView(PortfolioApiModel):
    holding_count: int = Field(ge=0)
    top_holding_weight: Decimal | None = None
    top_sector_weight: Decimal | None = None
    top_five_weight: Decimal | None = None
    risk_flags: tuple[str, ...] = ()


class BenchmarkView(PortfolioApiModel):
    benchmark_id: str
    name: str
    portfolio_return: Decimal
    benchmark_return: Decimal
    difference: Decimal
    period_start: date
    period_end: date


class PerformancePointView(PortfolioApiModel):
    date: date
    equity: Decimal
    cash: Decimal
    invested_value: Decimal
    daily_return: Decimal
    cumulative_return: Decimal
    benchmark_value: Decimal | None = None


class PerformanceView(PortfolioApiModel):
    realized_pnl: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    total_pnl: Decimal | None = None
    benchmark: BenchmarkView | None = None
    points: tuple[PerformancePointView, ...] = ()
    chart_available: bool = False


class ActivityView(PortfolioApiModel):
    activity_id: str
    occurred_at: str
    activity_type: str
    security: str | None = None
    quantity: Decimal | None = None
    amount: Decimal | None = None
    currency: str | None = None
    reference: str
    description: str | None = None


class PortfolioResponseBase(PortfolioApiModel):
    version: str = INTERSIGNAL_PORTFOLIO_OS_V1
    generated_at: datetime
    status: PortfolioAvailability
    reason: str | None = None
    has_portfolio: bool
    portfolio: PortfolioView | None = None
    portfolios: tuple[PortfolioOptionView, ...] = ()
    meta: PortfolioMeta


class PortfolioOverviewResponse(PortfolioResponseBase):
    summary: PortfolioSummaryView | None = None
    holdings: tuple[HoldingView, ...] = ()
    allocation: AllocationView | None = None
    concentration: ConcentrationView | None = None
    benchmark: BenchmarkView | None = None
    performance: PerformanceView | None = None
    recent_activity: tuple[ActivityView, ...] = ()


class PortfolioHoldingsResponse(PortfolioResponseBase):
    items: tuple[HoldingView, ...] = ()
    total_count: int = Field(ge=0)


class PortfolioActivityResponse(PortfolioResponseBase):
    items: tuple[ActivityView, ...] = ()
    total_count: int = Field(ge=0)


class PortfolioPerformanceResponse(PortfolioResponseBase):
    performance: PerformanceView | None = None


__all__ = tuple(name for name in globals() if name.endswith(("View", "Response"))) + (
    "INTERSIGNAL_PORTFOLIO_OS_V1",
    "PortfolioAvailability",
    "PortfolioMeta",
)
