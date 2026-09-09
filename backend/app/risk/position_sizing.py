from __future__ import annotations

from decimal import Decimal, ROUND_FLOOR
from typing import Any

from app.risk.risk_config import RiskStructureConfig, RiskStructureV11Config


def calculate_position_size(
    *,
    assumed_entry_price: Decimal | None,
    risk_per_share: Decimal | None,
    config: RiskStructureConfig = RiskStructureV11Config(),
) -> dict[str, Any]:
    warnings: list[str] = []
    rejections: list[str] = []
    capital = config.capital.research_capital_rupees
    risk_pct = config.capital.max_risk_per_trade_pct
    risk_budget = capital * risk_pct / Decimal("100")
    if assumed_entry_price is None or assumed_entry_price <= 0:
        return invalid_position("ENTRY_REFERENCE_UNAVAILABLE", capital, risk_pct, risk_budget)
    quantity_by_cash = floor_decimal(capital / assumed_entry_price)
    if risk_per_share is None or risk_per_share <= 0:
        return invalid_position("RISK_PER_SHARE_UNAVAILABLE", capital, risk_pct, risk_budget, quantity_by_cash=quantity_by_cash)
    quantity_by_risk = floor_decimal(risk_budget / risk_per_share)
    structured_quantity = min(quantity_by_risk, quantity_by_cash)

    if quantity_by_cash < 1:
        rejections.append("AFFORDABILITY_FAIL")
    if quantity_by_risk < 1:
        rejections.append("RISK_TOO_LARGE_FOR_CAPITAL")
    if structured_quantity < 1:
        rejections.append("STRUCTURED_QUANTITY_ZERO")

    if quantity_by_cash == 1 or quantity_by_risk == 1:
        warnings.append("SINGLE_SHARE_ONLY")
    if quantity_by_cash < quantity_by_risk:
        warnings.append("AFFORDABILITY_LIMITED")
    if quantity_by_risk <= quantity_by_cash:
        warnings.append("RISK_LIMITED_QUANTITY")

    position_notional = assumed_entry_price * Decimal(structured_quantity) if structured_quantity > 0 else Decimal("0")
    planned_risk = risk_per_share * Decimal(structured_quantity) if structured_quantity > 0 else Decimal("0")
    capital_utilization_pct = position_notional / capital * Decimal("100") if capital > 0 else Decimal("0")
    planned_risk_pct = planned_risk / capital * Decimal("100") if capital > 0 else Decimal("0")
    if structured_quantity > 0 and capital_utilization_pct < config.capital.low_capital_utilization_pct:
        warnings.append("LOW_CAPITAL_UTILIZATION")
    if planned_risk > risk_budget:
        rejections.append("PLANNED_RISK_EXCEEDS_BUDGET")

    valid = not rejections
    return {
        "research_capital": capital,
        "max_risk_per_trade_pct": risk_pct,
        "risk_budget_rupees": risk_budget,
        "quantity_by_risk": quantity_by_risk,
        "quantity_by_cash": quantity_by_cash,
        "structured_quantity": structured_quantity,
        "whole_share_status": config.share_quantity_mode,
        "no_leverage_status": config.leverage_status,
        "position_notional": position_notional,
        "capital_utilization_pct": capital_utilization_pct,
        "planned_rupee_risk": planned_risk,
        "planned_risk_pct": planned_risk_pct,
        "capital_status": "VALID" if valid else "INVALID",
        "capital_valid": valid,
        "capital_rejection_reasons": rejections,
        "capital_warning_flags": dedupe(warnings),
    }


def invalid_position(
    reason: str,
    capital: Decimal,
    risk_pct: Decimal,
    risk_budget: Decimal,
    *,
    quantity_by_cash: int = 0,
) -> dict[str, Any]:
    return {
        "research_capital": capital,
        "max_risk_per_trade_pct": risk_pct,
        "risk_budget_rupees": risk_budget,
        "quantity_by_risk": 0,
        "quantity_by_cash": quantity_by_cash,
        "structured_quantity": 0,
        "whole_share_status": "WHOLE_SHARES_ONLY",
        "no_leverage_status": "NO_LEVERAGE",
        "position_notional": Decimal("0"),
        "capital_utilization_pct": Decimal("0"),
        "planned_rupee_risk": Decimal("0"),
        "planned_risk_pct": Decimal("0"),
        "capital_status": "INVALID",
        "capital_valid": False,
        "capital_rejection_reasons": [reason],
        "capital_warning_flags": [],
    }


def floor_decimal(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value and value not in output:
            output.append(value)
    return output
