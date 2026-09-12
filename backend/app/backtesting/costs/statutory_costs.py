from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from app.backtesting.costs.brokerage import brokerage_raw
from app.backtesting.costs.cost_models import (
    BROKERAGE,
    DP_CHARGE,
    EXCHANGE_TRANSACTION_CHARGE,
    GST,
    OTHER_REGULATORY,
    SEBI_CHARGE,
    STAMP_DUTY,
    STT,
    CostModelConfig,
)


def round_rupees(value: Decimal, config: CostModelConfig) -> Decimal:
    if value < 0:
        raise ValueError("Cost components cannot be negative")
    if config.rounding_mode != "ROUND_HALF_UP":
        raise ValueError(f"Unsupported rounding mode: {config.rounding_mode}")
    return value.quantize(config.rounding_quantum, rounding=ROUND_HALF_UP)


def side_fee_components(
    *,
    config: CostModelConfig,
    side: str,
    value_date: date,
    executed_turnover: Decimal,
    include_costs: bool,
) -> dict[str, dict[str, Decimal]]:
    zero = {"raw": Decimal("0"), "rounded": Decimal("0.00")}
    if not include_costs:
        return {
            component: dict(zero)
            for component in (
                BROKERAGE,
                STT,
                EXCHANGE_TRANSACTION_CHARGE,
                SEBI_CHARGE,
                GST,
                STAMP_DUTY,
                DP_CHARGE,
                OTHER_REGULATORY,
            )
        } | {"GST_TAXABLE_BASE": dict(zero)}

    raw: dict[str, Decimal] = {
        BROKERAGE: brokerage_raw(executed_turnover, config.brokerage),
        STT: _scheduled_raw(config, STT, side, value_date, executed_turnover),
        EXCHANGE_TRANSACTION_CHARGE: _scheduled_raw(
            config, EXCHANGE_TRANSACTION_CHARGE, side, value_date, executed_turnover
        ),
        SEBI_CHARGE: _scheduled_raw(config, SEBI_CHARGE, side, value_date, executed_turnover),
        STAMP_DUTY: _optional_scheduled_raw(
            config, STAMP_DUTY, side, value_date, executed_turnover
        ),
        DP_CHARGE: _optional_scheduled_raw(
            config, DP_CHARGE, side, value_date, executed_turnover
        ),
        OTHER_REGULATORY: _scheduled_raw(
            config, OTHER_REGULATORY, side, value_date, executed_turnover
        ),
    }
    gst_base = sum((raw[name] for name in config.gst_taxable_components), Decimal("0"))
    gst_rate = config.schedule_for(GST, side, value_date).rate
    raw[GST] = gst_base * gst_rate
    result = {
        name: {"raw": amount, "rounded": round_rupees(amount, config)}
        for name, amount in raw.items()
    }
    result["GST_TAXABLE_BASE"] = {
        "raw": gst_base,
        "rounded": round_rupees(gst_base, config),
    }
    return result


def _scheduled_raw(
    config: CostModelConfig,
    component: str,
    side: str,
    value_date: date,
    turnover: Decimal,
) -> Decimal:
    schedule = config.schedule_for(component, side, value_date)
    if schedule.basis == "EXECUTED_TURNOVER":
        return turnover * schedule.rate
    if schedule.basis == "FLAT_PER_SELL_TRADE_RESEARCH_PROXY":
        return schedule.rate
    raise ValueError(f"Unsupported cost basis: {schedule.basis}")


def _optional_scheduled_raw(
    config: CostModelConfig,
    component: str,
    side: str,
    value_date: date,
    turnover: Decimal,
) -> Decimal:
    matches = [
        row
        for row in config.rate_schedules
        if row.component == component and row.applies(value_date, side)
    ]
    if not matches:
        return Decimal("0")
    if len(matches) != 1:
        raise ValueError(f"Ambiguous {component} schedule for {side} on {value_date}")
    schedule = matches[0]
    if schedule.basis == "EXECUTED_TURNOVER":
        return turnover * schedule.rate
    if schedule.basis == "FLAT_PER_SELL_TRADE_RESEARCH_PROXY":
        return schedule.rate
    raise ValueError(f"Unsupported cost basis: {schedule.basis}")
