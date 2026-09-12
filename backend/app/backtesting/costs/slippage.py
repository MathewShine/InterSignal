from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from app.backtesting.costs.cost_models import (
    FIXED_BPS,
    LIQUIDITY_AWARE_FUTURE_PLACEHOLDER,
    TURNOVER_TIERED,
    ZERO_SLIPPAGE,
)

BPS_DENOMINATOR = Decimal("10000")


def slippage_raw(
    turnover: Decimal,
    model: str,
    bps_per_side: Decimal,
    *,
    turnover_tiers: Sequence[tuple[Decimal | None, Decimal]] = (),
) -> Decimal:
    if turnover < 0 or bps_per_side < 0:
        raise ValueError("Slippage inputs cannot be negative")
    if model == ZERO_SLIPPAGE:
        return Decimal("0")
    if model == FIXED_BPS:
        return turnover * bps_per_side / BPS_DENOMINATOR
    if model == TURNOVER_TIERED:
        if not turnover_tiers:
            raise ValueError("Turnover-tiered slippage requires predeclared tiers")
        for maximum_turnover, tier_bps in turnover_tiers:
            if tier_bps < 0:
                raise ValueError("Tiered slippage bps cannot be negative")
            if maximum_turnover is None or turnover <= maximum_turnover:
                return turnover * tier_bps / BPS_DENOMINATOR
        raise ValueError("Turnover-tiered slippage requires a final unbounded tier")
    if model == LIQUIDITY_AWARE_FUTURE_PLACEHOLDER:
        raise NotImplementedError("Liquidity-aware slippage is a future placeholder")
    raise ValueError(f"Unsupported slippage model: {model}")
