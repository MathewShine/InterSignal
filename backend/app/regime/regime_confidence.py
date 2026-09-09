from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any, Sequence

from app.regime.regime_config import ConfidenceRules


def calculate_regime_confidence(
    components: Sequence[dict[str, Any]],
    *,
    available_weight_pct: Decimal,
    rules: ConfidenceRules,
) -> dict[str, Any]:
    agreement = component_agreement(components)
    coverage_pct = weighted_component_coverage_pct(components)
    penalty = Decimal("0")
    if any("NIFTY500_MEMBERSHIP_PARTIAL_HISTORY" in component.get("warnings", ()) for component in components):
        penalty += rules.partial_membership_penalty

    score = (
        available_weight_pct * rules.availability_weight
        + agreement["agreement_pct"] * rules.agreement_weight
        + coverage_pct * rules.coverage_weight
        - penalty
    )
    score = max(Decimal("0"), min(Decimal("100"), score))
    if score >= rules.high_threshold:
        state = "HIGH"
    elif score >= rules.medium_threshold:
        state = "MEDIUM"
    else:
        state = "LOW"
    return {
        "confidence_score": score,
        "confidence_state": state,
        "agreement": agreement,
        "coverage_score_pct": coverage_pct,
        "penalties": {"partial_membership_penalty": penalty},
    }


def component_agreement(components: Sequence[dict[str, Any]]) -> dict[str, Any]:
    directions: list[str] = []
    for component in components:
        contribution = component.get("signed_contribution")
        if contribution is None:
            continue
        contribution = Decimal(str(contribution))
        if contribution > 0:
            directions.append("POSITIVE")
        elif contribution < 0:
            directions.append("NEGATIVE")
        else:
            directions.append("NEUTRAL")

    directional = [direction for direction in directions if direction != "NEUTRAL"]
    if not directional:
        return {
            "agreement_pct": Decimal("50"),
            "dominant_direction": "NEUTRAL",
            "direction_counts": dict(Counter(directions)),
        }
    counts = Counter(directional)
    dominant_direction, dominant_count = counts.most_common(1)[0]
    return {
        "agreement_pct": Decimal(dominant_count) / Decimal(len(directional)) * Decimal("100"),
        "dominant_direction": dominant_direction,
        "direction_counts": dict(Counter(directions)),
    }


def weighted_component_coverage_pct(components: Sequence[dict[str, Any]]) -> Decimal:
    weighted = Decimal("0")
    total = Decimal("0")
    for component in components:
        target_weight = Decimal(str(component.get("target_weight", "0") or "0"))
        coverage = component.get("coverage_metadata", {}).get("coverage_pct", Decimal("0"))
        coverage_decimal = Decimal(str(coverage or "0"))
        coverage_decimal = max(Decimal("0"), min(Decimal("100"), coverage_decimal))
        weighted += target_weight * coverage_decimal / Decimal("100")
        total += target_weight
    if total == 0:
        return Decimal("0")
    return weighted / total * Decimal("100")

