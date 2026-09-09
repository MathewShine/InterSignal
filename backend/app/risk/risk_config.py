from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

RISK_STRUCTURE_VERSION = "RISK_STRUCTURE_V1"
RISK_STRUCTURE_V1_1_VERSION = "RISK_STRUCTURE_V1_1"
RISK_STRUCTURE_V1_CONFIG_HASH = "510f0456fe64b072"
RISK_STRUCTURE_V1_DATASET_HASH = "cbd4b8bc9a6a5fe7e8080680a85c2698ad780597d28056d59c77bd4950619896"
RISK_STRUCTURE_V1_1_CONFIG_HASH = "f66fbdf2fc5aecd0"
RISK_STRUCTURE_V1_1_DATASET_HASH = "b5628df1edfe5cc62f4bccf3caf3de3a86ad55bc4f8cbcc3886acbcd459ea1cc"
CURRENT_RISK_STRUCTURE_VERSION = RISK_STRUCTURE_V1_1_VERSION
CURRENT_RISK_STRUCTURE_CONFIG_HASH = RISK_STRUCTURE_V1_1_CONFIG_HASH
MOMENTUM_FIRST_METHODOLOGY = "MOMENTUM_FIRST_V1"
SETUP_SPECIFIC_FIRST_METHODOLOGY = "SETUP_SPECIFIC_FIRST_V1"

ACTIVE_FORWARD_BASELINE = "ACTIVE_FORWARD_BASELINE"
HISTORICAL_SUPERSEDED = "HISTORICAL_SUPERSEDED"

_DATASET_PATHS = {
    RISK_STRUCTURE_VERSION: Path("research/risk_structures/daily/v1/risk_structures_v1.csv.gz"),
    RISK_STRUCTURE_V1_1_VERSION: Path("research/risk_structures/daily/v1_1/risk_structures_v1_1.csv.gz"),
}
_VERSION_ALIASES = {
    "current": CURRENT_RISK_STRUCTURE_VERSION,
    "v1": RISK_STRUCTURE_VERSION,
    "v1_1": RISK_STRUCTURE_V1_1_VERSION,
    RISK_STRUCTURE_VERSION.lower(): RISK_STRUCTURE_VERSION,
    RISK_STRUCTURE_V1_1_VERSION.lower(): RISK_STRUCTURE_V1_1_VERSION,
}


@dataclass(frozen=True, slots=True)
class CapitalRiskRules:
    research_capital_rupees: Decimal = Decimal("100000")
    max_risk_per_trade_pct: Decimal = Decimal("1.00")
    preferred_max_concurrent_positions: int = 4
    small_live_capital_min_rupees: Decimal = Decimal("20000")
    small_live_capital_max_rupees: Decimal = Decimal("30000")
    future_small_live_risk_min_pct: Decimal = Decimal("0.25")
    future_small_live_risk_max_pct: Decimal = Decimal("0.50")
    low_capital_utilization_pct: Decimal = Decimal("10.00")


@dataclass(frozen=True, slots=True)
class EntryReferenceRules:
    entry_price_basis: str = "EOD_CLOSE_REFERENCE"
    execution_price_status: str = "NOT_KNOWN"
    long_entry_buffer_pct: Decimal = Decimal("0.10")


@dataclass(frozen=True, slots=True)
class StopPlacementRules:
    atr_buffer_multiple: Decimal = Decimal("0.20")
    causal_rolling_low_windows: tuple[int, ...] = (3, 5, 10)
    consolidation_low_window: int = 20
    minimum_stop_distance_pct: Decimal = Decimal("0.40")
    minimum_stop_distance_atr: Decimal = Decimal("0.35")
    wide_stop_distance_pct: Decimal = Decimal("8.00")
    wide_stop_distance_atr: Decimal = Decimal("3.00")
    maximum_stop_distance_pct: Decimal = Decimal("14.00")
    maximum_stop_distance_atr: Decimal = Decimal("5.00")
    good_invalidation_bases: tuple[str, ...] = (
        "BREAKOUT_STRUCTURE",
        "CONSOLIDATION_LOW",
        "DAILY_RECLAIM_LOW",
        "RECENT_SWING_LOW_5",
        "RECENT_SWING_LOW_10",
    )
    acceptable_invalidation_bases: tuple[str, ...] = (
        "RECENT_SWING_LOW_3",
        "CANDLE_LOW",
        "SMA20_SUPPORT",
    )


@dataclass(frozen=True, slots=True)
class TargetRules:
    minimum_reward_risk: Decimal = Decimal("1.50")
    preferred_reward_risk: Decimal = Decimal("2.00")
    strong_reward_risk: Decimal = Decimal("2.50")
    fallback_r_multiple: Decimal = Decimal("2.00")
    reference_reward_multiples: tuple[Decimal, ...] = (Decimal("1.50"), Decimal("2.00"), Decimal("2.50"))
    minimum_structural_target_distance_pct: Decimal = Decimal("0.50")
    allow_r_multiple_when_structure_unavailable: bool = True


@dataclass(frozen=True, slots=True)
class RiskStructureConfig:
    risk_version: str = RISK_STRUCTURE_VERSION
    risk_availability: str = "DAILY_EOD"
    decision_use: str = "NEXT_SESSION_RISK_CONTEXT"
    strategy_direction: str = "LONG_ONLY"
    instrument_type: str = "NSE_CASH_EQUITY"
    leverage_status: str = "NO_LEVERAGE"
    margin_status: str = "NO_MARGIN"
    share_quantity_mode: str = "WHOLE_SHARES_ONLY"
    full_evaluation_entry_readiness: tuple[str, ...] = ("READY_FOR_RISK_EVALUATION", "EXCEPTIONAL_LONG_REVIEW")
    preview_entry_readiness: tuple[str, ...] = ("CONDITIONALLY_READY",)
    capital: CapitalRiskRules = CapitalRiskRules()
    entry: EntryReferenceRules = EntryReferenceRules()
    stop: StopPlacementRules = StopPlacementRules()
    target: TargetRules = TargetRules()
    final_strategy_score_status: str = "NOT_IMPLEMENTED"
    trade_signal_status: str = "NOT_GENERATED"
    notes: str = (
        "Baseline deterministic risk-structure foundation only; no final score, backtest, "
        "paper trading, live execution, orders, leverage, shorts, or Supabase persistence."
    )

    def snapshot(self) -> dict[str, Any]:
        return json_ready(asdict(self))

    def config_hash(self) -> str:
        payload = json.dumps(self.snapshot(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class RiskStructureV11Config(RiskStructureConfig):
    risk_version: str = RISK_STRUCTURE_V1_1_VERSION
    previous_risk_version: str = RISK_STRUCTURE_VERSION
    previous_risk_config_hash: str = RISK_STRUCTURE_V1_CONFIG_HASH
    stop_selection_methodology: str = SETUP_SPECIFIC_FIRST_METHODOLOGY
    notes: str = (
        "Versioned setup-specific-first stop-selection correction. Target, reward:risk, "
        "capital, ATR-buffer, entry-buffer, and execution-safety rules remain unchanged."
    )


def get_current_risk_structure_version() -> str:
    return CURRENT_RISK_STRUCTURE_VERSION


def get_current_risk_structure_config() -> RiskStructureV11Config:
    return RiskStructureV11Config()


def normalize_risk_structure_version(version: str | None = None) -> str:
    if version is None:
        return CURRENT_RISK_STRUCTURE_VERSION
    normalized = _VERSION_ALIASES.get(version.strip().lower())
    if normalized is None:
        supported = ", ".join(sorted(_DATASET_PATHS))
        raise ValueError(f"Unsupported risk structure version {version!r}; expected one of: {supported}")
    return normalized


def resolve_risk_structure_dataset(data_dir: Path, version: str | None = None) -> Path:
    resolved_version = normalize_risk_structure_version(version)
    return Path(data_dir) / _DATASET_PATHS[resolved_version]


def resolve_current_risk_structure_dataset(data_dir: Path) -> Path:
    return resolve_risk_structure_dataset(data_dir, CURRENT_RISK_STRUCTURE_VERSION)


def risk_structure_version_status(version: str) -> str:
    resolved_version = normalize_risk_structure_version(version)
    if resolved_version == CURRENT_RISK_STRUCTURE_VERSION:
        return ACTIVE_FORWARD_BASELINE
    return HISTORICAL_SUPERSEDED


def json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, tuple):
        return [json_ready(item) for item in value]
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    return value
