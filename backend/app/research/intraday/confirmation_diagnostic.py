from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import statistics
import subprocess
import time
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from app.backtesting.portfolio_baseline import (
    portfolio_backtest_regression_hash_checks,
    portfolio_backtest_regression_hashes,
    verify_current_portfolio_backtest_baseline,
)
from app.research.intraday.calendar import NseCashSessionCalendar
from app.research.intraday.development_ingestion import (
    load_frozen_development_opportunities,
    load_frozen_development_trades,
)
from app.research.intraday.first_touch import evaluate_first_touch
from app.research.intraday.models import AmbiguityPolicy, CanonicalIntradayBar, FirstTouch
from app.research.intraday.normalization import parse_timestamp
from app.research.intraday.opening_range import calculate_opening_range
from app.research.intraday.temporal import PERFORMANCE_RESEARCH, validate_intraday_research_scope
from app.research.intraday.vwap import calculate_session_vwap
from app.research.temporal_validation.config import (
    DEFAULT_TEMPORAL_CONFIG,
    EXPECTED_HARNESS_CONFIG_HASH,
    SEALED,
    canonical_hash,
    json_ready,
)
from app.research.temporal_validation.guard import ValidationAccessError


DIAGNOSTIC_VERSION = "INTRADAY_CONFIRMATION_DIAGNOSTIC_V1"
PROFILE = "DEVELOPMENT_INTRADAY_CONFIRMATION_V1"
FAMILY = "INTRADAY_CONFIRMATION_DIAGNOSTIC"
COMMAND = "Step 02.15 / Command 01"
FIRST_TOUCH_ENGINE = "INTRADAY_FIRST_TOUCH_ENGINE_V1"

EXPECTED_SCOPE_HASH = "dcf4cc8587c923fd08e6299f472cd8f37add3baae54498351eb53fe76da75fe3"
EXPECTED_REQUEST_PLAN_HASH = "cd871adf88bc571339b0c3ca7efcb066d88ab8b63ceae5d0804a411fd8e7dfaf"
EXPECTED_DATASET_HASHES = {
    "normalized_5m_dataset_hash": "a694c232be5160ba50fc7f6e8e85b93fc90cc125aa03a7c082ce803a18752f87",
    "derived_10m_dataset_hash": "8d4eac312e58d6616eb68f7faae4b9c9a2b465b78c20f62c0a37064ccac10fe2",
    "derived_15m_dataset_hash": "deaedc7ffd23587d863de5b36783ae9d314e1fe614e06e52b6ba68e25991a0d6",
    "session_index_hash": "cf7732fb1acbb29b93c1b07ce4dbf03a624692968f34c2be4e9c65b866aab1d5",
    "opportunity_coverage_hash": "2664947c8efe6f5a9c21806ad1843a3ef78e9f6e0d0d6c65a814aa74c0b742f7",
}

EXPERIMENTS = (
    ("EXP-INTRACONF-001", "BASELINE_OPEN_REFERENCE_PROFILE"),
    ("EXP-INTRACONF-002", "FIRST_5M_CONFIRMATION_PROFILE"),
    ("EXP-INTRACONF-003", "FIRST_10M_CONFIRMATION_PROFILE"),
    ("EXP-INTRACONF-004", "FIRST_15M_CONFIRMATION_PROFILE"),
    ("EXP-INTRACONF-005", "CONFIRMATION_PRICE_DRIFT"),
    ("EXP-INTRACONF-006", "CONFIRMATION_RR_HEADROOM"),
    ("EXP-INTRACONF-007", "VWAP_CONFIRMATION_CONTEXT"),
    ("EXP-INTRACONF-008", "OPENING_RANGE_CONFIRMATION_CONTEXT"),
    ("EXP-INTRACONF-009", "FALSE_START_AND_EARLY_PATH"),
    ("EXP-INTRACONF-010", "CONFIRMATION_CONTEXT_INTERACTIONS"),
)
EXPERIMENT_IDS = tuple(item[0] for item in EXPERIMENTS)
WINDOWS = (5, 10, 15)
POPULATIONS = ("ALL_STRICT_COVERED", "ADMITTED_STRICT_COVERED")

PRICE_DRIFT_BUCKETS = (
    "LE_NEG_1_0_PCT",
    "GT_NEG_1_0_TO_LE_NEG_0_5_PCT",
    "GT_NEG_0_5_TO_LE_0_PCT",
    "GT_0_TO_LE_0_5_PCT",
    "GT_0_5_TO_LE_1_0_PCT",
    "GT_1_0_TO_LE_2_0_PCT",
    "GT_2_0_PCT",
)
RR_BUCKETS = ("RR_LT_1_5", "RR_1_5_TO_LT_2", "RR_2_TO_LT_2_5", "RR_GE_2_5")
VWAP_BUCKETS = ("BELOW_VWAP", "AT_VWAP", "ABOVE_VWAP")
OR_BUCKETS = ("ABOVE_OR_HIGH", "ON_OR_HIGH", "INSIDE_OR", "ON_OR_LOW", "BELOW_OR_LOW")
EARLY_PATH_BUCKETS = ("EARLY_STRENGTH", "EARLY_WEAKNESS", "FLAT")
PATH_QUALITY_BUCKETS = (
    "STOP_FIRST",
    "TARGET_FIRST",
    "NEITHER_WITH_POSITIVE_MFE",
    "NEITHER_WEAK",
    "AMBIGUOUS",
)

# Fixed before empirical computation. These thresholds classify evidence; they are
# not strategy rules and are never used to include/exclude opportunities.
CLASSIFICATION_RULES = {
    "usefulness_signal_pp": "failure early-weakness rate minus good-path early-weakness rate; supportive >=10pp, strong >=20pp, inverse <=-10pp",
    "acceptable_delay": "LOW or MODERATE",
    "rr_preservation": "median rr_delta >= -0.50 and structure-invalid rate <=10%",
    "adequate_sample": ">=300",
    "year_support": "for each 5m/10m/15m window, supportive signal in at least two DEVELOPMENT years and inverse in none; all three windows meeting this is CONSISTENT",
    "delay_low": "all windows: median drift <=0.20%, median rr_delta >=-0.25, target-before <=2%, structure-invalid <=2%",
    "delay_moderate": "no window crosses HIGH; at least one crosses LOW",
    "delay_high": "any window: median drift >0.50%, median rr_delta <-0.50, target-before >5%, or structure-invalid >10%",
    "delay_very_high": "any window: median drift >1%, median rr_delta <-0.75, or infeasible rate >20%",
    "vwap_support": "ABOVE minus BELOW median MFE_CONFIRM_R >=0.10 and stop-first rate no more than 5pp worse, with both cells >=30",
    "or_support": "ABOVE_OR_HIGH minus INSIDE_OR median MFE_CONFIRM_R >=0.10 and stop-first rate no more than 5pp worse, with both cells >=30",
    "good_path": "frozen TARGET_FIRST or frozen MFE_R_4 >=1.0",
    "flat_price": "exact Decimal equality",
    "vwap_at_tolerance_rupees": "0.005",
}
VWAP_AT_TOLERANCE = Decimal("0.005")

REPORT_FILENAMES = (
    "intraday_confirmation_v1_summary.json",
    "intraday_confirmation_v1_population.csv",
    "intraday_confirmation_v1_5m.csv",
    "intraday_confirmation_v1_10m.csv",
    "intraday_confirmation_v1_15m.csv",
    "intraday_confirmation_v1_price_drift.csv",
    "intraday_confirmation_v1_rr_headroom.csv",
    "intraday_confirmation_v1_vwap.csv",
    "intraday_confirmation_v1_opening_range.csv",
    "intraday_confirmation_v1_false_start.csv",
    "intraday_confirmation_v1_contexts.csv",
    "intraday_confirmation_v1_yearly.csv",
    "intraday_confirmation_v1_pilot.csv",
)


class ConfirmationResult(StrEnum):
    PROMISING_FOR_CONTROLLED_TEST = "PROMISING_FOR_CONTROLLED_TEST"
    MIXED = "MIXED"
    NO_CLEAR_BENEFIT = "NO_CLEAR_BENEFIT"
    LIKELY_HARMFUL = "LIKELY_HARMFUL"
    INCONCLUSIVE = "INCONCLUSIVE"


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def optional_decimal(value: Any) -> Decimal | None:
    return None if value is None or str(value).strip() == "" else Decimal(str(value))


def _source_key(row: Mapping[str, Any]) -> str:
    return f"{row.get('decision_date', '')}|{str(row.get('symbol', '')).upper()}"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_gzip_csv(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_ready(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _flatten_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): (
            json.dumps(json_ready(value), sort_keys=True, separators=(",", ":"))
            if isinstance(value, (dict, list, tuple))
            else json_ready(value)
        )
        for key, value in row.items()
    }


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    prepared = [_flatten_row(row) for row in rows]
    fields = sorted({field for row in prepared for field in row})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(prepared)


def _artifact_root(repo_root: Path) -> Path:
    return Path(repo_root) / "data/research/diagnostics/intraday/v1/confirmation_command_01"


def _report_root(repo_root: Path) -> Path:
    return Path(repo_root) / "data/reports"


def validate_development_only(dates: Iterable[date]) -> dict[str, Any]:
    values = tuple(dates)
    result = validate_intraday_research_scope(values, purpose=PERFORMANCE_RESEARCH)
    if result["validation_state"] != SEALED or result["performance_accessed"]:
        raise ValidationAccessError("Validation must remain SEALED for confirmation diagnostics")
    return result


def sample_safety(count: int) -> str:
    if count < 30:
        return "VERY_SMALL"
    if count < 100:
        return "SMALL"
    if count < 300:
        return "LIMITED"
    return "ADEQUATE_FOR_DESCRIPTION"


def price_drift_bucket(value: Decimal) -> str:
    if value <= Decimal("-1"):
        return PRICE_DRIFT_BUCKETS[0]
    if value <= Decimal("-0.5"):
        return PRICE_DRIFT_BUCKETS[1]
    if value <= 0:
        return PRICE_DRIFT_BUCKETS[2]
    if value <= Decimal("0.5"):
        return PRICE_DRIFT_BUCKETS[3]
    if value <= 1:
        return PRICE_DRIFT_BUCKETS[4]
    if value <= 2:
        return PRICE_DRIFT_BUCKETS[5]
    return PRICE_DRIFT_BUCKETS[6]


def rr_bucket(value: Decimal) -> str:
    if value < Decimal("1.5"):
        return RR_BUCKETS[0]
    if value < 2:
        return RR_BUCKETS[1]
    if value < Decimal("2.5"):
        return RR_BUCKETS[2]
    return RR_BUCKETS[3]


def early_path_classification(confirmation_price: Decimal, frozen_open: Decimal) -> str:
    if confirmation_price > frozen_open:
        return "EARLY_STRENGTH"
    if confirmation_price < frozen_open:
        return "EARLY_WEAKNESS"
    return "FLAT"


def vwap_classification(price: Decimal, vwap: Decimal | None) -> str:
    if vwap is None:
        return "DATA_UNAVAILABLE"
    distance = price - vwap
    if abs(distance) <= VWAP_AT_TOLERANCE:
        return "AT_VWAP"
    return "ABOVE_VWAP" if distance > 0 else "BELOW_VWAP"


def opening_range_classification(price: Decimal, high: Decimal, low: Decimal) -> str:
    if price > high:
        return "ABOVE_OR_HIGH"
    if price == high:
        return "ON_OR_HIGH"
    if price < low:
        return "BELOW_OR_LOW"
    if price == low:
        return "ON_OR_LOW"
    return "INSIDE_OR"


def confirmation_rr(
    confirmation_price: Decimal, stop: Decimal, target: Decimal
) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    risk = confirmation_price - stop
    reward = target - confirmation_price
    if confirmation_price <= stop or target <= confirmation_price or risk <= 0:
        return None, risk, reward
    return reward / risk, risk, reward


def confirmation_reference(
    five_minute_bars: Sequence[CanonicalIntradayBar],
    confirmation_bars: Sequence[CanonicalIntradayBar],
    window_minutes: int,
) -> tuple[Decimal, datetime, tuple[CanonicalIntradayBar, ...]]:
    if window_minutes not in WINDOWS:
        raise ValueError("Only 5m, 10m, and 15m confirmation references are registered")
    source_count = window_minutes // 5
    source = tuple(sorted(five_minute_bars, key=lambda row: row.bar_start)[:source_count])
    derived = sorted(confirmation_bars, key=lambda row: row.bar_start)
    if len(source) != source_count or not derived:
        raise ValueError(f"{window_minutes}m confirmation data unavailable")
    reference = derived[0]
    if reference.interval != f"{window_minutes}m" or reference.is_partial_bar:
        raise ValueError("Confirmation reference must be a complete registered interval")
    if reference.source_bar_count != source_count:
        raise ValueError("Confirmation reference source-bar count mismatch")
    if any(row.bar_end > reference.bar_end for row in source):
        raise ValueError("Partial-bar/future-bar leakage detected")
    if source[-1].close != reference.close or source[-1].bar_end != reference.bar_end:
        raise ValueError("Derived confirmation close is inconsistent with canonical 5m source")
    return reference.close, reference.bar_end, source


def preconfirmation_touch_state(
    bars: Sequence[CanonicalIntradayBar], stop: Decimal, target: Decimal
) -> dict[str, Any]:
    if not bars:
        return {
            "stop_touched": False,
            "target_touched": False,
            "first_touch": None,
            "ambiguous": False,
            "gap_status": None,
        }
    stop_any = any(row.low <= stop for row in bars)
    target_any = any(row.high >= target for row in bars)
    first = bars[0]
    if first.open <= stop:
        return {
            "stop_touched": True,
            "target_touched": target_any,
            "first_touch": "STOP_FIRST",
            "ambiguous": False,
            "gap_status": "GAP_THROUGH_STOP",
        }
    if first.open >= target:
        return {
            "stop_touched": stop_any,
            "target_touched": True,
            "first_touch": "TARGET_FIRST",
            "ambiguous": False,
            "gap_status": "GAP_THROUGH_TARGET",
        }
    for row in bars:
        stop_hit = row.low <= stop
        target_hit = row.high >= target
        if stop_hit and target_hit:
            return {
                "stop_touched": stop_any,
                "target_touched": target_any,
                "first_touch": "INTRABAR_SEQUENCE_AMBIGUOUS",
                "ambiguous": True,
                "gap_status": None,
            }
        if stop_hit:
            return {
                "stop_touched": stop_any,
                "target_touched": target_any,
                "first_touch": "STOP_FIRST",
                "ambiguous": False,
                "gap_status": None,
            }
        if target_hit:
            return {
                "stop_touched": stop_any,
                "target_touched": target_any,
                "first_touch": "TARGET_FIRST",
                "ambiguous": False,
                "gap_status": None,
            }
    return {
        "stop_touched": stop_any,
        "target_touched": target_any,
        "first_touch": None,
        "ambiguous": False,
        "gap_status": None,
    }


def confirmation_feasibility(
    touch: Mapping[str, Any], confirmation_effective_rr: Decimal | None
) -> str:
    if touch.get("ambiguous"):
        return "INTRABAR_AMBIGUOUS"
    if touch.get("first_touch") == "STOP_FIRST":
        return "STOP_INVALIDATED_BEFORE_CONFIRMATION"
    if touch.get("first_touch") == "TARGET_FIRST":
        return "TARGET_REACHED_BEFORE_CONFIRMATION"
    if confirmation_effective_rr is None:
        return "STRUCTURE_INVALID_AT_CONFIRMATION"
    return "FEASIBLE"


def _load_partition(
    path: Path, *, allowed_dates: set[date], interval: str
) -> list[CanonicalIntradayBar]:
    if not path.exists():
        return []
    rows: list[CanonicalIntradayBar] = []
    fixed_ingestion_time = datetime(1970, 1, 1, tzinfo=timezone.utc)
    for row in _read_gzip_csv(path):
        trading_date = date.fromisoformat(row["trading_date"])
        if trading_date not in allowed_dates or row.get("interval") != interval:
            continue
        rows.append(
            CanonicalIntradayBar(
                instrument_id=row.get("instrument_id") or None,
                symbol=str(row["symbol"]).upper(),
                isin=row.get("isin") or None,
                exchange=row.get("exchange") or "NSE",
                trading_date=trading_date,
                interval=interval,
                bar_start=parse_timestamp(row["bar_start"]),
                bar_end=parse_timestamp(row["bar_end"]),
                open=Decimal(row["open"]),
                high=Decimal(row["high"]),
                low=Decimal(row["low"]),
                close=Decimal(row["close"]),
                volume=int(row["volume"]) if row.get("volume") else None,
                source_provider=row.get("source_provider") or "GROWW_OFFICIAL_API",
                source_interval=row.get("source_interval") or "5m",
                source_timestamp=parse_timestamp(row.get("source_timestamp") or row["bar_start"]),
                ingested_at=fixed_ingestion_time,
                normalization_version=row.get("normalization_version") or "NSE_CASH_INTRADAY_5M_V1",
                session_id=row.get("session_id") or f"NSE:{trading_date.isoformat()}",
                session_sequence=int(row.get("session_sequence") or 0),
                is_partial_bar=_truthy(row.get("is_partial_bar")),
                is_missing_context=_truthy(row.get("is_missing_context")),
                quality_status=row.get("quality_status") or "COMPLETE",
                quality_flags=tuple(json.loads(row.get("quality_flags") or "[]")),
                source_bar_count=int(row.get("source_bar_count") or 1),
                provider_vwap=optional_decimal(row.get("provider_vwap")),
                corporate_action_reference=json.loads(row.get("corporate_action_reference") or "{}"),
            )
        )
    return rows


def _load_bars(
    repo_root: Path, required: Mapping[str, set[date]]
) -> dict[int, dict[tuple[str, date], list[CanonicalIntradayBar]]]:
    bases = {
        5: Path(repo_root) / "data/normalized/intraday/5m/development_bounded_v1",
        10: Path(repo_root) / "data/derived/intraday/10m/development_bounded_v1",
        15: Path(repo_root) / "data/derived/intraday/15m/development_bounded_v1",
    }
    result: dict[int, dict[tuple[str, date], list[CanonicalIntradayBar]]] = {
        window: defaultdict(list) for window in WINDOWS
    }
    for window in WINDOWS:
        for symbol, wanted in sorted(required.items()):
            for year in sorted({value.year for value in wanted}):
                path = bases[window] / str(year) / f"{symbol}.csv.gz"
                bars = _load_partition(
                    path,
                    allowed_dates={value for value in wanted if value.year == year},
                    interval=f"{window}m",
                )
                for bar in bars:
                    result[window][(symbol, bar.trading_date)].append(bar)
    return {window: dict(groups) for window, groups in result.items()}


def _scale_bars(
    bars: Sequence[CanonicalIntradayBar], factor: Decimal
) -> tuple[CanonicalIntradayBar, ...]:
    if factor <= 0:
        raise ValueError("Intraday price-basis scale factor must be positive")
    return tuple(
        replace(
            bar,
            open=bar.open * factor,
            high=bar.high * factor,
            low=bar.low * factor,
            close=bar.close * factor,
            provider_vwap=(
                bar.provider_vwap * factor if bar.provider_vwap is not None else None
            ),
        )
        for bar in bars
    )


def _price_basis_scale(
    frozen_next_open: Decimal, bars: Sequence[CanonicalIntradayBar]
) -> Decimal:
    if not bars:
        raise ValueError("Cannot align price basis without a T+1 intraday bar")
    raw_session_open = min(bars, key=lambda bar: bar.bar_start).open
    if frozen_next_open <= 0 or raw_session_open <= 0:
        raise ValueError("Price-basis anchors must be positive")
    return frozen_next_open / raw_session_open


def _read_risk_rows(data_dir: Path, wanted: set[str]) -> dict[str, dict[str, str]]:
    path = data_dir / "research/risk_structures/daily/v1_1/risk_structures_v1_1.csv.gz"
    selected: dict[str, dict[str, str]] = {}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = f"{row.get('trading_date', '')}|{str(row.get('symbol', '')).upper()}"
            if key in wanted:
                selected[key] = row
    return selected


def _population_rows(repo_root: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]], dict[str, Any]]:
    data_dir = Path(repo_root) / "data"
    opportunities = load_frozen_development_opportunities(data_dir)
    trades = load_frozen_development_trades(data_dir)
    scope = json.loads(
        (data_dir / "research/intraday/v1/development_bounded/manifests/development_intraday_scope_manifest_v1.json").read_text(
            encoding="utf-8"
        )
    )
    if scope.get("scope_hash") != EXPECTED_SCOPE_HASH:
        raise ValueError("Command 05 frozen scope hash changed")
    resume_summary = json.loads(
        (data_dir / "reports/development_intraday_resume_05b_summary.json").read_text(
            encoding="utf-8"
        )
    )
    selected_symbols = set(scope["selected_symbols"])
    opportunity_coverage = {
        row["opportunity_id"]: row
        for row in _read_csv(data_dir / "reports/development_intraday_resume_05b_opportunity_coverage.csv")
    }
    trade_coverage = {
        row["source_key"]: row
        for row in _read_csv(data_dir / "reports/development_intraday_resume_05b_trade_coverage.csv")
    }
    admitted = {_source_key(row): row for row in trades}
    sources = {_source_key(row): row for row in opportunities}
    wanted = set(sources)
    risk_rows = _read_risk_rows(data_dir, wanted)
    rows: list[dict[str, Any]] = []
    exclusions = Counter()
    for key, source in sorted(sources.items()):
        coverage = opportunity_coverage.get(key)
        if str(source.get("symbol", "")).upper() not in selected_symbols:
            exclusions["OUTSIDE_FROZEN_SELECTED_SYMBOL_SCOPE"] += 1
            continue
        if coverage is None or not _truthy(coverage.get("full_path_strict_usable")):
            exclusions["NOT_FULL_PATH_USABLE_STRICT"] += 1
            continue
        if not _truthy(coverage.get("corporate_action_safe")):
            exclusions["NOT_CORPORATE_ACTION_SAFE"] += 1
            continue
        frozen_open = optional_decimal(source.get("hypothetical_entry_price"))
        stop = optional_decimal(source.get("stop_price"))
        target = optional_decimal(source.get("target_price"))
        frozen_rr = optional_decimal(source.get("effective_reward_risk"))
        if (
            frozen_open is None
            or stop is None
            or target is None
            or frozen_rr is None
            or not stop < frozen_open < target
        ):
            exclusions["FROZEN_STRUCTURE_UNAVAILABLE_OR_INVALID"] += 1
            continue
        is_admitted = key in admitted and _truthy(trade_coverage.get(key, {}).get("full_hold_path_strict_usable"))
        if key in admitted and not is_admitted:
            exclusions["ADMITTED_WITHOUT_STRICT_FULL_PATH"] += 1
        rows.append(
            {
                "opportunity_id": key,
                "symbol": str(source["symbol"]).upper(),
                "decision_date": source["decision_date"],
                "entry_date": source["next_session_date"],
                "score": int(Decimal(str(source["raw_strategy_score"]))),
                "candidate_stage": source.get("candidate_category") or source.get("candidate_state"),
                "setup_quality": source.get("setup_quality"),
                "regime_state": source.get("regime_state"),
                "frozen_next_open": frozen_open,
                "frozen_stop": stop,
                "frozen_target": target,
                "frozen_effective_rr": frozen_rr,
                "intraday_quality": "USABLE_STRICT_FULL_PATH",
                "CA_safety": "SAFE",
                "population_group": "ADMITTED_COVERED_STRICT" if is_admitted else "SOURCE_COVERED_STRICT_ONLY",
                "is_admitted": is_admitted,
            }
        )
    dates = [date.fromisoformat(row["decision_date"]) for row in rows]
    validate_development_only(dates)
    return rows, sources, {
        "exclusions": dict(sorted(exclusions.items())),
        "risk_rows": risk_rows,
        "admitted_rows": admitted,
        "selected_symbols": sorted(selected_symbols),
        "total_development_opportunities": len(opportunities),
        "frozen_development_admitted_trades": len(trades),
        "intraday_session_quality": resume_summary["quality"],
    }


def freeze_population(rows: Sequence[Mapping[str, Any]]) -> str:
    ordered = sorted((dict(row) for row in rows), key=lambda row: row["opportunity_id"])
    if len({row["opportunity_id"] for row in ordered}) != len(ordered):
        raise ValueError("Population manifest contains duplicate opportunity IDs")
    if any(not ("2022-01-01" <= row["decision_date"] <= "2024-12-31") for row in ordered):
        raise ValidationAccessError("Population contains a non-DEVELOPMENT decision date")
    return canonical_hash(ordered)


def build_preregistration(
    population_hash: str, baseline_dependency: Mapping[str, Any]
) -> dict[str, Any]:
    hypotheses = {
        "EXP-INTRACONF-001": "Describe the immutable T+1-open reference without changing Strategy V1.",
        "EXP-INTRACONF-002": "The first completed 5m close may separate early failures while preserving feasible structure.",
        "EXP-INTRACONF-003": "The first completed 10m close may separate early failures while preserving feasible structure.",
        "EXP-INTRACONF-004": "The first completed 15m close may separate early failures while preserving feasible structure.",
        "EXP-INTRACONF-005": "Waiting may impose measurable price drift and opportunity cost.",
        "EXP-INTRACONF-006": "Waiting may alter frozen stop/target R:R headroom.",
        "EXP-INTRACONF-007": "Above-VWAP confirmations may have different later path quality than below-VWAP confirmations.",
        "EXP-INTRACONF-008": "Opening-range context may be associated with later path quality.",
        "EXP-INTRACONF-009": "Early weakness may identify some frozen failures but may also sacrifice good paths.",
        "EXP-INTRACONF-010": "Confirmation associations may differ across frozen contexts without defining a new filter.",
    }
    metric_sets = {
        "EXP-INTRACONF-001": ["count", "score", "stage", "setup", "regime", "gap", "frozen_rr", "mfe_r", "mae_r", "daily_path"],
        "EXP-INTRACONF-002": ["5m_feasibility", "drift", "rr", "mfe_confirm_r", "mae_confirm_r"],
        "EXP-INTRACONF-003": ["10m_feasibility", "drift", "rr", "mfe_confirm_r", "mae_confirm_r"],
        "EXP-INTRACONF-004": ["15m_feasibility", "drift", "rr", "mfe_confirm_r", "mae_confirm_r"],
        "EXP-INTRACONF-005": ["drift_percentiles", "chase_rate", "cheaper_rate", "preconfirmation_touch_rate"],
        "EXP-INTRACONF-006": ["confirmation_rr", "rr_delta", "target_headroom", "stop_headroom", "invalid_rate"],
        "EXP-INTRACONF-007": ["vwap_context", "drift", "rr", "mfe_confirm_r", "mae_confirm_r", "first_touch"],
        "EXP-INTRACONF-008": ["opening_range_context", "opening_range_width", "mfe_confirm_r", "mae_confirm_r", "first_touch"],
        "EXP-INTRACONF-009": ["false_start", "early_path", "potentially_filterable_failures", "good_trade_sacrifice"],
        "EXP-INTRACONF-010": ["score", "setup", "candidate_stage", "regime", "frozen_rr", "gap", "year"],
    }
    records: list[dict[str, Any]] = []
    for experiment_id, name in EXPERIMENTS:
        window = {"EXP-INTRACONF-002": 5, "EXP-INTRACONF-003": 10, "EXP-INTRACONF-004": 15}.get(experiment_id)
        parameters = {
            "diagnostic_version": DIAGNOSTIC_VERSION,
            "profile": PROFILE,
            "development_start": DEFAULT_TEMPORAL_CONFIG.development_start,
            "development_end": DEFAULT_TEMPORAL_CONFIG.development_end,
            "validation_state": SEALED,
            "population_hash": population_hash,
            "confirmation_window_minutes": window,
            "registered_windows_minutes": WINDOWS,
            "price_drift_buckets": PRICE_DRIFT_BUCKETS,
            "rr_buckets": RR_BUCKETS,
            "vwap_buckets": VWAP_BUCKETS,
            "opening_range_buckets": OR_BUCKETS,
            "early_path_buckets": EARLY_PATH_BUCKETS,
            "sample_safety": {"VERY_SMALL": "<30", "SMALL": "30-99", "LIMITED": "100-299", "ADEQUATE_FOR_DESCRIPTION": ">=300"},
            "classification_rules": CLASSIFICATION_RULES,
            "post_confirmation_path_starts": "NEXT_ELIGIBLE_5M_BAR",
            "first_touch_engine": FIRST_TOUCH_ENGINE,
            "ambiguity_policy": "PRESERVE_INTRABAR_SEQUENCE_AMBIGUOUS",
            "price_basis_alignment": {
                "method": "CAUSAL_T1_OPEN_RATIO_TO_FROZEN_DAILY_BASIS",
                "factor_available_at": "T1_SESSION_OPEN",
                "raw_groww_inputs_overwritten": False,
                "frozen_stop_target_modified": False,
            },
        }
        body = {
            "experiment_id": experiment_id,
            "family": FAMILY,
            "name": name,
            "hypothesis": hypotheses[experiment_id],
            "population_hash": population_hash,
            "confirmation_window": window,
            "metrics": metric_sets[experiment_id],
            "bucket_definitions": {
                "price_drift": PRICE_DRIFT_BUCKETS,
                "rr": RR_BUCKETS,
                "vwap": VWAP_BUCKETS,
                "opening_range": OR_BUCKETS,
                "early_path": EARLY_PATH_BUCKETS,
            },
            "baseline_dependencies": dict(baseline_dependency),
            "parameters": parameters,
            "parameter_hash": canonical_hash(parameters),
            "promotion_allowed": False,
            "eligible_for_promotion": False,
            "diagnostic_only": True,
            "pre_registered": True,
        }
        records.append({**body, "pre_registration_hash": canonical_hash(body), "status": "REGISTERED"})
    prereg_hash = canonical_hash(records)
    return {
        "diagnostic_version": DIAGNOSTIC_VERSION,
        "profile": PROFILE,
        "family": FAMILY,
        "written_before_result_computation": True,
        "no_post_result_threshold_edits": True,
        "population_hash": population_hash,
        "experiment_count": len(records),
        "experiments": records,
        "intraday_confirmation_prereg_hash": prereg_hash,
    }


def _baseline_snapshot(repo_root: Path) -> dict[str, Any]:
    root = Path(repo_root)
    data_dir = root / "data"
    verify_current_portfolio_backtest_baseline(data_dir)
    chain = portfolio_backtest_regression_hashes(data_dir)
    chain_checks = portfolio_backtest_regression_hash_checks(chain)
    if not all(chain_checks.values()):
        raise ValueError("Frozen feature-to-backtest baseline chain failed verification")
    if DEFAULT_TEMPORAL_CONFIG.config_hash() != EXPECTED_HARNESS_CONFIG_HASH:
        raise ValueError("Temporal harness config hash changed")
    scope_path = data_dir / "research/intraday/v1/development_bounded/manifests/development_intraday_scope_manifest_v1.json"
    plan_path = data_dir / "research/intraday/v1/development_bounded/manifests/request_plan_v1.json"
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if scope.get("scope_hash") != EXPECTED_SCOPE_HASH or plan.get("request_plan_hash") != EXPECTED_REQUEST_PLAN_HASH:
        raise ValueError("Command 05 scope/request-plan freeze changed")
    summary_path = data_dir / "reports/development_intraday_resume_05b_summary.json"
    resume_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    observed_dataset_hashes = {
        key: resume_summary["datasets"][key] for key in EXPECTED_DATASET_HASHES
    }
    if observed_dataset_hashes != EXPECTED_DATASET_HASHES:
        raise ValueError("Command 05B final dataset hashes changed")
    dataset_manifest_path = data_dir / "research/intraday/v1/development_bounded/resume_05b/dataset_manifest_v1.json"
    dataset_manifest = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
    partition_checks: dict[str, bool] = {}
    for window, key in ((5, "normalized_5m_dataset_hash"), (10, "derived_10m_dataset_hash"), (15, "derived_15m_dataset_hash")):
        entries = dataset_manifest["partitions"][f"{window}m"]
        valid = canonical_hash(entries) == EXPECTED_DATASET_HASHES[key]
        valid = valid and all(
            Path(row["path"]).exists() and _file_sha256(Path(row["path"])) == row["sha256"]
            for row in entries
        )
        partition_checks[f"{window}m"] = valid
    if not all(partition_checks.values()):
        raise ValueError("A frozen Command 05B intraday partition failed its hash check")
    guard_paths = [
        data_dir / "research/diagnostics/strategy/v1/registry/experiment_registry_v1.json",
        data_dir / "research/costs/v1/registry/cost_model_config_v1.json",
        data_dir / "research/costs/v1/registry/cost_scenarios_v1_preregistered.json",
        data_dir / "research/costs/v1/registry/cost_scenarios_v1.json",
        data_dir / "research/temporal_validation/v1/manifests/temporal_harness_config_v1.json",
        data_dir / "research/temporal_validation/v1/manifests/temporal_window_manifest_v1.json",
        data_dir / "reports/intraday_architecture_v1_summary.json",
        data_dir / "research/intraday/v1/real_intraday_pilot_manifest_v1.json",
        data_dir / "reports/groww_intraday_audit_05a_summary.json",
        data_dir / "research/intraday/v1/groww_root_cause_audit_05a/audit_manifest_v1.json",
        scope_path,
        plan_path,
        summary_path,
        dataset_manifest_path,
        data_dir / "research/intraday/v1/development_bounded/resume_05b/resume_manifest_v1.json",
    ]
    missing = [str(path) for path in guard_paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Frozen guard artifacts unavailable: {missing}")
    diagnostic_registry = json.loads(guard_paths[0].read_text(encoding="utf-8"))
    diagnostic_experiments = diagnostic_registry.get("experiments", [])
    diagnostic_registry_experiment_hashes = {
        str(row["experiment_id"]): {
            "parameter_hash": str(row["parameter_hash"]),
            "pre_registration_hash": str(row["pre_registration_hash"]),
        }
        for row in diagnostic_experiments
    }
    if len(diagnostic_registry_experiment_hashes) != len(diagnostic_experiments):
        raise ValueError("Frozen diagnostic registry has duplicate experiment IDs")
    return {
        "baseline_chain_hashes": chain,
        "baseline_chain_expected_checks": chain_checks,
        "diagnostic_registry_sha256": _file_sha256(guard_paths[0]),
        "diagnostic_registry_experiment_count": len(diagnostic_experiments),
        "diagnostic_registry_experiment_hashes": diagnostic_registry_experiment_hashes,
        "diagnostic_registry_semantic_hash": canonical_hash(
            diagnostic_registry_experiment_hashes
        ),
        "cost_model_config_sha256": _file_sha256(guard_paths[1]),
        "temporal_harness_config_hash": DEFAULT_TEMPORAL_CONFIG.config_hash(),
        "scope_hash": scope["scope_hash"],
        "request_plan_hash": plan["request_plan_hash"],
        "command_05b_dataset_hashes": observed_dataset_hashes,
        "command_05b_partition_checks": partition_checks,
        "guard_file_hashes": {
            path.relative_to(root).as_posix(): _file_sha256(path) for path in guard_paths
        },
    }


def _prereg_baseline_dependency(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Select immutable semantic guards for the pre-registration fingerprint.

    Whole-file guard hashes remain in the before/after audit, but are deliberately
    excluded here because prior diagnostic runners may rewrite non-semantic fields
    such as timestamps and result fingerprints during an independent test run.
    """
    keys = (
        "baseline_chain_hashes",
        "diagnostic_registry_experiment_count",
        "diagnostic_registry_experiment_hashes",
        "diagnostic_registry_semantic_hash",
        "cost_model_config_sha256",
        "temporal_harness_config_hash",
        "scope_hash",
        "request_plan_hash",
        "command_05b_dataset_hashes",
    )
    return {key: snapshot[key] for key in keys}


def _required_session_dates(
    population: Sequence[Mapping[str, Any]], sources: Mapping[str, Mapping[str, Any]]
) -> dict[str, set[date]]:
    result: dict[str, set[date]] = defaultdict(set)
    for row in population:
        source = sources[row["opportunity_id"]]
        for index in range(1, 5):
            value = str(source.get(f"session_date_{index}", ""))
            if value:
                result[row["symbol"]].add(date.fromisoformat(value))
    return dict(result)


def _frozen_path_group(source: Mapping[str, Any]) -> str:
    touch = str(source.get("first_touch_outcome", ""))
    if touch == "STOP_FIRST":
        return "STOP_FIRST"
    if touch == "TARGET_FIRST":
        return "TARGET_FIRST"
    if "AMBIGUOUS" in touch:
        return "AMBIGUOUS"
    mfe = optional_decimal(source.get("mfe_r_4")) or Decimal("0")
    return "NEITHER_WITH_POSITIVE_MFE" if mfe > 0 else "NEITHER_WEAK"


def _path_metrics(
    *,
    confirmation_price: Decimal,
    confirmation_timestamp: datetime,
    stop: Decimal,
    target: Decimal,
    risk: Decimal,
    all_bars: Sequence[CanonicalIntradayBar],
    max_holding_date: date,
) -> dict[str, Any]:
    post = sorted(
        (
            row
            for row in all_bars
            if row.bar_start >= confirmation_timestamp and row.trading_date <= max_holding_date
        ),
        key=lambda row: row.bar_start,
    )
    if not post:
        return {
            "post_confirmation_bar_count": 0,
            "post_first_touch": "NEITHER",
            "post_first_touch_timestamp": None,
            "time_to_first_touch_minutes": None,
            "mfe_from_confirmation_pct": None,
            "mae_from_confirmation_pct": None,
            "mfe_confirm_r": None,
            "mae_confirm_r": None,
            "post_path_quality_group": "NEITHER_WEAK",
        }
    result = evaluate_first_touch(
        entry_timestamp=confirmation_timestamp,
        stop_price=stop,
        target_price=target,
        bars=post,
        max_holding_date=max_holding_date,
        ambiguity_policy=AmbiguityPolicy.AMBIGUOUS_EXCLUDED,
    )
    event_timestamp = (
        result.first_stop_touch_timestamp or result.first_target_touch_timestamp
    )
    max_high = max(row.high for row in post)
    min_low = min(row.low for row in post)
    mfe = max(Decimal("0"), max_high - confirmation_price)
    mae = max(Decimal("0"), confirmation_price - min_low)
    first_touch = str(result.first_touch)
    if first_touch in {str(FirstTouch.STOP_FIRST), str(FirstTouch.GAP_THROUGH_STOP)}:
        group = "STOP_FIRST"
    elif first_touch in {str(FirstTouch.TARGET_FIRST), str(FirstTouch.GAP_THROUGH_TARGET)}:
        group = "TARGET_FIRST"
    elif first_touch == str(FirstTouch.INTRABAR_SEQUENCE_AMBIGUOUS):
        group = "AMBIGUOUS"
    else:
        group = "NEITHER_WITH_POSITIVE_MFE" if mfe > 0 else "NEITHER_WEAK"
    return {
        "post_confirmation_bar_count": len(post),
        "post_first_touch": first_touch,
        "post_policy_resolution": str(result.policy_resolution),
        "post_ambiguity_preserved": result.ambiguous_same_bar,
        "post_gap_status": result.gap_status,
        "post_first_touch_timestamp": event_timestamp,
        "time_to_first_touch_minutes": (
            Decimal(str((event_timestamp - confirmation_timestamp).total_seconds())) / Decimal("60")
            if event_timestamp is not None
            else None
        ),
        "mfe_from_confirmation_pct": mfe * Decimal("100") / confirmation_price,
        "mae_from_confirmation_pct": mae * Decimal("100") / confirmation_price,
        "mfe_confirm_r": mfe / risk,
        "mae_confirm_r": mae / risk,
        "post_path_quality_group": group,
    }


def build_window_record(
    *,
    manifest_row: Mapping[str, Any],
    source: Mapping[str, Any],
    risk_row: Mapping[str, Any],
    window: int,
    bars_by_window: Mapping[int, Mapping[tuple[str, date], Sequence[CanonicalIntradayBar]]],
) -> dict[str, Any]:
    symbol = str(manifest_row["symbol"])
    entry_date = date.fromisoformat(str(manifest_row["entry_date"]))
    raw_five = tuple(bars_by_window[5].get((symbol, entry_date), ()))
    raw_confirmation_bars = tuple(
        bars_by_window[window].get((symbol, entry_date), ())
    )
    frozen_open = Decimal(str(manifest_row["frozen_next_open"]))
    stop = Decimal(str(manifest_row["frozen_stop"]))
    target = Decimal(str(manifest_row["frozen_target"]))
    frozen_rr = Decimal(str(manifest_row["frozen_effective_rr"]))
    base = {
        **dict(manifest_row),
        "window_minutes": window,
        "data_available": False,
        "confirmation_feasibility": "DATA_UNAVAILABLE",
    }
    try:
        price_basis_scale = _price_basis_scale(frozen_open, raw_five)
    except ValueError:
        return base
    five = _scale_bars(raw_five, price_basis_scale)
    confirmation_bars = _scale_bars(raw_confirmation_bars, price_basis_scale)
    try:
        price, timestamp, causal_bars = confirmation_reference(five, confirmation_bars, window)
    except ValueError:
        return base
    drift = (price / frozen_open - 1) * Decimal("100")
    confirm_rr, risk, reward = confirmation_rr(price, stop, target)
    touch = preconfirmation_touch_state(causal_bars, stop, target)
    feasibility = confirmation_feasibility(touch, confirm_rr)
    vwap_points = calculate_session_vwap(causal_bars)
    vwap = vwap_points[-1].vwap if vwap_points else None
    calendar = NseCashSessionCalendar.from_trading_dates((entry_date,))
    atr = optional_decimal(risk_row.get("atr_14"))
    opening = calculate_opening_range(
        five,
        window_minutes=window,
        calendar=calendar,
        daily_atr=atr,
    )
    all_dates = [
        date.fromisoformat(str(source[f"session_date_{index}"]))
        for index in range(1, 5)
        if str(source.get(f"session_date_{index}", ""))
    ]
    all_five = [
        bar
        for trading_date in all_dates
        for bar in bars_by_window[5].get((symbol, trading_date), ())
    ]
    all_five = list(_scale_bars(all_five, price_basis_scale))
    path = (
        _path_metrics(
            confirmation_price=price,
            confirmation_timestamp=timestamp,
            stop=stop,
            target=target,
            risk=risk,
            all_bars=all_five,
            max_holding_date=max(all_dates),
        )
        if feasibility == "FEASIBLE" and risk is not None and risk > 0
        else {
            "post_confirmation_bar_count": 0,
            "post_first_touch": None,
            "post_first_touch_timestamp": None,
            "time_to_first_touch_minutes": None,
            "mfe_from_confirmation_pct": None,
            "mae_from_confirmation_pct": None,
            "mfe_confirm_r": None,
            "mae_confirm_r": None,
            "post_path_quality_group": None,
        }
    )
    frozen_mfe = optional_decimal(source.get("mfe_r_4"))
    frozen_group = _frozen_path_group(source)
    early = early_path_classification(price, frozen_open)
    post_stop_first = path.get("post_first_touch") in {
        str(FirstTouch.STOP_FIRST),
        str(FirstTouch.GAP_THROUGH_STOP),
    }
    good_path = str(source.get("first_touch_outcome")) == "TARGET_FIRST" or (
        frozen_mfe is not None and frozen_mfe >= 1
    )
    return {
        **base,
        "data_available": True,
        "raw_confirmation_price": price / price_basis_scale,
        "raw_t1_session_open": frozen_open / price_basis_scale,
        "price_basis_scale_factor": price_basis_scale,
        "price_basis_alignment": "CAUSAL_T1_OPEN_RATIO_TO_FROZEN_DAILY_BASIS",
        "confirmation_price": price,
        "confirmation_timestamp": timestamp,
        "causal_source_bar_count": len(causal_bars),
        "causal_cutoff_verified": all(row.bar_end <= timestamp for row in causal_bars),
        "price_change_from_open_pct": drift,
        "price_drift_bucket": price_drift_bucket(drift),
        "confirmation_risk": risk,
        "confirmation_reward": reward,
        "confirmation_effective_rr": confirm_rr,
        "rr_delta": confirm_rr - frozen_rr if confirm_rr is not None else None,
        "rr_viability": rr_bucket(confirm_rr) if confirm_rr is not None else "CONFIRMATION_STRUCTURE_INVALID",
        "remaining_target_distance_pct": (target - price) * Decimal("100") / price,
        "remaining_stop_distance_pct": (price - stop) * Decimal("100") / price,
        "stop_touched_before_confirmation": touch["stop_touched"],
        "target_touched_before_confirmation": touch["target_touched"],
        "preconfirmation_first_touch": touch["first_touch"],
        "preconfirmation_gap_status": touch["gap_status"],
        "preconfirmation_ambiguity": touch["ambiguous"],
        "confirmation_feasibility": feasibility,
        "early_path": early,
        "false_start": early == "EARLY_WEAKNESS" and post_stop_first,
        "frozen_path_quality_group": frozen_group,
        "potentially_filterable_failure": frozen_group == "STOP_FIRST" and early == "EARLY_WEAKNESS",
        "good_path": good_path,
        "good_trade_sacrifice": good_path and early == "EARLY_WEAKNESS",
        "confirmation_vwap": vwap,
        "confirmation_price_above_vwap": price > vwap if vwap is not None else None,
        "distance_to_vwap_pct": (price / vwap - 1) * Decimal("100") if vwap else None,
        "vwap_context": vwap_classification(price, vwap),
        "opening_range_high": opening.high,
        "opening_range_low": opening.low,
        "opening_range_width": opening.high - opening.low,
        "opening_range_width_pct": opening.range_pct,
        "opening_range_width_atr": opening.range_atr_relative,
        "opening_range_context": opening_range_classification(price, opening.high, opening.low),
        "daily_gap_pct": optional_decimal(source.get("gap_from_t_close_pct")),
        "daily_gap_band": source.get("gap_category"),
        "daily_mfe_r": frozen_mfe,
        "daily_mae_r": optional_decimal(source.get("mae_r_4")),
        "daily_path_result": source.get("first_touch_outcome"),
        "unexplained_mismatch_flag": symbol == "SCHAEFFLER" and date(2023, 9, 1) in all_dates,
        **path,
    }


def _values(rows: Sequence[Mapping[str, Any]], field: str) -> list[Decimal]:
    return [Decimal(str(row[field])) for row in rows if row.get(field) is not None and str(row.get(field)) != ""]


def _mean(rows: Sequence[Mapping[str, Any]], field: str) -> Decimal | None:
    values = _values(rows, field)
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else None


def _median(rows: Sequence[Mapping[str, Any]], field: str) -> Decimal | None:
    values = sorted(_values(rows, field))
    if not values:
        return None
    middle = len(values) // 2
    return values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2


def _percentile(rows: Sequence[Mapping[str, Any]], field: str, probability: Decimal) -> Decimal | None:
    values = sorted(_values(rows, field))
    if not values:
        return None
    position = probability * Decimal(len(values) - 1)
    low = int(position)
    high = math.ceil(position)
    if low == high:
        return values[low]
    fraction = position - Decimal(low)
    return values[low] + (values[high] - values[low]) * fraction


def _rate(numerator: int, denominator: int) -> Decimal | None:
    return Decimal(numerator) * Decimal("100") / Decimal(denominator) if denominator else None


def _population_slice(rows: Sequence[Mapping[str, Any]], population: str) -> list[Mapping[str, Any]]:
    if population == "ALL_STRICT_COVERED":
        return list(rows)
    if population == "ADMITTED_STRICT_COVERED":
        return [row for row in rows if row.get("is_admitted")]
    raise ValueError(f"Unknown population: {population}")


def window_profile(rows: Sequence[Mapping[str, Any]], population: str) -> dict[str, Any]:
    selected = _population_slice(rows, population)
    available = [row for row in selected if row.get("data_available")]
    feasible = [row for row in available if row.get("confirmation_feasibility") == "FEASIBLE"]
    stop_count = sum(_truthy(row.get("stop_touched_before_confirmation")) for row in available)
    target_count = sum(_truthy(row.get("target_touched_before_confirmation")) for row in available)
    ambiguity = sum(row.get("confirmation_feasibility") == "INTRABAR_AMBIGUOUS" for row in available)
    invalid = sum(row.get("confirmation_feasibility") == "STRUCTURE_INVALID_AT_CONFIRMATION" for row in available)
    structure_rows = [row for row in available if row.get("confirmation_effective_rr") is not None]
    post = [row for row in feasible if row.get("mfe_confirm_r") is not None]
    return {
        "population": population,
        "window_minutes": int(rows[0]["window_minutes"]) if rows else None,
        "source_opportunity_count": len(selected),
        "data_available_count": len(available),
        "feasible_count": len(feasible),
        "feasible_rate_pct": _rate(len(feasible), len(available)),
        "stop_before_confirmation_count": stop_count,
        "stop_before_confirmation_rate_pct": _rate(stop_count, len(available)),
        "target_before_confirmation_count": target_count,
        "target_before_confirmation_rate_pct": _rate(target_count, len(available)),
        "ambiguity_count": ambiguity,
        "invalid_structure_count": invalid,
        "invalid_structure_rate_pct": _rate(invalid, len(available)),
        "mean_price_drift_pct": _mean(available, "price_change_from_open_pct"),
        "median_price_drift_pct": _median(available, "price_change_from_open_pct"),
        "p25_price_drift_pct": _percentile(available, "price_change_from_open_pct", Decimal("0.25")),
        "p75_price_drift_pct": _percentile(available, "price_change_from_open_pct", Decimal("0.75")),
        "positive_drift_rate_pct": _rate(sum(Decimal(str(row["price_change_from_open_pct"])) > 0 for row in available), len(available)),
        "chase_gt_1_pct_rate": _rate(sum(Decimal(str(row["price_change_from_open_pct"])) > 1 for row in available), len(available)),
        "chase_gt_2_pct_rate": _rate(sum(Decimal(str(row["price_change_from_open_pct"])) > 2 for row in available), len(available)),
        "cheaper_than_open_rate_pct": _rate(sum(Decimal(str(row["price_change_from_open_pct"])) < 0 for row in available), len(available)),
        "mean_confirmation_rr": _mean(structure_rows, "confirmation_effective_rr"),
        "median_confirmation_rr": _median(structure_rows, "confirmation_effective_rr"),
        "median_frozen_open_rr": _median(available, "frozen_effective_rr"),
        "mean_rr_delta": _mean(structure_rows, "rr_delta"),
        "median_rr_delta": _median(structure_rows, "rr_delta"),
        "rr_below_1_5_count": sum(Decimal(str(row["confirmation_effective_rr"])) < Decimal("1.5") for row in structure_rows),
        "rr_below_1_5_rate_pct": _rate(sum(Decimal(str(row["confirmation_effective_rr"])) < Decimal("1.5") for row in structure_rows), len(structure_rows)),
        "rr_retaining_ge_2_count": sum(Decimal(str(row["confirmation_effective_rr"])) >= 2 for row in structure_rows),
        "rr_retaining_ge_2_rate_pct": _rate(sum(Decimal(str(row["confirmation_effective_rr"])) >= 2 for row in structure_rows), len(structure_rows)),
        "median_remaining_target_distance_pct": _median(available, "remaining_target_distance_pct"),
        "median_remaining_stop_distance_pct": _median(available, "remaining_stop_distance_pct"),
        "median_mfe_from_confirmation_pct": _median(post, "mfe_from_confirmation_pct"),
        "median_mae_from_confirmation_pct": _median(post, "mae_from_confirmation_pct"),
        "median_mfe_confirm_r": _median(post, "mfe_confirm_r"),
        "median_mae_confirm_r": _median(post, "mae_confirm_r"),
        "post_stop_first_count": sum(row.get("post_path_quality_group") == "STOP_FIRST" for row in feasible),
        "post_target_first_count": sum(row.get("post_path_quality_group") == "TARGET_FIRST" for row in feasible),
        "post_neither_count": sum(str(row.get("post_path_quality_group", "")).startswith("NEITHER") for row in feasible),
        "post_ambiguous_count": sum(row.get("post_path_quality_group") == "AMBIGUOUS" for row in feasible),
        "sample_safety": sample_safety(len(selected)),
    }


def _baseline_profile(
    population: Sequence[Mapping[str, Any]], sources: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for group in POPULATIONS:
        selected = _population_slice(population, group)
        source_rows = [sources[row["opportunity_id"]] for row in selected]
        result.append(
            {
                "population": group,
                "count": len(selected),
                "score_distribution": dict(sorted(Counter(row["score"] for row in selected).items())),
                "candidate_stage_distribution": dict(sorted(Counter(str(row["candidate_stage"]) for row in selected).items())),
                "setup_quality_distribution": dict(sorted(Counter(str(row["setup_quality"]) for row in selected).items())),
                "regime_distribution": dict(sorted(Counter(str(row["regime_state"]) for row in selected).items())),
                "gap_band_distribution": dict(sorted(Counter(str(row.get("gap_category")) for row in source_rows).items())),
                "median_gap_pct": _median(source_rows, "gap_from_t_close_pct"),
                "median_frozen_rr": _median(selected, "frozen_effective_rr"),
                "median_stop_distance_pct": statistics.median(
                    [(Decimal(str(row["frozen_next_open"])) - Decimal(str(row["frozen_stop"]))) * 100 / Decimal(str(row["frozen_next_open"])) for row in selected]
                ),
                "median_target_distance_pct": statistics.median(
                    [(Decimal(str(row["frozen_target"])) - Decimal(str(row["frozen_next_open"]))) * 100 / Decimal(str(row["frozen_next_open"])) for row in selected]
                ),
                "median_subsequent_mfe_r": _median(source_rows, "mfe_r_4"),
                "median_subsequent_mae_r": _median(source_rows, "mae_r_4"),
                "daily_path_distribution": dict(sorted(Counter(str(row.get("first_touch_outcome")) for row in source_rows).items())),
                "sample_safety": sample_safety(len(selected)),
            }
        )
    return result


def _group_path_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    feasible = [row for row in rows if row.get("confirmation_feasibility") == "FEASIBLE"]
    return {
        "count": len(rows),
        "feasible_count": len(feasible),
        "median_price_drift_pct": _median(rows, "price_change_from_open_pct"),
        "median_confirmation_rr": _median(rows, "confirmation_effective_rr"),
        "median_mfe_confirm_r": _median(feasible, "mfe_confirm_r"),
        "median_mae_confirm_r": _median(feasible, "mae_confirm_r"),
        "stop_first_count": sum(row.get("post_path_quality_group") == "STOP_FIRST" for row in feasible),
        "target_first_count": sum(row.get("post_path_quality_group") == "TARGET_FIRST" for row in feasible),
        "ambiguous_count": sum(row.get("post_path_quality_group") == "AMBIGUOUS" for row in feasible),
        "neither_count": sum(str(row.get("post_path_quality_group", "")).startswith("NEITHER") for row in feasible),
        "stop_first_rate_pct": _rate(sum(row.get("post_path_quality_group") == "STOP_FIRST" for row in feasible), len(feasible)),
        "target_first_rate_pct": _rate(sum(row.get("post_path_quality_group") == "TARGET_FIRST" for row in feasible), len(feasible)),
        "sample_safety": sample_safety(len(rows)),
    }


def _bucket_report(
    window_records: Mapping[int, Sequence[Mapping[str, Any]]],
    *,
    field: str,
    values: Sequence[str],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for window in WINDOWS:
        for population in POPULATIONS:
            selected = _population_slice(window_records[window], population)
            for value in values:
                cohort = [row for row in selected if row.get(field) == value]
                result.append(
                    {
                        "window_minutes": window,
                        "population": population,
                        field: value,
                        "rate_pct": _rate(len(cohort), len(selected)),
                        **_group_path_metrics(cohort),
                    }
                )
    return result


def _price_drift_report(window_records: Mapping[int, Sequence[Mapping[str, Any]]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for window in WINDOWS:
        for population in POPULATIONS:
            selected = _population_slice(window_records[window], population)
            for bucket in PRICE_DRIFT_BUCKETS:
                cohort = [row for row in selected if row.get("price_drift_bucket") == bucket]
                result.append(
                    {
                        "window_minutes": window,
                        "population": population,
                        "price_drift_bucket": bucket,
                        "count": len(cohort),
                        "rate_pct": _rate(len(cohort), len(selected)),
                        "median_price_drift_pct": _median(cohort, "price_change_from_open_pct"),
                        "median_confirmation_rr": _median(cohort, "confirmation_effective_rr"),
                        "sample_safety": sample_safety(len(cohort)),
                    }
                )
    return result


def _rr_report(window_records: Mapping[int, Sequence[Mapping[str, Any]]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for window in WINDOWS:
        for population in POPULATIONS:
            selected = _population_slice(window_records[window], population)
            for bucket in (*RR_BUCKETS, "CONFIRMATION_STRUCTURE_INVALID"):
                cohort = [row for row in selected if row.get("rr_viability") == bucket]
                result.append(
                    {
                        "window_minutes": window,
                        "population": population,
                        "rr_viability": bucket,
                        "count": len(cohort),
                        "rate_pct": _rate(len(cohort), len(selected)),
                        "median_confirmation_rr": _median(cohort, "confirmation_effective_rr"),
                        "median_rr_delta": _median(cohort, "rr_delta"),
                        "median_target_distance_pct": _median(cohort, "remaining_target_distance_pct"),
                        "median_stop_distance_pct": _median(cohort, "remaining_stop_distance_pct"),
                        "sample_safety": sample_safety(len(cohort)),
                    }
                )
    return result


def _false_start_report(window_records: Mapping[int, Sequence[Mapping[str, Any]]]) -> list[dict[str, Any]]:
    result = _bucket_report(window_records, field="early_path", values=EARLY_PATH_BUCKETS)
    for row in result:
        selected = [
            item
            for item in _population_slice(window_records[row["window_minutes"]], row["population"])
            if item.get("early_path") == row["early_path"]
        ]
        row.update(
            {
                "false_start_count": sum(_truthy(item.get("false_start")) for item in selected),
                "false_start_rate_pct": _rate(sum(_truthy(item.get("false_start")) for item in selected), len(selected)),
                "potentially_filterable_failure_count": sum(_truthy(item.get("potentially_filterable_failure")) for item in selected),
                "good_trade_sacrifice_count": sum(_truthy(item.get("good_trade_sacrifice")) for item in selected),
            }
        )
    return result


def _context_report(window_records: Mapping[int, Sequence[Mapping[str, Any]]]) -> list[dict[str, Any]]:
    dimensions: tuple[tuple[str, Callable[[Mapping[str, Any]], str]], ...] = (
        ("score", lambda row: str(row["score"])),
        ("setup_quality", lambda row: str(row["setup_quality"])),
        ("candidate_stage", lambda row: str(row["candidate_stage"])),
        ("regime_state", lambda row: str(row["regime_state"])),
        ("frozen_rr_band", lambda row: rr_bucket(Decimal(str(row["frozen_effective_rr"])))),
        ("opening_gap_band", lambda row: str(row.get("daily_gap_band"))),
    )
    result: list[dict[str, Any]] = []
    for window in WINDOWS:
        for population in POPULATIONS:
            selected = _population_slice(window_records[window], population)
            for dimension, selector in dimensions:
                for value in sorted({selector(row) for row in selected}):
                    cohort = [row for row in selected if selector(row) == value]
                    result.append(
                        {
                            "window_minutes": window,
                            "population": population,
                            "dimension": dimension,
                            "value": value,
                            **_group_path_metrics(cohort),
                            "early_weakness_rate_pct": _rate(sum(row.get("early_path") == "EARLY_WEAKNESS" for row in cohort), len(cohort)),
                            "false_start_rate_pct": _rate(sum(_truthy(row.get("false_start")) for row in cohort), len(cohort)),
                        }
                    )
    return result


def _yearly_report(window_records: Mapping[int, Sequence[Mapping[str, Any]]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for year in (2022, 2023, 2024):
        for window in WINDOWS:
            for population in POPULATIONS:
                selected = [
                    row
                    for row in _population_slice(window_records[window], population)
                    if str(row["decision_date"]).startswith(str(year))
                ]
                profile = window_profile(selected, "ALL_STRICT_COVERED")
                profile["population"] = population
                profile["year"] = year
                profile["false_start_rate_pct"] = _rate(sum(_truthy(row.get("false_start")) for row in selected), len(selected))
                profile["above_vwap_rate_pct"] = _rate(sum(row.get("vwap_context") == "ABOVE_VWAP" for row in selected), len(selected))
                profile["above_or_high_rate_pct"] = _rate(sum(row.get("opening_range_context") == "ABOVE_OR_HIGH" for row in selected), len(selected))
                result.append(profile)
    return result


def _failure_good_signal(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    failures = [row for row in rows if row.get("frozen_path_quality_group") == "STOP_FIRST"]
    good = [row for row in rows if row.get("good_path")]
    failure_weak = _rate(sum(row.get("early_path") == "EARLY_WEAKNESS" for row in failures), len(failures))
    good_weak = _rate(sum(row.get("early_path") == "EARLY_WEAKNESS" for row in good), len(good))
    signal = failure_weak - good_weak if failure_weak is not None and good_weak is not None else None
    return {
        "frozen_stop_first_count": len(failures),
        "frozen_stop_first_early_weakness_count": sum(row.get("early_path") == "EARLY_WEAKNESS" for row in failures),
        "frozen_stop_first_early_weakness_rate_pct": failure_weak,
        "good_path_count": len(good),
        "good_path_early_weakness_count": sum(row.get("early_path") == "EARLY_WEAKNESS" for row in good),
        "good_path_early_weakness_rate_pct": good_weak,
        "filter_signal_pp": signal,
    }


def _temporal_consistency(window_records: Mapping[int, Sequence[Mapping[str, Any]]]) -> tuple[str, list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    window_signs: dict[int, list[str]] = {}
    for window in WINDOWS:
        signs: list[str] = []
        for year in (2022, 2023, 2024):
            year_rows = [
                row
                for row in window_records[window]
                if str(row["decision_date"]).startswith(str(year))
            ]
            signal = _failure_good_signal(year_rows)
            value = signal["filter_signal_pp"]
            sign = (
                "INCONCLUSIVE"
                if value is None
                else "SUPPORTIVE"
                if value >= 10
                else "INVERSE"
                if value <= -10
                else "NEUTRAL"
            )
            signs.append(sign)
            evidence.append(
                {
                    "year": year,
                    "window_minutes": window,
                    "signal": sign,
                    **signal,
                    "sample_safety": sample_safety(len(year_rows)),
                }
            )
        window_signs[window] = signs
    supportive_windows = sum(
        signs.count("SUPPORTIVE") >= 2 and "INVERSE" not in signs
        for signs in window_signs.values()
    )
    all_supportive = all(signs.count("SUPPORTIVE") == 3 for signs in window_signs.values())
    mixed_direction = any("SUPPORTIVE" in signs and "INVERSE" in signs for signs in window_signs.values())
    inverse_windows = sum(signs.count("INVERSE") >= 2 for signs in window_signs.values())
    if all_supportive:
        result = "CONSISTENT"
    elif supportive_windows >= 2 and not mixed_direction:
        result = "MOSTLY_CONSISTENT"
    elif mixed_direction:
        result = "UNSTABLE"
    elif inverse_windows >= 2:
        result = "INVERSE_ACROSS_YEARS"
    else:
        result = "INCONCLUSIVE"
    return result, evidence


def _delay_cost(profiles: Mapping[int, Mapping[str, Any]]) -> tuple[str, dict[str, Any]]:
    very_high = False
    high = False
    low_all = True
    for profile in profiles.values():
        infeasible = Decimal("100") - Decimal(str(profile["feasible_rate_pct"] or 0))
        drift = Decimal(str(profile["median_price_drift_pct"] or 0))
        rr_delta = Decimal(str(profile["median_rr_delta"] or 0))
        target = Decimal(str(profile["target_before_confirmation_rate_pct"] or 0))
        invalid = Decimal(str(profile["invalid_structure_rate_pct"] or 0))
        very_high = very_high or drift > 1 or rr_delta < Decimal("-0.75") or infeasible > 20
        high = high or drift > Decimal("0.5") or rr_delta < Decimal("-0.5") or target > 5 or invalid > 10
        low_all = low_all and drift <= Decimal("0.2") and rr_delta >= Decimal("-0.25") and target <= 2 and invalid <= 2
    result = "VERY_HIGH" if very_high else "HIGH" if high else "LOW" if low_all else "MODERATE"
    return result, {"window_profiles": dict(profiles), "classification_rules": CLASSIFICATION_RULES}


def _context_association(
    report: Sequence[Mapping[str, Any]], *, field: str, positive: str, reference: str
) -> tuple[str, list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    supportive = inverse = comparable = 0
    for window in WINDOWS:
        left = next(row for row in report if row["window_minutes"] == window and row["population"] == "ALL_STRICT_COVERED" and row[field] == positive)
        right = next(row for row in report if row["window_minutes"] == window and row["population"] == "ALL_STRICT_COVERED" and row[field] == reference)
        if min(int(left["count"]), int(right["count"])) < 30 or left["median_mfe_confirm_r"] is None or right["median_mfe_confirm_r"] is None:
            signal = "INCONCLUSIVE"
        else:
            comparable += 1
            mfe_delta = Decimal(str(left["median_mfe_confirm_r"])) - Decimal(str(right["median_mfe_confirm_r"]))
            stop_delta = Decimal(str(left["stop_first_rate_pct"] or 0)) - Decimal(str(right["stop_first_rate_pct"] or 0))
            signal = "SUPPORTIVE" if mfe_delta >= Decimal("0.1") and stop_delta <= 5 else "INVERSE" if mfe_delta <= Decimal("-0.1") else "NEUTRAL"
            supportive += signal == "SUPPORTIVE"
            inverse += signal == "INVERSE"
        evidence.append({"window_minutes": window, "signal": signal, "positive": left, "reference": right})
    if comparable == 0:
        result = "INCONCLUSIVE"
    elif supportive >= 2:
        result = "PROMISING_FOR_CONTROLLED_TEST"
    elif supportive == 1 and inverse == 0:
        result = "WEAK_ASSOCIATION"
    elif supportive and inverse:
        result = "MIXED"
    else:
        result = "NO_CLEAR_ASSOCIATION"
    return result, evidence


def _window_classifications(
    window_records: Mapping[int, Sequence[Mapping[str, Any]]],
    profiles: Mapping[int, Mapping[str, Any]],
    delay_cost: str,
    temporal_result: str,
) -> tuple[dict[int, str], dict[int, Any]]:
    results: dict[int, str] = {}
    evidence: dict[int, Any] = {}
    for window in WINDOWS:
        rows = window_records[window]
        signal = _failure_good_signal(rows)
        value = signal["filter_signal_pp"]
        profile = profiles[window]
        adequate = len(rows) >= 300
        rr_preserved = Decimal(str(profile["median_rr_delta"] or -999)) >= Decimal("-0.5") and Decimal(str(profile["invalid_structure_rate_pct"] or 0)) <= 10
        year_support = temporal_result in {"CONSISTENT", "MOSTLY_CONSISTENT"}
        acceptable_delay = delay_cost in {"LOW", "MODERATE"}
        if not adequate or value is None:
            result = ConfirmationResult.INCONCLUSIVE
        elif value >= 10 and acceptable_delay and rr_preserved and year_support:
            result = ConfirmationResult.PROMISING_FOR_CONTROLLED_TEST
        elif delay_cost in {"HIGH", "VERY_HIGH"} and value < 10:
            result = ConfirmationResult.LIKELY_HARMFUL
        elif value >= 10 or (value > 0 and rr_preserved):
            result = ConfirmationResult.MIXED
        else:
            result = ConfirmationResult.NO_CLEAR_BENEFIT
        results[window] = str(result)
        evidence[window] = {
            **signal,
            "adequate_sample": adequate,
            "rr_preserved": rr_preserved,
            "acceptable_delay": acceptable_delay,
            "year_support": year_support,
        }
    return results, evidence


def _false_start_classification(window_records: Mapping[int, Sequence[Mapping[str, Any]]]) -> tuple[str, dict[int, Any]]:
    evidence = {window: _failure_good_signal(window_records[window]) for window in WINDOWS}
    values = [row["filter_signal_pp"] for row in evidence.values() if row["filter_signal_pp"] is not None]
    strong = sum(value >= 20 for value in values)
    supportive = sum(value >= 10 for value in values)
    inverse = sum(value <= -10 for value in values)
    if len(values) < 3:
        result = "INCONCLUSIVE"
    elif strong >= 2:
        result = "PROMISING_FOR_CONTROLLED_TEST"
    elif supportive >= 2 and inverse == 0:
        result = "PARTIAL"
    elif supportive and inverse:
        result = "MIXED"
    else:
        result = "NO_CLEAR_VALUE"
    return result, evidence


def _build_pilot(
    window_records: Mapping[int, Sequence[Mapping[str, Any]]]
) -> dict[str, Any]:
    definitions: list[tuple[str, int | None, Callable[[Mapping[str, Any]], bool]]] = [
        ("FEASIBLE_5M", 5, lambda row: row.get("confirmation_feasibility") == "FEASIBLE"),
        ("FEASIBLE_10M", 10, lambda row: row.get("confirmation_feasibility") == "FEASIBLE"),
        ("FEASIBLE_15M", 15, lambda row: row.get("confirmation_feasibility") == "FEASIBLE"),
        ("STOP_TOUCHED_BEFORE_5M", 5, lambda row: _truthy(row.get("stop_touched_before_confirmation"))),
        ("STOP_TOUCHED_BEFORE_15M", 15, lambda row: _truthy(row.get("stop_touched_before_confirmation"))),
        ("TARGET_TOUCHED_BEFORE_CONFIRMATION", None, lambda row: _truthy(row.get("target_touched_before_confirmation"))),
        ("CONFIRMATION_ABOVE_VWAP", None, lambda row: row.get("vwap_context") == "ABOVE_VWAP"),
        ("CONFIRMATION_BELOW_VWAP", None, lambda row: row.get("vwap_context") == "BELOW_VWAP"),
        ("CONFIRMATION_ABOVE_OR_HIGH", None, lambda row: row.get("opening_range_context") == "ABOVE_OR_HIGH"),
        ("CONFIRMATION_INSIDE_OR", None, lambda row: row.get("opening_range_context") == "INSIDE_OR"),
        ("POSITIVE_DRIFT_GT_1", None, lambda row: row.get("price_change_from_open_pct") is not None and Decimal(str(row["price_change_from_open_pct"])) > 1),
        ("NEGATIVE_DRIFT", None, lambda row: row.get("price_change_from_open_pct") is not None and Decimal(str(row["price_change_from_open_pct"])) < 0),
        ("RR_FALLS_BELOW_1_5", None, lambda row: row.get("confirmation_effective_rr") is not None and Decimal(str(row["confirmation_effective_rr"])) < Decimal("1.5")),
        ("GAP_THROUGH_STOP_POST_CONFIRMATION", None, lambda row: row.get("post_gap_status") == "GAP_THROUGH_STOP"),
    ]
    cases: list[dict[str, Any]] = []
    all_rows = [row for window in WINDOWS for row in window_records[window]]
    for category, window, predicate in definitions:
        candidates = window_records[window] if window is not None else all_rows
        selected = next((row for row in candidates if predicate(row)), None)
        if selected is None:
            cases.append({"category": category, "availability": "NOT_AVAILABLE", "validation_result": "NOT_AVAILABLE"})
            continue
        checks = {
            "development_only": "2022-01-01" <= str(selected["decision_date"]) <= "2024-12-31",
            "confirmation_timestamp_present": selected.get("confirmation_timestamp") is not None,
            "confirmation_close_present": selected.get("confirmation_price") is not None,
            "stop_target_present": selected.get("frozen_stop") is not None and selected.get("frozen_target") is not None,
            "vwap_present": selected.get("confirmation_vwap") is not None,
            "or_state_present": selected.get("opening_range_context") in OR_BUCKETS,
            "price_drift_recomputed": Decimal(str(selected["price_change_from_open_pct"])) == (Decimal(str(selected["confirmation_price"])) / Decimal(str(selected["frozen_next_open"])) - 1) * 100,
            "rr_recomputed": selected.get("confirmation_effective_rr") is None or Decimal(str(selected["confirmation_effective_rr"])) == (Decimal(str(selected["frozen_target"])) - Decimal(str(selected["confirmation_price"]))) / (Decimal(str(selected["confirmation_price"])) - Decimal(str(selected["frozen_stop"]))),
            "causal_cutoff": _truthy(selected.get("causal_cutoff_verified")),
            "bucket_assignment": selected.get("price_drift_bucket") == price_drift_bucket(Decimal(str(selected["price_change_from_open_pct"]))),
            "post_path_present_when_feasible": selected.get("confirmation_feasibility") != "FEASIBLE" or selected.get("post_confirmation_bar_count", 0) > 0,
        }
        cases.append(
            {
                "category": category,
                "availability": "AVAILABLE",
                "validation_result": "PASS" if all(checks.values()) else "FAIL",
                "checks": checks,
                "opportunity_id": selected["opportunity_id"],
                "symbol": selected["symbol"],
                "decision_date": selected["decision_date"],
                "entry_date": selected["entry_date"],
                "window_minutes": selected["window_minutes"],
                "T1_open": selected["frozen_next_open"],
                "confirmation_timestamp": selected["confirmation_timestamp"],
                "confirmation_close": selected["confirmation_price"],
                "stop": selected["frozen_stop"],
                "target": selected["frozen_target"],
                "vwap": selected["confirmation_vwap"],
                "opening_range_state": selected["opening_range_context"],
                "price_drift_pct": selected["price_change_from_open_pct"],
                "confirmation_rr": selected["confirmation_effective_rr"],
                "preconfirmation_stop_touch": selected["stop_touched_before_confirmation"],
                "preconfirmation_target_touch": selected["target_touched_before_confirmation"],
                "post_confirmation_path": selected.get("post_first_touch"),
                "mfe_confirm_r": selected.get("mfe_confirm_r"),
                "mae_confirm_r": selected.get("mae_confirm_r"),
                "bucket": selected["price_drift_bucket"],
            }
        )
    return {
        "cases": cases,
        "available_count": sum(row["availability"] == "AVAILABLE" for row in cases),
        "not_available_count": sum(row["availability"] == "NOT_AVAILABLE" for row in cases),
        "failed_count": sum(row["validation_result"] == "FAIL" for row in cases),
        "passed": all(row["validation_result"] in {"PASS", "NOT_AVAILABLE"} for row in cases),
    }


def _git_ignored(repo_root: Path, path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", path], cwd=repo_root, text=True, capture_output=True, check=False
    )
    return result.returncode == 0


def _storage(paths: Sequence[Path]) -> dict[str, Any]:
    existing = [path for path in paths if path.exists()]
    return {
        "artifact_count": len(existing),
        "bytes": sum(path.stat().st_size for path in existing),
        "paths": [str(path) for path in existing],
    }


def run_intraday_confirmation_diagnostic(
    *,
    repo_root: Path,
    tests_passed: bool = False,
    frontend_build_passed: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    root = Path(repo_root)
    notify = progress or (lambda _message: None)
    notify("Verifying the frozen baseline chain and Command 05/05A/05B artifacts")
    baseline_before = _baseline_snapshot(root)
    population, sources, context = _population_rows(root)
    population_hash = freeze_population(population)
    artifact_root = _artifact_root(root)
    report_root = _report_root(root)
    preregistration = build_preregistration(
        population_hash, _prereg_baseline_dependency(baseline_before)
    )
    prereg_path = artifact_root / "registry/intraday_confirmation_registry_v1_preregistered.json"
    population_manifest_path = artifact_root / "population_manifest_v1.json"
    _write_json(population_manifest_path, {"diagnostic_version": DIAGNOSTIC_VERSION, "profile": PROFILE, "intraday_confirmation_population_hash": population_hash, "rows": population})
    _write_json(prereg_path, preregistration)
    notify("Population frozen and exactly ten experiments pre-registered before empirical metrics")

    required_dates = _required_session_dates(population, sources)
    bars_by_window = _load_bars(root, required_dates)
    records: dict[int, list[dict[str, Any]]] = {window: [] for window in WINDOWS}
    for index, manifest_row in enumerate(population, start=1):
        source = sources[manifest_row["opportunity_id"]]
        risk = context["risk_rows"].get(manifest_row["opportunity_id"], {})
        for window in WINDOWS:
            records[window].append(
                build_window_record(
                    manifest_row=manifest_row,
                    source=source,
                    risk_row=risk,
                    window=window,
                    bars_by_window=bars_by_window,
                )
            )
        if index % 250 == 0:
            notify(f"Computed causal 5m/10m/15m references for {index}/{len(population)} frozen opportunities")

    pilot = _build_pilot(records)
    if not pilot["passed"]:
        raise ValueError("Real DEVELOPMENT pilot validation failed")
    notify("Real-case pilot passed; unavailable empirical categories were explicitly retained as NOT_AVAILABLE")

    baseline_profile = _baseline_profile(population, sources)
    profiles_by_window = {
        window: {
            population_name: window_profile(records[window], population_name)
            for population_name in POPULATIONS
        }
        for window in WINDOWS
    }
    source_profiles = {window: profiles_by_window[window]["ALL_STRICT_COVERED"] for window in WINDOWS}
    price_drift_rows = _price_drift_report(records)
    rr_rows = _rr_report(records)
    vwap_rows = _bucket_report(records, field="vwap_context", values=VWAP_BUCKETS)
    opening_rows = _bucket_report(records, field="opening_range_context", values=OR_BUCKETS)
    false_rows = _false_start_report(records)
    context_rows = _context_report(records)
    yearly_rows = _yearly_report(records)

    temporal_result, temporal_evidence = _temporal_consistency(records)
    delay_result, delay_evidence = _delay_cost(source_profiles)
    false_result, false_evidence = _false_start_classification(records)
    vwap_result, vwap_evidence = _context_association(vwap_rows, field="vwap_context", positive="ABOVE_VWAP", reference="BELOW_VWAP")
    opening_result, opening_evidence = _context_association(opening_rows, field="opening_range_context", positive="ABOVE_OR_HIGH", reference="INSIDE_OR")
    confirmation_results, confirmation_evidence = _window_classifications(records, source_profiles, delay_result, temporal_result)
    hypothesis_supported = (
        any(value == "PROMISING_FOR_CONTROLLED_TEST" for value in confirmation_results.values())
        and false_result in {"PROMISING_FOR_CONTROLLED_TEST", "PARTIAL"}
        and delay_result in {"LOW", "MODERATE"}
        and temporal_result in {"CONSISTENT", "MOSTLY_CONSISTENT"}
        and all(source_profiles[window]["source_opportunity_count"] >= 300 for window in WINDOWS)
    )
    if hypothesis_supported:
        overall_result = "SUPPORTED_FOR_CONTROLLED_TEST"
    elif any(value == "PROMISING_FOR_CONTROLLED_TEST" for value in confirmation_results.values()):
        overall_result = "WEAKLY_SUPPORTED"
    elif any(value == "MIXED" for value in confirmation_results.values()):
        overall_result = "MIXED"
    elif all(value in {"NO_CLEAR_BENEFIT", "LIKELY_HARMFUL"} for value in confirmation_results.values()):
        overall_result = "NOT_SUPPORTED"
    else:
        overall_result = "INCONCLUSIVE"

    mismatch_ids = sorted({row["opportunity_id"] for row in records[5] if row.get("unexplained_mismatch_flag")})
    mismatch_sensitivity = {
        "known_session": "SCHAEFFLER|2023-09-01",
        "entered_population": bool(mismatch_ids),
        "affected_opportunity_ids": mismatch_ids,
        "with_observation": {window: _failure_good_signal(records[window]) for window in WINDOWS},
        "without_observation": {
            window: _failure_good_signal([row for row in records[window] if not row.get("unexplained_mismatch_flag")])
            for window in WINDOWS
        },
        "result_tuned_around_observation": False,
    }
    source_vs_admitted = [
        {
            "window_minutes": window,
            "metric": metric,
            "source_value": profiles_by_window[window]["ALL_STRICT_COVERED"].get(metric),
            "admitted_value": profiles_by_window[window]["ADMITTED_STRICT_COVERED"].get(metric),
        }
        for window in WINDOWS
        for metric in (
            "feasible_rate_pct",
            "median_price_drift_pct",
            "median_rr_delta",
            "median_mfe_confirm_r",
            "median_mae_confirm_r",
            "stop_before_confirmation_rate_pct",
            "target_before_confirmation_rate_pct",
        )
    ]

    experiment_results: dict[str, Any] = {
        "EXP-INTRACONF-001": baseline_profile,
        "EXP-INTRACONF-002": profiles_by_window[5],
        "EXP-INTRACONF-003": profiles_by_window[10],
        "EXP-INTRACONF-004": profiles_by_window[15],
        "EXP-INTRACONF-005": price_drift_rows,
        "EXP-INTRACONF-006": rr_rows,
        "EXP-INTRACONF-007": vwap_rows,
        "EXP-INTRACONF-008": opening_rows,
        "EXP-INTRACONF-009": false_rows,
        "EXP-INTRACONF-010": context_rows,
    }
    result_paths: list[Path] = [population_manifest_path, prereg_path]
    for experiment_id in EXPERIMENT_IDS:
        path = artifact_root / "runs" / experiment_id / "result.json"
        _write_json(
            path,
            {
                "experiment_id": experiment_id,
                "diagnostic_only": True,
                "promotion_allowed": False,
                "population_hash": population_hash,
                "result": experiment_results[experiment_id],
                "result_fingerprint": canonical_hash(experiment_results[experiment_id]),
                "status": "COMPLETE",
            },
        )
        result_paths.append(path)
    final_registry = {
        **preregistration,
        "experiments": [
            {
                **row,
                "status": "COMPLETE",
                "result_fingerprint": canonical_hash(experiment_results[row["experiment_id"]]),
            }
            for row in preregistration["experiments"]
        ],
    }
    registry_path = artifact_root / "registry/intraday_confirmation_registry_v1.json"
    _write_json(registry_path, final_registry)
    result_paths.append(registry_path)

    report_payloads: dict[str, Any] = {
        "intraday_confirmation_v1_population.csv": population,
        "intraday_confirmation_v1_5m.csv": records[5],
        "intraday_confirmation_v1_10m.csv": records[10],
        "intraday_confirmation_v1_15m.csv": records[15],
        "intraday_confirmation_v1_price_drift.csv": price_drift_rows,
        "intraday_confirmation_v1_rr_headroom.csv": rr_rows,
        "intraday_confirmation_v1_vwap.csv": vwap_rows,
        "intraday_confirmation_v1_opening_range.csv": opening_rows,
        "intraday_confirmation_v1_false_start.csv": false_rows,
        "intraday_confirmation_v1_contexts.csv": context_rows,
        "intraday_confirmation_v1_yearly.csv": yearly_rows,
        "intraday_confirmation_v1_pilot.csv": pilot["cases"],
    }
    report_paths: list[Path] = []
    for filename, payload in report_payloads.items():
        path = report_root / filename
        _write_csv(path, payload)
        report_paths.append(path)

    baseline_after = _baseline_snapshot(root)
    mutation_violations = sum(
        baseline_before.get(key) != baseline_after.get(key) for key in baseline_before
    )
    output_ignore_checks = {
        "backend_env": _git_ignored(root, "backend/.env"),
        "diagnostic_registry": _git_ignored(root, "data/research/diagnostics/intraday/v1/confirmation_command_01/registry/intraday_confirmation_registry_v1.json"),
        "diagnostic_reports": _git_ignored(root, "data/reports/intraday_confirmation_v1_summary.json"),
        "diagnostic_csv": _git_ignored(root, "data/reports/intraday_confirmation_v1_5m.csv"),
    }
    governance = {
        "strategy_v1_modified": False,
        "strategy_v2_created": False,
        "confirmation_rule_promoted": False,
        "best_or_winner_selected": False,
        "optimization_performed": False,
        "portfolio_rerun_performed": False,
        "costed_portfolio_generated": False,
        "validation_state": SEALED,
        "validation_run_count": 0,
        "validation_rows_accessed": 0,
        "holdout_performance_exposed": False,
        "live_signals": 0,
        "live_orders": 0,
        "broker_order_calls": 0,
        "remote_migrations": 0,
        "supabase_persistence": 0,
        "additional_intraday_ingestion_requests": 0,
    }
    classifications = {
        "CONFIRMATION_5M_RESULT": confirmation_results[5],
        "CONFIRMATION_10M_RESULT": confirmation_results[10],
        "CONFIRMATION_15M_RESULT": confirmation_results[15],
        "VWAP_CONTEXT_RESULT": vwap_result,
        "OPENING_RANGE_CONTEXT_RESULT": opening_result,
        "FALSE_START_FILTERING_RESULT": false_result,
        "CONFIRMATION_DELAY_COST_RESULT": delay_result,
        "TEMPORAL_CONSISTENCY_RESULT": temporal_result,
        "INTRADAY_CONFIRMATION_DIAGNOSTIC_RESULT": overall_result,
        "INTRADAY_CONFIRMATION_HYPOTHESIS_SUPPORTED_FOR_LATER_TESTING": "YES" if hypothesis_supported else "NO",
    }
    summary: dict[str, Any] = {
        "phase": "Step 02.15",
        "command": COMMAND,
        "diagnostic_version": DIAGNOSTIC_VERSION,
        "profile": PROFILE,
        "family": FAMILY,
        "real_data_source": "GROWW_OFFICIAL_API",
        "scope": {
            "development_start": DEFAULT_TEMPORAL_CONFIG.development_start,
            "development_end": DEFAULT_TEMPORAL_CONFIG.development_end,
            "selected_symbol_count": len(context["selected_symbols"]),
            "total_development_opportunities": context["total_development_opportunities"],
            "all_strict_covered_opportunities": len(population),
            "admitted_strict_covered_trades": sum(row["is_admitted"] for row in population),
            "all_development_strict_coverage_pct": Decimal(len(population)) * 100 / Decimal(context["total_development_opportunities"]),
            "selected_scope_bias": "The frozen 100-symbol intraday scope represents about 54% of all DEVELOPMENT opportunities and is not whole-universe representative.",
            "exclusions": context["exclusions"],
            "corporate_action_exclusions": context["exclusions"].get("NOT_CORPORATE_ACTION_SAFE", 0),
            "opportunities_excluded_without_strict_full_path": context["exclusions"].get("NOT_FULL_PATH_USABLE_STRICT", 0),
            "intraday_session_quality": {
                "usable_strict": context["intraday_session_quality"]["usable_strict"],
                "usable_with_warning_excluded_from_primary": context["intraday_session_quality"]["usable_with_warning"],
                "unusable_excluded_from_primary": context["intraday_session_quality"]["unusable"],
            },
        },
        "population_freeze": {
            "intraday_confirmation_population_hash": population_hash,
            "path": str(population_manifest_path),
            "post_result_additions_or_removals": 0,
        },
        "pre_registration": {
            "intraday_confirmation_prereg_hash": preregistration["intraday_confirmation_prereg_hash"],
            "experiment_count": len(EXPERIMENT_IDS),
            "experiment_ids": EXPERIMENT_IDS,
            "path": str(prereg_path),
            "definitions_frozen_before_results": True,
            "promotion_allowed": False,
            "eligible_for_promotion": False,
        },
        "baseline_open_profile": baseline_profile,
        "window_profiles": profiles_by_window,
        "classifications": classifications,
        "classification_evidence": {
            "confirmation_windows": confirmation_evidence,
            "delay_cost": delay_evidence,
            "false_start": false_evidence,
            "vwap": vwap_evidence,
            "opening_range": opening_evidence,
            "temporal": temporal_evidence,
        },
        "good_trade_sacrifice": {
            window: {
                "count": sum(row["good_trade_sacrifice"] for row in records[window]),
                "rate_among_good_paths_pct": _rate(sum(row["good_trade_sacrifice"] for row in records[window]), sum(row["good_path"] for row in records[window])),
            }
            for window in WINDOWS
        },
        "delayed_entry_opportunity_cost": {
            window: {
                "target_touched_before_count": sum(row["target_touched_before_confirmation"] for row in records[window]),
                "positive_drift_gt_1_count": sum(Decimal(str(row["price_change_from_open_pct"])) > 1 for row in records[window]),
                "positive_drift_gt_2_count": sum(Decimal(str(row["price_change_from_open_pct"])) > 2 for row in records[window]),
                "rr_below_1_5_count": sum(row["confirmation_effective_rr"] is not None and Decimal(str(row["confirmation_effective_rr"])) < Decimal("1.5") for row in records[window]),
            }
            for window in WINDOWS
        },
        "source_vs_admitted": source_vs_admitted,
        "yearly": yearly_rows,
        "contexts": context_rows,
        "mismatch_sensitivity": mismatch_sensitivity,
        "pilot": pilot,
        "baseline_regression": {
            "before": baseline_before,
            "after": baseline_after,
            "baseline_mutation_violations": mutation_violations,
            "all_frozen_hashes_unchanged": mutation_violations == 0,
        },
        "governance": governance,
        "security": {
            "output_ignore_checks": output_ignore_checks,
            "all_required_outputs_ignored": all(output_ignore_checks.values()),
            "secrets_logged": False,
            "provider_headers_logged": False,
        },
        "paths": {
            "registry": str(registry_path),
            "preregistration_registry": str(prereg_path),
            "reports": [str(report_root / name) for name in REPORT_FILENAMES],
            "documentation": str(root / "docs/intraday-confirmation-diagnostic-v1.md"),
        },
        "tests": {"backend_passed": tests_passed},
        "frontend": {"build_passed": frontend_build_passed, "tile_added": False},
        "runtime_seconds": Decimal(str(time.perf_counter() - started)),
        "storage": {},
        "known_limitations": [
            "The real intraday dataset is bounded to the frozen 100-symbol scope and is not whole-universe representative.",
            "Only USABLE_STRICT full-path opportunities are in the primary population; warning rows are excluded rather than imputed.",
            "The 5m/10m/15m confirmation close is part of its same-length opening range, so ABOVE_OR_HIGH and BELOW_OR_LOW are mechanically unavailable at that timestamp; exact-boundary and inside states are retained.",
            "Intrabar stop/target ordering inside one 5m bar remains ambiguous and is preserved.",
            "The one unexplained material daily mismatch is flagged and reported with a deterministic omit-one sensitivity.",
            "Raw Groww prices are retained at rest. Diagnostic OHLC and VWAP are rebased in memory by the causal T+1-open ratio so they share the frozen adjusted daily stop/target basis.",
            "Confirmation prices are hypothetical research references, not executions, and no costs or portfolio equity curve are computed.",
        ],
        "recommended_next_action": "Review this DEVELOPMENT-only diagnostic. Authorize a separately pre-registered isolated confirmation-rule experiment only if the evidence gate is accepted; do not unseal validation.",
    }
    summary_path = report_root / REPORT_FILENAMES[0]
    summary["ready_for_review"] = (
        tests_passed
        and frontend_build_passed
        and mutation_violations == 0
        and all(output_ignore_checks.values())
        and pilot["passed"]
        and len(EXPERIMENT_IDS) == 10
        and governance["validation_state"] == SEALED
        and governance["validation_run_count"] == 0
        and governance["validation_rows_accessed"] == 0
    )
    _write_json(summary_path, summary)
    report_paths.append(summary_path)
    summary["storage"] = _storage([*result_paths, *report_paths])
    summary["runtime_seconds"] = Decimal(str(time.perf_counter() - started))
    _write_json(summary_path, summary)
    run_manifest_path = artifact_root / "run_manifest_v1.json"
    _write_json(
        run_manifest_path,
        {
            "diagnostic_version": DIAGNOSTIC_VERSION,
            "profile": PROFILE,
            "population_hash": population_hash,
            "preregistration_hash": preregistration["intraday_confirmation_prereg_hash"],
            "report_hashes": {path.name: _file_sha256(path) for path in report_paths},
            "registry_hash": _file_sha256(registry_path),
            "baseline_mutation_violations": mutation_violations,
            "validation_state": SEALED,
            "validation_run_count": 0,
            "ready_for_review": summary["ready_for_review"],
        },
    )
    notify(f"Completed the finite diagnostic in {summary['runtime_seconds']:.2f}s; no validation, portfolio, or live path was touched")
    return summary


__all__ = [
    "CLASSIFICATION_RULES",
    "DIAGNOSTIC_VERSION",
    "EXPERIMENT_IDS",
    "FAMILY",
    "PRICE_DRIFT_BUCKETS",
    "PROFILE",
    "REPORT_FILENAMES",
    "RR_BUCKETS",
    "WINDOWS",
    "build_preregistration",
    "build_window_record",
    "confirmation_feasibility",
    "confirmation_reference",
    "confirmation_rr",
    "early_path_classification",
    "freeze_population",
    "opening_range_classification",
    "preconfirmation_touch_state",
    "price_drift_bucket",
    "rr_bucket",
    "run_intraday_confirmation_diagnostic",
    "sample_safety",
    "validate_development_only",
    "vwap_classification",
    "window_profile",
]
