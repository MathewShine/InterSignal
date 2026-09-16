from __future__ import annotations

import re
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator, model_validator

from app.platform.models import ImmutableDomainModel


HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ZERO = Decimal("0")
TOLERANCE = Decimal("0.000001")


class PortfolioOSModel(ImmutableDomainModel):
    @field_validator(
        "as_of",
        "timestamp",
        "generated_at",
        check_fields=False,
    )
    @classmethod
    def require_aware_portfolio_timestamp(
        cls, value: datetime | None
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Portfolio OS timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @field_validator("base_currency", "currency", check_fields=False)
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not 3 <= len(normalized) <= 8 or not normalized.isalnum():
            raise ValueError("currency must be a 3-8 character alphanumeric code")
        return normalized


class PortfolioType(StrEnum):
    RESEARCH = "RESEARCH"
    INVESTMENT = "INVESTMENT"
    TRADING = "TRADING"
    SHADOW = "SHADOW"
    MANUAL = "MANUAL"
    CONSOLIDATED = "CONSOLIDATED"


class PortfolioStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    NOT_READY = "NOT_READY"


class AccountProvider(StrEnum):
    GROWW = "GROWW"
    ZERODHA = "ZERODHA"
    MANUAL = "MANUAL"
    SIMULATED = "SIMULATED"
    OTHER = "OTHER"


class AccountType(StrEnum):
    BROKERAGE = "BROKERAGE"
    CASH = "CASH"
    MUTUAL_FUND = "MUTUAL_FUND"
    MANUAL = "MANUAL"
    RESEARCH = "RESEARCH"
    OTHER = "OTHER"


class AccountStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"
    NOT_READY = "NOT_READY"


class BrokerSyncState(StrEnum):
    NEVER_SYNCED = "NEVER_SYNCED"
    SYNC_PENDING = "SYNC_PENDING"
    SYNCED = "SYNCED"
    STALE = "STALE"
    ERROR = "ERROR"


class InstrumentType(StrEnum):
    EQUITY = "EQUITY"
    ETF = "ETF"
    MUTUAL_FUND = "MUTUAL_FUND"
    INDEX = "INDEX"
    CASH = "CASH"
    OTHER = "OTHER"


class TransactionType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    DIVIDEND = "DIVIDEND"
    INTEREST = "INTEREST"
    FEE = "FEE"
    TAX = "TAX"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    TRANSFER_IN = "TRANSFER_IN"
    TRANSFER_OUT = "TRANSFER_OUT"
    CORPORATE_ACTION = "CORPORATE_ACTION"
    ADJUSTMENT = "ADJUSTMENT"
    REVERSAL = "REVERSAL"


class CorporateActionType(StrEnum):
    SPLIT = "SPLIT"
    BONUS = "BONUS"
    DIVIDEND = "DIVIDEND"
    RIGHTS = "RIGHTS"
    MERGER_DEMERGER_ADJUSTMENT = "MERGER_DEMERGER_ADJUSTMENT"


class PortfolioEventType(StrEnum):
    PORTFOLIO_CREATED = "PORTFOLIO_CREATED"
    ACCOUNT_LINKED = "ACCOUNT_LINKED"
    TRANSACTION_RECORDED = "TRANSACTION_RECORDED"
    HOLDING_REBUILT = "HOLDING_REBUILT"
    VALUATION_CREATED = "VALUATION_CREATED"
    RISK_SNAPSHOT_CREATED = "RISK_SNAPSHOT_CREATED"
    BENCHMARK_LINKED = "BENCHMARK_LINKED"
    STATUS_CHANGED = "STATUS_CHANGED"
    MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT"


class RiskFlag(StrEnum):
    CONCENTRATION_HIGH = "CONCENTRATION_HIGH"
    CASH_LOW = "CASH_LOW"
    TURNOVER_HIGH = "TURNOVER_HIGH"
    COST_DRAG_HIGH = "COST_DRAG_HIGH"
    STALE_VALUATION = "STALE_VALUATION"
    MISSING_PRICE = "MISSING_PRICE"
    DATA_QUALITY_WARNING = "DATA_QUALITY_WARNING"
    FX_CONVERSION_REQUIRED = "FX_CONVERSION_REQUIRED"


class GoalStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class IntegrityStatus(StrEnum):
    HEALTHY = "HEALTHY"
    ERROR = "ERROR"


class LotPolicy(StrEnum):
    FIFO = "FIFO"


class Portfolio(PortfolioOSModel):
    portfolio_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    portfolio_type: PortfolioType
    base_currency: str
    market_scope: tuple[str, ...]
    status: PortfolioStatus
    created_at: datetime
    updated_at: datetime
    benchmark_ids: tuple[str, ...] = ()
    account_ids: tuple[str, ...] = ()
    strategy_ids: tuple[str, ...] = ()
    goal_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_portfolio_dates(self) -> "Portfolio":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        return self


class PortfolioAccount(PortfolioOSModel):
    account_id: str = Field(min_length=1)
    portfolio_id: str = Field(min_length=1)
    account_type: AccountType
    provider: AccountProvider
    provider_account_reference: str = Field(min_length=1)
    currency: str
    status: AccountStatus
    created_at: datetime
    broker_sync_state: BrokerSyncState = BrokerSyncState.NEVER_SYNCED
    metadata: dict[str, Any] = Field(default_factory=dict)


class CashBalance(PortfolioOSModel):
    account_id: str = Field(min_length=1)
    currency: str
    available_cash: Decimal
    settled_cash: Decimal
    reserved_cash: Decimal = ZERO
    as_of: datetime
    source: str = Field(min_length=1)
    lineage_node_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_cash(self) -> "CashBalance":
        if self.reserved_cash < ZERO:
            raise ValueError("reserved_cash cannot be negative")
        if self.available_cash + self.reserved_cash > self.settled_cash:
            raise ValueError("available plus reserved cash cannot exceed settled cash")
        return self


class SecurityReference(PortfolioOSModel):
    security_id: str = Field(min_length=1)
    market: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    isin: str | None = None
    instrument_type: InstrumentType
    currency: str
    name: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Holding(PortfolioOSModel):
    holding_id: str = Field(min_length=1)
    portfolio_id: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    security_id: str = Field(min_length=1)
    quantity: Decimal = Field(ge=ZERO)
    average_cost: Decimal = Field(ge=ZERO)
    current_price: Decimal = Field(ge=ZERO)
    market_value: Decimal
    cost_basis: Decimal = Field(ge=ZERO)
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal | None = None
    currency: str
    as_of: datetime
    source: str = Field(min_length=1)
    strategy_attribution: dict[str, Decimal] = Field(default_factory=dict)
    evidence_id: str | None = None
    lineage_node_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_holding_math(self) -> "Holding":
        expected_market = self.quantity * self.current_price
        expected_pnl = self.market_value - self.cost_basis
        if abs(self.market_value - expected_market) > TOLERANCE:
            raise ValueError("market_value must equal quantity * current_price")
        if abs(self.unrealized_pnl - expected_pnl) > TOLERANCE:
            raise ValueError("unrealized_pnl must equal market_value - cost_basis")
        if self.cost_basis > ZERO:
            expected_pct = self.unrealized_pnl / self.cost_basis
            if self.unrealized_pnl_pct is None or abs(
                self.unrealized_pnl_pct - expected_pct
            ) > TOLERANCE:
                raise ValueError("unrealized_pnl_pct is inconsistent")
        return self


class PositionLot(PortfolioOSModel):
    lot_id: str = Field(min_length=1)
    holding_id: str = Field(min_length=1)
    security_id: str = Field(min_length=1)
    quantity: Decimal = Field(gt=ZERO)
    entry_price: Decimal = Field(gt=ZERO)
    entry_date: date
    remaining_quantity: Decimal = Field(ge=ZERO)
    cost_basis: Decimal = Field(ge=ZERO)
    source_transaction_ids: tuple[str, ...]
    strategy_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_lot(self) -> "PositionLot":
        if self.remaining_quantity > self.quantity:
            raise ValueError("remaining_quantity cannot exceed original quantity")
        if abs(self.cost_basis - self.remaining_quantity * self.entry_price) > TOLERANCE:
            raise ValueError("lot cost_basis is inconsistent")
        return self


class PortfolioTransaction(PortfolioOSModel):
    transaction_id: str = Field(min_length=1)
    portfolio_id: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    security_id: str | None = None
    transaction_type: TransactionType
    quantity: Decimal = ZERO
    price: Decimal = ZERO
    gross_amount: Decimal = ZERO
    fees: Decimal = Field(default=ZERO, ge=ZERO)
    taxes: Decimal = Field(default=ZERO, ge=ZERO)
    net_amount: Decimal
    currency: str
    trade_date: date
    settlement_date: date
    source: str = Field(min_length=1)
    external_reference: str | None = None
    strategy_id: str | None = None
    evidence_id: str | None = None
    lineage_node_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_transaction(self) -> "PortfolioTransaction":
        if self.settlement_date < self.trade_date:
            raise ValueError("settlement_date cannot precede trade_date")
        if self.transaction_type in {TransactionType.BUY, TransactionType.SELL}:
            if not self.security_id or self.quantity <= ZERO or self.price <= ZERO:
                raise ValueError("BUY/SELL require security, positive quantity and price")
            if abs(self.gross_amount - self.quantity * self.price) > TOLERANCE:
                raise ValueError("gross_amount must equal quantity * price")
            expected = (
                -(self.gross_amount + self.fees + self.taxes)
                if self.transaction_type == TransactionType.BUY
                else self.gross_amount - self.fees - self.taxes
            )
            if abs(self.net_amount - expected) > TOLERANCE:
                raise ValueError("net_amount is inconsistent with BUY/SELL cash flow")
        return self


class PortfolioValuation(PortfolioOSModel):
    portfolio_id: str = Field(min_length=1)
    as_of: datetime
    gross_market_value: Decimal = Field(ge=ZERO)
    cash: Decimal
    net_liquidation_value: Decimal
    cost_basis: Decimal = Field(ge=ZERO)
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    currency: str
    source: str = Field(min_length=1)
    lineage_node_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_valuation(self) -> "PortfolioValuation":
        if abs(
            self.net_liquidation_value - (self.gross_market_value + self.cash)
        ) > TOLERANCE:
            raise ValueError("net_liquidation_value is inconsistent")
        if abs(self.total_pnl - (self.realized_pnl + self.unrealized_pnl)) > TOLERANCE:
            raise ValueError("total_pnl is inconsistent")
        return self


class ValuationSnapshot(PortfolioOSModel):
    snapshot_id: str = Field(min_length=1)
    valuation: PortfolioValuation
    holding_ids: tuple[str, ...]
    cash_balance_accounts: tuple[str, ...]
    snapshot_hash: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("snapshot_hash")
    @classmethod
    def validate_snapshot_hash(cls, value: str) -> str:
        if not HASH_PATTERN.fullmatch(value):
            raise ValueError("snapshot_hash must be a lowercase SHA-256 digest")
        return value


class ExposureSnapshot(PortfolioOSModel):
    portfolio_id: str = Field(min_length=1)
    as_of: datetime
    gross_exposure: Decimal
    net_exposure: Decimal
    cash_pct: Decimal | None = None
    security_concentration: dict[str, Decimal] = Field(default_factory=dict)
    sector_exposure: dict[str, Decimal] = Field(default_factory=dict)
    strategy_exposure: dict[str, Decimal] = Field(default_factory=dict)
    account_exposure: dict[str, Decimal] = Field(default_factory=dict)
    currency_exposure: dict[str, Decimal] = Field(default_factory=dict)
    risk_flags: tuple[RiskFlag, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class PortfolioRiskSnapshot(PortfolioOSModel):
    portfolio_id: str = Field(min_length=1)
    as_of: datetime
    drawdown: Decimal
    volatility: Decimal
    concentration: Decimal
    top_1_weight: Decimal
    top_5_weight: Decimal
    cash_pct: Decimal
    turnover: Decimal
    cost_drag: Decimal
    gross_exposure: Decimal
    net_exposure: Decimal
    risk_flags: tuple[RiskFlag, ...] = ()
    lineage_node_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BenchmarkReference(PortfolioOSModel):
    benchmark_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    market: str = Field(min_length=1)
    currency: str
    source: str = Field(min_length=1)
    version: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PortfolioBenchmarkComparison(PortfolioOSModel):
    portfolio_id: str = Field(min_length=1)
    benchmark_id: str = Field(min_length=1)
    portfolio_return: Decimal
    benchmark_return: Decimal
    active_return: Decimal
    relative_drawdown: Decimal
    tracking_difference: Decimal
    period_start: date
    period_end: date
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_comparison(self) -> "PortfolioBenchmarkComparison":
        if self.period_end < self.period_start:
            raise ValueError("period_end cannot precede period_start")
        if abs(
            self.active_return - (self.portfolio_return - self.benchmark_return)
        ) > TOLERANCE:
            raise ValueError("active_return is inconsistent")
        return self


class PortfolioPerformancePoint(PortfolioOSModel):
    portfolio_id: str = Field(min_length=1)
    date: date
    equity: Decimal
    cash: Decimal
    invested_value: Decimal
    daily_return: Decimal
    cumulative_return: Decimal
    benchmark_value: Decimal | None = None
    lineage_node_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PortfolioMetrics(PortfolioOSModel):
    portfolio_id: str = Field(min_length=1)
    total_return: Decimal
    cagr: Decimal | None = None
    max_drawdown: Decimal
    volatility: Decimal
    positive_period_rate: Decimal
    turnover: Decimal
    costs: Decimal
    cash_utilization: Decimal
    period_start: date
    period_end: date


class PortfolioAttribution(PortfolioOSModel):
    portfolio_id: str = Field(min_length=1)
    period_start: date
    period_end: date
    currency: str
    security_attribution: dict[str, Decimal] = Field(default_factory=dict)
    strategy_attribution: dict[str, Decimal] = Field(default_factory=dict)
    sector_attribution: dict[str, Decimal] = Field(default_factory=dict)
    transaction_cost_attribution: Decimal = ZERO
    total_contribution: Decimal = ZERO
    metadata: dict[str, Any] = Field(default_factory=dict)


class PortfolioGoal(PortfolioOSModel):
    goal_id: str = Field(min_length=1)
    portfolio_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    target_amount: Decimal = Field(gt=ZERO)
    target_date: date
    currency: str
    status: GoalStatus
    metadata: dict[str, Any] = Field(default_factory=dict)


class PortfolioEvent(PortfolioOSModel):
    event_id: str = Field(min_length=1)
    portfolio_id: str = Field(min_length=1)
    event_type: PortfolioEventType
    entity_type: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    timestamp: datetime
    reason: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class HoldingsRebuildResult(PortfolioOSModel):
    portfolio_id: str = Field(min_length=1)
    as_of: datetime
    lot_policy: LotPolicy = LotPolicy.FIFO
    lots: tuple[PositionLot, ...]
    holdings: tuple[Holding, ...]
    realized_pnl: dict[str, Decimal]
    transaction_ids: tuple[str, ...]


class CashLedgerResult(PortfolioOSModel):
    portfolio_id: str = Field(min_length=1)
    as_of: datetime
    balances: dict[str, Decimal]
    account_balances: dict[str, Decimal]
    transaction_count: int = Field(ge=0)


class PortfolioReconciliationResult(PortfolioOSModel):
    portfolio_id: str = Field(min_length=1)
    as_of: datetime
    cash_consistent: bool
    positions_consistent: bool
    transaction_totals_consistent: bool
    cost_basis_consistent: bool
    valuation_consistent: bool
    errors: tuple[str, ...] = ()
    risk_flags: tuple[RiskFlag, ...] = ()
    status: IntegrityStatus


class PortfolioOSIntegritySummary(PortfolioOSModel):
    broken_refs: int = Field(ge=0)
    negative_holding_violations: int = Field(ge=0)
    cash_reconciliation_errors: int = Field(ge=0)
    duplicate_transaction_ids: int = Field(ge=0)
    valuation_mismatches: int = Field(ge=0)
    event_sequence_errors: int = Field(ge=0)
    status: IntegrityStatus
    metadata: dict[str, Any] = Field(default_factory=dict)


class PortfolioOSSnapshot(PortfolioOSModel):
    snapshot_version: str = Field(min_length=1)
    generated_at: datetime
    portfolios: tuple[Portfolio, ...]
    accounts: tuple[PortfolioAccount, ...]
    holdings: tuple[Holding, ...]
    cash: tuple[CashBalance, ...]
    risk: tuple[PortfolioRiskSnapshot, ...]
    benchmarks: tuple[BenchmarkReference, ...]
    integrity: PortfolioOSIntegritySummary
    snapshot_hash: str

    @field_validator("snapshot_hash")
    @classmethod
    def validate_portfolio_snapshot_hash(cls, value: str) -> str:
        if not HASH_PATTERN.fullmatch(value):
            raise ValueError("snapshot_hash must be a lowercase SHA-256 digest")
        return value


__all__ = tuple(
    name
    for name in globals()
    if name[0].isupper() and name not in {"Any", "Decimal", "Field"}
)
