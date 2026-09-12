from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Any

COST_MODEL_VERSION = "INDIA_EQUITY_COST_MODEL_V1"
COST_PROFILE = "NSE_CASH_DELIVERY_RESEARCH_V1"
COSTED_BACKTEST_VERSION = "PORTFOLIO_BACKTEST_V1_COSTED_RESEARCH"
SLIPPAGE_MODEL_VERSION = "SLIPPAGE_MODEL_V1"
ANALYSIS_MODE = "FROZEN_TRADE_SET_COST_OVERLAY"
HISTORICAL_RATE_PRECISION = "APPROXIMATE_RESEARCH_ASSUMPTION"
NET_ESTIMATE_WARNING = "NET_RESULTS_ARE_APPROXIMATE_RESEARCH_ESTIMATES"

BUY = "BUY"
SELL = "SELL"
BOTH = "BOTH"

BROKERAGE = "BROKERAGE"
STT = "STT"
EXCHANGE_TRANSACTION_CHARGE = "EXCHANGE_TRANSACTION_CHARGE"
SEBI_CHARGE = "SEBI_CHARGE"
GST = "GST"
STAMP_DUTY = "STAMP_DUTY"
DP_CHARGE = "DP_CHARGE"
OTHER_REGULATORY = "OTHER_REGULATORY"
SLIPPAGE = "SLIPPAGE"

BROKERAGE_ZERO_DELIVERY = "BROKERAGE_ZERO_DELIVERY"
BROKERAGE_PERCENTAGE = "BROKERAGE_PERCENTAGE"
BROKERAGE_FLAT_PER_ORDER = "BROKERAGE_FLAT_PER_ORDER"
ZERO_DELIVERY_RESEARCH_ASSUMPTION = "ZERO_DELIVERY_RESEARCH_ASSUMPTION"

ZERO_SLIPPAGE = "ZERO_SLIPPAGE"
FIXED_BPS = "FIXED_BPS"
TURNOVER_TIERED = "TURNOVER_TIERED"
LIQUIDITY_AWARE_FUTURE_PLACEHOLDER = "LIQUIDITY_AWARE_FUTURE_PLACEHOLDER"

SOURCE_STATUSES = {
    "AUTHORITATIVE",
    "BROKER_PUBLISHED",
    "REGULATORY_PUBLISHED",
    "RESEARCH_ASSUMPTION",
    "HISTORICAL_APPROXIMATION",
}


def json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return [json_ready(item) for item in value]
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    return value


def canonical_hash(value: Any) -> str:
    payload = json.dumps(json_ready(value), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CostRateSchedule:
    component: str
    side: str
    rate: Decimal
    basis: str
    effective_from: date
    effective_to: date | None
    source_status: str
    research_assumption: bool
    source_note: str
    source_url: str

    def applies(self, value_date: date, side: str) -> bool:
        return (
            self.side in {side, BOTH}
            and self.effective_from <= value_date
            and (self.effective_to is None or value_date <= self.effective_to)
        )

    def snapshot(self) -> dict[str, Any]:
        return json_ready(asdict(self))


@dataclass(frozen=True, slots=True)
class BrokerageConfig:
    model: str = BROKERAGE_ZERO_DELIVERY
    assumption_label: str = ZERO_DELIVERY_RESEARCH_ASSUMPTION
    percentage_rate: Decimal = Decimal("0")
    flat_per_order_rupees: Decimal = Decimal("0")
    source_status: str = "RESEARCH_ASSUMPTION"
    research_assumption: bool = True
    notes: str = (
        "Provider-neutral zero-delivery brokerage research assumption; not a universal broker claim."
    )

    def snapshot(self) -> dict[str, Any]:
        return json_ready(asdict(self))


@dataclass(frozen=True, slots=True)
class SlippageConfig:
    version: str = SLIPPAGE_MODEL_VERSION
    supported_models: tuple[str, ...] = (
        ZERO_SLIPPAGE,
        FIXED_BPS,
        TURNOVER_TIERED,
        LIQUIDITY_AWARE_FUTURE_PLACEHOLDER,
    )
    baseline_model: str = FIXED_BPS
    baseline_bps_per_side: Decimal = Decimal("5")
    assumption_status: str = "RESEARCH_ASSUMPTION"
    notes: str = "Pre-registered conservative fixed-bps assumption; not fitted to results."

    def snapshot(self) -> dict[str, Any]:
        return json_ready(asdict(self))


@dataclass(frozen=True, slots=True)
class CostModelConfig:
    version: str
    profile: str
    venue: str
    product_scope: str
    currency: str
    brokerage: BrokerageConfig
    slippage: SlippageConfig
    rate_schedules: tuple[CostRateSchedule, ...]
    gst_taxable_components: tuple[str, ...]
    rounding_quantum: Decimal
    rounding_mode: str
    component_rounding_policy: str
    historical_rate_precision: str
    net_estimate_warning: str

    def snapshot(self) -> dict[str, Any]:
        return json_ready(asdict(self))

    def config_hash(self) -> str:
        return canonical_hash(self.snapshot())

    def schedule_for(self, component: str, side: str, value_date: date) -> CostRateSchedule:
        matches = [
            row
            for row in self.rate_schedules
            if row.component == component and row.applies(value_date, side)
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Expected one {component} schedule for {side} on {value_date}, found {len(matches)}"
            )
        return matches[0]


@dataclass(frozen=True, slots=True)
class CostScenario:
    scenario_id: str
    name: str
    include_statutory_and_broker_costs: bool
    slippage_model: str
    slippage_bps_per_side: Decimal
    purpose: str
    preregistered: bool = True
    optimization_prohibited: bool = True

    def snapshot(self) -> dict[str, Any]:
        return json_ready(asdict(self))

    def scenario_hash(self, cost_config_hash: str) -> str:
        return canonical_hash(
            {"cost_config_hash": cost_config_hash, "scenario": self.snapshot()}
        )
