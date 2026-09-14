from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from app.backtesting.costs.cost_config import EXPECTED_COST_CONFIG_HASH
from app.backtesting.costs.cost_engine import SCENARIO_BASELINE_SLIPPAGE
from app.backtesting.costs.cost_models import canonical_hash
from app.research.strategy.family_a_momentum import (
    decimal,
    estimate_order_cost,
    file_sha256,
    read_csv,
    write_csv,
    write_json,
)
from app.research.strategy.family_c_breakout_continuation import (
    COMPRESSION_THRESHOLD,
    CONTROL_ID,
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    EXPECTED_CONTROL_REFERENCE_HASH,
    EXPECTED_FAMILY_C_CONFIG_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    FAMILY_VERSION,
    HOLDING_SESSIONS,
    MAX_CONCURRENT_POSITIONS,
    STARTING_CAPITAL,
    TARGET_NOTIONAL_FRACTION,
    _load_adjusted_bars,
    _load_aliases,
    _load_membership,
    _load_sessions,
    entry_exit_chronology,
)
from app.research.strategy.family_c_development_evaluation import (
    EXECUTABLE_MODE,
    _bar_path_available,
    _bucket_label,
    _load_signal_rows,
    expectancy,
    position_win_rate,
    profit_factor,
    quantile,
    verify_freeze_gate as verify_development_freeze_gate,
)


COMMAND = "Step 03.03 / Command 03"
COMMAND_VERSION = "FAMILY_C_C001_ATTRIBUTION_AUDIT_V1"
COMMAND_PROFILE = "COMPRESSION_BREAKOUT_CAPACITY_ATTRIBUTION_V1"
REPLAY_LABEL = "ATTRIBUTION_REPLAY_NOT_STRATEGY_EXPERIMENT"
COHORT_LABEL = "SIGNAL_QUALITY_COHORT_ONLY"
NORMALIZED_EVENT_NOTIONAL = STARTING_CAPITAL * TARGET_NOTIONAL_FRACTION

EXPECTED_CONTROL_RESULT_HASH = (
    "efdf9ccdf70f4c58d1ce40e2f1e1ccb7e7fa8ad83c5fb3832ce0994d323b991f"
)
EXPECTED_C001_RESULT_HASH = (
    "8adc1aec00041256748a8fa086b4dae562a6841b844875fc39b3dd19b61680e4"
)
EXPECTED_C002_RESULT_HASH = (
    "49afe8ee5d766afa9a0e01195fa49041605c71483df0de9ac4c354b469a9a240"
)
EXPECTED_DEVELOPMENT_REGISTRY_HASH = (
    "529322157a13058f0e2f73e88d471b5f15e006b8eae1c1050a0110b77d6345bc"
)

REPORT_NAMES = (
    "family_c_c001_attribution_v1_summary.json",
    "family_c_c001_attribution_v1_event_cohort.csv",
    "family_c_c001_attribution_v1_compression.csv",
    "family_c_c001_attribution_v1_yearly.csv",
    "family_c_c001_attribution_v1_admitted_vs_rejected.csv",
    "family_c_c001_attribution_v1_capacity_days.csv",
    "family_c_c001_attribution_v1_capacity_ranking.csv",
    "family_c_c001_attribution_v1_same_day_matches.csv",
    "family_c_c001_attribution_v1_holding_path.csv",
    "family_c_c001_attribution_v1_breakout_strength.csv",
    "family_c_c001_attribution_v1_entry_gap.csv",
    "family_c_c001_attribution_v1_compression_distribution.csv",
)


class FamilyCC001AttributionInputMismatch(RuntimeError):
    pass


class FamilyCC001AttributionImmutabilityError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def output_root(root: Path) -> Path:
    return root / "data/research/strategy_families/family_c/v1/c001_attribution_audit"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _without_hash(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != field}


def _hash_matches(value: Mapping[str, Any], field: str, expected: str) -> bool:
    return value.get(field) == expected and canonical_hash(
        _without_hash(value, field)
    ) == expected


def command_02_snapshot(root: Path) -> dict[str, Any]:
    evaluation_root = (
        root
        / "data/research/strategy_families/family_c/v1/development_evaluation"
    )
    paths = [path for path in evaluation_root.rglob("*") if path.is_file()]
    paths.extend(sorted((root / "data/reports").glob("family_c_dev_v1_*")))
    paths.extend(
        root / relative
        for relative in (
            "backend/app/research/strategy/family_c_development_evaluation.py",
            "backend/scripts/run_family_c_development_evaluation.py",
            "backend/tests/test_family_c_development_evaluation.py",
            "docs/strategy-family-c-development-evaluation-v1.md",
        )
    )
    hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in sorted(set(paths))
        if path.is_file()
    }
    return {"artifact_hashes": hashes, "snapshot_hash": canonical_hash(hashes)}


def verify_frozen_inputs(root: Path) -> dict[str, Any]:
    development_gate = verify_development_freeze_gate(root)
    development_root = (
        root
        / "data/research/strategy_families/family_c/v1/development_evaluation"
    )
    result_specs = (
        (
            development_root / "control/control_c_000_development_result_v1.json",
            "control_c_000_result_hash",
            EXPECTED_CONTROL_RESULT_HASH,
        ),
        (
            development_root / "brk_c_001/brk_c_001_development_result_v1.json",
            "brk_c_001_result_hash",
            EXPECTED_C001_RESULT_HASH,
        ),
        (
            development_root / "brk_c_002/brk_c_002_development_result_v1.json",
            "brk_c_002_result_hash",
            EXPECTED_C002_RESULT_HASH,
        ),
        (
            development_root
            / "comparison/family_c_development_registry_v1.json",
            "family_c_development_registry_hash",
            EXPECTED_DEVELOPMENT_REGISTRY_HASH,
        ),
    )
    documents: dict[str, dict[str, Any]] = {}
    checks: dict[str, bool] = {
        "family_config_hash": development_gate["config"]["family_c_config_hash"]
        == EXPECTED_FAMILY_C_CONFIG_HASH,
        "success_criteria_hash": development_gate["criteria"][
            "success_criteria_hash"
        ]
        == EXPECTED_SUCCESS_CRITERIA_HASH,
        "control_reference_hash": development_gate["registry"]["control"][
            "control_reference_hash"
        ]
        == EXPECTED_CONTROL_REFERENCE_HASH,
    }
    for path, field, expected in result_specs:
        if not path.is_file():
            raise FamilyCC001AttributionInputMismatch(
                f"FAMILY_C_ATTRIBUTION_INPUT_MISMATCH: missing {path}"
            )
        value = _read_json(path)
        documents[field] = value
        checks[field] = _hash_matches(value, field, expected)

    manifest_path = development_root / "development_evaluation_manifest_v1.json"
    summary_path = root / "data/reports/family_c_dev_v1_summary.json"
    manifest = _read_json(manifest_path)
    summary = _read_json(summary_path)
    manifest_field = "development_evaluation_manifest_hash"
    checks["development_manifest_hash"] = canonical_hash(
        _without_hash(manifest, manifest_field)
    ) == manifest.get(manifest_field)
    checks["development_summary_hash"] = manifest.get("summary_hash") == file_sha256(
        summary_path
    )
    artifact_mismatches = [
        relative
        for relative, expected in manifest["artifact_hashes"].items()
        if not (root / relative).is_file()
        or file_sha256(root / relative) != expected
    ]
    checks["development_artifact_hashes"] = not artifact_mismatches
    checks["development_result_state"] = (
        summary["classifications"]["FAMILY_C_DEVELOPMENT_RESULT"] == "MIXED"
        and summary["classifications"]["FAMILY_C_NEXT_RESEARCH_STAGE"]
        == "CONTINUE_CONTROLLED_DEVELOPMENT"
        and summary["classifications"]["BRK_C_001_DEVELOPMENT_RESULT"]
        == "PARTIALLY_SUPPORTED"
        and summary["classifications"]["BRK_C_002_DEVELOPMENT_RESULT"] == "FAILED"
    )
    checks["development_partition"] = (
        summary["development_partition"]["start"] == DEVELOPMENT_START.isoformat()
        and summary["development_partition"]["end"] == DEVELOPMENT_END.isoformat()
        and summary["development_partition"]["post_2024_data_accessed"] is False
        and summary["development_partition"]["validation_accessed"] is False
    )
    if not all(checks.values()):
        raise FamilyCC001AttributionInputMismatch(
            "FAMILY_C_ATTRIBUTION_INPUT_MISMATCH: "
            f"checks={checks}; artifacts={artifact_mismatches}"
        )
    return {
        "status": "VERIFIED",
        "checks": checks,
        "development_gate": development_gate,
        "development_summary": summary,
        "development_manifest": manifest,
        "documents": documents,
        "artifact_mismatches": artifact_mismatches,
    }


def normalized_event_outcome(
    entry_date: date,
    exit_date: date,
    entry_price: Decimal,
    exit_price: Decimal,
) -> dict[str, Decimal]:
    if entry_price <= 0 or exit_price <= 0:
        raise ValueError("Event prices must be positive")
    entry_notional = NORMALIZED_EVENT_NOTIONAL
    exit_notional = entry_notional * exit_price / entry_price
    buy_cost = decimal(
        estimate_order_cost("BUY", entry_date, entry_notional)["total_cost"]
    )
    sell_cost = decimal(
        estimate_order_cost("SELL", exit_date, exit_notional)["total_cost"]
    )
    gross_return = exit_price / entry_price - Decimal("1")
    net_return = (exit_notional - sell_cost) / (entry_notional + buy_cost) - Decimal(
        "1"
    )
    return {
        "normalized_entry_notional": entry_notional,
        "normalized_exit_notional": exit_notional,
        "normalized_buy_cost": buy_cost,
        "normalized_sell_cost": sell_cost,
        "estimated_normalized_round_trip_cost": buy_cost + sell_cost,
        "gross_10session_return": gross_return,
        "estimated_normalized_net_return": net_return,
    }


def build_event_cohort(
    signal_rows: Sequence[Mapping[str, Any]],
    sessions: Sequence[date],
    bars: Mapping[date, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in signal_rows:
        if not bool(row["control_signal"]):
            continue
        formation_date = row["decision_date"]
        chronology = entry_exit_chronology(sessions, formation_date)
        available, _ = _bar_path_available(str(row["symbol"]), chronology, bars)
        if not available:
            continue
        entry_date = chronology["entry_date"]
        exit_date = chronology["exit_date"]
        if entry_date is None or exit_date is None or exit_date > DEVELOPMENT_END:
            raise ValueError("Complete-path cohort escaped DEVELOPMENT")
        entry_bar = bars[entry_date][str(row["symbol"])]
        exit_bar = bars[exit_date][str(row["symbol"])]
        holding_bars = [
            bars[holding_date][str(row["symbol"])]
            for holding_date in chronology["holding_dates"]
        ]
        compression = row["compression_range_pct"]
        compression_pass = bool(
            compression is not None and decimal(compression) <= COMPRESSION_THRESHOLD
        )
        if bool(row["c001_signal"]) != compression_pass:
            raise ValueError("C001 exact <=8% rule does not match signal input")
        cost = normalized_event_outcome(
            entry_date,
            exit_date,
            entry_bar.open_price,
            exit_bar.open_price,
        )
        highs = [bar.high_price for bar in holding_bars] + [exit_bar.open_price]
        lows = [bar.low_price for bar in holding_bars] + [exit_bar.open_price]
        event_key = f"{formation_date.isoformat()}|{row['symbol']}"
        events.append(
            {
                "event_key": event_key,
                "cohort_label": COHORT_LABEL,
                "replay_label": REPLAY_LABEL,
                "symbol": row["symbol"],
                "isin": row["isin"],
                "formation_date": formation_date.isoformat(),
                "entry_date": entry_date.isoformat(),
                "formation_close": row["close"],
                "entry_open": entry_bar.open_price,
                "exit_date": exit_date.isoformat(),
                "exit_open": exit_bar.open_price,
                "breakout_strength_pct": row["breakout_strength_pct"],
                "compression_range_pct": compression,
                "compression_pass": compression_pass,
                "formation_volume_ratio": row["formation_volume_ratio"],
                "control_signal": True,
                "c001_signal": bool(row["c001_signal"]),
                "entry_gap_pct": entry_bar.open_price / decimal(row["close"])
                - Decimal("1"),
                **cost,
                "MFE_pct": max(highs) / entry_bar.open_price - Decimal("1"),
                "MAE_pct": min(lows) / entry_bar.open_price - Decimal("1"),
                "return_after_1_session": holding_bars[0].close_price
                / entry_bar.open_price
                - Decimal("1"),
                "return_after_3_sessions": holding_bars[2].close_price
                / entry_bar.open_price
                - Decimal("1"),
                "return_after_5_sessions": holding_bars[4].close_price
                / entry_bar.open_price
                - Decimal("1"),
                "return_after_10_sessions": holding_bars[9].close_price
                / entry_bar.open_price
                - Decimal("1"),
                "year": formation_date.year,
                "terminal_path_status": "COMPLETE_WITHIN_DEVELOPMENT",
            }
        )
    if len({row["event_key"] for row in events}) != len(events):
        raise ValueError("Duplicate event keys in signal-quality cohort")
    return sorted(events, key=lambda row: (row["formation_date"], row["symbol"]))


def cohort_metrics(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    net_returns = [decimal(row["estimated_normalized_net_return"]) for row in events]
    gross_returns = [decimal(row["gross_10session_return"]) for row in events]
    winners = [value for value in net_returns if value > 0]
    losers = [value for value in net_returns if value < 0]
    return {
        "event_count": len(events),
        "win_rate": position_win_rate(net_returns),
        "gross_mean_return": expectancy(gross_returns),
        "gross_median_return": quantile(gross_returns, Decimal("0.50")),
        "mean_return": expectancy(net_returns),
        "median_return": quantile(net_returns, Decimal("0.50")),
        "average_winner": expectancy(winners),
        "average_loser": expectancy(losers),
        "net_expectancy": expectancy(net_returns),
        "net_profit_factor": profit_factor(net_returns),
        "median_MFE": quantile(
            [decimal(row["MFE_pct"]) for row in events], Decimal("0.50")
        ),
        "median_MAE": quantile(
            [decimal(row["MAE_pct"]) for row in events], Decimal("0.50")
        ),
    }


def metric_difference(
    first: Mapping[str, Any], second: Mapping[str, Any], fields: Iterable[str]
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for field in fields:
        left = first.get(field)
        right = second.get(field)
        output[field] = (
            None
            if left is None or right is None
            else decimal(left) - decimal(right)
        )
    return output


def classify_signal_quality(
    pass_metrics: Mapping[str, Any], fail_metrics: Mapping[str, Any]
) -> str:
    if not pass_metrics["event_count"] or not fail_metrics["event_count"]:
        return "INCONCLUSIVE"
    differences = metric_difference(
        pass_metrics,
        fail_metrics,
        ("win_rate", "net_expectancy", "net_profit_factor", "median_return"),
    )
    positive = sum(decimal(differences[field]) > 0 for field in differences)
    negative = sum(decimal(differences[field]) < 0 for field in differences)
    if (
        positive == 4
        and decimal(pass_metrics["net_expectancy"]) > 0
        and decimal(differences["win_rate"]) >= Decimal("0.03")
        and decimal(differences["net_profit_factor"]) >= Decimal("0.10")
    ):
        return "CLEAR_POSITIVE"
    if (
        decimal(differences["net_expectancy"]) > 0
        and decimal(differences["net_profit_factor"]) > 0
        and positive >= 3
        and decimal(pass_metrics["net_expectancy"]) > 0
    ):
        return "MODEST_POSITIVE"
    if negative == 4:
        return "NEGATIVE"
    if all(abs(decimal(value)) <= Decimal("0.0005") for value in differences.values()):
        return "NO_MEANINGFUL_DIFFERENCE"
    return "MIXED"


def classify_temporal_consistency(yearly_rows: Sequence[Mapping[str, Any]]) -> str:
    by_year: dict[int, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in yearly_rows:
        by_year[int(row["year"])][str(row["cohort"])] = row
    if set(by_year) != {2022, 2023, 2024} or any(
        set(rows) != {"COMPRESSION_PASS", "COMPRESSION_FAIL"}
        for rows in by_year.values()
    ):
        return "INCONCLUSIVE"
    directions = []
    pass_signs = []
    for rows in by_year.values():
        passed = rows["COMPRESSION_PASS"]
        failed = rows["COMPRESSION_FAIL"]
        directions.append(
            decimal(passed["net_expectancy"])
            > decimal(failed["net_expectancy"])
        )
        pass_signs.append(decimal(passed["net_expectancy"]) > 0)
    positive_years = sum(directions)
    if positive_years == 3 and all(pass_signs):
        return "CONSISTENT"
    if positive_years >= 2:
        return "MOSTLY_CONSISTENT"
    if positive_years == 1:
        return "UNSTABLE"
    return "CONTRADICTORY"


def _event_key(formation_date: str, symbol: str) -> str:
    return f"{formation_date}|{symbol}"


def reconstruct_frozen_admissions(
    root: Path,
    signal_rows: Sequence[Mapping[str, Any]],
    sessions: Sequence[date],
    bars: Mapping[date, Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
    frozen_summary: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    position_path = (
        root
        / "data/research/strategy_families/family_c/v1/development_evaluation"
        / "positions/brk_c_001_executable_integer_share_500k_positions_v1.csv"
    )
    positions = read_csv(position_path)
    admitted_keys = {
        _event_key(row["formation_date"], row["symbol"]) for row in positions
    }
    event_map = {str(row["event_key"]): row for row in events}
    c001_rows = [row for row in signal_rows if bool(row["c001_signal"])]
    rows_by_date: dict[date, list[Mapping[str, Any]]] = defaultdict(list)
    records: list[dict[str, Any]] = []
    for row in c001_rows:
        chronology = entry_exit_chronology(sessions, row["decision_date"])
        if chronology["entry_date"] is None:
            records.append(
                {
                    "event_key": _event_key(
                        row["decision_date"].isoformat(), str(row["symbol"])
                    ),
                    "formation_date": row["decision_date"].isoformat(),
                    "entry_date": "",
                    "symbol": row["symbol"],
                    "breakout_strength_pct": row["breakout_strength_pct"],
                    "admission_status": "OTHER_EXPLAINED",
                    "explanation": "NO_T_PLUS_1_DEVELOPMENT_SESSION",
                    "open_positions_before_entry": "",
                    "same_day_rank": "",
                    "same_day_ranked_candidates": "",
                }
            )
            continue
        available, reason = _bar_path_available(
            str(row["symbol"]), chronology, bars
        )
        if not available:
            status = (
                "TERMINAL_UNAVAILABLE"
                if reason == "TERMINAL_PATH_UNAVAILABLE_WITHIN_DEVELOPMENT"
                else "OTHER_EXPLAINED"
            )
            records.append(
                {
                    "event_key": _event_key(
                        row["decision_date"].isoformat(), str(row["symbol"])
                    ),
                    "formation_date": row["decision_date"].isoformat(),
                    "entry_date": chronology["entry_date"].isoformat(),
                    "symbol": row["symbol"],
                    "breakout_strength_pct": row["breakout_strength_pct"],
                    "admission_status": status,
                    "explanation": reason,
                    "open_positions_before_entry": "",
                    "same_day_rank": "",
                    "same_day_ranked_candidates": "",
                }
            )
            continue
        rows_by_date[row["decision_date"]].append(row)

    for formation_date, candidates in sorted(rows_by_date.items()):
        chronology = entry_exit_chronology(sessions, formation_date)
        entry_date = chronology["entry_date"]
        if entry_date is None:
            raise ValueError("Complete C001 event has no entry date")
        open_symbols = {
            row["symbol"]
            for row in positions
            if row["entry_date"] < entry_date.isoformat() < row["exit_date"]
        }
        occupied_before = set(open_symbols)
        open_before = len(open_symbols)
        nonoverlapping = [
            row for row in candidates if str(row["symbol"]) not in occupied_before
        ]
        ordered = sorted(
            nonoverlapping,
            key=lambda row: (
                -decimal(row["breakout_strength_pct"]),
                str(row["symbol"]),
            ),
        )
        rank_by_key = {
            _event_key(formation_date.isoformat(), str(row["symbol"])): rank
            for rank, row in enumerate(ordered, 1)
        }
        processing_order = sorted(
            (
                row
                for row in candidates
                if str(row["symbol"]) in occupied_before
            ),
            key=lambda item: str(item["symbol"]),
        ) + ordered
        for row in processing_order:
            key = _event_key(formation_date.isoformat(), str(row["symbol"]))
            if str(row["symbol"]) in occupied_before:
                status = "ALREADY_OPEN"
                explanation = "SYMBOL_OCCUPIED_BEFORE_ENTRY_PROCESSING"
            elif key in admitted_keys:
                status = "ADMITTED"
                explanation = "FROZEN_COMMAND_02_POSITION_MATCH"
                open_symbols.add(str(row["symbol"]))
            elif len(open_symbols) >= MAX_CONCURRENT_POSITIONS:
                status = "CAPACITY_REJECTED"
                explanation = "FROZEN_20_POSITION_CAP"
            else:
                status = "AFFORDABILITY_REJECTED"
                explanation = "FROZEN_INTEGER_SHARE_CASH_CHECK"
            event = event_map[key]
            records.append(
                {
                    "event_key": key,
                    "formation_date": formation_date.isoformat(),
                    "entry_date": entry_date.isoformat(),
                    "symbol": row["symbol"],
                    "breakout_strength_pct": row["breakout_strength_pct"],
                    "admission_status": status,
                    "explanation": explanation,
                    "open_positions_before_entry": open_before,
                    "same_day_rank": rank_by_key.get(key, ""),
                    "same_day_ranked_candidates": len(ordered),
                    "gross_10session_return": event["gross_10session_return"],
                    "estimated_normalized_net_return": event[
                        "estimated_normalized_net_return"
                    ],
                    "MFE_pct": event["MFE_pct"],
                    "MAE_pct": event["MAE_pct"],
                    "year": event["year"],
                }
            )

    records.sort(key=lambda row: (row["formation_date"], row["symbol"]))
    counts = Counter(row["admission_status"] for row in records)
    metrics = frozen_summary["results"]["BRK-C-001"]["executable_metrics"]
    expected = {
        "ADMITTED": int(metrics["admitted_signals"]),
        "CAPACITY_REJECTED": int(metrics["capacity_rejected_signals"]),
        "ALREADY_OPEN": int(metrics["already_open_rejections"]),
        "AFFORDABILITY_REJECTED": int(metrics["affordability_rejections"]),
        "TERMINAL_UNAVAILABLE": int(metrics["terminal_path_unavailable"]),
    }
    reconciliation = {
        "raw_c001_signals": len(c001_rows),
        "classification_counts": dict(sorted(counts.items())),
        "frozen_expected_counts": expected,
        "entry_ready_signals": sum(counts[key] for key in expected if key not in {"TERMINAL_UNAVAILABLE"}),
        "unprocessed_final_formation_signals": sum(
            row["explanation"] == "NO_T_PLUS_1_DEVELOPMENT_SESSION"
            for row in records
        ),
        "other_complete_path_failures": sum(
            row["admission_status"] == "OTHER_EXPLAINED"
            and row["explanation"] != "NO_T_PLUS_1_DEVELOPMENT_SESSION"
            for row in records
        ),
    }
    reconciliation["frozen_primary_counts_match"] = all(
        counts[key] == value for key, value in expected.items()
    )
    reconciliation["all_signals_classified"] = len(records) == len(c001_rows)
    reconciliation["admitted_keys_match"] = {
        row["event_key"]
        for row in records
        if row["admission_status"] == "ADMITTED"
    } == admitted_keys
    if not all(
        reconciliation[key]
        for key in (
            "frozen_primary_counts_match",
            "all_signals_classified",
            "admitted_keys_match",
        )
    ):
        raise ValueError(f"Frozen C001 admission reconciliation failed: {reconciliation}")
    return records, reconciliation


def _cohort_row(label: str, events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {"cohort": label, **cohort_metrics(events)}


def compression_rows(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        _cohort_row(
            "COMPRESSION_PASS",
            [row for row in events if bool(row["compression_pass"])],
        ),
        _cohort_row(
            "COMPRESSION_FAIL",
            [row for row in events if not bool(row["compression_pass"])],
        ),
    ]


def yearly_compression_rows(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for year in (2022, 2023, 2024):
        for passed, label in ((True, "COMPRESSION_PASS"), (False, "COMPRESSION_FAIL")):
            cohort = [
                row
                for row in events
                if int(row["year"]) == year
                and bool(row["compression_pass"]) is passed
            ]
            output.append({"year": year, **_cohort_row(label, cohort)})
    return output


def admitted_rejected_rows(
    admission_records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for status, label in (
        ("ADMITTED", "C001_ADMITTED"),
        ("CAPACITY_REJECTED", "C001_CAPACITY_REJECTED"),
    ):
        cohort = [
            row for row in admission_records if row["admission_status"] == status
        ]
        output.append(_cohort_row(label, cohort))
        for year in (2022, 2023, 2024):
            yearly = [row for row in cohort if int(row["year"]) == year]
            output.append({"year": year, **_cohort_row(label, yearly)})
    return output


def classify_capacity_selection(
    admitted: Mapping[str, Any], rejected: Mapping[str, Any]
) -> str:
    if not admitted["event_count"] or not rejected["event_count"]:
        return "INCONCLUSIVE"
    differences = metric_difference(
        admitted,
        rejected,
        ("win_rate", "median_return", "net_expectancy", "net_profit_factor"),
    )
    positive = sum(decimal(value) > 0 for value in differences.values())
    negative = sum(decimal(value) < 0 for value in differences.values())
    if positive == 4:
        return "SELECTED_BETTER"
    if negative == 4:
        return "SELECTED_WORSE"
    if (
        abs(decimal(differences["win_rate"])) < Decimal("0.02")
        and abs(decimal(differences["median_return"])) < Decimal("0.002")
        and abs(decimal(differences["net_expectancy"])) < Decimal("0.001")
        and abs(decimal(differences["net_profit_factor"])) < Decimal("0.05")
    ):
        return "SELECTED_SIMILAR"
    return "MIXED"


def _quartile(rank: int, count: int) -> str:
    index = min(4, ((rank - 1) * 4 // count) + 1)
    return (
        "TOP_QUARTILE",
        "SECOND_QUARTILE",
        "THIRD_QUARTILE",
        "BOTTOM_QUARTILE",
    )[index - 1]


def capacity_ranking_rows(
    admission_records: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in admission_records:
        if row["admission_status"] in {
            "ADMITTED",
            "CAPACITY_REJECTED",
            "AFFORDABILITY_REJECTED",
        }:
            grouped[str(row["formation_date"])].append(row)
    detail: list[dict[str, Any]] = []
    for formation_date, rows in sorted(grouped.items()):
        if not any(row["admission_status"] == "CAPACITY_REJECTED" for row in rows):
            continue
        count = max(int(row["same_day_ranked_candidates"]) for row in rows)
        for row in sorted(rows, key=lambda item: int(item["same_day_rank"])):
            rank = int(row["same_day_rank"])
            detail.append(
                {
                    **row,
                    "rank_quartile": _quartile(rank, count),
                    "capacity_constrained_day": True,
                    "descriptive_only": True,
                }
            )
    aggregate = []
    for quartile in (
        "TOP_QUARTILE",
        "SECOND_QUARTILE",
        "THIRD_QUARTILE",
        "BOTTOM_QUARTILE",
    ):
        cohort = [row for row in detail if row["rank_quartile"] == quartile]
        aggregate.append({"rank_quartile": quartile, **cohort_metrics(cohort)})
    return detail, aggregate


def classify_ranking(aggregate: Sequence[Mapping[str, Any]]) -> str:
    if len(aggregate) != 4 or any(not row["event_count"] for row in aggregate):
        return "INCONCLUSIVE"
    values = [decimal(row["net_expectancy"]) for row in aggregate]
    adjacent_positive = sum(values[index] >= values[index + 1] for index in range(3))
    difference = values[0] - values[-1]
    if adjacent_positive == 3 and difference > 0:
        return "POSITIVE_DISCRIMINATION"
    if difference > Decimal("0.001") and adjacent_positive >= 2:
        return "WEAK_POSITIVE"
    if adjacent_positive == 0 and difference < 0:
        return "NEGATIVE_DISCRIMINATION"
    if abs(difference) <= Decimal("0.001"):
        return "NO_DISCRIMINATION"
    return "MIXED"


def same_day_matched_rows(
    ranking_detail: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in ranking_detail:
        if row["admission_status"] in {"ADMITTED", "CAPACITY_REJECTED"}:
            grouped[str(row["formation_date"])].append(row)
    output: list[dict[str, Any]] = []
    admitted_all: list[Mapping[str, Any]] = []
    rejected_all: list[Mapping[str, Any]] = []
    for formation_date, rows in sorted(grouped.items()):
        admitted = [row for row in rows if row["admission_status"] == "ADMITTED"]
        rejected = [
            row for row in rows if row["admission_status"] == "CAPACITY_REJECTED"
        ]
        if not admitted or not rejected:
            continue
        admitted_all.extend(admitted)
        rejected_all.extend(rejected)
        admitted_metrics = cohort_metrics(admitted)
        rejected_metrics = cohort_metrics(rejected)
        differences = metric_difference(
            admitted_metrics,
            rejected_metrics,
            ("win_rate", "median_return", "net_expectancy", "net_profit_factor"),
        )
        output.append(
            {
                "formation_date": formation_date,
                "admitted_count": len(admitted),
                "rejected_count": len(rejected),
                "admitted_win_rate": admitted_metrics["win_rate"],
                "rejected_win_rate": rejected_metrics["win_rate"],
                "win_rate_difference": differences["win_rate"],
                "admitted_median_return": admitted_metrics["median_return"],
                "rejected_median_return": rejected_metrics["median_return"],
                "median_return_difference": differences["median_return"],
                "admitted_expectancy": admitted_metrics["net_expectancy"],
                "rejected_expectancy": rejected_metrics["net_expectancy"],
                "expectancy_difference": differences["net_expectancy"],
                "admitted_profit_factor": admitted_metrics["net_profit_factor"],
                "rejected_profit_factor": rejected_metrics["net_profit_factor"],
                "profit_factor_difference": differences["net_profit_factor"],
            }
        )
    admitted_metrics = cohort_metrics(admitted_all)
    rejected_metrics = cohort_metrics(rejected_all)
    aggregate = {
        "matched_day_count": len(output),
        "admitted": admitted_metrics,
        "capacity_rejected": rejected_metrics,
        "admitted_minus_rejected": metric_difference(
            admitted_metrics,
            rejected_metrics,
            ("win_rate", "median_return", "net_expectancy", "net_profit_factor"),
        ),
        "aggregation": "POOLED_EVENTS_RESTRICTED_TO_SAME_FORMATION_DATES",
    }
    return output, aggregate


def capacity_by_year_rows(
    admission_records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    output = []
    valid_statuses = {
        "ADMITTED",
        "CAPACITY_REJECTED",
        "ALREADY_OPEN",
        "AFFORDABILITY_REJECTED",
    }
    for year in (2022, 2023, 2024):
        rows = [
            row
            for row in admission_records
            if row.get("year") == year and row["admission_status"] in valid_statuses
        ]
        admitted = sum(row["admission_status"] == "ADMITTED" for row in rows)
        rejected = sum(
            row["admission_status"] == "CAPACITY_REJECTED" for row in rows
        )
        constrained_days = len(
            {
                row["formation_date"]
                for row in rows
                if any(
                    candidate["formation_date"] == row["formation_date"]
                    and candidate["admission_status"] == "CAPACITY_REJECTED"
                    for candidate in rows
                )
            }
        )
        output.append(
            {
                "year": year,
                "valid_signals": len(rows),
                "admitted": admitted,
                "capacity_rejected": rejected,
                "capacity_rejection_rate": Decimal(rejected) / Decimal(len(rows))
                if rows
                else Decimal("0"),
                "constrained_days": constrained_days,
            }
        )
    return output


def _signal_load_bucket(count: int) -> str:
    if count <= 5:
        return "1_TO_5"
    if count <= 10:
        return "6_TO_10"
    if count <= 20:
        return "11_TO_20"
    if count <= 30:
        return "21_TO_30"
    return "31_PLUS"


def capacity_by_signal_load_rows(
    admission_records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    valid = [
        row
        for row in admission_records
        if row["admission_status"]
        in {"ADMITTED", "CAPACITY_REJECTED", "ALREADY_OPEN", "AFFORDABILITY_REJECTED"}
    ]
    by_date: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in valid:
        by_date[str(row["formation_date"])].append(row)
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    day_counts: Counter[str] = Counter()
    for rows in by_date.values():
        bucket = _signal_load_bucket(len(rows))
        day_counts[bucket] += 1
        grouped[bucket].extend(rows)
    output = []
    for bucket in ("1_TO_5", "6_TO_10", "11_TO_20", "21_TO_30", "31_PLUS"):
        rows = grouped[bucket]
        metrics = cohort_metrics(rows)
        admitted = sum(row["admission_status"] == "ADMITTED" for row in rows)
        output.append(
            {
                "signal_load_bucket": bucket,
                "days": day_counts[bucket],
                "signals": len(rows),
                "admitted": admitted,
                "admission_rate": Decimal(admitted) / Decimal(len(rows))
                if rows
                else None,
                "event_level_win_rate": metrics["win_rate"],
                "net_expectancy": metrics["net_expectancy"],
            }
        )
    return output


def occupancy_metrics(
    admission_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_entry_date: dict[str, int] = {}
    for row in admission_records:
        value = row.get("open_positions_before_entry")
        if value in (None, ""):
            continue
        by_entry_date[str(row["entry_date"])] = int(value)
    values = list(by_entry_date.values())
    return {
        "entry_day_count": len(values),
        "average_open_positions_before_entry": statistics.fmean(values)
        if values
        else None,
        "median_open_positions_before_entry": statistics.median(values)
        if values
        else None,
        "p90_open_positions_before_entry": quantile(
            [Decimal(value) for value in values], Decimal("0.90")
        ),
        "fraction_entry_days_at_least_18_open": Decimal(
            sum(value >= 18 for value in values)
        )
        / Decimal(len(values))
        if values
        else None,
        "fraction_entry_days_exactly_20_open": Decimal(
            sum(value == 20 for value in values)
        )
        / Decimal(len(values))
        if values
        else None,
    }


def classify_capacity_materiality(
    rejection_rate: Decimal,
    occupancy: Mapping[str, Any],
    selection_quality: str,
) -> str:
    if occupancy["fraction_entry_days_at_least_18_open"] is None:
        return "INCONCLUSIVE"
    crowded = decimal(occupancy["fraction_entry_days_at_least_18_open"])
    if (
        rejection_rate >= Decimal("0.50")
        and crowded >= Decimal("0.50")
        and selection_quality in {"SELECTED_SIMILAR", "SELECTED_WORSE", "MIXED"}
    ):
        return "DOMINANT"
    if rejection_rate >= Decimal("0.25"):
        return "MATERIAL"
    if rejection_rate >= Decimal("0.10"):
        return "MODERATE"
    if rejection_rate > 0:
        return "MINOR"
    return "NONE"


def holding_path_rows(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for passed, label in ((True, "COMPRESSION_PASS"), (False, "COMPRESSION_FAIL")):
        cohort = [row for row in events if bool(row["compression_pass"]) is passed]
        for horizon in (1, 3, 5, 10):
            values = [
                decimal(row[f"return_after_{horizon}_session" + ("s" if horizon != 1 else "")])
                for row in cohort
            ]
            output.append(
                {
                    "cohort": label,
                    "completed_sessions": horizon,
                    "event_count": len(values),
                    "average_return": expectancy(values),
                    "median_return": quantile(values, Decimal("0.50")),
                    "diagnostic_only": True,
                    "exit_rule_changed": False,
                }
            )
    return output


def compression_bucket_rows(
    events: Sequence[Mapping[str, Any]], kind: str
) -> list[dict[str, Any]]:
    field = "breakout_strength_pct" if kind == "BREAKOUT_STRENGTH" else "entry_gap_pct"
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in events:
        bucket = _bucket_label(decimal(row[field]), kind)
        cohort = "COMPRESSION_PASS" if row["compression_pass"] else "COMPRESSION_FAIL"
        grouped[(bucket, cohort)].append(row)
    output = []
    for (bucket, cohort), rows in sorted(grouped.items()):
        output.append(
            {
                "diagnostic": kind,
                "bucket": bucket,
                **_cohort_row(cohort, rows),
                "descriptive_only": True,
                "threshold_optimized": False,
            }
        )
    return output


def compression_distribution_rows(
    events: Sequence[Mapping[str, Any]],
    admission_records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    admitted_keys = {
        row["event_key"]
        for row in admission_records
        if row["admission_status"] == "ADMITTED"
    }
    cohorts = {
        "ALL_CONTROL_COMPLETE_PATH": events,
        "ADMITTED_C001": [row for row in events if row["event_key"] in admitted_keys],
    }
    output = []
    for label, rows in cohorts.items():
        values = [decimal(row["compression_range_pct"]) for row in rows]
        output.append(
            {
                "cohort": label,
                "count": len(values),
                "p10": quantile(values, Decimal("0.10")),
                "p25": quantile(values, Decimal("0.25")),
                "median": quantile(values, Decimal("0.50")),
                "p75": quantile(values, Decimal("0.75")),
                "p90": quantile(values, Decimal("0.90")),
                "alternate_cutoff_tested": False,
            }
        )
    return output


def classify_development_advantage(
    signal_quality: str,
    capacity_selection: str,
    capacity_materiality: str,
) -> str:
    positive_signal = signal_quality in {"CLEAR_POSITIVE", "MODEST_POSITIVE"}
    material_capacity = capacity_materiality in {"DOMINANT", "MATERIAL"}
    if positive_signal and material_capacity and capacity_selection == "SELECTED_BETTER":
        return "MIXED_SIGNAL_AND_CAPACITY"
    if positive_signal:
        return "PRIMARILY_COMPRESSION_SIGNAL"
    if capacity_selection == "SELECTED_BETTER":
        return "PRIMARILY_CAPACITY_PATH"
    if signal_quality in {"NEGATIVE", "NO_MEANINGFUL_DIFFERENCE"}:
        return "NO_REAL_ADVANTAGE"
    return "INCONCLUSIVE"


def next_stage(
    signal_quality: str,
    temporal_consistency: str,
    capacity_selection: str,
    capacity_materiality: str,
) -> str:
    if signal_quality == "NEGATIVE":
        return "STOP_FAMILY_C"
    if signal_quality in {"NO_MEANINGFUL_DIFFERENCE", "MIXED"}:
        return "PAUSE_FAMILY_C"
    if signal_quality == "INCONCLUSIVE" or temporal_consistency == "INCONCLUSIVE":
        return "INCONCLUSIVE"
    if (
        signal_quality in {"CLEAR_POSITIVE", "MODEST_POSITIVE"}
        and capacity_selection == "SELECTED_WORSE"
        and capacity_materiality in {"DOMINANT", "MATERIAL"}
    ):
        return "PREREGISTER_NEW_C001_IMPLEMENTATION_HYPOTHESIS"
    if (
        signal_quality in {"CLEAR_POSITIVE", "MODEST_POSITIVE"}
        and temporal_consistency in {"CONSISTENT", "MOSTLY_CONSISTENT"}
        and capacity_selection != "INCONCLUSIVE"
        and capacity_materiality != "INCONCLUSIVE"
    ):
        return "FREEZE_C001_FOR_VALIDATION_DESIGN"
    return "MORE_ATTRIBUTION_REQUIRED"


def _immutable_audit_record(path: Path, record: Mapping[str, Any]) -> None:
    if path.is_file():
        previous = _read_json(path)
        field = "family_c_c001_attribution_hash"
        if previous.get(field) != record.get(field):
            raise FamilyCC001AttributionImmutabilityError(
                "Frozen Family C C001 attribution result would change"
            )
    write_json(path, record)


def build_family_c_c001_attribution_audit(root: Path) -> dict[str, Any]:
    started_at = utc_now()
    frozen = verify_frozen_inputs(root)
    command_02_before = command_02_snapshot(root)
    signal_rows = _load_signal_rows(root)
    aliases = _load_aliases(root)
    membership = _load_membership(root)
    sessions = _load_sessions(root)
    bars = _load_adjusted_bars(root, set(membership.grouped), aliases)
    if any(session > DEVELOPMENT_END for session in bars):
        raise ValueError("Post-2024 data was loaded")

    events = build_event_cohort(signal_rows, sessions, bars)
    c001_events = [row for row in events if row["compression_pass"]]
    subset_violations = sum(not row["control_signal"] for row in c001_events)
    if subset_violations:
        raise ValueError("C001 subset invariant failed")

    compression = compression_rows(events)
    compression_by_name = {row["cohort"]: row for row in compression}
    compression_effect = metric_difference(
        compression_by_name["COMPRESSION_PASS"],
        compression_by_name["COMPRESSION_FAIL"],
        (
            "win_rate",
            "net_expectancy",
            "net_profit_factor",
            "median_return",
            "median_MFE",
            "median_MAE",
        ),
    )
    signal_quality = classify_signal_quality(
        compression_by_name["COMPRESSION_PASS"],
        compression_by_name["COMPRESSION_FAIL"],
    )
    yearly = yearly_compression_rows(events)
    temporal_consistency = classify_temporal_consistency(yearly)

    admissions, reconciliation = reconstruct_frozen_admissions(
        root,
        signal_rows,
        sessions,
        bars,
        events,
        frozen["development_summary"],
    )
    admitted_rejected = admitted_rejected_rows(admissions)
    overall_admission = {
        row["cohort"]: row for row in admitted_rejected if "year" not in row
    }
    admission_effect = metric_difference(
        overall_admission["C001_ADMITTED"],
        overall_admission["C001_CAPACITY_REJECTED"],
        ("win_rate", "median_return", "net_expectancy", "net_profit_factor"),
    )
    capacity_selection = classify_capacity_selection(
        overall_admission["C001_ADMITTED"],
        overall_admission["C001_CAPACITY_REJECTED"],
    )
    ranking_detail, ranking_aggregate = capacity_ranking_rows(admissions)
    ranking_result = classify_ranking(ranking_aggregate)
    matched_days, matched_aggregate = same_day_matched_rows(ranking_detail)
    capacity_yearly = capacity_by_year_rows(admissions)
    capacity_load = capacity_by_signal_load_rows(admissions)
    occupancy = occupancy_metrics(admissions)
    frozen_c001 = frozen["development_summary"]["results"]["BRK-C-001"][
        "executable_metrics"
    ]
    rejection_rate = decimal(frozen_c001["capacity_rejection_rate"])
    capacity_materiality = classify_capacity_materiality(
        rejection_rate, occupancy, capacity_selection
    )

    holding = holding_path_rows(events)
    breakout = compression_bucket_rows(events, "BREAKOUT_STRENGTH")
    entry_gap = compression_bucket_rows(events, "ENTRY_GAP")
    distribution = compression_distribution_rows(events, admissions)
    advantage_attribution = classify_development_advantage(
        signal_quality, capacity_selection, capacity_materiality
    )
    family_next_stage = next_stage(
        signal_quality,
        temporal_consistency,
        capacity_selection,
        capacity_materiality,
    )

    pass_metrics = compression_by_name["COMPRESSION_PASS"]
    rejected_metrics = overall_admission["C001_CAPACITY_REJECTED"]
    sixty_percent = {
        "event_level_compression_pass_win_rate": pass_metrics["win_rate"],
        "portfolio_admitted_win_rate": frozen_c001["position_win_rate"],
        "capacity_rejected_win_rate": rejected_metrics["win_rate"],
        "C001_60PCT_WIN_RATE_OBSERVED": "YES"
        if any(
            decimal(value) >= Decimal("0.60")
            for value in (
                pass_metrics["win_rate"],
                frozen_c001["position_win_rate"],
                rejected_metrics["win_rate"],
            )
        )
        else "NO",
        "descriptive_only": True,
    }
    gross_edge = decimal(pass_metrics["gross_mean_return"])
    net_edge = decimal(pass_metrics["net_expectancy"])
    cost_context = {
        "normalized_event_notional": NORMALIZED_EVENT_NOTIONAL,
        "gross_event_expectancy": gross_edge,
        "normalized_net_event_expectancy": net_edge,
        "normalized_cost_drag": gross_edge - net_edge,
        "edge_positive_after_frozen_friction": net_edge > 0,
        "frozen_portfolio_turnover": frozen_c001["turnover"],
        "frozen_portfolio_modeled_costs": frozen_c001["transaction_costs"],
        "alternative_cost_assumptions_run": False,
    }

    audit_body = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "family_version": FAMILY_VERSION,
        "replay_label": REPLAY_LABEL,
        "cohort_label": COHORT_LABEL,
        "frozen_hashes": {
            "family_c_config_hash": EXPECTED_FAMILY_C_CONFIG_HASH,
            "success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
            "control_reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
            "control_result_hash": EXPECTED_CONTROL_RESULT_HASH,
            "brk_c_001_result_hash": EXPECTED_C001_RESULT_HASH,
            "brk_c_002_result_hash": EXPECTED_C002_RESULT_HASH,
            "family_c_development_registry_hash": EXPECTED_DEVELOPMENT_REGISTRY_HASH,
            "cost_config_hash": EXPECTED_COST_CONFIG_HASH,
            "cost_scenario": SCENARIO_BASELINE_SLIPPAGE,
        },
        "development_partition": {
            "start": DEVELOPMENT_START.isoformat(),
            "end": DEVELOPMENT_END.isoformat(),
            "post_2024_accessed": False,
            "validation_accessed": False,
        },
        "signal_cohort": {
            "control_complete_path_events": len(events),
            "c001_complete_path_events": len(c001_events),
            "c001_subset_violations": subset_violations,
            "compression": compression,
            "compression_pass_minus_fail": compression_effect,
            "C001_SIGNAL_QUALITY_ATTRIBUTION": signal_quality,
            "C001_SIGNAL_TEMPORAL_CONSISTENCY": temporal_consistency,
        },
        "capacity": {
            "reconciliation": reconciliation,
            "admitted_vs_capacity_rejected": admitted_rejected,
            "admitted_minus_rejected": admission_effect,
            "C001_CAPACITY_SELECTION_QUALITY": capacity_selection,
            "BREAKOUT_STRENGTH_CAPACITY_RANKING_RESULT": ranking_result,
            "ranking_quartiles": ranking_aggregate,
            "same_day_matched": matched_aggregate,
            "by_year": capacity_yearly,
            "by_signal_load": capacity_load,
            "occupancy": occupancy,
            "C001_CAPACITY_EFFECT_MATERIALITY": capacity_materiality,
        },
        "diagnostics": {
            "holding_path": holding,
            "breakout_strength": breakout,
            "entry_gap": entry_gap,
            "compression_distribution": distribution,
            "sixty_percent_context": sixty_percent,
            "cost_turnover_context": cost_context,
        },
        "attribution": {
            "C001_DEVELOPMENT_ADVANTAGE_ATTRIBUTION": advantage_attribution,
            "C002_CURRENT_STATUS": "DEPRIORITIZED_FAILED_DEVELOPMENT",
            "C002_RESEARCH_STATUS": "DEPRIORITIZED",
            "FAMILY_C_C001_NEXT_STAGE": family_next_stage,
        },
        "governance": {
            "new_strategy_created": False,
            "strategy_id_created": False,
            "parameter_mutations": 0,
            "compression_threshold_changed": False,
            "alternate_compression_threshold_tested": False,
            "breakout_period_changed": False,
            "capacity_changed": False,
            "alternate_capacity_tested": False,
            "holding_period_changed": False,
            "alternate_holding_period_tested": False,
            "stop_added": False,
            "target_added": False,
            "intraday_confirmation_added": False,
            "combined_filter_tested": False,
            "c002_reevaluated": False,
            "validation_accessed": False,
            "strategy_v2_created": False,
            "family_d_started": False,
        },
        "security": {
            "live_signals": 0,
            "live_orders": 0,
            "broker_calls": 0,
            "remote_migrations": 0,
            "supabase_persistence": 0,
            "external_writes": 0,
            "secrets_added": 0,
        },
    }
    audit_record = {
        **audit_body,
        "family_c_c001_attribution_hash": canonical_hash(audit_body),
    }

    audit_root = output_root(root)
    reports_root = root / "data/reports"
    manifest_path = audit_root / "manifests/family_c_c001_attribution_manifest_v1.json"
    audit_record_path = audit_root / "manifests/family_c_c001_attribution_result_v1.json"
    _immutable_audit_record(audit_record_path, audit_record)
    write_csv(audit_root / "event_cohort/signal_quality_cohort_v1.csv", events)
    write_csv(audit_root / "capacity/c001_admission_classification_v1.csv", admissions)
    write_csv(audit_root / "capacity/capacity_by_year_v1.csv", capacity_yearly)
    write_csv(audit_root / "capacity/capacity_by_signal_load_v1.csv", capacity_load)
    write_json(audit_root / "capacity/portfolio_occupancy_v1.json", occupancy)
    write_csv(audit_root / "ranking/capacity_ranking_events_v1.csv", ranking_detail)
    write_csv(audit_root / "ranking/capacity_ranking_quartiles_v1.csv", ranking_aggregate)
    write_csv(audit_root / "matched_days/same_day_matches_v1.csv", matched_days)
    write_csv(audit_root / "diagnostics/compression_pass_fail_v1.csv", compression)
    write_csv(audit_root / "diagnostics/compression_yearly_v1.csv", yearly)
    write_csv(audit_root / "diagnostics/admitted_vs_rejected_v1.csv", admitted_rejected)
    write_csv(audit_root / "diagnostics/holding_path_v1.csv", holding)
    write_csv(audit_root / "diagnostics/breakout_strength_v1.csv", breakout)
    write_csv(audit_root / "diagnostics/entry_gap_v1.csv", entry_gap)
    write_csv(audit_root / "diagnostics/compression_distribution_v1.csv", distribution)

    report_rows = {
        REPORT_NAMES[1]: events,
        REPORT_NAMES[2]: compression,
        REPORT_NAMES[3]: yearly,
        REPORT_NAMES[4]: admitted_rejected,
        REPORT_NAMES[5]: capacity_yearly,
        REPORT_NAMES[6]: ranking_detail,
        REPORT_NAMES[7]: matched_days,
        REPORT_NAMES[8]: holding,
        REPORT_NAMES[9]: breakout,
        REPORT_NAMES[10]: entry_gap,
        REPORT_NAMES[11]: distribution,
    }
    for name, rows in report_rows.items():
        write_csv(reports_root / name, rows)

    command_02_after = command_02_snapshot(root)
    if command_02_before != command_02_after:
        raise FamilyCC001AttributionImmutabilityError(
            "Family C Command 02 changed during attribution audit"
        )

    artifact_paths = [
        audit_record_path,
        *(path for path in audit_root.rglob("*") if path.is_file() and path != manifest_path),
        *(reports_root / name for name in REPORT_NAMES[1:]),
    ]
    artifact_hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in sorted(set(artifact_paths))
    }
    summary = {
        **audit_record,
        "generated_at": started_at,
        "freeze_gate": {
            "status": frozen["status"],
            "checks": frozen["checks"],
        },
        "immutability": {
            "command_02_snapshot_before": command_02_before["snapshot_hash"],
            "command_02_snapshot_after": command_02_after["snapshot_hash"],
            "command_02_unchanged": True,
        },
        "storage": {
            "root": audit_root.relative_to(root).as_posix(),
            "artifact_hashes": artifact_hashes,
        },
        "known_limitations": (
            "DEVELOPMENT_ONLY_AND_NOT_VALIDATED",
            "EVENT_COHORT_IS_SIGNAL_QUALITY_ONLY_NOT_SIMULTANEOUSLY_DEPLOYABLE",
            "NORMALIZED_EVENT_COST_USES_FIXED_25000_RUPEE_REFERENCE_NOTIONAL",
            "SAME_DAY_MATCHING_PARTIALLY_CONTROLS_MARKET_CONDITIONS_ONLY",
            "CAPACITY_ADMISSION_REPLAY_RECONCILES_FROZEN_OUTPUT_BUT_IS_NOT_A_NEW_STRATEGY",
            "BUCKETS_AND_HOLDING_PATHS_ARE_DESCRIPTIVE_NOT_OPTIMIZED_RULES",
        ),
        "verification": {
            "backend_targeted_tests": "NOT_RUN",
            "backend_full_tests": "NOT_RUN",
            "frontend_build": "NOT_RUN",
            "ready_for_review": False,
        },
    }
    summary_path = reports_root / REPORT_NAMES[0]
    write_json(summary_path, summary)
    manifest_body = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "family_version": FAMILY_VERSION,
        "family_c_c001_attribution_hash": audit_record[
            "family_c_c001_attribution_hash"
        ],
        "artifact_hashes": artifact_hashes,
        "summary_hash": file_sha256(summary_path),
        "command_02_snapshot_hash": command_02_after["snapshot_hash"],
        "validation_accessed": False,
        "strategy_v2_created": False,
    }
    manifest = {
        **manifest_body,
        "family_c_c001_attribution_manifest_hash": canonical_hash(manifest_body),
    }
    write_json(manifest_path, manifest)
    return summary


def finalize_family_c_c001_attribution_review(
    root: Path,
    *,
    backend_targeted_tests: str,
    backend_full_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    summary_path = root / "data/reports" / REPORT_NAMES[0]
    manifest_path = output_root(root) / "manifests/family_c_c001_attribution_manifest_v1.json"
    summary = _read_json(summary_path)
    passed = all(
        "passed" in value.lower()
        for value in (backend_targeted_tests, backend_full_tests, frontend_build)
    )
    summary["verification"] = {
        "backend_targeted_tests": backend_targeted_tests,
        "backend_full_tests": backend_full_tests,
        "frontend_build": frontend_build,
        "ready_for_review": passed,
    }
    write_json(summary_path, summary)
    manifest = _read_json(manifest_path)
    manifest["summary_hash"] = file_sha256(summary_path)
    field = "family_c_c001_attribution_manifest_hash"
    manifest[field] = canonical_hash(_without_hash(manifest, field))
    write_json(manifest_path, manifest)
    return summary


__all__ = [
    "COHORT_LABEL",
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "EXPECTED_C001_RESULT_HASH",
    "EXPECTED_C002_RESULT_HASH",
    "EXPECTED_CONTROL_RESULT_HASH",
    "EXPECTED_DEVELOPMENT_REGISTRY_HASH",
    "NORMALIZED_EVENT_NOTIONAL",
    "REPLAY_LABEL",
    "REPORT_NAMES",
    "build_event_cohort",
    "build_family_c_c001_attribution_audit",
    "capacity_ranking_rows",
    "classify_capacity_materiality",
    "classify_capacity_selection",
    "classify_development_advantage",
    "classify_ranking",
    "classify_signal_quality",
    "classify_temporal_consistency",
    "cohort_metrics",
    "compression_bucket_rows",
    "compression_distribution_rows",
    "finalize_family_c_c001_attribution_review",
    "holding_path_rows",
    "next_stage",
    "normalized_event_outcome",
    "occupancy_metrics",
    "reconstruct_frozen_admissions",
    "same_day_matched_rows",
    "verify_frozen_inputs",
]
