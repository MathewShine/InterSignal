from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.risk.risk_config import RiskStructureConfig, RiskStructureV11Config


def calculate_reward_risk(
    *,
    assumed_entry_price: Decimal | None,
    stop_price: Decimal | None,
    selected_target_price: Decimal | None,
    config: RiskStructureConfig = RiskStructureV11Config(),
) -> dict[str, Any]:
    warnings: list[str] = []
    rejections: list[str] = []
    if assumed_entry_price is None or assumed_entry_price <= 0:
        return invalid_reward_risk("ENTRY_REFERENCE_UNAVAILABLE")
    if stop_price is None or stop_price <= 0 or stop_price >= assumed_entry_price:
        return invalid_reward_risk("INVALID_STOP_PRICE")
    risk_per_share = assumed_entry_price - stop_price
    if selected_target_price is None or selected_target_price <= assumed_entry_price:
        return invalid_reward_risk("TARGET_UNAVAILABLE_OR_BELOW_ENTRY", risk_per_share=risk_per_share)
    reward_per_share = selected_target_price - assumed_entry_price
    ratio = reward_per_share / risk_per_share
    status = reward_risk_status(ratio, config)
    valid = status in {"MINIMUM_ACCEPTABLE", "GOOD", "STRONG"}
    if status == "BELOW_MINIMUM":
        rejections.append("RR_BELOW_MINIMUM")
    elif status == "MINIMUM_ACCEPTABLE":
        warnings.append("RR_BELOW_PREFERRED")
    return {
        "risk_per_share": risk_per_share,
        "reward_per_share": reward_per_share,
        "reward_risk_ratio": ratio,
        "reward_risk_status": status,
        "rr_valid": valid,
        "reward_risk_rejection_reasons": rejections,
        "reward_risk_warning_flags": warnings,
    }


def invalid_reward_risk(reason: str, *, risk_per_share: Decimal | None = None) -> dict[str, Any]:
    return {
        "risk_per_share": risk_per_share,
        "reward_per_share": None,
        "reward_risk_ratio": None,
        "reward_risk_status": "INVALID",
        "rr_valid": False,
        "reward_risk_rejection_reasons": [reason],
        "reward_risk_warning_flags": [],
    }


def reward_risk_status(ratio: Decimal, config: RiskStructureConfig) -> str:
    if ratio < config.target.minimum_reward_risk:
        return "BELOW_MINIMUM"
    if ratio < config.target.preferred_reward_risk:
        return "MINIMUM_ACCEPTABLE"
    if ratio < config.target.strong_reward_risk:
        return "GOOD"
    return "STRONG"
