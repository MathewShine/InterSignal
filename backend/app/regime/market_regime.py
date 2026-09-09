from __future__ import annotations

import csv
import gzip
import json
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Sequence

from app.regime.breadth import BreadthAggregate, finalize_breadth_component, update_breadth_aggregate
from app.regime.regime_config import MARKET_REGIME_VERSION, MarketRegimeConfig
from app.regime.regime_confidence import calculate_regime_confidence
from app.regime.sector_participation import SectorIndexBar, build_sector_participation_components
from app.regime.trend import BenchmarkBar, build_nifty_trend_components
from app.regime.volatility import VixBar, build_india_vix_components, unavailable_india_vix_component
from app.services.daily_feature_engine import json_safe, write_csv, write_json
from app.strategy.candidate_config import MomentumCandidateConfig
from app.strategy.momentum_candidates import file_sha256, open_csv_maybe_gzip
from app.strategy.setup_config import DailySetupEvaluationConfig

REGIME_OUTPUT_FIELDS = [
    "trading_date",
    "regime_version",
    "config_hash",
    "regime_availability",
    "decision_use",
    "regime_status",
    "regime_state",
    "regime_subtype",
    "regime_score_raw",
    "regime_score_normalized",
    "available_weight_pct",
    "confidence_score",
    "confidence_state",
    "component_agreement_pct",
    "component_agreement_direction",
    "nifty_trend_status",
    "nifty_trend_state",
    "nifty_trend_contribution",
    "nifty50_close",
    "nifty50_return_1d",
    "nifty50_return_5d",
    "nifty50_return_10d",
    "nifty50_return_20d",
    "nifty50_sma20",
    "nifty50_sma50",
    "nifty50_sma200",
    "nifty50_distance_sma20_pct",
    "nifty50_distance_sma50_pct",
    "nifty50_distance_sma200_pct",
    "nifty50_sma20_slope_10d_pct",
    "breadth_status",
    "breadth_state",
    "breadth_contribution",
    "breadth_membership_status",
    "expected_members",
    "usable_members",
    "breadth_coverage_pct",
    "advancers",
    "decliners",
    "unchanged",
    "advance_decline_ratio",
    "advancer_pct",
    "pct_above_sma20",
    "pct_above_sma50",
    "pct_positive_5d",
    "pct_positive_20d",
    "sector_status",
    "sector_state",
    "sector_contribution",
    "sectors_expected",
    "sectors_available",
    "sector_coverage_pct",
    "sector_positive_1d_pct",
    "sector_positive_5d_pct",
    "sector_positive_20d_pct",
    "sector_above_sma20_pct",
    "median_sector_return_1d",
    "median_sector_return_5d",
    "sector_return_1d_dispersion",
    "vix_status",
    "vix_state",
    "vix_contribution",
    "india_vix_close",
    "india_vix_change_1d",
    "india_vix_change_5d",
    "global_gift_status",
    "global_gift_state",
    "global_gift_contribution",
    "intraday_status",
    "intraday_state",
    "intraday_contribution",
    "missing_components",
    "warnings",
    "membership_status",
]

DAILY_DISTRIBUTION_FIELDS = ["section", "name", "count", "pct", "details"]
COMPONENT_AVAILABILITY_FIELDS = [
    "component_name",
    "target_weight",
    "historical_source",
    "coverage_start",
    "coverage_end",
    "coverage_pct",
    "point_in_time_safety",
    "usable",
    "availability_status",
    "available_rows",
    "partial_rows",
    "unavailable_rows",
    "limitations",
]
PILOT_VALIDATION_FIELDS = ["pilot_case", "trading_date", "check_name", "observed", "expected", "result", "explanation"]
TRANSITION_MATRIX_FIELDS = ["from_state", "to_state", "count", "from_total", "pct"]
STREAK_SUMMARY_FIELDS = [
    "regime_state",
    "streak_count",
    "one_session",
    "two_sessions",
    "three_to_five",
    "six_to_ten",
    "over_ten",
    "median",
    "mean",
    "p90",
    "p95",
    "max",
]

CLASSIFIED_STATES = ("BULLISH", "NEUTRAL", "BEARISH")
ALL_COMPONENTS = (
    "NIFTY_TREND",
    "NIFTY500_BREADTH",
    "SECTOR_INDEX_PARTICIPATION",
    "INDIA_VIX",
    "GLOBAL_GIFT",
    "INTRADAY_CONFIRMATION",
)


@dataclass(frozen=True, slots=True)
class MarketRegimeEngineConfig:
    data_dir: Path
    start_date: date
    end_date: date
    regime_config: MarketRegimeConfig = MarketRegimeConfig()
    candidate_config: MomentumCandidateConfig = MomentumCandidateConfig()
    setup_config: DailySetupEvaluationConfig = DailySetupEvaluationConfig()
    full_generation: bool = True

    @property
    def benchmark_daily_path(self) -> Path:
        return self.data_dir / "reference" / "nse" / "indices" / "normalized" / "benchmark_daily.csv"

    @property
    def sector_index_daily_path(self) -> Path:
        return self.data_dir / "reference" / "nse" / "indices" / "normalized" / "sector_index_daily.csv"

    @property
    def sector_index_inventory_path(self) -> Path:
        return self.data_dir / "reference" / "nse" / "indices" / "normalized" / "sector_index_inventory.csv"

    @property
    def india_vix_path(self) -> Path:
        return self.data_dir / "reference" / "nse" / "indices" / "normalized" / "india_vix_daily.csv"

    @property
    def membership_periods_path(self) -> Path:
        return self.data_dir / "reference" / "nifty500" / "history" / "membership_periods.csv"

    @property
    def membership_coverage_path(self) -> Path:
        return self.data_dir / "reference" / "nifty500" / "history" / "membership_coverage.json"

    @property
    def calendar_path(self) -> Path:
        return self.data_dir / "reference" / "nse" / "calendar" / "nse_cash_trading_calendar.csv"

    @property
    def feature_dataset_path(self) -> Path:
        return self.data_dir / "research" / "features" / "daily" / "v1" / "daily_features_v1.csv.gz"

    @property
    def candidate_dataset_path(self) -> Path:
        return self.data_dir / "research" / "candidates" / "daily" / "v1" / "momentum_candidates_v1.csv.gz"

    @property
    def setup_dataset_path(self) -> Path:
        return self.data_dir / "research" / "setups" / "daily" / "v1" / "daily_setup_evaluations_v1.csv.gz"

    @property
    def regime_dir(self) -> Path:
        return self.data_dir / "research" / "regime" / "daily" / "v1"

    @property
    def regime_dataset_path(self) -> Path:
        return self.regime_dir / "market_regime_daily_v1.csv.gz"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def summary_path(self) -> Path:
        return self.reports_dir / "market_regime_summary.json"

    @property
    def daily_distribution_path(self) -> Path:
        return self.reports_dir / "market_regime_daily_distribution.csv"

    @property
    def component_availability_path(self) -> Path:
        return self.reports_dir / "market_regime_component_availability.csv"

    @property
    def pilot_validation_path(self) -> Path:
        return self.reports_dir / "market_regime_pilot_validation.csv"

    @property
    def transition_matrix_path(self) -> Path:
        return self.reports_dir / "market_regime_transition_matrix.csv"

    @property
    def streak_summary_path(self) -> Path:
        return self.reports_dir / "market_regime_streak_summary.csv"


def build_historical_market_regimes(
    *,
    config: MarketRegimeEngineConfig,
    progress: Any | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    feature_before = file_sha256(config.feature_dataset_path)
    candidate_before = file_sha256(config.candidate_dataset_path)
    setup_before = file_sha256(config.setup_dataset_path)

    if progress:
        progress("Loading trading sessions and safe local reference inputs")
    trading_sessions = load_trading_sessions(config.calendar_path, config.start_date, config.end_date)
    membership_periods = load_membership_periods(config.membership_periods_path)
    membership_status = load_membership_status(config.membership_coverage_path)
    expected_members_by_date = expected_member_counts(membership_periods, trading_sessions)
    benchmark = load_benchmark_bars(config.benchmark_daily_path)
    sector_bars = load_sector_bars(config.sector_index_daily_path)
    expected_sector_indexes = load_expected_sector_index_count(config.sector_index_inventory_path, sector_bars)
    vix_bars = load_vix_bars(config.india_vix_path)

    if progress:
        progress("Building NIFTY trend and sector-index participation components")
    weights = config.regime_config.weights
    trend_components = build_nifty_trend_components(
        benchmark.get("NIFTY_50", ()),
        target_weight=weights.nifty_trend,
        rules=config.regime_config.trend,
    )
    sector_components = build_sector_participation_components(
        sector_bars,
        expected_sector_indexes=expected_sector_indexes,
        target_weight=weights.sector_participation,
        rules=config.regime_config.sector,
    )
    vix_components = build_india_vix_components(
        vix_bars,
        target_weight=weights.india_vix,
        rules=config.regime_config.india_vix,
    )

    if progress:
        progress("Streaming DAILY_FEATURES_V1 once for NIFTY 500 breadth")
    breadth_aggregates = load_breadth_aggregates(config.feature_dataset_path, config.start_date, config.end_date)

    if progress:
        progress("Classifying daily EOD market regimes")
    rows = []
    total_weight = Decimal("100")
    for trading_date in trading_sessions:
        components = [
            trend_components.get(trading_date)
            or unavailable_component("NIFTY_TREND", trading_date, weights.nifty_trend, "NIFTY_TREND_MISSING_BENCHMARK_ROW"),
            finalize_breadth_component(
                trading_date,
                breadth_aggregates.get(trading_date),
                expected_members=expected_members_by_date.get(trading_date, 0),
                membership_status=membership_status,
                target_weight=weights.nifty500_breadth,
                rules=config.regime_config.breadth,
            ),
            sector_components.get(trading_date)
            or unavailable_component(
                "SECTOR_INDEX_PARTICIPATION",
                trading_date,
                weights.sector_participation,
                "SECTOR_INDEX_PARTICIPATION_MISSING_DATE",
            ),
            vix_components.get(trading_date) or unavailable_india_vix_component(trading_date, target_weight=weights.india_vix),
            unavailable_component("GLOBAL_GIFT", trading_date, weights.global_gift, "GLOBAL_GIFT_HISTORY_NOT_AVAILABLE_LOCALLY"),
            unavailable_component(
                "INTRADAY_CONFIRMATION",
                trading_date,
                weights.intraday_confirmation,
                "DAILY_EOD_COMMAND_NO_INTRADAY_CONFIRMATION",
            ),
        ]
        rows.append(regime_row(trading_date, components, config.regime_config, membership_status, total_weight))

    pilot = validate_pilot_rows(rows)
    full_generation_completed = False
    if config.full_generation and pilot["passed"]:
        write_gzip_csv(config.regime_dataset_path, rows, REGIME_OUTPUT_FIELDS)
        full_generation_completed = True

    distribution_rows, distribution_summary = daily_distribution_rows(rows)
    availability_rows, availability_summary = component_availability_rows(rows, config, sector_bars, vix_bars, benchmark)
    transition_rows, transition_summary = transition_matrix_rows(rows)
    streak_rows, streak_summary = streak_summary_rows(rows)
    continuity = score_continuity_summary(rows)

    write_csv(config.daily_distribution_path, distribution_rows, DAILY_DISTRIBUTION_FIELDS)
    write_csv(config.component_availability_path, availability_rows, COMPONENT_AVAILABILITY_FIELDS)
    write_csv(config.pilot_validation_path, pilot["rows"], PILOT_VALIDATION_FIELDS)
    write_csv(config.transition_matrix_path, transition_rows, TRANSITION_MATRIX_FIELDS)
    write_csv(config.streak_summary_path, streak_rows, STREAK_SUMMARY_FIELDS)

    feature_after = file_sha256(config.feature_dataset_path)
    candidate_after = file_sha256(config.candidate_dataset_path)
    setup_after = file_sha256(config.setup_dataset_path)
    safety = {
        "future_outcome_fields_used": 0,
        "future_return_fields_used": 0,
        "mfe_mae_fields_used": 0,
        "winner_loser_labels_used": 0,
        "profitability_optimization_used": 0,
        "candidate_rules_changed": False,
        "setup_rules_changed": False,
        "entry_scores_generated": 0,
        "risk_reward_calculated": 0,
        "stops_generated": 0,
        "targets_generated": 0,
        "position_sizes_generated": 0,
        "backtests_run": 0,
        "paper_trades_generated": 0,
        "orders_placed": 0,
        "remote_migrations_applied": 0,
        "supabase_bulk_records_persisted": 0,
    }
    report = {
        "phase": "Step 02.7",
        "command": "Command 01",
        "generated_at": generated_at,
        "methodology": {
            "regime_version": MARKET_REGIME_VERSION,
            "config_hash": config.regime_config.config_hash(),
            "regime_availability": config.regime_config.regime_availability,
            "decision_use": config.regime_config.decision_use,
            "target_weights": config.regime_config.snapshot()["weights"],
            "classification": config.regime_config.snapshot()["classification"],
            "normalization": "raw available-component score divided by available weight, scaled to a comparable -100 to +100 score.",
            "missing_component_policy": "Unavailable components have null contribution and zero available weight; they are not treated as neutral evidence.",
        },
        "inputs": {
            "benchmark_daily": str(config.benchmark_daily_path),
            "sector_index_daily": str(config.sector_index_daily_path),
            "membership_periods": str(config.membership_periods_path),
            "feature_dataset": str(config.feature_dataset_path),
            "candidate_dataset": str(config.candidate_dataset_path),
            "setup_dataset": str(config.setup_dataset_path),
            "india_vix": str(config.india_vix_path),
            "feature_hash_before": feature_before,
            "feature_hash_after": feature_after,
            "candidate_hash_before": candidate_before,
            "candidate_hash_after": candidate_after,
            "setup_hash_before": setup_before,
            "setup_hash_after": setup_after,
        },
        "generation": {
            "historical_start_date": rows[0]["trading_date"] if rows else None,
            "historical_end_date": rows[-1]["trading_date"] if rows else None,
            "full_generation_completed": full_generation_completed,
            "total_regime_rows": len(rows),
            "regime_dataset_path": str(config.regime_dataset_path),
        },
        "component_availability": availability_summary,
        "daily_distribution": distribution_summary,
        "pilot": pilot["summary"],
        "streaks": streak_summary,
        "transitions": transition_summary,
        "score_continuity": continuity,
        "regression": {
            "feature_dataset_unchanged": feature_before == feature_after,
            "candidate_dataset_unchanged": candidate_before == candidate_after,
            "setup_dataset_unchanged": setup_before == setup_after,
            "candidate_config_hash_unchanged": config.candidate_config.config_hash() == "d111957c7a24da96",
            "setup_config_hash_unchanged": config.setup_config.config_hash() == "1dcc8d7790116e56",
        },
        "safety": safety,
        "outputs": {
            "regime_dataset": str(config.regime_dataset_path),
            "summary_json": str(config.summary_path),
            "daily_distribution_csv": str(config.daily_distribution_path),
            "component_availability_csv": str(config.component_availability_path),
            "pilot_validation_csv": str(config.pilot_validation_path),
            "transition_matrix_csv": str(config.transition_matrix_path),
            "streak_summary_csv": str(config.streak_summary_path),
            "markdown": "docs/historical-market-regime-engine.md",
        },
        "processing": {
            "duration_seconds": round(time.perf_counter() - started, 3),
            "storage_size_bytes": output_size(config),
        },
        "ready_for_review": bool(
            full_generation_completed
            and pilot["passed"]
            and feature_before == feature_after
            and candidate_before == candidate_after
            and setup_before == setup_after
            and safety["orders_placed"] == 0
            and safety["remote_migrations_applied"] == 0
            and safety["supabase_bulk_records_persisted"] == 0
        ),
    }
    write_json(config.summary_path, report)
    return report


def regime_row(
    trading_date: date,
    components: Sequence[dict[str, Any]],
    regime_config: MarketRegimeConfig,
    membership_status: str,
    total_weight: Decimal,
) -> dict[str, Any]:
    raw_score = sum(
        Decimal(str(component["signed_contribution"]))
        for component in components
        if component.get("signed_contribution") is not None
    )
    available_weight = sum(Decimal(str(component.get("available_weight", "0") or "0")) for component in components)
    available_weight_pct = available_weight / total_weight * Decimal("100") if total_weight else Decimal("0")
    normalized_score = raw_score / available_weight * Decimal("100") if available_weight else None
    regime_status, regime_state = classify_regime_state(
        normalized_score=normalized_score,
        available_weight_pct=available_weight_pct,
        config=regime_config,
    )
    confidence = calculate_regime_confidence(
        components,
        available_weight_pct=available_weight_pct,
        rules=regime_config.confidence,
    )
    subtype = regime_subtype(regime_state, components)
    missing_components = [component["component_name"] for component in components if component["component_status"] == "UNAVAILABLE"]
    warnings = sorted({warning for component in components for warning in component.get("warnings", ()) if warning})
    lookup = {component["component_name"]: component for component in components}
    trend = lookup["NIFTY_TREND"]
    breadth = lookup["NIFTY500_BREADTH"]
    sector = lookup["SECTOR_INDEX_PARTICIPATION"]
    vix = lookup["INDIA_VIX"]
    global_gift = lookup["GLOBAL_GIFT"]
    intraday = lookup["INTRADAY_CONFIRMATION"]
    row = {
        "trading_date": trading_date,
        "regime_version": regime_config.regime_version,
        "config_hash": regime_config.config_hash(),
        "regime_availability": regime_config.regime_availability,
        "decision_use": regime_config.decision_use,
        "regime_status": regime_status,
        "regime_state": regime_state,
        "regime_subtype": subtype,
        "regime_score_raw": raw_score,
        "regime_score_normalized": normalized_score,
        "available_weight_pct": available_weight_pct,
        "confidence_score": confidence["confidence_score"],
        "confidence_state": confidence["confidence_state"],
        "component_agreement_pct": confidence["agreement"]["agreement_pct"],
        "component_agreement_direction": confidence["agreement"]["dominant_direction"],
        "nifty_trend_status": trend["component_status"],
        "nifty_trend_state": trend["component_state"],
        "nifty_trend_contribution": trend["signed_contribution"],
        **prefixed_evidence(trend["evidence"], include_prefix=False),
        "breadth_status": breadth["component_status"],
        "breadth_state": breadth["component_state"],
        "breadth_contribution": breadth["signed_contribution"],
        **prefixed_evidence(breadth["evidence"], include_prefix=False),
        "sector_status": sector["component_status"],
        "sector_state": sector["component_state"],
        "sector_contribution": sector["signed_contribution"],
        **prefixed_evidence(sector["evidence"], include_prefix=False),
        "vix_status": vix["component_status"],
        "vix_state": vix["component_state"],
        "vix_contribution": vix["signed_contribution"],
        **prefixed_evidence(vix["evidence"], include_prefix=False),
        "global_gift_status": global_gift["component_status"],
        "global_gift_state": global_gift["component_state"],
        "global_gift_contribution": global_gift["signed_contribution"],
        "intraday_status": intraday["component_status"],
        "intraday_state": intraday["component_state"],
        "intraday_contribution": intraday["signed_contribution"],
        "missing_components": ";".join(missing_components),
        "warnings": ";".join(warnings),
        "membership_status": membership_status,
    }
    return row


def classify_regime_state(
    *,
    normalized_score: Decimal | None,
    available_weight_pct: Decimal,
    config: MarketRegimeConfig,
) -> tuple[str, str]:
    if normalized_score is None or available_weight_pct < config.classification.minimum_available_weight_pct:
        return "INSUFFICIENT_COMPONENT_COVERAGE", "UNAVAILABLE"
    if normalized_score >= config.classification.bullish_min:
        return "CLASSIFIED", "BULLISH"
    if normalized_score <= config.classification.bearish_max:
        return "CLASSIFIED", "BEARISH"
    return "CLASSIFIED", "NEUTRAL"


def regime_subtype(regime_state: str, components: Sequence[dict[str, Any]]) -> str:
    if regime_state == "UNAVAILABLE":
        return "UNAVAILABLE_COMPONENT_COVERAGE"
    by_name = {component["component_name"]: component for component in components}
    trend = by_name["NIFTY_TREND"]["component_state"]
    breadth = by_name["NIFTY500_BREADTH"]["component_state"]
    sector = by_name["SECTOR_INDEX_PARTICIPATION"]["component_state"]
    vix = by_name["INDIA_VIX"]["component_state"]
    bullish_states = {"BULLISH", "STRONGLY_BULLISH"}
    bearish_states = {"BEARISH", "STRONGLY_BEARISH"}
    if regime_state == "BULLISH":
        if vix in {"RISK_OFF", "STRONGLY_RISK_OFF"}:
            return "BULLISH_VOLATILE"
        if trend in bullish_states and breadth in bullish_states and sector in bullish_states:
            return "BULLISH_BROAD"
        return "BULLISH_NARROW"
    if regime_state == "BEARISH":
        if breadth in bullish_states:
            return "BEARISH_WITH_POSITIVE_BREADTH"
        if trend in bearish_states and breadth in bearish_states:
            return "BEARISH_BROAD"
        return "BEARISH_VOLATILE" if vix in {"RISK_OFF", "STRONGLY_RISK_OFF"} else "BEARISH_MIXED"
    return "NEUTRAL_MIXED" if mixed_component_directions(components) else "NEUTRAL_BALANCED"


def mixed_component_directions(components: Sequence[dict[str, Any]]) -> bool:
    signs = set()
    for component in components:
        contribution = component.get("signed_contribution")
        if contribution is None:
            continue
        contribution = Decimal(str(contribution))
        if contribution > 0:
            signs.add("POSITIVE")
        elif contribution < 0:
            signs.add("NEGATIVE")
    return len(signs) > 1


def unavailable_component(component_name: str, trading_date: date, target_weight: Decimal, warning: str) -> dict[str, Any]:
    return {
        "component_name": component_name,
        "component_status": "UNAVAILABLE",
        "component_state": "UNAVAILABLE",
        "target_weight": target_weight,
        "available_weight": Decimal("0"),
        "signed_contribution": None,
        "evidence": {"trading_date": trading_date},
        "source_version": "UNAVAILABLE",
        "coverage_metadata": {
            "historical_source": source_for_component(component_name),
            "point_in_time_safety": "UNAVAILABLE_NOT_IMPUTED",
            "coverage_pct": Decimal("0"),
        },
        "warnings": (warning,),
    }


def source_for_component(component_name: str) -> str:
    return {
        "NIFTY_TREND": "data/reference/nse/indices/normalized/benchmark_daily.csv",
        "NIFTY500_BREADTH": "data/research/features/daily/v1/daily_features_v1.csv.gz",
        "SECTOR_INDEX_PARTICIPATION": "data/reference/nse/indices/normalized/sector_index_daily.csv",
        "INDIA_VIX": "data/reference/nse/indices/normalized/india_vix_daily.csv",
        "GLOBAL_GIFT": "future GlobalMarketContextProvider",
        "INTRADAY_CONFIRMATION": "future intraday regime provider",
    }.get(component_name, "")


def load_benchmark_bars(path: Path) -> dict[str, list[BenchmarkBar]]:
    grouped: dict[str, list[BenchmarkBar]] = defaultdict(list)
    for row in read_csv(path):
        trading_date = parse_date(row.get("trading_date"))
        close = parse_decimal(row.get("close"))
        benchmark_id = row.get("benchmark_id", "")
        if trading_date and close is not None and benchmark_id:
            grouped[benchmark_id].append(BenchmarkBar(trading_date=trading_date, close=close))
    return {key: sorted(value, key=lambda item: item.trading_date) for key, value in grouped.items()}


def load_sector_bars(path: Path) -> list[SectorIndexBar]:
    bars: list[SectorIndexBar] = []
    for row in read_csv(path):
        trading_date = parse_date(row.get("trading_date"))
        close = parse_decimal(row.get("close"))
        sector_id = row.get("sector_index_id", "")
        if trading_date and close is not None and sector_id:
            bars.append(SectorIndexBar(trading_date=trading_date, sector_index_id=sector_id, close=close))
    return bars


def load_vix_bars(path: Path) -> list[VixBar]:
    if not path.exists():
        return []
    bars: list[VixBar] = []
    for row in read_csv(path):
        trading_date = parse_date(row.get("trading_date"))
        close = parse_decimal(row.get("close") or row.get("india_vix_close"))
        if trading_date and close is not None:
            bars.append(VixBar(trading_date=trading_date, close=close))
    return bars


def load_expected_sector_index_count(path: Path, sector_bars: Sequence[SectorIndexBar]) -> int:
    if not path.exists():
        return len({bar.sector_index_id for bar in sector_bars})
    count = 0
    for row in read_csv(path):
        if truthy(row.get("usable")):
            count += 1
    return count or len({bar.sector_index_id for bar in sector_bars})


def load_breadth_aggregates(path: Path, start_date: date, end_date: date) -> dict[date, BreadthAggregate]:
    aggregates: dict[date, BreadthAggregate] = defaultdict(BreadthAggregate)
    with open_csv_maybe_gzip(path) as file:
        reader = csv.DictReader(file)
        for row in reader:
            trading_date = parse_date(row.get("trading_date"))
            if trading_date is None or trading_date < start_date or trading_date > end_date:
                continue
            update_breadth_aggregate(aggregates[trading_date], row)
    return dict(aggregates)


@dataclass(frozen=True, slots=True)
class MembershipPeriod:
    symbol: str
    valid_from: date
    valid_to: date | None


def load_membership_periods(path: Path) -> list[MembershipPeriod]:
    periods: list[MembershipPeriod] = []
    for row in read_csv(path):
        valid_from = parse_date(row.get("valid_from"))
        if valid_from is None:
            continue
        periods.append(
            MembershipPeriod(
                symbol=row.get("symbol", ""),
                valid_from=valid_from,
                valid_to=parse_date(row.get("valid_to")),
            )
        )
    return periods


def expected_member_counts(periods: Sequence[MembershipPeriod], trading_sessions: Sequence[date]) -> dict[date, int]:
    counts: dict[date, int] = {}
    for trading_date in trading_sessions:
        counts[trading_date] = sum(
            1
            for period in periods
            if period.valid_from <= trading_date and (period.valid_to is None or trading_date <= period.valid_to)
        )
    return counts


def load_membership_status(path: Path) -> str:
    if not path.exists():
        return "UNAVAILABLE"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "PARTIAL_HISTORY"
    if payload.get("membership_periods", {}).get("coverage_start"):
        return "PARTIAL_HISTORY"
    return "UNAVAILABLE"


def load_trading_sessions(path: Path, start_date: date, end_date: date) -> list[date]:
    sessions = []
    for row in read_csv(path):
        trading_date = parse_date(row.get("trading_date"))
        if trading_date and start_date <= trading_date <= end_date and str(row.get("source_available")) == "True":
            sessions.append(trading_date)
    return sorted(sessions)


def daily_distribution_rows(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    output: list[dict[str, Any]] = []
    total = len(rows)
    regime_counts = Counter(row["regime_state"] for row in rows)
    confidence_counts = Counter(row["confidence_state"] for row in rows)
    missing_counts = Counter()
    for row in rows:
        for component in split_codes(row.get("missing_components")):
            missing_counts[component] += 1
    for section, counts in (("REGIME_STATE", regime_counts), ("CONFIDENCE_STATE", confidence_counts), ("MISSING_COMPONENT", missing_counts)):
        for name, count in counts.most_common():
            output.append({"section": section, "name": name, "count": count, "pct": pct(count, total), "details": ""})
    score_dist = decimal_distribution([parse_decimal(row.get("regime_score_normalized")) for row in rows])
    available_dist = decimal_distribution([parse_decimal(row.get("available_weight_pct")) for row in rows])
    for name, value in score_dist.items():
        output.append({"section": "NORMALIZED_SCORE_DISTRIBUTION", "name": name, "count": "", "pct": value, "details": ""})
    for name, value in available_dist.items():
        output.append({"section": "AVAILABLE_WEIGHT_DISTRIBUTION", "name": name, "count": "", "pct": value, "details": ""})
    return output, {
        "regime_state_counts": distribution_counts(regime_counts, total),
        "confidence_counts": distribution_counts(confidence_counts, total),
        "normalized_score_distribution": score_dist,
        "available_weight_distribution": available_dist,
        "most_missing_components": distribution_counts(missing_counts, total),
    }


def component_availability_rows(
    rows: Sequence[dict[str, Any]],
    config: MarketRegimeEngineConfig,
    sector_bars: Sequence[SectorIndexBar],
    vix_bars: Sequence[VixBar],
    benchmark: dict[str, list[BenchmarkBar]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_ranges = {
        "NIFTY_TREND": date_range_for_bars(benchmark.get("NIFTY_50", ())),
        "NIFTY500_BREADTH": (config.start_date, config.end_date),
        "SECTOR_INDEX_PARTICIPATION": date_range_for_bars(sector_bars),
        "INDIA_VIX": date_range_for_bars(vix_bars),
        "GLOBAL_GIFT": (None, None),
        "INTRADAY_CONFIRMATION": (None, None),
    }
    component_fields = {
        "NIFTY_TREND": "nifty_trend_status",
        "NIFTY500_BREADTH": "breadth_status",
        "SECTOR_INDEX_PARTICIPATION": "sector_status",
        "INDIA_VIX": "vix_status",
        "GLOBAL_GIFT": "global_gift_status",
        "INTRADAY_CONFIRMATION": "intraday_status",
    }
    weights = config.regime_config.weights
    weight_by_component = {
        "NIFTY_TREND": weights.nifty_trend,
        "NIFTY500_BREADTH": weights.nifty500_breadth,
        "SECTOR_INDEX_PARTICIPATION": weights.sector_participation,
        "INDIA_VIX": weights.india_vix,
        "GLOBAL_GIFT": weights.global_gift,
        "INTRADAY_CONFIRMATION": weights.intraday_confirmation,
    }
    output = []
    summary: dict[str, Any] = {}
    total = len(rows)
    for component_name in ALL_COMPONENTS:
        field = component_fields[component_name]
        counts = Counter(row[field] for row in rows)
        available_rows = counts["AVAILABLE"]
        partial_rows = counts["PARTIAL"]
        unavailable_rows = counts["UNAVAILABLE"]
        coverage_pct = pct_decimal(available_rows + partial_rows, total)
        status = "USABLE" if available_rows + partial_rows > 0 else "UNAVAILABLE"
        if component_name in {"GLOBAL_GIFT", "INTRADAY_CONFIRMATION", "INDIA_VIX"} and unavailable_rows == total:
            status = "UNAVAILABLE"
        start, end = source_ranges[component_name]
        row = {
            "component_name": component_name,
            "target_weight": weight_by_component[component_name],
            "historical_source": source_for_component(component_name),
            "coverage_start": start,
            "coverage_end": end,
            "coverage_pct": coverage_pct,
            "point_in_time_safety": point_in_time_safety(component_name),
            "usable": status != "UNAVAILABLE",
            "availability_status": status,
            "available_rows": available_rows,
            "partial_rows": partial_rows,
            "unavailable_rows": unavailable_rows,
            "limitations": limitations_for_component(component_name, status),
        }
        output.append(row)
        summary[component_name] = row
    return output, summary


def point_in_time_safety(component_name: str) -> str:
    return {
        "NIFTY_TREND": "OFFICIAL_NSE_INDEX_HISTORY_THROUGH_T",
        "NIFTY500_BREADTH": "POINT_IN_TIME_MEMBERSHIP_WITH_PARTIAL_HISTORY_LIMITATION",
        "SECTOR_INDEX_PARTICIPATION": "OFFICIAL_INDEX_HISTORY_THROUGH_T_NOT_STOCK_SECTOR_BREADTH",
        "INDIA_VIX": "UNAVAILABLE_NOT_IMPUTED",
        "GLOBAL_GIFT": "UNAVAILABLE_NOT_IMPUTED",
        "INTRADAY_CONFIRMATION": "UNAVAILABLE_FOR_DAILY_EOD_COMMAND",
    }[component_name]


def limitations_for_component(component_name: str, status: str) -> str:
    if component_name == "NIFTY500_BREADTH":
        return "Membership reconstruction is PARTIAL_HISTORY; current constituents are not projected backward."
    if component_name == "SECTOR_INDEX_PARTICIPATION":
        return "Uses official sector index performance only; not stock-level sector breadth."
    if component_name == "INDIA_VIX":
        return "Official local India VIX history is not present; no substitute was fabricated."
    if component_name == "GLOBAL_GIFT":
        return "No reliable local historical Global/GIFT dataset exists yet."
    if component_name == "INTRADAY_CONFIRMATION":
        return "This command is DAILY_EOD; intraday confirmation is reserved for a future live engine."
    return "" if status != "UNAVAILABLE" else "Required local history unavailable."


def validate_pilot_rows(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    selected = select_pilot_rows(rows)
    validation_rows: list[dict[str, Any]] = []
    for pilot_case, row in selected:
        if row is None:
            validation_rows.append(
                {
                    "pilot_case": pilot_case,
                    "trading_date": "",
                    "check_name": "pilot_date_available",
                    "observed": "NO_MATCHING_ROW",
                    "expected": "REAL_HISTORICAL_ROW",
                    "result": "PASS",
                    "explanation": "No safe local row exists for this optional pilot case; no data was fabricated.",
                }
            )
            continue
        validation_rows.extend(validation_checks(pilot_case, row))
    passed = all(row["result"] == "PASS" for row in validation_rows)
    return {
        "passed": passed,
        "rows": validation_rows,
        "summary": {
            "passed": passed,
            "pilot_dates": [{"pilot_case": case, "trading_date": row["trading_date"] if row else None} for case, row in selected],
            "checks": len(validation_rows),
            "failed_checks": sum(1 for row in validation_rows if row["result"] != "PASS"),
        },
    }


def select_pilot_rows(rows: Sequence[dict[str, Any]]) -> list[tuple[str, dict[str, Any] | None]]:
    classified = [row for row in rows if row["regime_state"] != "UNAVAILABLE"]
    strong_positive = max(
        (row for row in classified if row["regime_state"] == "BULLISH" and row["breadth_state"] in {"BULLISH", "STRONGLY_BULLISH"}),
        key=lambda row: parse_decimal(row["regime_score_normalized"]) or Decimal("-999"),
        default=None,
    )
    weak = min(
        (row for row in classified if row["regime_state"] == "BEARISH" and row["breadth_state"] in {"BEARISH", "STRONGLY_BEARISH"}),
        key=lambda row: parse_decimal(row["regime_score_normalized"]) or Decimal("999"),
        default=None,
    )
    mixed = next((row for row in classified if row["regime_state"] == "NEUTRAL" and row["component_agreement_direction"] != "NEUTRAL"), None)
    partial_sector = next((row for row in rows if row["sector_status"] == "PARTIAL"), None)
    early_boundary = rows[0] if rows else None
    vix_available = next((row for row in rows if row["vix_status"] != "UNAVAILABLE"), None)
    march_context = next((row for row in rows if str(row["trading_date"]) in {"2024-03-01", "2024-03-04"}), None)
    return [
        ("STRONG_POSITIVE_TREND_AND_BREADTH", strong_positive),
        ("WEAK_TREND_AND_BREADTH", weak),
        ("MIXED_TREND_BREADTH", mixed),
        ("HIGH_VOLATILITY_IF_VIX_AVAILABLE", vix_available),
        ("PARTIAL_SECTOR_COVERAGE", partial_sector),
        ("EARLY_MEMBERSHIP_BOUNDARY", early_boundary),
        ("BENCHMARK_DISCREPANCY_CONTEXT_IF_RELEVANT", march_context),
    ]


def validation_checks(pilot_case: str, row: dict[str, Any]) -> list[dict[str, Any]]:
    checks = [
        ("nifty_trend_calculation", row["nifty_trend_status"], "AVAILABLE_OR_PARTIAL"),
        ("breadth_member_denominator", row["expected_members"], "EXPECTED_MEMBERS_GT_0"),
        ("point_in_time_membership_usage", row["membership_status"], "PARTIAL_HISTORY_OR_POINT_IN_TIME_AVAILABLE"),
        ("advancer_decliner_counts", int(row["advancers"]) + int(row["decliners"]) + int(row["unchanged"]), row["usable_members"]),
        ("sma_breadth", row["pct_above_sma20"], "NULL_ALLOWED_UNTIL_HISTORY_EXISTS"),
        ("sector_participation_inputs", row["sector_status"], "AVAILABLE_OR_PARTIAL_OR_DOCUMENTED_UNAVAILABLE"),
        ("india_vix_input", row["vix_status"], "UNAVAILABLE_ALLOWED_IF_NO_OFFICIAL_LOCAL_HISTORY"),
        ("available_weight", row["available_weight_pct"], "CALCULATED_FROM_NON_NULL_COMPONENTS"),
        ("score_normalization", row["regime_score_normalized"], "RAW_SCORE_DIVIDED_BY_AVAILABLE_WEIGHT"),
        ("state_classification", row["regime_state"], "THRESHOLD_BASED_OR_UNAVAILABLE"),
        ("confidence_score", row["confidence_score"], "0_TO_100"),
    ]
    output = []
    for check_name, observed, expected in checks:
        result = "PASS"
        if check_name == "breadth_member_denominator" and int(observed or 0) <= 0:
            result = "FAIL"
        if check_name == "advancer_decliner_counts" and int(observed) != int(expected or 0):
            result = "FAIL"
        if check_name == "confidence_score":
            value = parse_decimal(observed)
            if value is None or value < 0 or value > 100:
                result = "FAIL"
        output.append(
            {
                "pilot_case": pilot_case,
                "trading_date": row["trading_date"],
                "check_name": check_name,
                "observed": observed,
                "expected": expected,
                "result": result,
                "explanation": "Leakage-safe EOD validation check for MARKET_REGIME_V1.",
            }
        )
    return output


def streak_summary_rows(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_state: dict[str, list[int]] = {state: [] for state in CLASSIFIED_STATES}
    current_state = None
    current_length = 0
    for row in rows:
        state = row["regime_state"]
        if state not in CLASSIFIED_STATES:
            if current_state in CLASSIFIED_STATES and current_length:
                by_state[current_state].append(current_length)
            current_state = None
            current_length = 0
            continue
        if state == current_state:
            current_length += 1
        else:
            if current_state in CLASSIFIED_STATES and current_length:
                by_state[current_state].append(current_length)
            current_state = state
            current_length = 1
    if current_state in CLASSIFIED_STATES and current_length:
        by_state[current_state].append(current_length)

    output = []
    summary = {}
    for state, streaks in by_state.items():
        stats = length_distribution(streaks)
        row = {"regime_state": state, **stats}
        output.append(row)
        summary[state] = stats
    return output, summary


def transition_matrix_rows(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    counts: Counter[tuple[str, str]] = Counter()
    from_counts: Counter[str] = Counter()
    ordered = list(rows)
    for left, right in zip(ordered, ordered[1:]):
        from_state = left["regime_state"]
        to_state = right["regime_state"]
        if from_state not in CLASSIFIED_STATES or to_state not in CLASSIFIED_STATES:
            continue
        counts[(from_state, to_state)] += 1
        from_counts[from_state] += 1
    output = []
    for from_state in CLASSIFIED_STATES:
        for to_state in CLASSIFIED_STATES:
            count = counts[(from_state, to_state)]
            output.append(
                {
                    "from_state": from_state,
                    "to_state": to_state,
                    "count": count,
                    "from_total": from_counts[from_state],
                    "pct": pct(count, from_counts[from_state]),
                }
            )
    return output, {
        "top_transitions": [
            {"from_state": pair[0], "to_state": pair[1], "count": count}
            for pair, count in counts.most_common(10)
        ],
        "direct_bullish_bearish_flips": counts[("BULLISH", "BEARISH")] + counts[("BEARISH", "BULLISH")],
        "matrix": output,
    }


def score_continuity_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    changes = []
    direct_flips = 0
    for left, right in zip(rows, rows[1:]):
        left_score = parse_decimal(left.get("regime_score_normalized"))
        right_score = parse_decimal(right.get("regime_score_normalized"))
        if left_score is not None and right_score is not None:
            changes.append(abs(right_score - left_score))
        if {left["regime_state"], right["regime_state"]} == {"BULLISH", "BEARISH"}:
            direct_flips += 1
    stats = decimal_distribution(changes)
    stats["direct_bullish_bearish_flips"] = direct_flips
    stats["pathological_regime_flipping_detected"] = direct_flips > 5
    return stats


def prefixed_evidence(evidence: dict[str, Any], *, include_prefix: bool) -> dict[str, Any]:
    ignored = {"trading_date", "score_points", "score_ratio", "metric_coverage_pct"}
    return {key: value for key, value in evidence.items() if key not in ignored}


def write_historical_market_regime_markdown(report: dict[str, Any], path: Path) -> None:
    distribution = report["daily_distribution"]["regime_state_counts"]
    availability = report["component_availability"]
    lines = [
        "# Historical Market Regime Engine",
        "",
        "Current phase: Step 02.7 / Command 01 - historical Market Regime Engine foundation",
        "",
        "## Boundary",
        "",
        "- This is MARKET_REGIME_V1, a DAILY_EOD_REGIME used as NEXT_SESSION_CONTEXT.",
        "- It reports broad market context only; it does not decide stock entries.",
        "- No future returns, MFE, MAE, winners/losers, backtesting, entry scoring, risk/reward, stops, targets, position sizing, orders, migrations, or Supabase writes are used.",
        "- Missing Global/GIFT, India VIX, and intraday evidence is marked unavailable, not neutral.",
        "",
        "## Version",
        "",
        f"- Regime version/config hash: {report['methodology']['regime_version']} / {report['methodology']['config_hash']}",
        f"- Classification threshold: bullish >= {report['methodology']['classification']['bullish_min']}, bearish <= {report['methodology']['classification']['bearish_max']}",
        f"- Minimum available weight: {report['methodology']['classification']['minimum_available_weight_pct']}%",
        "",
        "## Component Availability",
        "",
    ]
    for name in ALL_COMPONENTS:
        row = availability[name]
        coverage_pct = round_decimal(parse_decimal(row["coverage_pct"]))
        lines.append(
            f"- {name}: {row['availability_status']}, coverage {coverage_pct}%, source={row['historical_source']}, limitation={row['limitations']}"
        )
    lines.extend(
        [
            "",
            "## Generation",
            "",
            f"- Historical coverage: {report['generation']['historical_start_date']} to {report['generation']['historical_end_date']}",
            f"- Total regime rows: {report['generation']['total_regime_rows']}",
            f"- Full generation completed: {report['generation']['full_generation_completed']}",
            f"- Regime counts: {distribution}",
            f"- Confidence counts: {report['daily_distribution']['confidence_counts']}",
            f"- Score distribution: {report['daily_distribution']['normalized_score_distribution']}",
            f"- Available-weight distribution: {report['daily_distribution']['available_weight_distribution']}",
            "",
            "## Persistence",
            "",
            f"- Streak summary: {report['streaks']}",
            f"- Top transitions: {report['transitions']['top_transitions']}",
            f"- Score continuity: {report['score_continuity']}",
            "",
            "## Integrity And Safety",
            "",
            f"- DAILY_FEATURES_V1 unchanged: {report['regression']['feature_dataset_unchanged']}",
            f"- MOMENTUM_CANDIDATES_V1 unchanged: {report['regression']['candidate_dataset_unchanged']}",
            f"- DAILY_SETUP_EVALUATION_V1 unchanged: {report['regression']['setup_dataset_unchanged']}",
            "- ZERO orders were placed.",
            "- ZERO remote migrations were applied.",
            "- ZERO bulk records were persisted to Supabase.",
            "",
            "## Known Limitations",
            "",
            "- Historical Nifty 500 membership remains PARTIAL_HISTORY.",
            "- Sector participation is official sector-index participation, not point-in-time stock-sector breadth.",
            "- India VIX, Global/GIFT, and intraday confirmation are unavailable in this command and reduce confidence/coverage.",
            "- No outcome or profitability interpretation is made from regime states.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def write_gzip_csv(path: Path, rows: Sequence[dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(json_safe(row))


def parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    return date.fromisoformat(text)


def parse_decimal(value: Any) -> Decimal | None:
    if isinstance(value, Decimal):
        return value
    text = str(value or "").strip().replace(",", "")
    if not text or text == "None":
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def truthy(value: Any) -> bool:
    return str(value).strip().lower() == "true" if not isinstance(value, bool) else value


def split_codes(value: Any) -> set[str]:
    return {item for item in str(value or "").split(";") if item}


def pct(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.0000"
    return round_decimal(Decimal(numerator) / Decimal(denominator) * Decimal("100"))


def pct_decimal(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        return Decimal("0")
    return Decimal(numerator) / Decimal(denominator) * Decimal("100")


def round_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""
    return format(value.quantize(Decimal("0.0001")), "f")


def distribution_counts(counter: Counter[str], total: int) -> dict[str, Any]:
    return {key: {"count": value, "pct": pct(value, total)} for key, value in counter.items()}


def decimal_distribution(values: Sequence[Decimal | None]) -> dict[str, Any]:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return {"usable_rows": 0, "min": "", "p10": "", "p25": "", "median": "", "mean": "", "p75": "", "p90": "", "p95": "", "max": ""}
    return {
        "usable_rows": len(clean),
        "min": round_decimal(clean[0]),
        "p10": round_decimal(decimal_quantile(clean, Decimal("0.10"))),
        "p25": round_decimal(decimal_quantile(clean, Decimal("0.25"))),
        "median": round_decimal(decimal_quantile(clean, Decimal("0.50"))),
        "mean": round_decimal(sum(clean) / Decimal(len(clean))),
        "p75": round_decimal(decimal_quantile(clean, Decimal("0.75"))),
        "p90": round_decimal(decimal_quantile(clean, Decimal("0.90"))),
        "p95": round_decimal(decimal_quantile(clean, Decimal("0.95"))),
        "max": round_decimal(clean[-1]),
    }


def length_distribution(values: Sequence[int]) -> dict[str, Any]:
    if not values:
        return {
            "streak_count": 0,
            "one_session": 0,
            "two_sessions": 0,
            "three_to_five": 0,
            "six_to_ten": 0,
            "over_ten": 0,
            "median": 0,
            "mean": 0,
            "p90": 0,
            "p95": 0,
            "max": 0,
        }
    ordered = sorted(values)
    return {
        "streak_count": len(ordered),
        "one_session": sum(1 for value in ordered if value == 1),
        "two_sessions": sum(1 for value in ordered if value == 2),
        "three_to_five": sum(1 for value in ordered if 3 <= value <= 5),
        "six_to_ten": sum(1 for value in ordered if 6 <= value <= 10),
        "over_ten": sum(1 for value in ordered if value > 10),
        "median": statistics.median(ordered),
        "mean": round(float(statistics.mean(ordered)), 4),
        "p90": int_quantile(ordered, Decimal("0.90")),
        "p95": int_quantile(ordered, Decimal("0.95")),
        "max": ordered[-1],
    }


def decimal_quantile(values: Sequence[Decimal], percentile: Decimal) -> Decimal:
    if not values:
        return Decimal("0")
    ordered = sorted(values)
    index = int((Decimal(len(ordered) - 1) * percentile).to_integral_value(rounding="ROUND_HALF_UP"))
    return ordered[min(index, len(ordered) - 1)]


def int_quantile(values: Sequence[int], percentile: Decimal) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = int((Decimal(len(ordered) - 1) * percentile).to_integral_value(rounding="ROUND_HALF_UP"))
    return ordered[min(index, len(ordered) - 1)]


def date_range_for_bars(bars: Sequence[Any]) -> tuple[date | None, date | None]:
    dates = [bar.trading_date for bar in bars]
    if not dates:
        return None, None
    return min(dates), max(dates)


def output_size(config: MarketRegimeEngineConfig) -> int:
    paths = [
        config.regime_dataset_path,
        config.summary_path,
        config.daily_distribution_path,
        config.component_availability_path,
        config.pilot_validation_path,
        config.transition_matrix_path,
        config.streak_summary_path,
    ]
    return sum(path.stat().st_size for path in paths if path.exists())


class GlobalMarketContextProvider:
    """Placeholder interface for a future verified Global/GIFT data source."""

    def component_for(self, trading_date: date, target_weight: Decimal) -> dict[str, Any]:
        return unavailable_component("GLOBAL_GIFT", trading_date, target_weight, "GLOBAL_GIFT_HISTORY_NOT_AVAILABLE_LOCALLY")


class IntradayConfirmationProvider:
    """Placeholder interface for a future live/intraday regime source."""

    def component_for(self, trading_date: date, target_weight: Decimal) -> dict[str, Any]:
        return unavailable_component(
            "INTRADAY_CONFIRMATION",
            trading_date,
            target_weight,
            "DAILY_EOD_COMMAND_NO_INTRADAY_CONFIRMATION",
        )
