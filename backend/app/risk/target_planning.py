from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.risk.risk_config import RiskStructureConfig, RiskStructureV11Config


def build_target_plan(
    *,
    setup_row: dict[str, Any],
    feature_row: dict[str, Any] | None,
    assumed_entry_price: Decimal | None,
    risk_per_share: Decimal | None,
    config: RiskStructureConfig = RiskStructureV11Config(),
) -> dict[str, Any]:
    if assumed_entry_price is None or assumed_entry_price <= 0 or risk_per_share is None or risk_per_share <= 0:
        return unavailable_target("RISK_PER_SHARE_UNAVAILABLE")

    target_1_5r = assumed_entry_price + risk_per_share * Decimal("1.50")
    target_2r = assumed_entry_price + risk_per_share * Decimal("2.00")
    target_2_5r = assumed_entry_price + risk_per_share * Decimal("2.50")
    structural_price, structural_basis = structural_target(
        setup_row=setup_row,
        feature_row=feature_row,
        assumed_entry_price=assumed_entry_price,
        config=config,
    )
    warnings: list[str] = []
    if structural_price is not None:
        selected_price = structural_price
        selected_basis = structural_basis
        structural_status = "AVAILABLE"
    elif config.target.allow_r_multiple_when_structure_unavailable:
        selected_price = target_2r
        selected_basis = "R_MULTIPLE_2R_RESEARCH_REFERENCE"
        structural_status = "UNAVAILABLE"
        warnings.append("STRUCTURAL_TARGET_UNAVAILABLE")
    else:
        return unavailable_target("STRUCTURAL_TARGET_UNAVAILABLE")

    return {
        "target_1_5r": target_1_5r,
        "target_2r": target_2r,
        "target_2_5r": target_2_5r,
        "structural_target_price": structural_price,
        "structural_target_basis": structural_basis if structural_price is not None else "UNAVAILABLE",
        "structural_target_status": structural_status,
        "selected_target_price": selected_price,
        "selected_target_basis": selected_basis,
        "target_rejection_reasons": [],
        "target_warning_flags": warnings,
    }


def unavailable_target(reason: str) -> dict[str, Any]:
    return {
        "target_1_5r": None,
        "target_2r": None,
        "target_2_5r": None,
        "structural_target_price": None,
        "structural_target_basis": "UNAVAILABLE",
        "structural_target_status": "UNAVAILABLE",
        "selected_target_price": None,
        "selected_target_basis": "UNAVAILABLE",
        "target_rejection_reasons": [reason],
        "target_warning_flags": [],
    }


def structural_target(
    *,
    setup_row: dict[str, Any],
    feature_row: dict[str, Any] | None,
    assumed_entry_price: Decimal,
    config: RiskStructureConfig,
) -> tuple[Decimal | None, str]:
    candidates = [
        ("PRIOR_52W_HIGH_RESISTANCE", decimal_value(setup_row.get("prior_high_52w")) or decimal_value((feature_row or {}).get("prior_high_52w"))),
        ("PRIOR_20D_HIGH_RESISTANCE", decimal_value(setup_row.get("prior_high_20d")) or decimal_value((feature_row or {}).get("prior_high_20d"))),
    ]
    min_target = assumed_entry_price * (Decimal("1") + config.target.minimum_structural_target_distance_pct / Decimal("100"))
    valid = [(basis, value) for basis, value in candidates if value is not None and value > min_target]
    if not valid:
        return None, "UNAVAILABLE"
    return min((item for item in valid), key=lambda item: item[1])[1], min((item for item in valid), key=lambda item: item[1])[0]


def decimal_value(value: Any) -> Decimal | None:
    if isinstance(value, Decimal):
        return value
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except Exception:
        return None
