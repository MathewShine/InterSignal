from __future__ import annotations

from decimal import Decimal

from app.backtesting.costs.cost_models import (
    BROKERAGE_FLAT_PER_ORDER,
    BROKERAGE_PERCENTAGE,
    BROKERAGE_ZERO_DELIVERY,
    BrokerageConfig,
)


def brokerage_raw(turnover: Decimal, config: BrokerageConfig) -> Decimal:
    if turnover < 0:
        raise ValueError("Brokerage turnover cannot be negative")
    if config.model == BROKERAGE_ZERO_DELIVERY:
        return Decimal("0")
    if config.model == BROKERAGE_PERCENTAGE:
        return turnover * config.percentage_rate
    if config.model == BROKERAGE_FLAT_PER_ORDER:
        return config.flat_per_order_rupees
    raise ValueError(f"Unsupported brokerage model: {config.model}")
