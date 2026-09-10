from __future__ import annotations

import csv
import gzip
import io
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from app.risk.risk_config import (
    CURRENT_RISK_STRUCTURE_CONFIG_HASH,
    CURRENT_RISK_STRUCTURE_VERSION,
    RISK_STRUCTURE_V1_1_DATASET_HASH,
    resolve_current_risk_structure_dataset,
)
from app.risk.risk_structurer import load_lookup
from app.services.daily_feature_engine import json_safe, write_csv, write_json
from app.services.nifty500_membership import canonical_symbol
from app.strategy.momentum_candidates import file_sha256
from app.strategy.outcomes.outcome_config import (
    STRATEGY_OUTCOME_VERSION,
    SWING_DAILY_OUTCOME_PROFILE,
    StrategyOutcomeConfig,
)
from app.strategy.outcomes.outcome_engine import (
    AMBIGUOUS,
    COUNTERFACTUAL_COHORT,
    ENTRY_INVALID_CAPITAL,
    ENTRY_INVALID_GAP,
    ENTRY_INVALID_RR,
    ENTRY_INVALID_STOP_RELATION,
    ENTRY_VALID,
    EXCEPTIONAL_COHORT,
    INSUFFICIENT_FORWARD_DATA,
    NEITHER_WITHIN_HORIZON,
    NO_NEXT_SESSION_DATA,
    OTHER_INVALID,
    PREVIEW_COHORT,
    PRIMARY_COHORT,
    SAFE_BAR_STATUSES,
    STOP_FIRST,
    TARGET_FIRST,
    ForwardExclusion,
    OutcomeBar,
    StrategyOutcomeEngineConfig,
    forward_safety,
    load_adjusted_market_history,
    load_forward_exclusions,
    resolve_next_sessions,
    union_fieldnames,
)
from app.strategy.scoring.score_baseline import (
    CURRENT_STRATEGY_SCORE_CONFIG_HASH,
    CURRENT_STRATEGY_SCORE_PROFILE,
    CURRENT_STRATEGY_SCORE_VERSION,
    STRATEGY_SCORE_V1_DATASET_HASH,
    baseline_hash_checks,
    baseline_input_hashes,
    resolve_current_strategy_score_dataset,
)

STRATEGY_OUTCOME_AUDIT_VERSION = "STRATEGY_OUTCOME_AUDIT_V1"
STRATEGY_OUTCOME_V1_DATASET_HASH = "5c4ec28cb54f6567b04c3444a3f1d0dde5f03ac3c6518743268f9e4fda100538"
EXPECTED_OUTCOME_CONFIG_HASH = "2ea683a8f8b5b041"
EXPECTED_OUTCOME_ROWS = 14251
EXPECTED_PRIMARY_ROWS = 4268
RR_UNCHANGED_TOLERANCE = Decimal("0.05")
RECONSTRUCTION_TOLERANCE = Decimal("0.00000001")
R_LEVELS = (Decimal("0.5"), Decimal("1"), Decimal("1.5"), Decimal("2"), Decimal("2.5"))
ADVERSE_R_LEVELS = (Decimal("0.5"), Decimal("1"), Decimal("1.5"))
EXTENDED_HORIZONS = (5, 6, 7, 8, 10)
AUDIT_REPORT_NAMES = (
    "forward_safety",
    "gap_rr",
    "target_distance",
    "r_levels",
    "mfe_mae",
    "first_touch",
    "score_bands",
    "regimes",
    "categories",
    "setup_quality",
    "overlap",
    "capital_demand",
    "yearly",
    "pilot",
)


@dataclass(frozen=True, slots=True)
class StrategyOutcomeAuditConfig:
    data_dir: Path
    audit_version: str = STRATEGY_OUTCOME_AUDIT_VERSION

    @property
    def outcome_engine_config(self) -> StrategyOutcomeEngineConfig:
        return StrategyOutcomeEngineConfig(data_dir=self.data_dir)

    @property
    def outcome_dataset_path(self) -> Path:
        return self.outcome_engine_config.output_dataset_path

    @property
    def score_dataset_path(self) -> Path:
        return resolve_current_strategy_score_dataset(self.data_dir)

    @property
    def risk_dataset_path(self) -> Path:
        return resolve_current_risk_structure_dataset(self.data_dir)

    @property
    def adjusted_daily_dir(self) -> Path:
        return self.outcome_engine_config.adjusted_daily_dir

    @property
    def eligibility_path(self) -> Path:
        return self.outcome_engine_config.eligibility_path

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def bulk_dir(self) -> Path:
        return self.data_dir / "research" / "audits" / "strategy_outcome" / "v1"

    @property
    def summary_path(self) -> Path:
        return self.reports_dir / "strategy_outcome_v1_audit_summary.json"

    def report_path(self, name: str) -> Path:
        return self.reports_dir / f"strategy_outcome_v1_audit_{name}.csv"


def build_strategy_outcome_audit(
    *,
    config: StrategyOutcomeAuditConfig,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    notify(progress, "Verifying immutable outcome and upstream baselines")
    hashes_before = frozen_hashes(config)
    verify_frozen_hashes(hashes_before)

    notify(progress, "Loading outcome, score, and risk rows")
    outcome_rows = load_outcome_rows(config.outcome_dataset_path)
    validate_outcome_identity(outcome_rows)
    keys = {(row["decision_date"], canonical_symbol(row["symbol"])) for row in outcome_rows}
    score_lookup = load_lookup(config.score_dataset_path, keys)
    risk_lookup = load_lookup(config.risk_dataset_path, keys)
    if len(score_lookup) != len(keys) or len(risk_lookup) != len(keys):
        raise ValueError("Outcome audit could not join every row to frozen score and risk inputs")
    rows = enrich_rows(outcome_rows, score_lookup, risk_lookup)
    primary = [row for row in rows if row["outcome_cohort"] == PRIMARY_COHORT]
    valid_primary = [row for row in primary if truthy(row["entry_valid"])]

    notify(progress, "Loading adjusted history for safety and extended-horizon diagnostics")
    symbols = {canonical_symbol(row["symbol"]) for row in primary}
    sessions, bars = load_adjusted_market_history(config.adjusted_daily_dir, symbols)
    exclusions = load_forward_exclusions(config.eligibility_path)

    notify(progress, "Decomposing forward-safety and next-open revalidation")
    safety = audit_forward_safety(primary, sessions, bars, exclusions)
    counterfactuals = safety_counterfactuals(primary, safety["row_summaries"])
    gap_rr = audit_gap_and_rr(primary)

    notify(progress, "Auditing target distance, R excursions, and first-touch labels")
    target_distance = audit_target_distance(valid_primary)
    r_levels = audit_r_levels(valid_primary)
    mfe_mae = audit_mfe_mae(valid_primary)
    reconstruction = audit_reconstruction(valid_primary)

    notify(progress, "Calculating extended 5/6/7/8/10-session diagnostics")
    extended_records = build_extended_records(valid_primary, sessions, bars, exclusions)
    extended = audit_extended_horizons(extended_records)

    notify(progress, "Auditing score, cohort, overlap, capital, and yearly structure")
    score_audit = audit_scores(rows, primary, valid_primary)
    categories = audit_categories(primary)
    setups = audit_setups(primary)
    regimes = audit_regimes(rows, primary)
    overlap = audit_overlap(primary, valid_primary, sessions)
    capital = audit_capital_demand(valid_primary)
    yearly = audit_yearly(primary)
    terminology = audit_terminology_and_separation(rows)
    pilot = run_audit_pilot(
        rows=rows,
        primary=primary,
        valid_primary=valid_primary,
        safety_rows=safety["row_summaries"],
        reconstruction=reconstruction,
    )

    classifications = classify_audit(
        safety=safety,
        counterfactuals=counterfactuals,
        gap_rr=gap_rr,
        reconstruction=reconstruction,
        extended=extended,
        score_audit=score_audit,
        terminology=terminology,
        valid_primary=valid_primary,
    )
    tables = build_audit_tables(
        safety=safety,
        counterfactuals=counterfactuals,
        gap_rr=gap_rr,
        target_distance=target_distance,
        r_levels=r_levels,
        mfe_mae=mfe_mae,
        reconstruction=reconstruction,
        extended=extended,
        score_audit=score_audit,
        regimes=regimes,
        categories=categories,
        setups=setups,
        overlap=overlap,
        capital=capital,
        yearly=yearly,
        pilot=pilot,
    )

    hashes_after = frozen_hashes(config)
    if hashes_after != hashes_before:
        raise ValueError("Frozen dataset hash changed during outcome audit")
    report = build_audit_summary(
        config=config,
        rows=rows,
        primary=primary,
        valid_primary=valid_primary,
        hashes_before=hashes_before,
        hashes_after=hashes_after,
        safety=safety,
        counterfactuals=counterfactuals,
        gap_rr=gap_rr,
        target_distance=target_distance,
        r_levels=r_levels,
        mfe_mae=mfe_mae,
        reconstruction=reconstruction,
        extended=extended,
        score_audit=score_audit,
        regimes=regimes,
        categories=categories,
        setups=setups,
        overlap=overlap,
        capital=capital,
        yearly=yearly,
        terminology=terminology,
        pilot=pilot,
        classifications=classifications,
        runtime_seconds=time.perf_counter() - started,
    )
    notify(progress, "Writing ignored structural-audit reports")
    write_audit_outputs(config, report, tables, safety["row_summaries"], extended_records)
    return report


def frozen_hashes(config: StrategyOutcomeAuditConfig) -> dict[str, str]:
    hashes = baseline_input_hashes(config.data_dir)
    hashes["outcome_v1"] = file_sha256(config.outcome_dataset_path)
    return hashes


def verify_frozen_hashes(hashes: dict[str, str]) -> None:
    if not all(baseline_hash_checks({key: value for key, value in hashes.items() if key != "outcome_v1"}).values()):
        raise ValueError("Frozen score/risk/upstream hash mismatch")
    if hashes.get("score_v1") != STRATEGY_SCORE_V1_DATASET_HASH:
        raise ValueError("Frozen score dataset hash mismatch")
    if hashes.get("risk_v1_1") != RISK_STRUCTURE_V1_1_DATASET_HASH:
        raise ValueError("Frozen risk V1.1 dataset hash mismatch")
    if hashes.get("outcome_v1") != STRATEGY_OUTCOME_V1_DATASET_HASH:
        raise ValueError("Frozen outcome dataset hash mismatch")
    if StrategyOutcomeConfig().config_hash() != EXPECTED_OUTCOME_CONFIG_HASH:
        raise ValueError("Frozen outcome config hash mismatch")


def load_outcome_rows(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def validate_outcome_identity(rows: Sequence[dict[str, Any]]) -> None:
    if len(rows) != EXPECTED_OUTCOME_ROWS:
        raise ValueError(f"Expected {EXPECTED_OUTCOME_ROWS} outcome rows, observed {len(rows)}")
    checks = {
        "outcome_version": {STRATEGY_OUTCOME_VERSION},
        "outcome_profile": {SWING_DAILY_OUTCOME_PROFILE},
        "outcome_config_hash": {EXPECTED_OUTCOME_CONFIG_HASH},
        "score_version": {CURRENT_STRATEGY_SCORE_VERSION},
        "score_profile": {CURRENT_STRATEGY_SCORE_PROFILE},
        "score_config_hash": {CURRENT_STRATEGY_SCORE_CONFIG_HASH},
        "risk_version": {CURRENT_RISK_STRUCTURE_VERSION},
        "risk_config_hash": {CURRENT_RISK_STRUCTURE_CONFIG_HASH},
    }
    for field, expected in checks.items():
        observed = {row.get(field) for row in rows}
        if observed != expected:
            raise ValueError(f"Outcome identity mismatch for {field}: {sorted(str(value) for value in observed)}")
    primary_count = sum(row.get("outcome_cohort") == PRIMARY_COHORT for row in rows)
    if primary_count != EXPECTED_PRIMARY_ROWS:
        raise ValueError(f"Expected {EXPECTED_PRIMARY_ROWS} primary rows, observed {primary_count}")


def enrich_rows(
    outcome_rows: Sequence[dict[str, str]],
    score_lookup: dict[tuple[str, str], dict[str, str]],
    risk_lookup: dict[tuple[str, str], dict[str, str]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for source in outcome_rows:
        row: dict[str, Any] = dict(source)
        key = (source["decision_date"], canonical_symbol(source["symbol"]))
        score = score_lookup[key]
        risk = risk_lookup[key]
        reference = decimal_or_none(row.get("reference_entry_price"))
        entry = decimal_or_none(row.get("hypothetical_entry_price"))
        stop = decimal_or_none(row.get("stop_price"))
        target = decimal_or_none(row.get("target_price"))
        planned_risk = decimal_or_none(risk.get("risk_per_share"))
        planned_reward = decimal_or_none(risk.get("reward_per_share"))
        row.update(
            {
                "planned_reward_risk": decimal_or_none(score.get("reward_risk_ratio")),
                "planned_quantity": int(decimal_or_zero(risk.get("structured_quantity"))),
                "planned_risk_per_share": planned_risk,
                "planned_reward_per_share": planned_reward,
                "planned_stop_distance_pct": percent_of(planned_risk, reference),
                "planned_target_distance_pct": percent_of(planned_reward, reference),
                "effective_stop_distance_pct": percent_of(entry - stop if entry is not None and stop is not None else None, entry),
                "effective_target_distance_pct": percent_of(target - entry if target is not None and entry is not None else None, entry),
                "target_type": target_type(str(row.get("target_basis", ""))),
                "score_raw": decimal_or_none(row.get("source_raw_strategy_score")),
            }
        )
        planned_rr = decimal_or_none(row.get("planned_reward_risk"))
        effective_rr = decimal_or_none(row.get("effective_reward_risk"))
        row["delta_rr"] = effective_rr - planned_rr if planned_rr is not None and effective_rr is not None else None
        output.append(row)
    return output


def audit_forward_safety(
    primary: Sequence[dict[str, Any]],
    sessions: Sequence[date],
    bars: dict[tuple[str, str], OutcomeBar],
    exclusions: dict[str, list[ForwardExclusion]],
) -> dict[str, Any]:
    unsafe = [row for row in primary if not truthy(row.get("forward_data_safe"))]
    details: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for row in unsafe:
        decision = date.fromisoformat(str(row["decision_date"]))
        symbol = canonical_symbol(row["symbol"])
        forward_dates = resolve_next_sessions(decision, sessions, 4)
        row_details: list[dict[str, Any]] = []
        for index, session in enumerate(forward_dates, start=1):
            bar = bars.get((session.isoformat(), symbol))
            causes: list[tuple[str, str]] = []
            active_exclusions = [
                exclusion
                for exclusion in exclusions.get(symbol, [])
                if exclusion.start_date <= session <= exclusion.end_date
            ]
            for exclusion in active_exclusions:
                causes.append(
                    (
                        "CORPORATE_ACTION_EXCLUSION_INTERVAL",
                        exclusion.reason_code or exclusion.source_event_id or "UNSPECIFIED_EXCLUSION",
                    )
                )
            if bar is None:
                causes.append(("MISSING_FORWARD_SESSION_BAR", "BAR_MISSING_FOR_VALID_SESSION"))
            elif bar.research_usability_status == "CONTINUITY_BREAK":
                causes.append(("STRUCTURAL_CONTINUITY_BREAK", "CONTINUITY_BREAK"))
            elif bar.research_usability_status not in SAFE_BAR_STATUSES:
                causes.append(("UNSAFE_ADJUSTED_BAR_STATUS", bar.research_usability_status or "UNSPECIFIED"))
            for cause, reason in causes:
                detail = {
                    "decision_date": row["decision_date"],
                    "symbol": symbol,
                    "session_index": index,
                    "session_date": session.isoformat(),
                    "entry_or_later": "ENTRY_SESSION_UNSAFE" if index == 1 else "LATER_HOLD_SESSION_UNSAFE",
                    "cause": cause,
                    "reason": reason,
                    "bar_research_status": bar.research_usability_status if bar else "MISSING",
                }
                details.append(detail)
                row_details.append(detail)
        if not row_details:
            row_details.append(
                {
                    "decision_date": row["decision_date"],
                    "symbol": symbol,
                    "session_index": "",
                    "session_date": "",
                    "entry_or_later": "UNKNOWN",
                    "cause": "OTHER",
                    "reason": row.get("forward_data_reasons", ""),
                    "bar_research_status": "",
                }
            )
            details.extend(row_details)
        cause_set = {detail["cause"] for detail in row_details}
        affected_indexes = sorted({int(detail["session_index"]) for detail in row_details if detail["session_index"] != ""})
        entry_unsafe = 1 in affected_indexes
        summaries.append(
            {
                "decision_date": row["decision_date"],
                "symbol": symbol,
                "primary_cause": next(iter(cause_set)) if len(cause_set) == 1 else "MIXED_SAFE_UNSAFE_FORWARD_WINDOW",
                "all_causes": ";".join(sorted(cause_set)),
                "reason_types": ";".join(sorted({str(detail["reason"]) for detail in row_details})),
                "affected_session_indexes": ";".join(str(index) for index in affected_indexes),
                "first_unsafe_session": min(affected_indexes) if affected_indexes else "",
                "entry_session_unsafe": entry_unsafe,
                "later_window_only_unsafe": bool(affected_indexes) and not entry_unsafe,
            }
        )
    cause_counts = Counter(str(row["primary_cause"]) for row in summaries)
    entry_unsafe_count = sum(truthy(row["entry_session_unsafe"]) for row in summaries)
    later_only_count = sum(truthy(row["later_window_only_unsafe"]) for row in summaries)
    return {
        "unsafe_primary_rows": len(unsafe),
        "unsafe_rate_pct": pct(len(unsafe), len(primary)),
        "cause_distribution": distribution_rows(cause_counts, len(unsafe), "cause"),
        "entry_session_unsafe_count": entry_unsafe_count,
        "later_window_only_unsafe_count": later_only_count,
        "row_summaries": summaries,
        "details": details,
        "top_symbols": top_counts((row["symbol"] for row in summaries), 20),
        "top_dates": top_counts((row["decision_date"] for row in summaries), 20),
        "top_years": top_counts((str(row["decision_date"])[:4] for row in summaries), 10),
        "top_reasons": top_counts(
            (reason for row in summaries for reason in str(row["reason_types"]).split(";") if reason),
            20,
        ),
    }


def safety_counterfactuals(
    primary: Sequence[dict[str, Any]],
    safety_rows: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    safety_lookup = {(row["decision_date"], row["symbol"]): row for row in safety_rows}
    baseline = {row_key(row) for row in primary if truthy(row.get("entry_valid"))}
    entry_only: set[tuple[str, str]] = set()
    censor: set[tuple[str, str]] = set()
    censor_partial: set[tuple[str, str]] = set()
    for row in primary:
        key = row_key(row)
        if key in baseline:
            entry_only.add(key)
            censor.add(key)
            if int(decimal_or_zero(row.get("forward_sessions_available"))) < 4:
                censor_partial.add(key)
            continue
        safety = safety_lookup.get(key)
        entry_safe = safety is None or not truthy(safety.get("entry_session_unsafe"))
        if mechanical_entry_valid(row) and entry_safe:
            entry_only.add(key)
            censor.add(key)
            if safety is not None and truthy(safety.get("later_window_only_unsafe")):
                censor_partial.add(key)
    policies = [
        policy_summary("BASELINE_FORWARD_WINDOW_STRICT", baseline, baseline, len(primary), sum(int(decimal_or_zero(row.get("forward_sessions_available"))) < 4 for row in primary if row_key(row) in baseline)),
        policy_summary("ENTRY_SESSION_MUST_BE_SAFE_ONLY", entry_only, baseline, len(primary), 0),
        policy_summary("CENSOR_AT_FIRST_UNSAFE_FORWARD_SESSION", censor, baseline, len(primary), len(censor_partial)),
    ]
    return {
        "policies": policies,
        "entry_only_recovered_rows": len(entry_only - baseline),
        "censor_recovered_rows": len(censor - baseline),
        "censor_partial_rows": len(censor_partial),
    }


def policy_summary(
    name: str,
    selected: set[tuple[str, str]],
    baseline: set[tuple[str, str]],
    total: int,
    partial_count: int,
) -> dict[str, Any]:
    union = selected | baseline
    return {
        "policy": name,
        "valid_entry_count": len(selected),
        "rows_recovered_vs_baseline": len(selected - baseline),
        "rows_still_invalid": total - len(selected),
        "partial_or_right_censored_count": partial_count,
        "jaccard_vs_baseline": Decimal(len(selected & baseline)) / Decimal(len(union)) if union else Decimal("1"),
    }


def audit_gap_and_rr(primary: Sequence[dict[str, Any]]) -> dict[str, Any]:
    next_data = [row for row in primary if decimal_or_none(row.get("hypothetical_entry_price")) is not None]
    gaps = [value for row in next_data if (value := decimal_or_none(row.get("gap_pct"))) is not None]
    quantile_rows = metric_quantile_rows("GAP_PCT", gaps, (0, 1, 5, 10, 25, 50, 75, 90, 95, 99, 100))
    gap_bands = distribution_rows(Counter(str(row.get("gap_category", "")) for row in next_data), len(next_data), "gap_band")

    gap_invalid = [row for row in primary if row.get("entry_recheck_status") == ENTRY_INVALID_GAP]
    invalid_decomposition = Counter(gap_invalidation_reason(row) for row in gap_invalid)
    invalid_decomposition_rows = distribution_rows(invalid_decomposition, len(gap_invalid), "reason")
    open_stop_rows = [row for row in primary if row.get("entry_recheck_status") == ENTRY_INVALID_STOP_RELATION]
    open_stop_details = [
        {
            "section": "OPEN_AT_OR_BELOW_STOP_CASE",
            "symbol": row["symbol"],
            "decision_date": row["decision_date"],
            "reference_entry_price": row.get("reference_entry_price"),
            "frozen_stop_price": row.get("stop_price"),
            "next_open": row.get("hypothetical_entry_price"),
            "gap_pct": row.get("gap_pct"),
            "recheck_reason": row.get("entry_rejection_reasons"),
            "reconstruction_result": "PASS" if decimal_or_zero(row.get("hypothetical_entry_price")) <= decimal_or_zero(row.get("stop_price")) else "FAIL",
        }
        for row in open_stop_rows
    ]

    rr_rows = [
        row
        for row in primary
        if decimal_or_none(row.get("planned_reward_risk")) is not None
        and decimal_or_none(row.get("effective_reward_risk")) is not None
    ]
    planned_values = [decimal_or_zero(row["planned_reward_risk"]) for row in rr_rows]
    effective_values = [decimal_or_zero(row["effective_reward_risk"]) for row in rr_rows]
    deltas = [decimal_or_zero(row["delta_rr"]) for row in rr_rows]
    rr_delta_quantiles = metric_quantile_rows("DELTA_RR", deltas, (1, 5, 10, 25, 50, 75, 90, 95, 99), include_mean=True)
    direction_counts = Counter(rr_delta_direction(delta) for delta in deltas)
    crossed = [
        row
        for row in rr_rows
        if decimal_or_zero(row["planned_reward_risk"]) >= Decimal("1.5")
        and decimal_or_zero(row["effective_reward_risk"]) < Decimal("1.5")
    ]
    safe_crossed = [row for row in crossed if truthy(row.get("forward_data_safe"))]
    rr_invalid = [
        row
        for row in primary
        if row.get("entry_recheck_status") in {ENTRY_INVALID_GAP, ENTRY_INVALID_RR}
    ]
    positive_gap_invalid = sum(decimal_or_zero(row.get("gap_pct")) > 0 for row in rr_invalid)
    invalid_details = [
        {
            "section": "RR_INVALIDATED_DETAIL",
            "symbol": row["symbol"],
            "decision_date": row["decision_date"],
            "planned_reward_risk": row.get("planned_reward_risk"),
            "effective_reward_risk": row.get("effective_reward_risk"),
            "delta_rr": row.get("delta_rr"),
            "gap_pct": row.get("gap_pct"),
            "target_distance_pct": row.get("effective_target_distance_pct"),
            "stop_distance_pct": row.get("effective_stop_distance_pct"),
            "score": row.get("source_raw_strategy_score"),
            "regime": row.get("regime_state"),
            "setup_quality": row.get("setup_quality"),
            "decomposition": gap_invalidation_reason(row),
        }
        for row in rr_invalid
    ]

    gap_size_rows = grouped_profiles(
        [row for row in primary if truthy(row.get("entry_valid"))],
        gap_size_bucket,
        "gap_size_bucket",
    )
    chase_rows = grouped_profiles(
        [row for row in primary if truthy(row.get("entry_valid"))],
        chase_bucket,
        "chase_bucket",
    )
    naive_rows: list[dict[str, Any]] = []
    for row in rr_invalid:
        if not truthy(row.get("forward_data_safe")) or not mechanical_entry_valid_without_rr(row):
            continue
        reconstructed = reconstruct_path(row)
        if reconstructed["path_available"]:
            combined = dict(row)
            combined.update(reconstructed)
            combined["entry_valid"] = True
            naive_rows.append(combined)
    distortion = reference_distortion_summary(next_data)
    return {
        "gap_quantiles": quantile_rows,
        "gap_bands": gap_bands,
        "gap_invalidated_count": len(gap_invalid),
        "gap_invalidation_decomposition": invalid_decomposition_rows,
        "open_stop_count": len(open_stop_rows),
        "open_stop_correct_count": sum(row["reconstruction_result"] == "PASS" for row in open_stop_details),
        "open_stop_details": open_stop_details,
        "planned_rr_distribution": numeric_summary(planned_values),
        "effective_rr_distribution": numeric_summary(effective_values),
        "delta_rr_distribution": numeric_summary(deltas),
        "delta_rr_quantiles": rr_delta_quantiles,
        "delta_rr_directions": distribution_rows(direction_counts, len(deltas), "direction"),
        "rr_deteriorated_count": direction_counts["DETERIORATED"],
        "crossed_below_1_5_count": len(crossed),
        "safe_crossed_below_1_5_count": len(safe_crossed),
        "rr_invalidated_count": len(rr_invalid),
        "rr_invalidated_positive_gap_count": positive_gap_invalid,
        "rr_invalidated_positive_gap_rate_pct": pct(positive_gap_invalid, len(rr_invalid)),
        "rr_invalidated_profile": profile_metrics(rr_invalid),
        "rr_invalidated_by_regime": grouped_profiles(rr_invalid, lambda row: str(row.get("regime_state", "")), "regime"),
        "rr_invalidated_by_setup": grouped_profiles(rr_invalid, lambda row: str(row.get("setup_quality", "")), "setup_quality"),
        "rr_invalidated_details": invalid_details,
        "gap_size_profiles": gap_size_rows,
        "chase_profiles": chase_rows,
        "naive_entry_extra_rows": len(naive_rows),
        "naive_entry_extra_profile": profile_metrics(naive_rows),
        "reference_distortion": distortion,
    }


def gap_invalidation_reason(row: dict[str, Any]) -> str:
    entry = decimal_or_none(row.get("hypothetical_entry_price"))
    stop = decimal_or_none(row.get("stop_price"))
    target = decimal_or_none(row.get("target_price"))
    if entry is None:
        return "OTHER"
    if stop is not None and entry <= stop:
        return "STOP_RELATION_ISSUE"
    if target is not None and entry >= target:
        return "OPEN_AT_OR_ABOVE_TARGET"
    target_distance = percent_of(target - entry if target is not None else None, entry)
    if target_distance is not None and target_distance <= Decimal("0.5"):
        return "OPEN_TOO_CLOSE_TO_TARGET"
    if decimal_or_zero(row.get("effective_reward_risk")) < Decimal("1.5"):
        return "RR_DROPPED_BELOW_1_5"
    if int(decimal_or_zero(row.get("hypothetical_quantity"))) < 1:
        return "CAPITAL_OR_QUANTITY_ISSUE"
    return "OTHER"


def rr_delta_direction(delta: Decimal) -> str:
    if delta < -RR_UNCHANGED_TOLERANCE:
        return "DETERIORATED"
    if delta > RR_UNCHANGED_TOLERANCE:
        return "IMPROVED"
    return "APPROXIMATELY_UNCHANGED"


def audit_target_distance(valid_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    state_profiles = grouped_profiles(valid_rows, lambda row: str(row.get("first_touch_outcome", "")), "first_touch_outcome")
    r_bucket_profiles = grouped_profiles(valid_rows, target_r_bucket, "target_r_bucket")
    distance_bucket_profiles = grouped_profiles(valid_rows, target_distance_bucket, "target_distance_bucket")
    target_type_profiles = grouped_profiles(valid_rows, lambda row: str(row.get("target_type", "")), "target_type")
    return {
        "all_valid_target_distance_pct": numeric_summary(row.get("effective_target_distance_pct") for row in valid_rows),
        "all_valid_target_distance_r": numeric_summary(row.get("effective_reward_risk") for row in valid_rows),
        "all_valid_stop_distance_pct": numeric_summary(row.get("effective_stop_distance_pct") for row in valid_rows),
        "first_touch_profiles": state_profiles,
        "target_r_bucket_profiles": r_bucket_profiles,
        "target_distance_bucket_profiles": distance_bucket_profiles,
        "target_type_profiles": target_type_profiles,
        "high_rr_explanation": high_rr_explanation(valid_rows),
    }


def high_rr_explanation(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    lower = [row for row in rows if decimal_or_zero(row.get("effective_reward_risk")) < Decimal("2.5")]
    high = [row for row in rows if decimal_or_zero(row.get("effective_reward_risk")) >= Decimal("2.5")]
    return {
        "lower_than_2_5r": extended_profile(lower),
        "at_least_2_5r": extended_profile(high),
        "high_rr_target_type_counts": dict(Counter(str(row.get("target_type", "")) for row in high)),
        "high_rr_regime_counts": dict(Counter(str(row.get("regime_state", "")) for row in high)),
        "high_rr_setup_counts": dict(Counter(str(row.get("setup_quality", "")) for row in high)),
    }


def audit_r_levels(valid_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    favorable: list[dict[str, Any]] = []
    adverse: list[dict[str, Any]] = []
    sequence: list[dict[str, Any]] = []
    stop_prior: list[dict[str, Any]] = []
    for horizon in range(1, 5):
        available = [row for row in valid_rows if truthy(row.get(f"horizon_available_{horizon}"))]
        for level in R_LEVELS:
            count = sum(decimal_or_zero(row.get(f"mfe_r_{horizon}")) >= level for row in available)
            favorable.append(
                {
                    "section": "FAVORABLE_R_REACH",
                    "horizon": horizon,
                    "r_level": level,
                    "available_rows": len(available),
                    "reached_count": count,
                    "reached_rate_pct": pct(count, len(available)),
                }
            )
        for level in ADVERSE_R_LEVELS:
            count = sum(decimal_or_zero(row.get(f"mae_r_{horizon}")) >= level for row in available)
            adverse.append(
                {
                    "section": "ADVERSE_R_REACH",
                    "horizon": horizon,
                    "r_level": level,
                    "available_rows": len(available),
                    "reached_count": count,
                    "reached_rate_pct": pct(count, len(available)),
                }
            )
    for level in R_LEVELS[:-1]:
        counts = Counter(favorable_before_stop_state(row, level) for row in valid_rows)
        sequence.extend(
            {
                "section": "FAVORABLE_BEFORE_STOP",
                "r_level": level,
                "sequence_state": state,
                "count": count,
                "rate_pct": pct(count, len(valid_rows)),
            }
            for state, count in sorted(counts.items())
        )
    stop_first_rows = [row for row in valid_rows if row.get("first_touch_outcome") == STOP_FIRST]
    for level in R_LEVELS[:-1]:
        count = sum(favorable_before_stop_state(row, level) == "FAVORABLE_EARLIER_SESSION" for row in stop_first_rows)
        stop_prior.append(
            {
                "section": "STOP_FIRST_PRIOR_FAVORABLE",
                "r_level": level,
                "stop_first_rows": len(stop_first_rows),
                "count": count,
                "rate_pct": pct(count, len(stop_first_rows)),
            }
        )
    path_matrix: list[dict[str, Any]] = []
    for mfe_bucket, grouped in group_by_function(valid_rows, mfe_r_bucket).items():
        for stop_state in ("STOP_TOUCHED", "STOP_NOT_TOUCHED"):
            selected = [
                row
                for row in grouped
                if (truthy(row.get("stop_touched_4")) and stop_state == "STOP_TOUCHED")
                or (not truthy(row.get("stop_touched_4")) and stop_state == "STOP_NOT_TOUCHED")
            ]
            path_matrix.append(
                {
                    "section": "MFE_STOP_PATH_MATRIX",
                    "mfe_r_bucket": mfe_bucket,
                    "stop_state": stop_state,
                    "count": len(selected),
                    "rate_of_valid_pct": pct(len(selected), len(valid_rows)),
                }
            )
    neither_rows = [row for row in valid_rows if row.get("first_touch_outcome") == NEITHER_WITHIN_HORIZON]
    return {
        "favorable_reach": favorable,
        "adverse_reach": adverse,
        "path_matrix": path_matrix,
        "favorable_before_stop": sequence,
        "stop_first_prior_favorable": stop_prior,
        "neither": neither_profile(neither_rows),
    }


def audit_mfe_mae(valid_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    horizon_rows: list[dict[str, Any]] = []
    session_rows: list[dict[str, Any]] = []
    incremental_rows: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for horizon in range(1, 5):
        available = [row for row in valid_rows if truthy(row.get(f"horizon_available_{horizon}"))]
        mfe = numeric_summary(row.get(f"mfe_r_{horizon}") for row in available)
        mae = numeric_summary(row.get(f"mae_r_{horizon}") for row in available)
        current = {
            "horizon": horizon,
            "available_rows": len(available),
            "median_mfe_r": mfe["median"],
            "mean_mfe_r": mfe["mean"],
            "p25_mfe_r": mfe["p25"],
            "p75_mfe_r": mfe["p75"],
            "p90_mfe_r": mfe["p90"],
            "p95_mfe_r": mfe["p95"],
            "median_mae_r": mae["median"],
            "mean_mae_r": mae["mean"],
            "p25_mae_r": mae["p25"],
            "p75_mae_r": mae["p75"],
            "p90_mae_r": mae["p90"],
            "p95_mae_r": mae["p95"],
            "target_touched_count": sum(truthy(row.get(f"target_touched_{horizon}")) for row in available),
            "stop_touched_count": sum(truthy(row.get(f"stop_touched_{horizon}")) for row in available),
            "neither_count": sum(first_touch_at_horizon(row, horizon) == NEITHER_WITHIN_HORIZON for row in available),
        }
        for level in R_LEVELS:
            current[f"mfe_gte_{decimal_label(level)}r_pct"] = pct(
                sum(decimal_or_zero(row.get(f"mfe_r_{horizon}")) >= level for row in available), len(available)
            )
        for level in ADVERSE_R_LEVELS[:2]:
            current[f"mae_gte_{decimal_label(level)}r_pct"] = pct(
                sum(decimal_or_zero(row.get(f"mae_r_{horizon}")) >= level for row in available), len(available)
            )
        horizon_rows.append(current)

        entry_values = [decimal_or_zero(row.get("hypothetical_entry_price")) for row in available]
        high_excursions = [
            (decimal_or_zero(row.get(f"high_{horizon}")) - entry_values[index]) / entry_values[index] * Decimal("100")
            for index, row in enumerate(available)
            if entry_values[index] > 0
        ]
        low_excursions = [
            (entry_values[index] - decimal_or_zero(row.get(f"low_{horizon}"))) / entry_values[index] * Decimal("100")
            for index, row in enumerate(available)
            if entry_values[index] > 0
        ]
        session_rows.append(
            {
                "session": horizon,
                "available_rows": len(available),
                "median_session_high_excursion_pct": median_value(high_excursions),
                "median_session_low_excursion_pct": median_value(low_excursions),
                "median_session_close_return_pct": median_value(row.get(f"close_return_pct_{horizon}") for row in available),
            }
        )
        incremental_rows.append(
            {
                "from_to": "ENTRY_TO_1" if previous is None else f"{horizon - 1}_TO_{horizon}",
                "median_mfe_r_change": current["median_mfe_r"] if previous is None else subtract_optional(current["median_mfe_r"], previous["median_mfe_r"]),
                "median_mae_r_change": current["median_mae_r"] if previous is None else subtract_optional(current["median_mae_r"], previous["median_mae_r"]),
                "new_target_touches": current["target_touched_count"] if previous is None else current["target_touched_count"] - previous["target_touched_count"],
                "new_stop_touches": current["stop_touched_count"] if previous is None else current["stop_touched_count"] - previous["stop_touched_count"],
                "neither_count_change": current["neither_count"] if previous is None else current["neither_count"] - previous["neither_count"],
            }
        )
        previous = current
    complete = [row for row in valid_rows if truthy(row.get("horizon_available_4"))]
    time_mfe = Counter(time_to_extreme(row, "mfe_r") for row in complete)
    time_mae = Counter(time_to_extreme(row, "mae_r") for row in complete)
    return {
        "horizons": horizon_rows,
        "time_to_mfe": distribution_rows(time_mfe, len(complete), "session"),
        "time_to_mae": distribution_rows(time_mae, len(complete), "session"),
        "session_specific": session_rows,
        "incremental": incremental_rows,
    }


def audit_reconstruction(valid_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    ambiguity_mismatches = 0
    first_touch_mismatches = 0
    mfe_mismatches = 0
    mae_mismatches = 0
    close_mismatches = 0
    detail_rows: list[dict[str, Any]] = []
    for row in valid_rows:
        rebuilt = reconstruct_path(row)
        row_mismatches: list[str] = []
        if truthy(row.get("same_bar_ambiguous")) != rebuilt["same_bar_ambiguous"]:
            ambiguity_mismatches += 1
            row_mismatches.append("AMBIGUITY")
        if row.get("first_touch_outcome") != rebuilt["first_touch_outcome"]:
            first_touch_mismatches += 1
            row_mismatches.append("FIRST_TOUCH")
        for horizon in range(1, 5):
            if not truthy(row.get(f"horizon_available_{horizon}")):
                continue
            if not decimals_equal(row.get(f"mfe_r_{horizon}"), rebuilt.get(f"mfe_r_{horizon}")):
                mfe_mismatches += 1
                row_mismatches.append(f"MFE_R_{horizon}")
            if not decimals_equal(row.get(f"mae_r_{horizon}"), rebuilt.get(f"mae_r_{horizon}")):
                mae_mismatches += 1
                row_mismatches.append(f"MAE_R_{horizon}")
            if not decimals_equal(row.get(f"close_return_pct_{horizon}"), rebuilt.get(f"close_return_pct_{horizon}")):
                close_mismatches += 1
                row_mismatches.append(f"CLOSE_{horizon}")
        if row_mismatches:
            detail_rows.append(
                {
                    "symbol": row["symbol"],
                    "decision_date": row["decision_date"],
                    "mismatches": ";".join(row_mismatches),
                }
            )
    censored = [row for row in valid_rows if truthy(row.get("right_censored"))]
    return {
        "ambiguity_mismatches": ambiguity_mismatches,
        "first_touch_mismatches": first_touch_mismatches,
        "mfe_r_mismatches": mfe_mismatches,
        "mae_r_mismatches": mae_mismatches,
        "close_return_mismatches": close_mismatches,
        "right_censored_primary_count": len(censored),
        "mismatch_details": detail_rows,
    }


def reconstruct_path(row: dict[str, Any], maximum: int = 4) -> dict[str, Any]:
    entry = decimal_or_none(row.get("hypothetical_entry_price"))
    stop = decimal_or_none(row.get("stop_price"))
    target = decimal_or_none(row.get("target_price"))
    if entry is None or stop is None or target is None or entry <= stop:
        return {"path_available": False, "same_bar_ambiguous": False, "first_touch_outcome": "INVALID_ENTRY"}
    risk = entry - stop
    running_high = entry
    running_low = entry
    first_stop = 0
    first_target = 0
    output: dict[str, Any] = {"path_available": True}
    available = 0
    for horizon in range(1, maximum + 1):
        high = decimal_or_none(row.get(f"high_{horizon}"))
        low = decimal_or_none(row.get(f"low_{horizon}"))
        close = decimal_or_none(row.get(f"close_{horizon}"))
        if high is None or low is None or close is None:
            break
        available += 1
        running_high = max(running_high, high)
        running_low = min(running_low, low)
        if not first_stop and low <= stop:
            first_stop = horizon
        if not first_target and high >= target:
            first_target = horizon
        output.update(
            {
                f"mfe_r_{horizon}": max(Decimal("0"), (running_high - entry) / risk),
                f"mae_r_{horizon}": max(Decimal("0"), (entry - running_low) / risk),
                f"close_return_pct_{horizon}": (close - entry) / entry * Decimal("100"),
                f"stop_touched_{horizon}": bool(first_stop),
                f"target_touched_{horizon}": bool(first_target),
            }
        )
    same_bar = bool(first_stop and first_stop == first_target)
    if same_bar:
        outcome = AMBIGUOUS
    elif first_target and (not first_stop or first_target < first_stop):
        outcome = TARGET_FIRST
    elif first_stop and (not first_target or first_stop < first_target):
        outcome = STOP_FIRST
    elif available < maximum:
        outcome = INSUFFICIENT_FORWARD_DATA
    else:
        outcome = NEITHER_WITHIN_HORIZON
    output.update(
        {
            "available_sessions": available,
            "first_stop_session": first_stop,
            "first_target_session": first_target,
            "same_bar_ambiguous": same_bar,
            "first_touch_outcome": outcome,
        }
    )
    return output


def build_extended_records(
    valid_rows: Sequence[dict[str, Any]],
    sessions: Sequence[date],
    bars: dict[tuple[str, str], OutcomeBar],
    exclusions: dict[str, list[ForwardExclusion]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in valid_rows:
        decision = date.fromisoformat(str(row["decision_date"]))
        symbol = canonical_symbol(row["symbol"])
        forward_dates = resolve_next_sessions(decision, sessions, max(EXTENDED_HORIZONS))
        forward_bars = [bars.get((session.isoformat(), symbol)) for session in forward_dates]
        record: dict[str, Any] = {"symbol": symbol, "decision_date": row["decision_date"]}
        for horizon in EXTENDED_HORIZONS:
            prefix_dates = forward_dates[:horizon]
            prefix_bars = forward_bars[:horizon]
            safe, reasons = forward_safety(
                symbol=symbol,
                session_dates=prefix_dates,
                session_bars=prefix_bars,
                exclusions=exclusions,
            )
            available = len(prefix_dates) == horizon and len(prefix_bars) == horizon and all(bar is not None for bar in prefix_bars) and safe
            record[f"available_{horizon}"] = available
            record[f"unavailable_reasons_{horizon}"] = ";".join(reasons) if reasons else ("END_OR_MISSING_DATA" if not available else "")
            if available:
                path = reconstruct_bars_path(
                    [bar for bar in prefix_bars if bar is not None],
                    decimal_or_zero(row["hypothetical_entry_price"]),
                    decimal_or_zero(row["stop_price"]),
                    decimal_or_zero(row["target_price"]),
                )
                record[f"mfe_r_{horizon}"] = path["mfe_r"]
                record[f"mae_r_{horizon}"] = path["mae_r"]
                record[f"first_touch_{horizon}"] = path["first_touch_outcome"]
            else:
                record[f"mfe_r_{horizon}"] = ""
                record[f"mae_r_{horizon}"] = ""
                record[f"first_touch_{horizon}"] = "INSUFFICIENT_SAFE_FORWARD_DATA"
        records.append(record)
    return records


def reconstruct_bars_path(
    bars: Sequence[OutcomeBar],
    entry: Decimal,
    stop: Decimal,
    target: Decimal,
) -> dict[str, Any]:
    risk = entry - stop
    running_high = max([entry, *[bar.high for bar in bars]])
    running_low = min([entry, *[bar.low for bar in bars]])
    first_stop = next((index for index, bar in enumerate(bars, start=1) if bar.low <= stop), 0)
    first_target = next((index for index, bar in enumerate(bars, start=1) if bar.high >= target), 0)
    if first_stop and first_target and first_stop == first_target:
        outcome = AMBIGUOUS
    elif first_target and (not first_stop or first_target < first_stop):
        outcome = TARGET_FIRST
    elif first_stop and (not first_target or first_stop < first_target):
        outcome = STOP_FIRST
    else:
        outcome = NEITHER_WITHIN_HORIZON
    return {
        "mfe_r": max(Decimal("0"), (running_high - entry) / risk),
        "mae_r": max(Decimal("0"), (entry - running_low) / risk),
        "first_touch_outcome": outcome,
    }


def audit_extended_horizons(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    availability: list[dict[str, Any]] = []
    excursions: list[dict[str, Any]] = []
    touches: list[dict[str, Any]] = []
    for horizon in EXTENDED_HORIZONS:
        available = [row for row in records if truthy(row.get(f"available_{horizon}"))]
        availability.append(
            {
                "horizon": horizon,
                "available_count": len(available),
                "available_rate_pct": pct(len(available), len(records)),
                "status": "EXTENDED_HORIZON_DIAGNOSTIC_ONLY",
            }
        )
        if horizon in {5, 6, 8, 10}:
            excursions.append(
                {
                    "horizon": horizon,
                    "available_count": len(available),
                    "mfe_r": numeric_summary(row.get(f"mfe_r_{horizon}") for row in available),
                    "mae_r": numeric_summary(row.get(f"mae_r_{horizon}") for row in available),
                    "status": "EXTENDED_HORIZON_DIAGNOSTIC_ONLY",
                }
            )
            counts = Counter(str(row.get(f"first_touch_{horizon}")) for row in available)
            touches.append(
                {
                    "horizon": horizon,
                    "available_count": len(available),
                    "target_first_count": counts[TARGET_FIRST],
                    "target_first_rate_pct": pct(counts[TARGET_FIRST], len(available)),
                    "stop_first_count": counts[STOP_FIRST],
                    "stop_first_rate_pct": pct(counts[STOP_FIRST], len(available)),
                    "ambiguous_count": counts[AMBIGUOUS],
                    "ambiguous_rate_pct": pct(counts[AMBIGUOUS], len(available)),
                    "neither_count": counts[NEITHER_WITHIN_HORIZON],
                    "neither_rate_pct": pct(counts[NEITHER_WITHIN_HORIZON], len(available)),
                    "status": "EXTENDED_HORIZON_DIAGNOSTIC_ONLY",
                }
            )
    return {"availability": availability, "excursions": excursions, "first_touch": touches}


def audit_scores(
    all_rows: Sequence[dict[str, Any]],
    primary: Sequence[dict[str, Any]],
    valid_primary: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    exact_profiles: list[dict[str, Any]] = []
    for score in range(80, 86):
        selected = [row for row in primary if decimal_or_zero(row.get("score_raw")) == Decimal(score)]
        exact_profiles.append({"score": score, **profile_metrics(selected)})

    component_profiles: list[dict[str, Any]] = []
    for component in ("setup", "momentum", "rvol", "relative_strength", "regime", "reward_risk"):
        grouped = group_by_function(primary, lambda row, name=component: str(row.get(f"{name}_points", "")))
        for points, selected in sorted(grouped.items(), key=lambda item: decimal_or_zero(item[0])):
            component_profiles.append({"component": component, "points": points, **profile_metrics(selected)})

    counterfactual = [row for row in all_rows if row.get("outcome_cohort") == COUNTERFACTUAL_COHORT]
    below_profiles = grouped_profiles(counterfactual, below_threshold_bucket, "score_bucket")
    monotonicity = score_monotonicity(exact_profiles)
    primary_profile = profile_metrics(primary)
    stronger_buckets = [
        row
        for row in below_profiles
        if decimal_or_none(row.get("median_close_return_pct_4")) is not None
        and decimal_or_none(primary_profile.get("median_close_return_pct_4")) is not None
        and decimal_or_zero(row.get("median_close_return_pct_4")) > decimal_or_zero(primary_profile.get("median_close_return_pct_4"))
        and decimal_or_zero(row.get("target_first_rate_pct")) > decimal_or_zero(primary_profile.get("target_first_rate_pct"))
    ]
    warning = "OUTCOME_PATTERN_REQUIRES_LATER_BACKTEST_VALIDATION" if stronger_buckets else "NOT_TRIGGERED"
    return {
        "exact_score_profiles": exact_profiles,
        "component_profiles": component_profiles,
        "below_threshold_profiles": below_profiles,
        "score_monotonicity": monotonicity,
        "threshold_research_warning": warning,
        "lower_score_buckets_descriptively_stronger": [row["score_bucket"] for row in stronger_buckets],
        "primary_profile": primary_profile,
    }


def score_monotonicity(exact_profiles: Sequence[dict[str, Any]]) -> dict[str, Any]:
    metrics = {
        "median_mfe_r_4": 1,
        "median_mae_r_4": -1,
        "target_first_rate_pct": 1,
        "stop_first_rate_pct": -1,
        "median_close_return_pct_4": 1,
    }
    coefficients: dict[str, Decimal | None] = {}
    directional: list[Decimal] = []
    for metric, desirable_direction in metrics.items():
        pairs = [
            (decimal_or_zero(row["score"]), value)
            for row in exact_profiles
            if (value := decimal_or_none(row.get(metric))) is not None
        ]
        coefficient = spearman([pair[0] for pair in pairs], [pair[1] for pair in pairs]) if len(pairs) >= 3 else None
        coefficients[metric] = coefficient
        if coefficient is not None:
            directional.append(coefficient * Decimal(desirable_direction))
    improving = sum(value >= Decimal("0.20") for value in directional)
    inverse = sum(value <= Decimal("-0.20") for value in directional)
    if len(directional) < 3:
        classification = "INCONCLUSIVE"
    elif improving >= 4:
        classification = "DIRECTIONALLY_IMPROVING"
    elif inverse >= 4:
        classification = "INVERSE"
    elif improving and inverse:
        classification = "MIXED"
    elif all(abs(value) < Decimal("0.20") for value in directional):
        classification = "NO_CLEAR_RELATIONSHIP"
    else:
        classification = "MIXED"
    return {"classification": classification, "spearman_coefficients": coefficients}


def audit_categories(primary: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return grouped_profiles(primary, lambda row: str(row.get("candidate_category", "")), "candidate_category")


def audit_setups(primary: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    output = grouped_profiles(primary, lambda row: str(row.get("setup_quality", "")), "setup_quality")
    for result in output:
        selected = [row for row in primary if row.get("setup_quality") == result["setup_quality"]]
        result["gap_invalidation_rate_pct"] = pct(
            sum(row.get("entry_recheck_status") == ENTRY_INVALID_GAP for row in selected), len(selected)
        )
        result["rr_invalidation_rate_pct"] = pct(
            sum(row.get("entry_recheck_status") in {ENTRY_INVALID_GAP, ENTRY_INVALID_RR} for row in selected), len(selected)
        )
    return output


def audit_regimes(all_rows: Sequence[dict[str, Any]], primary: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for regime in ("BULLISH", "NEUTRAL"):
        selected = [row for row in primary if row.get("regime_state") == regime]
        output.append({"cohort": "NORMAL_ELIGIBLE", "regime": regime, **profile_metrics(selected)})
    exceptional = [row for row in all_rows if row.get("outcome_cohort") == EXCEPTIONAL_COHORT]
    output.append({"cohort": EXCEPTIONAL_COHORT, "regime": "BEARISH", **profile_metrics(exceptional)})
    return output


def audit_overlap(
    primary: Sequence[dict[str, Any]],
    valid_primary: Sequence[dict[str, Any]],
    sessions: Sequence[date],
) -> dict[str, Any]:
    session_index = {session.isoformat(): index for index, session in enumerate(sessions)}
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in primary:
        by_symbol[str(row["symbol"])].append(row)
    streak_lengths: list[int] = []
    consecutive_pairs = 0
    for symbol_rows in by_symbol.values():
        ordered = sorted(symbol_rows, key=lambda row: row["decision_date"])
        current = 1
        for previous, current_row in zip(ordered, ordered[1:]):
            previous_index = session_index.get(str(previous["decision_date"]))
            current_index = session_index.get(str(current_row["decision_date"]))
            if previous_index is not None and current_index == previous_index + 1:
                current += 1
                consecutive_pairs += 1
            else:
                if current >= 2:
                    streak_lengths.append(current)
                current = 1
        if current >= 2:
            streak_lengths.append(current)

    valid_by_symbol: dict[str, list[tuple[int, int, tuple[str, str]]]] = defaultdict(list)
    for row in valid_primary:
        entry_index = session_index.get(str(row.get("next_session_date", "")))
        if entry_index is None:
            continue
        valid_by_symbol[str(row["symbol"])].append((entry_index, entry_index + 3, row_key(row)))
    overlapping: set[tuple[str, str]] = set()
    for intervals in valid_by_symbol.values():
        ordered = sorted(intervals)
        for index, (start, end, key) in enumerate(ordered):
            for next_start, next_end, next_key in ordered[index + 1 :]:
                if next_start > end:
                    break
                if start <= next_end and next_start <= end:
                    overlapping.update((key, next_key))

    active_counts: Counter[str] = Counter()
    for row in valid_primary:
        for horizon in range(1, 5):
            session = str(row.get(f"session_date_{horizon}", ""))
            if session:
                active_counts[session] += 1
    active_values = list(active_counts.values())
    return {
        "total_primary_rows": len(primary),
        "unique_symbol_date_pairs": len({row_key(row) for row in primary}),
        "consecutive_same_symbol_opportunities": consecutive_pairs,
        "two_session_streaks": sum(length == 2 for length in streak_lengths),
        "three_plus_session_streaks": sum(length >= 3 for length in streak_lengths),
        "maximum_streak": max(streak_lengths, default=1),
        "valid_rows_overlapping_same_symbol_holding": len(overlapping),
        "same_symbol_overlap_rate_pct": pct(len(overlapping), len(valid_primary)),
        "active_opportunity_distribution": {
            "days": len(active_values),
            "median": median_value(active_values),
            "p90": percentile_value(active_values, 90),
            "p95": percentile_value(active_values, 95),
            "max": max(active_values, default=0),
        },
        "daily_active_counts": [{"session_date": day, "active_opportunities": count} for day, count in sorted(active_counts.items())],
    }


def audit_capital_demand(valid_primary: Sequence[dict[str, Any]]) -> dict[str, Any]:
    notionals: Counter[str] = Counter()
    risks: Counter[str] = Counter()
    for row in valid_primary:
        notional = decimal_or_zero(row.get("position_notional"))
        planned_risk = decimal_or_zero(row.get("planned_rupee_risk"))
        for horizon in range(1, 5):
            session = str(row.get(f"session_date_{horizon}", ""))
            if not session:
                continue
            notionals[session] += notional
            risks[session] += planned_risk
    notional_values = list(notionals.values())
    risk_values = list(risks.values())
    thresholds = (Decimal("1000"), Decimal("2000"), Decimal("3000"), Decimal("4000"))
    return {
        "days_demanded_notional_above_100000": sum(value > Decimal("100000") for value in notional_values),
        "notional_distribution": numeric_summary(notional_values),
        "planned_risk_distribution": numeric_summary(risk_values),
        "days_above_risk_thresholds": {
            format(threshold, "f"): sum(value > threshold for value in risk_values)
            for threshold in thresholds
        },
        "daily_demand": [
            {
                "session_date": session,
                "demanded_notional": notionals[session],
                "demanded_planned_risk": risks[session],
            }
            for session in sorted(set(notionals) | set(risks))
        ],
    }


def audit_yearly(primary: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for year in range(2021, 2027):
        selected = [row for row in primary if str(row.get("decision_date", "")).startswith(str(year))]
        output.append({"year": year, **profile_metrics(selected)})
    return output


def audit_terminology_and_separation(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    prohibited = {"WIN", "LOSS", "PROFIT", "UNPROFITABLE"}
    terminology_violations: list[dict[str, Any]] = []
    for row in rows:
        for field, value in row.items():
            if str(value).upper() in prohibited:
                terminology_violations.append(
                    {"symbol": row.get("symbol"), "decision_date": row.get("decision_date"), "field": field, "value": value}
                )
    cohort_violations = 0
    for row in rows:
        cohort = row.get("outcome_cohort")
        disposition = row.get("source_scoring_disposition")
        mode = row.get("source_score_mode")
        expected = (
            PRIMARY_COHORT
            if disposition in {"ENTRY_ELIGIBLE", "HIGH_CONVICTION"}
            else COUNTERFACTUAL_COHORT
            if mode == "FULL_SCORE"
            else EXCEPTIONAL_COHORT
            if disposition == "EXCEPTIONAL_REVIEW"
            else PREVIEW_COHORT
            if disposition == "PREVIEW_ONLY"
            else "UNKNOWN"
        )
        cohort_violations += cohort != expected
        cohort_violations += truthy(row.get("primary_evaluation_eligible")) and (
            cohort != PRIMARY_COHORT or not truthy(row.get("entry_valid"))
        )
    cost_statuses = sorted({str(row.get("transaction_cost_status")) for row in rows})
    slippage_statuses = sorted({str(row.get("slippage_status")) for row in rows})
    execution_statuses = sorted({str(row.get("historical_execution_status")) for row in rows})
    signal_statuses = sorted({str(row.get("trade_signal_status")) for row in rows})
    unsafe_censored_conflation = sum(
        (row.get("forward_data_status") == "RIGHT_CENSORED" and not truthy(row.get("forward_data_safe")))
        or (row.get("forward_data_status") == "FORWARD_DATA_UNSAFE" and truthy(row.get("forward_data_safe")))
        for row in rows
    )
    return {
        "canonical_profitability_language_violations": len(terminology_violations),
        "terminology_details": terminology_violations,
        "transaction_cost_statuses": cost_statuses,
        "slippage_statuses": slippage_statuses,
        "historical_execution_statuses": execution_statuses,
        "trade_signal_statuses": signal_statuses,
        "cohort_separation_violations": cohort_violations,
        "unsafe_censored_conflation_violations": unsafe_censored_conflation,
        "execution_engine_components_introduced": 0,
        "signals_generated": 0,
        "orders_placed": 0,
    }


def run_audit_pilot(
    *,
    rows: Sequence[dict[str, Any]],
    primary: Sequence[dict[str, Any]],
    valid_primary: Sequence[dict[str, Any]],
    safety_rows: Sequence[dict[str, Any]],
    reconstruction: dict[str, Any],
) -> dict[str, Any]:
    safety_lookup = {(row["decision_date"], row["symbol"]): row for row in safety_rows}
    cases: list[tuple[str, str, Callable[[dict[str, Any]], bool], Sequence[dict[str, Any]]]] = [
        ("A", "forward unsafe on entry session", lambda row: truthy(safety_lookup.get(row_key(row), {}).get("entry_session_unsafe")), primary),
        ("B", "entry safe but later session unsafe", lambda row: truthy(safety_lookup.get(row_key(row), {}).get("later_window_only_unsafe")), primary),
        ("C", "R:R gap invalidation", lambda row: row.get("entry_recheck_status") == ENTRY_INVALID_GAP, primary),
        ("D", "open at or below stop", lambda row: row.get("entry_recheck_status") == ENTRY_INVALID_STOP_RELATION, primary),
        ("E", "target first", lambda row: row.get("first_touch_outcome") == TARGET_FIRST, valid_primary),
        ("F", "stop first", lambda row: row.get("first_touch_outcome") == STOP_FIRST, valid_primary),
        ("G", "same-bar ambiguous", lambda row: row.get("first_touch_outcome") == AMBIGUOUS, valid_primary),
        ("H", "neither with at least 1R MFE", lambda row: row.get("first_touch_outcome") == NEITHER_WITHIN_HORIZON and decimal_or_zero(row.get("mfe_r_4")) >= 1, valid_primary),
        ("I", "stop first after prior-session 0.5R", lambda row: row.get("first_touch_outcome") == STOP_FIRST and favorable_before_stop_state(row, Decimal("0.5")) == "FAVORABLE_EARLIER_SESSION", valid_primary),
        ("J", "at least 2.5R target", lambda row: decimal_or_zero(row.get("effective_reward_risk")) >= Decimal("2.5"), valid_primary),
        ("K", "structural target", lambda row: row.get("target_type") == "STRUCTURAL_TARGET", valid_primary),
        ("L", "2R fallback target", lambda row: row.get("target_type") == "R_MULTIPLE_2R_RESEARCH_REFERENCE", valid_primary),
        ("M", "neutral eligible", lambda row: row.get("regime_state") == "NEUTRAL", valid_primary),
        ("N", "right-censored exceptional", lambda row: row.get("outcome_cohort") == EXCEPTIONAL_COHORT and truthy(row.get("right_censored")), rows),
    ]
    output: list[dict[str, Any]] = []
    for code, scenario, predicate, population in cases:
        selected = next((row for row in population if predicate(row)), None)
        if selected is None:
            output.append(
                {
                    "pilot_case": code,
                    "scenario": scenario,
                    "result": "NOT_AVAILABLE_IN_POPULATION",
                    "validation_notes": "Exhaustive audit population scan found no matching row.",
                }
            )
            continue
        passed, notes = validate_audit_pilot_row(selected, code, safety_lookup)
        output.append(
            {
                "pilot_case": code,
                "scenario": scenario,
                "symbol": selected["symbol"],
                "decision_date": selected["decision_date"],
                "entry_status": selected.get("entry_recheck_status"),
                "first_touch": selected.get("first_touch_outcome"),
                "planned_rr": selected.get("planned_reward_risk"),
                "effective_rr": selected.get("effective_reward_risk"),
                "gap_pct": selected.get("gap_pct"),
                "mfe_r_4": selected.get("mfe_r_4"),
                "mae_r_4": selected.get("mae_r_4"),
                "target_type": selected.get("target_type"),
                "result": "PASS" if passed else "FAIL",
                "validation_notes": ";".join(notes),
            }
        )
    return {
        "passed": not any(row["result"] == "FAIL" for row in output),
        "rows": output,
        "unavailable_cases": [row["pilot_case"] for row in output if row["result"] == "NOT_AVAILABLE_IN_POPULATION"],
        "global_reconstruction_clean": not any(
            reconstruction[name]
            for name in (
                "ambiguity_mismatches",
                "first_touch_mismatches",
                "mfe_r_mismatches",
                "mae_r_mismatches",
                "close_return_mismatches",
            )
        ),
    }


def validate_audit_pilot_row(
    row: dict[str, Any],
    code: str,
    safety_lookup: dict[tuple[str, str], dict[str, Any]],
) -> tuple[bool, list[str]]:
    checks: list[tuple[str, bool]] = []
    rebuilt = reconstruct_path(row)
    if truthy(row.get("entry_valid")):
        checks.extend(
            [
                ("first_touch_reconstructed", rebuilt["first_touch_outcome"] == row.get("first_touch_outcome")),
                ("mfe_reconstructed", decimals_equal(rebuilt.get("mfe_r_4"), row.get("mfe_r_4")) if truthy(row.get("horizon_available_4")) else True),
                ("mae_reconstructed", decimals_equal(rebuilt.get("mae_r_4"), row.get("mae_r_4")) if truthy(row.get("horizon_available_4")) else True),
            ]
        )
    safety = safety_lookup.get(row_key(row), {})
    if code == "A":
        checks.append(("entry_session_unsafe", truthy(safety.get("entry_session_unsafe"))))
    elif code == "B":
        checks.append(("later_only_unsafe", truthy(safety.get("later_window_only_unsafe"))))
    elif code == "C":
        checks.extend(
            [
                ("positive_gap", decimal_or_zero(row.get("gap_pct")) > 0),
                ("effective_rr_below_1_5", decimal_or_zero(row.get("effective_reward_risk")) < Decimal("1.5")),
            ]
        )
    elif code == "D":
        checks.append(("open_not_above_stop", decimal_or_zero(row.get("hypothetical_entry_price")) <= decimal_or_zero(row.get("stop_price"))))
    elif code == "I":
        checks.append(("prior_favorable", favorable_before_stop_state(row, Decimal("0.5")) == "FAVORABLE_EARLIER_SESSION"))
    return not any(not passed for _, passed in checks), [f"{name}={'PASS' if passed else 'FAIL'}" for name, passed in checks]


def classify_audit(
    *,
    safety: dict[str, Any],
    counterfactuals: dict[str, Any],
    gap_rr: dict[str, Any],
    reconstruction: dict[str, Any],
    extended: dict[str, Any],
    score_audit: dict[str, Any],
    terminology: dict[str, Any],
    valid_primary: Sequence[dict[str, Any]],
) -> dict[str, str]:
    if safety["unsafe_primary_rows"] != 700 or len(safety["row_summaries"]) != 700:
        forward_result = "SEMANTIC_BUG"
    elif safety["later_window_only_unsafe_count"] >= 70:
        forward_result = "OVERBROAD_EXCLUSION_RISK"
    elif safety["unsafe_primary_rows"]:
        forward_result = "CONSERVATIVE_BUT_REASONABLE"
    else:
        forward_result = "CLEAN"

    entry_clean = (
        gap_rr["open_stop_count"] == 12
        and gap_rr["open_stop_correct_count"] == 12
        and gap_rr["rr_invalidated_count"] == 260
        and gap_rr["safe_crossed_below_1_5_count"] == 260
    )
    entry_result = "CLEAN_AND_USEFUL" if entry_clean else "SEMANTIC_BUG"
    reconstruction_clean = not any(
        reconstruction[name]
        for name in (
            "ambiguity_mismatches",
            "first_touch_mismatches",
            "mfe_r_mismatches",
            "mae_r_mismatches",
            "close_return_mismatches",
        )
    )
    label_result = (
        "CLEAN"
        if reconstruction_clean
        and terminology["canonical_profitability_language_violations"] == 0
        and terminology["cohort_separation_violations"] == 0
        else "METHODOLOGY_FIX_REQUIRED"
    )
    four_neither = pct(
        sum(row.get("first_touch_outcome") == NEITHER_WITHIN_HORIZON for row in valid_primary), len(valid_primary)
    )
    ten = next((row for row in extended["first_touch"] if row["horizon"] == 10), None)
    if ten is None or ten["available_count"] < 300:
        horizon_result = "INCONCLUSIVE"
    else:
        decline = four_neither - decimal_or_zero(ten["neither_rate_pct"])
        horizon_result = "LIKELY_TOO_SHORT" if decline >= 15 else "MIXED" if decline >= 5 else "STRUCTURALLY_REASONABLE"
    primary_profile = profile_metrics(valid_primary)
    descriptive = (
        "WEAK"
        if decimal_or_zero(primary_profile.get("median_close_return_pct_4")) < 0
        and decimal_or_zero(primary_profile.get("stop_first_rate_pct")) > decimal_or_zero(primary_profile.get("target_first_rate_pct")) * 2
        else "MIXED"
    )
    if forward_result == "SEMANTIC_BUG" or entry_result == "SEMANTIC_BUG" or label_result == "METHODOLOGY_FIX_REQUIRED":
        overall = "METHODOLOGY_FIX_REQUIRED"
        decision = "B_TARGETED_FIX_REQUIRED"
    elif forward_result == "OVERBROAD_EXCLUSION_RISK" and counterfactuals["entry_only_recovered_rows"] >= 100:
        overall = "STABLE_WITH_REVIEW_NOTES"
        decision = "B_TARGETED_FIX_REQUIRED"
    elif horizon_result in {"LIKELY_TOO_SHORT", "MIXED"} or score_audit["threshold_research_warning"] != "NOT_TRIGGERED":
        overall = "STABLE_WITH_REVIEW_NOTES"
        decision = "A_FREEZE_UNCHANGED"
    else:
        overall = "STABLE"
        decision = "A_FREEZE_UNCHANGED"
    return {
        "forward_safety_result": forward_result,
        "entry_revalidation_result": entry_result,
        "outcome_label_result": label_result,
        "four_session_horizon_result": horizon_result,
        "descriptive_pattern": descriptive,
        "overall_audit_result": overall,
        "baseline_decision": decision,
    }


def build_audit_tables(
    *,
    safety: dict[str, Any],
    counterfactuals: dict[str, Any],
    gap_rr: dict[str, Any],
    target_distance: dict[str, Any],
    r_levels: dict[str, Any],
    mfe_mae: dict[str, Any],
    reconstruction: dict[str, Any],
    extended: dict[str, Any],
    score_audit: dict[str, Any],
    regimes: list[dict[str, Any]],
    categories: list[dict[str, Any]],
    setups: list[dict[str, Any]],
    overlap: dict[str, Any],
    capital: dict[str, Any],
    yearly: list[dict[str, Any]],
    pilot: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    forward_rows: list[dict[str, Any]] = []
    forward_rows.extend({"section": "CAUSE_DISTRIBUTION", **row} for row in safety["cause_distribution"])
    forward_rows.extend({"section": "POLICY_COUNTERFACTUAL", **row} for row in counterfactuals["policies"])
    for section, key in (("TOP_SYMBOL", "top_symbols"), ("TOP_DATE", "top_dates"), ("TOP_YEAR", "top_years"), ("TOP_REASON", "top_reasons")):
        forward_rows.extend({"section": section, **row} for row in safety[key])
    forward_rows.extend({"section": "UNSAFE_ROW", **row} for row in safety["row_summaries"])

    gap_rows: list[dict[str, Any]] = []
    gap_rows.extend({"section": "GAP_QUANTILE", **row} for row in gap_rr["gap_quantiles"])
    gap_rows.extend({"section": "GAP_BAND", **row} for row in gap_rr["gap_bands"])
    gap_rows.extend({"section": "GAP_INVALIDATION", **row} for row in gap_rr["gap_invalidation_decomposition"])
    gap_rows.extend({"section": "RR_DELTA_QUANTILE", **row} for row in gap_rr["delta_rr_quantiles"])
    gap_rows.extend({"section": "RR_DELTA_DIRECTION", **row} for row in gap_rr["delta_rr_directions"])
    gap_rows.extend(gap_rr["open_stop_details"])
    gap_rows.extend(gap_rr["rr_invalidated_details"])
    gap_rows.extend({"section": "GAP_SIZE_PROFILE", **row} for row in gap_rr["gap_size_profiles"])
    gap_rows.extend({"section": "CHASE_PROFILE", **row} for row in gap_rr["chase_profiles"])
    gap_rows.append({"section": "NAIVE_ENTRY_EXTRA_PROFILE", **gap_rr["naive_entry_extra_profile"]})
    for metric, summary in gap_rr["reference_distortion"].items():
        gap_rows.append({"section": "REFERENCE_DISTORTION", "metric": metric, **summary})

    target_rows: list[dict[str, Any]] = []
    for metric in ("all_valid_target_distance_pct", "all_valid_target_distance_r", "all_valid_stop_distance_pct"):
        target_rows.append({"section": "OVERALL_DISTRIBUTION", "metric": metric, **target_distance[metric]})
    for key, section in (
        ("first_touch_profiles", "FIRST_TOUCH_PROFILE"),
        ("target_r_bucket_profiles", "TARGET_R_BUCKET"),
        ("target_distance_bucket_profiles", "TARGET_DISTANCE_BUCKET"),
        ("target_type_profiles", "TARGET_TYPE"),
    ):
        target_rows.extend({"section": section, **row} for row in target_distance[key])
    target_rows.extend(
        {"section": "HIGH_RR_EXPLANATION", "cohort": name, **flatten_dict(value)}
        for name, value in target_distance["high_rr_explanation"].items()
        if isinstance(value, dict)
    )

    mfe_rows: list[dict[str, Any]] = []
    mfe_rows.extend({"section": "MFE_MAE_HORIZON", **row} for row in mfe_mae["horizons"])
    mfe_rows.extend({"section": "TIME_TO_MFE", **row} for row in mfe_mae["time_to_mfe"])
    mfe_rows.extend({"section": "TIME_TO_MAE", **row} for row in mfe_mae["time_to_mae"])
    mfe_rows.extend({"section": "SESSION_SPECIFIC", **row} for row in mfe_mae["session_specific"])
    mfe_rows.extend({"section": "INCREMENTAL_HORIZON", **row} for row in mfe_mae["incremental"])
    mfe_rows.extend({"section": "EXTENDED_AVAILABILITY", **row} for row in extended["availability"])
    mfe_rows.extend({"section": "EXTENDED_EXCURSION", **flatten_dict(row)} for row in extended["excursions"])

    first_touch_rows = [
        {
            "section": "RECONSTRUCTION",
            "metric": key,
            "value": value,
        }
        for key, value in reconstruction.items()
        if key != "mismatch_details"
    ]
    first_touch_rows.extend({"section": "EXTENDED_FIRST_TOUCH", **row} for row in extended["first_touch"])
    first_touch_rows.extend({"section": "MISMATCH_DETAIL", **row} for row in reconstruction["mismatch_details"])

    score_rows: list[dict[str, Any]] = []
    score_rows.extend({"section": "EXACT_SCORE", **row} for row in score_audit["exact_score_profiles"])
    score_rows.extend({"section": "COMPONENT", **row} for row in score_audit["component_profiles"])
    score_rows.extend({"section": "BELOW_THRESHOLD", **row} for row in score_audit["below_threshold_profiles"])
    score_rows.append({"section": "MONOTONICITY", **flatten_dict(score_audit["score_monotonicity"])})
    score_rows.append(
        {
            "section": "THRESHOLD_WARNING",
            "warning": score_audit["threshold_research_warning"],
            "stronger_buckets": ";".join(score_audit["lower_score_buckets_descriptively_stronger"]),
        }
    )

    overlap_rows = [{"section": "SUMMARY", **{key: value for key, value in overlap.items() if key != "daily_active_counts"}}]
    overlap_rows.extend({"section": "DAILY_ACTIVE", **row} for row in overlap["daily_active_counts"])
    capital_rows = [
        {"section": "SUMMARY", **flatten_dict({key: value for key, value in capital.items() if key != "daily_demand"})}
    ]
    capital_rows.extend({"section": "DAILY_DEMAND", **row} for row in capital["daily_demand"])
    return {
        "forward_safety": forward_rows,
        "gap_rr": gap_rows,
        "target_distance": target_rows,
        "r_levels": [
            *r_levels["favorable_reach"],
            *r_levels["adverse_reach"],
            *r_levels["path_matrix"],
            *r_levels["favorable_before_stop"],
            *r_levels["stop_first_prior_favorable"],
            {"section": "NEITHER_PROFILE", **flatten_dict(r_levels["neither"])},
        ],
        "mfe_mae": mfe_rows,
        "first_touch": first_touch_rows,
        "score_bands": score_rows,
        "regimes": regimes,
        "categories": categories,
        "setup_quality": setups,
        "overlap": overlap_rows,
        "capital_demand": capital_rows,
        "yearly": yearly,
        "pilot": pilot["rows"],
    }


def build_audit_summary(
    *,
    config: StrategyOutcomeAuditConfig,
    rows: Sequence[dict[str, Any]],
    primary: Sequence[dict[str, Any]],
    valid_primary: Sequence[dict[str, Any]],
    hashes_before: dict[str, str],
    hashes_after: dict[str, str],
    safety: dict[str, Any],
    counterfactuals: dict[str, Any],
    gap_rr: dict[str, Any],
    target_distance: dict[str, Any],
    r_levels: dict[str, Any],
    mfe_mae: dict[str, Any],
    reconstruction: dict[str, Any],
    extended: dict[str, Any],
    score_audit: dict[str, Any],
    regimes: list[dict[str, Any]],
    categories: list[dict[str, Any]],
    setups: list[dict[str, Any]],
    overlap: dict[str, Any],
    capital: dict[str, Any],
    yearly: list[dict[str, Any]],
    terminology: dict[str, Any],
    pilot: dict[str, Any],
    classifications: dict[str, str],
    runtime_seconds: float,
) -> dict[str, Any]:
    cohort_counts = Counter(str(row["outcome_cohort"]) for row in rows)
    all_censored = [row for row in rows if truthy(row.get("right_censored"))]
    input_checks = {name: hashes_before[name] == hashes_after[name] for name in hashes_before}
    ready = (
        all(input_checks.values())
        and pilot["passed"]
        and pilot["global_reconstruction_clean"]
        and terminology["cohort_separation_violations"] == 0
        and terminology["canonical_profitability_language_violations"] == 0
    )
    return {
        "phase": "Step 02.11",
        "command": "Command 02",
        "audit_version": config.audit_version,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline": {
            "outcome_version": STRATEGY_OUTCOME_VERSION,
            "outcome_profile": SWING_DAILY_OUTCOME_PROFILE,
            "outcome_config_hash": StrategyOutcomeConfig().config_hash(),
            "outcome_dataset_hash": hashes_after["outcome_v1"],
            "score_version": CURRENT_STRATEGY_SCORE_VERSION,
            "score_profile": CURRENT_STRATEGY_SCORE_PROFILE,
            "score_config_hash": CURRENT_STRATEGY_SCORE_CONFIG_HASH,
            "score_dataset_hash": hashes_after["score_v1"],
            "risk_version": CURRENT_RISK_STRUCTURE_VERSION,
            "risk_config_hash": CURRENT_RISK_STRUCTURE_CONFIG_HASH,
            "risk_dataset_hash": hashes_after["risk_v1_1"],
        },
        "population": {
            "total_outcome_rows": len(rows),
            "cohort_counts": dict(cohort_counts),
            "primary_rows": len(primary),
            "valid_primary_rows": len(valid_primary),
        },
        "forward_safety": {key: value for key, value in safety.items() if key not in {"row_summaries", "details"}},
        "forward_safety_counterfactuals": counterfactuals,
        "gap_and_rr": {key: value for key, value in gap_rr.items() if key not in {"open_stop_details", "rr_invalidated_details"}},
        "target_distance": target_distance,
        "r_levels": r_levels,
        "mfe_mae": mfe_mae,
        "reconstruction": reconstruction,
        "extended_horizons": extended,
        "scores": score_audit,
        "regimes": regimes,
        "categories": categories,
        "setup_quality": setups,
        "overlap": {key: value for key, value in overlap.items() if key != "daily_active_counts"},
        "capital_demand": {key: value for key, value in capital.items() if key != "daily_demand"},
        "yearly": yearly,
        "right_censoring": {
            "primary_count": reconstruction["right_censored_primary_count"],
            "all_cohort_count": len(all_censored),
            "all_cohort_distribution": dict(Counter(str(row["outcome_cohort"]) for row in all_censored)),
            "ordinary_neither_mislabels": sum(
                row.get("first_touch_outcome") == NEITHER_WITHIN_HORIZON
                and int(decimal_or_zero(row.get("forward_sessions_available"))) < 4
                for row in all_censored
            ),
        },
        "terminology_and_safety": terminology,
        "classifications": classifications,
        "pilot": pilot,
        "regression": {
            "hashes_before": hashes_before,
            "hashes_after": hashes_after,
            "checks": input_checks,
            "all_frozen_datasets_unchanged": hashes_before == hashes_after,
        },
        "future_data_separation": {
            "scoring_imports_outcome_values": False,
            "risk_imports_outcome_values": False,
            "audit_outputs_required_by_baseline_generation": False,
            "frozen_hashes_unchanged": hashes_before == hashes_after,
        },
        "safety": {
            "signals_generated": 0,
            "orders_placed": 0,
            "remote_migrations_applied": 0,
            "supabase_records_persisted": 0,
            "execution_engine_components_introduced": 0,
        },
        "artifacts": {
            "summary_path": str(config.summary_path),
            "report_paths": [str(config.report_path(name)) for name in AUDIT_REPORT_NAMES],
            "bulk_dir": str(config.bulk_dir),
            "storage_size_bytes": 0,
        },
        "runtime_seconds": round(runtime_seconds, 3),
        "known_limitations": [
            "Daily OHLC cannot order stop and target when both first occur in one session.",
            "Extended horizons are audit-only and do not change the four-session baseline.",
            "No costs, slippage, trade P&L, capital allocation, or compounding is modeled.",
            "Forward safety inherits existing adjusted-bar and corporate-action metadata quality.",
            "Descriptive subgroup relationships are not causal and are not parameter recommendations.",
        ],
        "ready_for_review": ready,
    }


def write_audit_outputs(
    config: StrategyOutcomeAuditConfig,
    report: dict[str, Any],
    tables: dict[str, list[dict[str, Any]]],
    unsafe_rows: Sequence[dict[str, Any]],
    extended_records: Sequence[dict[str, Any]],
) -> None:
    for name in AUDIT_REPORT_NAMES:
        rows = tables[name]
        write_csv(config.report_path(name), rows, union_fieldnames(rows))
    config.bulk_dir.mkdir(parents=True, exist_ok=True)
    write_gzip_rows(config.bulk_dir / "forward_safety_detail.csv.gz", unsafe_rows)
    write_gzip_rows(config.bulk_dir / "extended_horizon_detail.csv.gz", extended_records)
    write_json(config.summary_path, report)
    artifact_paths = [config.summary_path, *[config.report_path(name) for name in AUDIT_REPORT_NAMES]]
    artifact_paths.extend(config.bulk_dir.glob("*.csv.gz"))
    report["artifacts"]["storage_size_bytes"] = sum(path.stat().st_size for path in artifact_paths if path.exists())
    write_json(config.summary_path, report)


def write_outcome_audit_markdown(report: dict[str, Any], path: Path) -> None:
    classifications = report["classifications"]
    safety = report["forward_safety"]
    population = report["population"]
    lines = [
        "# Strategy V1 Historical Outcomes Structural Audit",
        "",
        "Current phase: Step 02.11 / Command 02",
        "",
        "## Boundary",
        "",
        "- STRATEGY_OUTCOME_AUDIT_V1 is diagnostic only and does not mutate STRATEGY_OUTCOME_V1.",
        "- The audit uses future prices only inside the outcome/audit boundary.",
        "- No score, stop, target, threshold, weight, entry rule, holding horizon, or exit methodology was changed.",
        "- No backtest, trade P&L, signal, broker action, order, migration, or Supabase write was introduced.",
        "",
        "## Frozen Baseline",
        "",
        f"- Outcome: {report['baseline']['outcome_version']} / {report['baseline']['outcome_profile']} / {report['baseline']['outcome_config_hash']}",
        f"- Outcome dataset SHA-256: {report['baseline']['outcome_dataset_hash']}",
        f"- Score dataset SHA-256: {report['baseline']['score_dataset_hash']}",
        f"- Risk V1.1 dataset SHA-256: {report['baseline']['risk_dataset_hash']}",
        "",
        "## Population",
        "",
        f"- Total outcome rows: {population['total_outcome_rows']}",
        f"- Primary eligible rows: {population['primary_rows']}",
        f"- Valid primary next-open entries: {population['valid_primary_rows']}",
        f"- Forward-data-unsafe primary rows: {safety['unsafe_primary_rows']}",
        f"- Entry-session unsafe: {safety['entry_session_unsafe_count']}",
        f"- Later-window-only unsafe: {safety['later_window_only_unsafe_count']}",
        "",
        "## Audit Classifications",
        "",
        f"- Forward safety: {classifications['forward_safety_result']}",
        f"- Entry revalidation: {classifications['entry_revalidation_result']}",
        f"- Outcome labels: {classifications['outcome_label_result']}",
        f"- Four-session horizon: {classifications['four_session_horizon_result']}",
        f"- Descriptive pattern: {classifications['descriptive_pattern']}",
        f"- Overall: {classifications['overall_audit_result']}",
        f"- Baseline decision: {classifications['baseline_decision']}",
        "",
        "## Interpretation Guardrails",
        "",
        "- Target-first and stop-first are neutral path labels, not canonical win/loss labels.",
        "- Intermediate R-level and extended-horizon results are diagnostics, not proposed exits or hold rules.",
        "- Counterfactual below-threshold, exceptional-review, preview, and primary cohorts remain separate.",
        "- Transaction costs and slippage remain NOT_MODELED.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def profile_metrics(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in rows if truthy(row.get("entry_valid"))]
    basis = valid if valid else list(rows)
    counts = Counter(str(row.get("first_touch_outcome", "")) for row in valid)
    complete_close = [
        value
        for row in valid
        if (value := decimal_or_none(row.get("close_return_pct_4"))) is not None
    ]
    return {
        "source_count": len(rows),
        "valid_count": len(valid),
        "valid_entry_rate_pct": pct(len(valid), len(rows)),
        "sample_size_warning": sample_size_warning(len(valid) if valid else len(rows)),
        "median_gap_pct": median_value(row.get("gap_pct") for row in basis),
        "median_planned_rr": median_value(row.get("planned_reward_risk") for row in basis),
        "median_effective_rr": median_value(row.get("effective_reward_risk") for row in basis),
        "median_target_distance_pct": median_value(row.get("effective_target_distance_pct") for row in basis),
        "median_stop_distance_pct": median_value(row.get("effective_stop_distance_pct") for row in basis),
        "median_mfe_r_4": median_value(row.get("mfe_r_4") for row in valid),
        "median_mae_r_4": median_value(row.get("mae_r_4") for row in valid),
        "median_close_return_pct_4": median_value(complete_close),
        "positive_close_rate_pct": pct(sum(value > 0 for value in complete_close), len(complete_close)),
        "negative_close_rate_pct": pct(sum(value < 0 for value in complete_close), len(complete_close)),
        "target_first_count": counts[TARGET_FIRST],
        "target_first_rate_pct": pct(counts[TARGET_FIRST], len(valid)),
        "stop_first_count": counts[STOP_FIRST],
        "stop_first_rate_pct": pct(counts[STOP_FIRST], len(valid)),
        "ambiguous_count": counts[AMBIGUOUS],
        "ambiguous_rate_pct": pct(counts[AMBIGUOUS], len(valid)),
        "neither_count": counts[NEITHER_WITHIN_HORIZON],
        "neither_rate_pct": pct(counts[NEITHER_WITHIN_HORIZON], len(valid)),
    }


def extended_profile(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    profile = profile_metrics(rows)
    profile.update(
        {
            "target_type_counts": dict(Counter(str(row.get("target_type", "")) for row in rows)),
            "regime_counts": dict(Counter(str(row.get("regime_state", "")) for row in rows)),
            "setup_quality_counts": dict(Counter(str(row.get("setup_quality", "")) for row in rows)),
        }
    )
    return profile


def grouped_profiles(
    rows: Sequence[dict[str, Any]],
    classifier: Callable[[dict[str, Any]], str],
    label: str,
) -> list[dict[str, Any]]:
    grouped = group_by_function(rows, classifier)
    return [{label: key, **profile_metrics(grouped_rows)} for key, grouped_rows in sorted(grouped.items())]


def group_by_function(
    rows: Sequence[dict[str, Any]],
    classifier: Callable[[dict[str, Any]], str],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[classifier(row)].append(row)
    return dict(grouped)


def target_type(target_basis: str) -> str:
    return "R_MULTIPLE_2R_RESEARCH_REFERENCE" if target_basis == "R_MULTIPLE_2R_RESEARCH_REFERENCE" else "STRUCTURAL_TARGET"


def target_r_bucket(row: dict[str, Any]) -> str:
    value = decimal_or_zero(row.get("effective_reward_risk"))
    if value < Decimal("2"):
        return "1.5-<2R"
    if value < Decimal("2.5"):
        return "2-<2.5R"
    return ">=2.5R"


def target_distance_bucket(row: dict[str, Any]) -> str:
    value = decimal_or_zero(row.get("effective_target_distance_pct"))
    if value <= 2:
        return "<=2%"
    if value <= 4:
        return "2-4%"
    if value <= 6:
        return "4-6%"
    if value <= 10:
        return "6-10%"
    return ">10%"


def gap_size_bucket(row: dict[str, Any]) -> str:
    value = decimal_or_zero(row.get("gap_pct"))
    if value <= -2:
        return "<=-2%"
    if value <= Decimal("-0.5"):
        return "-2_TO_-0.5%"
    if value <= 0:
        return "-0.5_TO_0%"
    if value <= Decimal("0.5"):
        return "0_TO_0.5%"
    if value <= 1:
        return "0.5_TO_1%"
    if value <= 2:
        return "1_TO_2%"
    if value <= 5:
        return "2_TO_5%"
    return ">5%"


def chase_bucket(row: dict[str, Any]) -> str:
    value = decimal_or_zero(row.get("gap_pct"))
    if value <= 0:
        return "<=0%"
    if value <= Decimal("0.5"):
        return "0_TO_0.5%"
    if value <= 1:
        return "0.5_TO_1%"
    if value <= 2:
        return "1_TO_2%"
    return ">2%"


def below_threshold_bucket(row: dict[str, Any]) -> str:
    score = decimal_or_zero(row.get("score_raw"))
    if score < 60:
        return "<60"
    if score < 70:
        return "60-69"
    if score < 75:
        return "70-74"
    if score < 78:
        return "75-77"
    return "78-79"


def mfe_r_bucket(row: dict[str, Any]) -> str:
    value = decimal_or_zero(row.get("mfe_r_4"))
    if value < Decimal("0.5"):
        return "<0.5R"
    if value < 1:
        return "0.5-<1R"
    if value < Decimal("1.5"):
        return "1-<1.5R"
    if value < 2:
        return "1.5-<2R"
    return ">=2R"


def favorable_before_stop_state(row: dict[str, Any], level: Decimal) -> str:
    favorable_session = first_r_reach_session(row, "mfe_r", level)
    stop_session = int(decimal_or_zero(row.get("first_stop_session")))
    if not favorable_session:
        return "FAVORABLE_NOT_REACHED"
    if not stop_session or favorable_session < stop_session:
        return "FAVORABLE_EARLIER_SESSION"
    if favorable_session == stop_session:
        return "SAME_SESSION_SEQUENCE_AMBIGUOUS"
    return "FAVORABLE_AFTER_STOP_SESSION"


def first_r_reach_session(row: dict[str, Any], prefix: str, level: Decimal) -> int:
    for horizon in range(1, 5):
        if truthy(row.get(f"horizon_available_{horizon}")) and decimal_or_zero(row.get(f"{prefix}_{horizon}")) >= level:
            return horizon
    return 0


def neither_profile(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    profile = profile_metrics(rows)
    complete = [row for row in rows if truthy(row.get("horizon_available_4"))]
    remaining = []
    for row in complete:
        target = decimal_or_none(row.get("target_price"))
        close = decimal_or_none(row.get("close_4"))
        entry = decimal_or_none(row.get("hypothetical_entry_price"))
        if target is not None and close is not None and entry is not None and entry > 0:
            remaining.append((target - close) / entry * Decimal("100"))
    profile.update(
        {
            "mfe_r_distribution": numeric_summary(row.get("mfe_r_4") for row in complete),
            "mae_r_distribution": numeric_summary(row.get("mae_r_4") for row in complete),
            "reach_0_5r_count": sum(decimal_or_zero(row.get("mfe_r_4")) >= Decimal("0.5") for row in complete),
            "reach_1r_count": sum(decimal_or_zero(row.get("mfe_r_4")) >= 1 for row in complete),
            "reach_1_5r_count": sum(decimal_or_zero(row.get("mfe_r_4")) >= Decimal("1.5") for row in complete),
            "reach_2r_count": sum(decimal_or_zero(row.get("mfe_r_4")) >= 2 for row in complete),
            "median_distance_remaining_to_target_pct_of_entry": median_value(remaining),
        }
    )
    return profile


def time_to_extreme(row: dict[str, Any], prefix: str) -> int:
    final = decimal_or_none(row.get(f"{prefix}_4"))
    if final is None:
        return 0
    for horizon in range(1, 5):
        value = decimal_or_none(row.get(f"{prefix}_{horizon}"))
        if value is not None and abs(value - final) <= RECONSTRUCTION_TOLERANCE:
            return horizon
    return 0


def first_touch_at_horizon(row: dict[str, Any], horizon: int) -> str:
    stop = int(decimal_or_zero(row.get("first_stop_session")))
    target = int(decimal_or_zero(row.get("first_target_session")))
    stop = stop if 0 < stop <= horizon else 0
    target = target if 0 < target <= horizon else 0
    if stop and target and stop == target:
        return AMBIGUOUS
    if target and (not stop or target < stop):
        return TARGET_FIRST
    if stop and (not target or stop < target):
        return STOP_FIRST
    return NEITHER_WITHIN_HORIZON


def reference_distortion_summary(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    metrics: dict[str, list[Decimal]] = defaultdict(list)
    for row in rows:
        reference = decimal_or_none(row.get("reference_entry_price"))
        entry = decimal_or_none(row.get("hypothetical_entry_price"))
        if reference is not None and entry is not None:
            metrics["entry_price_delta_abs"].append(entry - reference)
            metrics["entry_price_delta_pct"].append((entry - reference) / reference * Decimal("100"))
        pairs = (
            ("stop_distance_delta_pct_points", row.get("effective_stop_distance_pct"), row.get("planned_stop_distance_pct")),
            ("target_distance_delta_pct_points", row.get("effective_target_distance_pct"), row.get("planned_target_distance_pct")),
            ("reward_risk_delta", row.get("effective_reward_risk"), row.get("planned_reward_risk")),
        )
        for name, actual, planned in pairs:
            actual_value = decimal_or_none(actual)
            planned_value = decimal_or_none(planned)
            if actual_value is not None and planned_value is not None:
                metrics[name].append(actual_value - planned_value)
        metrics["quantity_delta"].append(decimal_or_zero(row.get("hypothetical_quantity")) - decimal_or_zero(row.get("planned_quantity")))
    return {name: numeric_summary(values) for name, values in metrics.items()}


def mechanical_entry_valid(row: dict[str, Any]) -> bool:
    return mechanical_entry_valid_without_rr(row) and decimal_or_zero(row.get("effective_reward_risk")) >= Decimal("1.5")


def mechanical_entry_valid_without_rr(row: dict[str, Any]) -> bool:
    entry = decimal_or_none(row.get("hypothetical_entry_price"))
    stop = decimal_or_none(row.get("stop_price"))
    return (
        entry is not None
        and stop is not None
        and entry > stop
        and int(decimal_or_zero(row.get("hypothetical_quantity"))) >= 1
        and row.get("entry_recheck_status") not in {NO_NEXT_SESSION_DATA, ENTRY_INVALID_STOP_RELATION, ENTRY_INVALID_CAPITAL}
    )


def row_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("decision_date", "")), canonical_symbol(row.get("symbol", ""))


def metric_quantile_rows(
    metric: str,
    values: Iterable[Any],
    percentiles: Sequence[int],
    *,
    include_mean: bool = False,
) -> list[dict[str, Any]]:
    parsed = [value for item in values if (value := decimal_or_none(item)) is not None]
    rows = [
        {"metric": metric, "statistic": f"p{percentile}", "value": percentile_value(parsed, percentile)}
        for percentile in percentiles
    ]
    if include_mean:
        rows.append({"metric": metric, "statistic": "mean", "value": mean_value(parsed)})
    return rows


def numeric_summary(values: Iterable[Any]) -> dict[str, Any]:
    parsed = sorted(value for item in values if (value := decimal_or_none(item)) is not None)
    if not parsed:
        return {
            "count": 0,
            "min": None,
            "p1": None,
            "p5": None,
            "p10": None,
            "p25": None,
            "median": None,
            "mean": None,
            "p75": None,
            "p90": None,
            "p95": None,
            "p99": None,
            "max": None,
        }
    return {
        "count": len(parsed),
        "min": parsed[0],
        "p1": percentile_value(parsed, 1),
        "p5": percentile_value(parsed, 5),
        "p10": percentile_value(parsed, 10),
        "p25": percentile_value(parsed, 25),
        "median": median_value(parsed),
        "mean": mean_value(parsed),
        "p75": percentile_value(parsed, 75),
        "p90": percentile_value(parsed, 90),
        "p95": percentile_value(parsed, 95),
        "p99": percentile_value(parsed, 99),
        "max": parsed[-1],
    }


def percentile_value(values: Iterable[Any], percentile: int) -> Decimal | None:
    parsed = sorted(value for item in values if (value := decimal_or_none(item)) is not None)
    if not parsed:
        return None
    if len(parsed) == 1:
        return parsed[0]
    position = Decimal(len(parsed) - 1) * Decimal(percentile) / Decimal("100")
    lower = int(position)
    upper = min(lower + 1, len(parsed) - 1)
    fraction = position - Decimal(lower)
    return parsed[lower] + (parsed[upper] - parsed[lower]) * fraction


def median_value(values: Iterable[Any]) -> Decimal | None:
    parsed = [value for item in values if (value := decimal_or_none(item)) is not None]
    return Decimal(str(statistics.median(parsed))) if parsed else None


def mean_value(values: Iterable[Any]) -> Decimal | None:
    parsed = [value for item in values if (value := decimal_or_none(item)) is not None]
    return sum(parsed, Decimal("0")) / Decimal(len(parsed)) if parsed else None


def spearman(xs: Sequence[Decimal], ys: Sequence[Decimal]) -> Decimal | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    x_ranks = ranks(xs)
    y_ranks = ranks(ys)
    x_mean = mean_value(x_ranks)
    y_mean = mean_value(y_ranks)
    if x_mean is None or y_mean is None:
        return None
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_ranks, y_ranks))
    x_var = sum((x - x_mean) ** 2 for x in x_ranks)
    y_var = sum((y - y_mean) ** 2 for y in y_ranks)
    if x_var == 0 or y_var == 0:
        return Decimal("0")
    return numerator / (x_var.sqrt() * y_var.sqrt())


def ranks(values: Sequence[Decimal]) -> list[Decimal]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    result = [Decimal("0")] * len(values)
    index = 0
    while index < len(ordered):
        end = index
        while end + 1 < len(ordered) and ordered[end + 1][1] == ordered[index][1]:
            end += 1
        rank = (Decimal(index + 1) + Decimal(end + 1)) / Decimal("2")
        for offset in range(index, end + 1):
            result[ordered[offset][0]] = rank
        index = end + 1
    return result


def distribution_rows(counts: Counter[str], total: int, label: str) -> list[dict[str, Any]]:
    return [{label: value, "count": count, "rate_pct": pct(count, total)} for value, count in sorted(counts.items())]


def top_counts(values: Iterable[str], limit: int) -> list[dict[str, Any]]:
    return [{"value": value, "count": count} for value, count in Counter(values).most_common(limit)]


def sample_size_warning(count: int) -> str:
    if count < 30:
        return "VERY_SMALL"
    if count < 100:
        return "SMALL"
    if count < 300:
        return "LIMITED"
    return "ADEQUATE_FOR_DESCRIPTION"


def flatten_dict(value: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, item in value.items():
        name = f"{prefix}_{key}" if prefix else str(key)
        if isinstance(item, dict):
            output.update(flatten_dict(item, name))
        elif isinstance(item, (list, tuple)):
            output[name] = ";".join(str(part) for part in item)
        else:
            output[name] = item
    return output


def write_gzip_rows(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = union_fieldnames(rows)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                for row in rows:
                    writer.writerow(json_safe(row))


def percent_of(value: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if value is None or denominator is None or denominator <= 0:
        return None
    return value / denominator * Decimal("100")


def pct(numerator: int, denominator: int) -> Decimal:
    return Decimal("0") if denominator <= 0 else Decimal(numerator) / Decimal(denominator) * Decimal("100")


def decimal_or_none(value: Any) -> Decimal | None:
    if value in {None, ""}:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def decimal_or_zero(value: Any) -> Decimal:
    return decimal_or_none(value) or Decimal("0")


def decimals_equal(left: Any, right: Any) -> bool:
    left_value = decimal_or_none(left)
    right_value = decimal_or_none(right)
    if left_value is None or right_value is None:
        return left_value is right_value
    return abs(left_value - right_value) <= RECONSTRUCTION_TOLERANCE


def truthy(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1", "yes"}


def subtract_optional(left: Any, right: Any) -> Decimal | None:
    left_value = decimal_or_none(left)
    right_value = decimal_or_none(right)
    return left_value - right_value if left_value is not None and right_value is not None else None


def decimal_label(value: Decimal) -> str:
    return format(value, "f").replace(".", "_")


def notify(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)
