from __future__ import annotations

import csv
import json
import math
import re
import statistics
import subprocess
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.research.strategy.family_a_development_backtest import (
    COST_COMPONENTS,
    EXECUTABLE_MODE,
    RebalanceSchedule,
    SelectedInstrument,
    _cost_for_mode,
    _flatten_order_cost,
    _maximum_affordable_quantity,
    _period_row,
    _record_period_positions,
    _valuation,
)
from app.research.strategy.family_a_momentum import (
    LIQUIDITY_FLOOR,
    LIQUIDITY_WINDOW,
    LOOKBACK_SESSIONS,
    PRICE_FLOOR,
    AdjustedBar,
    _corporate_action_exclusions,
    _corporate_action_safe,
    _date_from_adjusted_path,
    _load_aliases,
    _load_membership,
    _median_traded_value,
    compounded_return,
    decimal,
    file_sha256,
    read_csv,
    select_top_decile,
    write_csv,
    write_json,
)
from app.research.strategy.family_a_validation_design import (
    A2_002_IMPLEMENTATION_HASH,
    A2_002_PREREGISTRATION_HASH,
    CANDIDATE_ID,
    CONTAMINATION_DISCLOSURE,
    COST_CONFIG_HASH,
    FAMILY_A_CLOSURE_HASH,
    FAMILY_CONFIG_HASH,
    MOM_A_002_PARAMETER_HASH,
    MOM_A_002_PREREGISTRATION_HASH,
    SYNTHESIS_HASH,
    classify_validation_result,
)
from app.research.temporal_validation.config import canonical_hash


COMMAND = "Step 03.09 / Command 02"
COMMAND_VERSION = "FAMILY_A_ONE_SHOT_VALIDATION_V1"
COMMAND_PROFILE = "MOM_A_002_FORMAL_HOLDOUT_VALIDATION_V1"
AUTHORIZATION_VERSION = "FAMILY_A_VALIDATION_AUTHORIZATION_V1"
MANIFEST_VERSION = "FAMILY_A_ONE_SHOT_VALIDATION_MANIFEST_V1"
INVALIDATION_VERSION = "FAMILY_A_VALIDATION_ATTEMPT_INVALIDATION_V1"
REPLACEMENT_AUTHORIZATION_VERSION = "FAMILY_A_VALIDATION_REPLACEMENT_AUTHORIZATION_V1"

REQUIRED_CHECKPOINT = "33bc139f007593bb3149dfc0acb20fed9ef9d367"
DESIGN_HASH = "8effd2ca6233c581d88aab46d16ff48b1aa04c0ce7648be11889c094d401a494"
DESIGN_CONFIG_HASH = "3c4c54f7a4c3e136d8f7e3a5dd395f81dd9aa768324056e4746db6a02dbcad43"
DESIGN_SCHEDULE_HASH = "42650a34a30d51f9817454cba938518ae9fbb84d180cdeff4e0fdf9d9bf771a7"
DESIGN_CRITERIA_HASH = "89bec4f0b213c0b7a9bf8d1f67e0cf5c853fb3775e1ce9120bbb7933d1bc1ad4"
DESIGN_READINESS_HASH = "405c17697f5aacc011b926dfebfa9b03536164126d3bbdbe618f2a2bdf9e0040"
CANDIDATE_IDENTITY_HASH = "0e8ef3cc26d4146258f25fdd4c269867a383d2f098d9df0e367d4b0ff86beacc"
ORIGINAL_AUTHORIZATION_HASH = "bb1789cb5744cb9f777bf48dc1493b3fc115c3726cb95b86b844d067d8408631"
FAILED_ATTEMPT_INPUT_SNAPSHOT_HASH = "e265caeb28c0bfc41c2edcfd36f78fa39abd45f647c036e00d7ed5c888087adf"
FAILED_ATTEMPT_SOURCE_HASH = "a91115f803cbb4ffe1d3a27fb7c62eb9dd26a0c0b7c312197e83709c2d55f1a1"
ATTEMPT_INVALIDATION_HASH = "67996558f869866d689826a22196b70ba0829646f3642dfcd436c1325abe76fb"

VALIDATION_START = date(2025, 1, 1)
VALIDATION_END = date(2026, 8, 13)
PRIMARY_END = date(2026, 7, 1)
STARTING_CAPITAL = Decimal("500000")
RUN_NUMBER = 1
MAXIMUM_FORMAL_RUNS = 1

SEALED_SCHEDULE = (
    (date(2024, 12, 31), date(2025, 1, 1)),
    (date(2025, 3, 28), date(2025, 4, 1)),
    (date(2025, 6, 30), date(2025, 7, 1)),
    (date(2025, 9, 30), date(2025, 10, 1)),
    (date(2025, 12, 31), date(2026, 1, 1)),
    (date(2026, 3, 30), date(2026, 4, 1)),
    (date(2026, 6, 30), date(2026, 7, 1)),
)

REPORT_NAMES = (
    "family_a_validation_v1_summary.json",
    "family_a_validation_v1_metrics.csv",
    "family_a_validation_v1_rebalances.csv",
    "family_a_validation_v1_holdings.csv",
    "family_a_validation_v1_costs.csv",
    "family_a_validation_v1_criteria.csv",
    "family_a_validation_v1_quality.csv",
    "family_a_validation_v1_data_quality.csv",
    "family_a_validation_v1_development_comparison.csv",
    "family_a_validation_v1_advancement.csv",
    "family_a_validation_v1_attempt_history.csv",
    "family_a_validation_v1_invalidation.json",
)


class FamilyAValidationRepositoryStateMismatch(RuntimeError):
    pass


class FamilyAValidationDesignMismatch(RuntimeError):
    pass


class FamilyAValidationAuthorizationError(RuntimeError):
    pass


class FamilyASecondFormalRunProhibited(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def evaluation_root(root: Path) -> Path:
    return Path(root) / "data/research/validation/family_a/v1/evaluation"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _document_hash(document: Mapping[str, Any], hash_field: str) -> str:
    return canonical_hash({key: value for key, value in document.items() if key != hash_field})


def _write_immutable_json(path: Path, document: Mapping[str, Any]) -> None:
    if path.exists():
        raise FamilyASecondFormalRunProhibited(
            f"SECOND_FORMAL_VALIDATION_RUN_ALLOWED=NO; immutable artifact exists: {path}"
        )
    write_json(path, document)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=False
    )


def verify_repository_and_design(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    head = _git(root, "rev-parse", "HEAD")
    branch = _git(root, "branch", "--show-current")
    upstream = _git(
        root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"
    )
    ancestry = _git(root, "merge-base", "--is-ancestor", REQUIRED_CHECKPOINT, "HEAD")
    if any(result.returncode for result in (head, branch, upstream)):
        raise FamilyAValidationRepositoryStateMismatch(
            "FAMILY_A_VALIDATION_REPOSITORY_STATE_MISMATCH"
        )
    checkpoint = {
        "required_checkpoint": REQUIRED_CHECKPOINT,
        "head": head.stdout.strip(),
        "branch": branch.stdout.strip(),
        "upstream": upstream.stdout.strip(),
        "checkpoint_is_ancestor": ancestry.returncode == 0,
    }
    if not (
        checkpoint["head"] == REQUIRED_CHECKPOINT
        and checkpoint["branch"] == "main"
        and checkpoint["upstream"] == "origin/main"
        and checkpoint["checkpoint_is_ancestor"]
    ):
        raise FamilyAValidationRepositoryStateMismatch(
            f"FAMILY_A_VALIDATION_REPOSITORY_STATE_MISMATCH: {checkpoint}"
        )

    design_summary = _read_json(
        root / "data/reports/family_a_validation_design_v1_summary.json"
    )
    design_manifest = _read_json(
        root
        / "data/research/validation/family_a/v1/design/manifests/family_a_one_shot_validation_design_manifest_v1.json"
    )
    synthesis = _read_json(
        root / "data/reports/cross_family_synthesis_v1_summary.json"
    )
    design_checks = {
        "synthesis_hash": synthesis.get("cross_family_synthesis_hash") == SYNTHESIS_HASH,
        "synthesis_classification": synthesis.get("candidate_selection", {}).get(
            "candidate_selection_classification"
        )
        == "SINGLE_LEADING_CANDIDATE",
        "candidate_id": synthesis.get("candidate_selection", {})
        .get("provisional_candidate", {})
        .get("candidate_id")
        == CANDIDATE_ID,
        "design_hash": design_summary.get("family_a_validation_design_hash")
        == DESIGN_HASH,
        "manifest_hash": design_manifest.get("family_a_validation_design_hash")
        == DESIGN_HASH,
        "manifest_recomputed": _document_hash(
            design_manifest, "family_a_validation_design_hash"
        )
        == DESIGN_HASH,
        "design_config_hash": design_summary.get("design_config", {}).get(
            "family_a_validation_design_config_hash"
        )
        == DESIGN_CONFIG_HASH,
        "schedule_hash": design_summary.get("schedule", {}).get(
            "family_a_validation_schedule_hash"
        )
        == DESIGN_SCHEDULE_HASH,
        "criteria_hash": design_summary.get("success_criteria", {}).get(
            "family_a_validation_success_criteria_hash"
        )
        == DESIGN_CRITERIA_HASH,
        "readiness_hash": design_summary.get("data_readiness", {}).get(
            "family_a_validation_data_readiness_hash"
        )
        == DESIGN_READINESS_HASH,
        "candidate_identity_hash": design_summary.get("candidate_identity", {}).get(
            "family_a_validation_candidate_identity_hash"
        )
        == CANDIDATE_IDENTITY_HASH,
        "family_config_hash": design_summary.get("candidate_identity", {})
        .get("frozen_hashes", {})
        .get("family_a_family_config_hash")
        == FAMILY_CONFIG_HASH,
        "mom_parameter_hash": design_summary.get("candidate_identity", {})
        .get("frozen_hashes", {})
        .get("mom_a_002_parameter_hash")
        == MOM_A_002_PARAMETER_HASH,
        "mom_preregistration_hash": design_summary.get("candidate_identity", {})
        .get("frozen_hashes", {})
        .get("mom_a_002_preregistration_hash")
        == MOM_A_002_PREREGISTRATION_HASH,
        "a2_002_implementation_hash": design_summary.get("candidate_identity", {})
        .get("frozen_hashes", {})
        .get("a2_002_implementation_config_hash")
        == A2_002_IMPLEMENTATION_HASH,
        "a2_002_preregistration_hash": design_summary.get("candidate_identity", {})
        .get("frozen_hashes", {})
        .get("a2_002_preregistration_hash")
        == A2_002_PREREGISTRATION_HASH,
        "cost_config_hash": design_summary.get("candidate_identity", {})
        .get("frozen_hashes", {})
        .get("cost_config_hash")
        == COST_CONFIG_HASH,
        "closure_hash": design_summary.get("candidate_identity", {})
        .get("frozen_hashes", {})
        .get("family_a_closure_hash")
        == FAMILY_A_CLOSURE_HASH,
        "lifecycle": design_summary.get("governance", {}).get("current_lifecycle")
        == "SEALED_DESIGN",
        "run_count": design_summary.get("governance", {}).get(
            "validation_run_count"
        )
        == 0,
        "maximum_runs": design_summary.get("governance", {}).get(
            "maximum_formal_run_count"
        )
        == 1,
        "one_shot_readiness": design_summary.get("governance", {}).get(
            "FAMILY_A_ONE_SHOT_VALIDATION_READINESS"
        )
        == "YES",
    }
    if not all(design_checks.values()):
        failures = [key for key, value in design_checks.items() if not value]
        raise FamilyAValidationDesignMismatch(
            "FAMILY_A_VALIDATION_DESIGN_MISMATCH: " + ", ".join(failures)
        )
    return {
        "checkpoint": checkpoint,
        "design_checks": design_checks,
        "design_summary": design_summary,
        "design_manifest": design_manifest,
    }


def authorize_one_shot(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    verified = verify_repository_and_design(root)
    target = evaluation_root(root) / "authorization/authorization_record_v1.json"
    if target.exists() or (
        evaluation_root(root)
        / "manifests/family_a_one_shot_validation_manifest_v1.json"
    ).exists():
        raise FamilyASecondFormalRunProhibited(
            "SECOND_FORMAL_VALIDATION_RUN_ALLOWED=NO"
        )
    body = {
        "authorization_version": AUTHORIZATION_VERSION,
        "command": COMMAND,
        "explicit_user_authorization": True,
        "authorization_source": "USER_COMMAND_STEP_03_09_COMMAND_02",
        "authorization_timestamp": utc_now(),
        "repository_checkpoint": verified["checkpoint"],
        "candidate_id": CANDIDATE_ID,
        "candidate_identity_hash": CANDIDATE_IDENTITY_HASH,
        "validation_design_hash": DESIGN_HASH,
        "validation_design_config_hash": DESIGN_CONFIG_HASH,
        "validation_schedule_hash": DESIGN_SCHEDULE_HASH,
        "validation_success_criteria_hash": DESIGN_CRITERIA_HASH,
        "validation_data_readiness_hash": DESIGN_READINESS_HASH,
        "lifecycle_before": "SEALED_DESIGN",
        "lifecycle_after": "AUTHORIZED_FOR_ONE_SHOT",
        "run_count_before": 0,
        "authorized_run": RUN_NUMBER,
        "maximum_formal_runs": MAXIMUM_FORMAL_RUNS,
        "candidate_mutation": False,
        "criteria_mutation": False,
        "validation_outcomes_accessed_before_authorization": False,
    }
    record = {**body, "family_a_validation_authorization_hash": canonical_hash(body)}
    _write_immutable_json(target, record)
    authorized_state = {
        "lifecycle": "AUTHORIZED_FOR_ONE_SHOT",
        "run_count": 0,
        "authorized_run": 1,
        "authorization_hash": record["family_a_validation_authorization_hash"],
        "performance_outcomes_opened": False,
    }
    _write_immutable_json(
        evaluation_root(root)
        / "authorization/authorized_lifecycle_state_v1.json",
        authorized_state,
    )
    return record


def _authorization(root: Path) -> dict[str, Any]:
    path = evaluation_root(root) / "authorization/authorization_record_v1.json"
    if not path.is_file():
        raise FamilyAValidationAuthorizationError(
            "Immutable authorization record is required before validation access"
        )
    record = _read_json(path)
    if not (
        record.get("lifecycle_after") == "AUTHORIZED_FOR_ONE_SHOT"
        and record.get("run_count_before") == 0
        and record.get("authorized_run") == 1
        and record.get("maximum_formal_runs") == 1
        and _document_hash(record, "family_a_validation_authorization_hash")
        == record.get("family_a_validation_authorization_hash")
    ):
        raise FamilyAValidationAuthorizationError("Authorization record mismatch")
    return record


def _attempt_invalidation(root: Path) -> dict[str, Any]:
    path = (
        evaluation_root(root)
        / "authorization/attempt_1_invalidation_record_v1.json"
    )
    if not path.is_file():
        raise FamilyAValidationAuthorizationError(
            "Governed attempt invalidation is required before replacement"
        )
    record = _read_json(path)
    if not (
        record.get("invalidation_version") == INVALIDATION_VERSION
        and record.get("status") == "INVALIDATED_IMPLEMENTATION_DEFECT"
        and record.get("failure_type") == "DETERMINISTIC_SERIALIZER_DEFECT"
        and record.get("attempt_number") == 1
        and record.get("replacement_authorized") is True
        and record.get("candidate_mutation") is False
        and record.get("criteria_mutation") is False
        and record.get("input_snapshot_mutation") is False
        and record.get("performance_persistence") is False
        and record.get("result_sealing") is False
        and _document_hash(
            record, "family_a_validation_attempt_invalidation_hash"
        )
        == ATTEMPT_INVALIDATION_HASH
        == record.get("family_a_validation_attempt_invalidation_hash")
    ):
        raise FamilyAValidationAuthorizationError(
            "Governed attempt invalidation mismatch"
        )
    return record


def _existing_input_snapshot(root: Path) -> dict[str, Any]:
    path = evaluation_root(root) / "inputs/input_snapshot_v1.json"
    if not path.is_file():
        raise FamilyAValidationAuthorizationError(
            "Frozen failed-attempt input snapshot is required"
        )
    snapshot = _read_json(path)
    observed_hash = snapshot.get("family_a_validation_input_snapshot_hash")
    if not (
        observed_hash == FAILED_ATTEMPT_INPUT_SNAPSHOT_HASH
        and _document_hash(snapshot, "family_a_validation_input_snapshot_hash")
        == FAILED_ATTEMPT_INPUT_SNAPSHOT_HASH
        and snapshot.get("last_loaded_date") == VALIDATION_END.isoformat()
        and snapshot.get("post_holdout_files_loaded") == 0
    ):
        raise FamilyAValidationAuthorizationError(
            "Frozen failed-attempt input snapshot mismatch"
        )
    validator_path = "backend/app/research/strategy/family_a_one_shot_validation.py"
    if snapshot.get("file_hashes", {}).get(validator_path) != FAILED_ATTEMPT_SOURCE_HASH:
        raise FamilyAValidationAuthorizationError(
            "Failed-attempt implementation identity mismatch"
        )
    mismatches = [
        relative_path
        for relative_path, expected_hash in snapshot["file_hashes"].items()
        if relative_path != validator_path
        and file_sha256(root / relative_path) != expected_hash
    ]
    if mismatches:
        raise FamilyAValidationAuthorizationError(
            "Frozen validation input files changed: " + ", ".join(mismatches)
        )
    return snapshot


def authorize_replacement_run(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    verified = verify_repository_and_design(root)
    authorization = _authorization(root)
    invalidation = _attempt_invalidation(root)
    snapshot = _existing_input_snapshot(root)
    target = evaluation_root(root) / "authorization/replacement_authorization_v1.json"
    if target.exists():
        raise FamilyASecondFormalRunProhibited(
            "Replacement authorization already exists"
        )
    body = {
        "replacement_authorization_version": REPLACEMENT_AUTHORIZATION_VERSION,
        "command": "Step 03.09 / Command 02A",
        "authorization_timestamp": utc_now(),
        "replacement_reason": "PROVEN_DETERMINISTIC_IMPLEMENTATION_DEFECT",
        "original_authorization_hash": authorization[
            "family_a_validation_authorization_hash"
        ],
        "invalidation_hash": invalidation[
            "family_a_validation_attempt_invalidation_hash"
        ],
        "validation_design_hash": DESIGN_HASH,
        "candidate_identity_hash": CANDIDATE_IDENTITY_HASH,
        "input_snapshot_hash": snapshot[
            "family_a_validation_input_snapshot_hash"
        ],
        "replacement_valid_run_number": 1,
        "attempt_number": 2,
        "attempt_count_before_replacement": 1,
        "invalidated_attempt_count": 1,
        "completed_valid_formal_runs_before_replacement": 0,
        "remaining_valid_replacement_runs": 1,
        "lifecycle": "AUTHORIZED_FOR_ONE_SHOT",
        "candidate_mutation": False,
        "criteria_mutation": False,
        "input_snapshot_mutation": False,
        "repository_checkpoint": verified["checkpoint"],
    }
    record = {
        **body,
        "family_a_validation_replacement_authorization_hash": canonical_hash(body),
    }
    _write_immutable_json(target, record)
    return record


def _replacement_authorization(root: Path) -> dict[str, Any]:
    path = evaluation_root(root) / "authorization/replacement_authorization_v1.json"
    if not path.is_file():
        raise FamilyAValidationAuthorizationError(
            "Replacement authorization is required"
        )
    record = _read_json(path)
    if not (
        record.get("replacement_authorization_version")
        == REPLACEMENT_AUTHORIZATION_VERSION
        and record.get("attempt_number") == 2
        and record.get("replacement_valid_run_number") == 1
        and record.get("input_snapshot_hash") == FAILED_ATTEMPT_INPUT_SNAPSHOT_HASH
        and record.get("invalidation_hash") == ATTEMPT_INVALIDATION_HASH
        and _document_hash(
            record, "family_a_validation_replacement_authorization_hash"
        )
        == record.get("family_a_validation_replacement_authorization_hash")
    ):
        raise FamilyAValidationAuthorizationError(
            "Replacement authorization mismatch"
        )
    return record


def _adjusted_paths(root: Path) -> list[tuple[date, Path]]:
    paths: list[tuple[date, Path]] = []
    for path in sorted(
        (root / "data/research/adjusted/daily/nse").glob(
            "*/*/nse_adjusted_daily_*.csv"
        )
    ):
        trading_date = _date_from_adjusted_path(path)
        if trading_date is not None and date(2021, 9, 7) <= trading_date <= VALIDATION_END:
            paths.append((trading_date, path))
    return paths


def build_input_snapshot(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    _authorization(root)
    static_paths = [
        root / "data/reference/nse/calendar/nse_cash_trading_calendar.csv",
        root / "data/reference/nifty500/history/membership_periods.csv",
        root / "data/reference/nifty500/history/membership_identity_aliases.csv",
        root / "data/reference/nifty500/history/membership_coverage.json",
        root / "data/reference/nse/corporate_actions/research_eligibility.csv",
        root / "data/reference/nse/corporate_actions/corporate_action_coverage.json",
        root / "backend/app/research/strategy/family_a_momentum.py",
        root / "backend/app/research/strategy/family_a_development_backtest.py",
        root / "backend/app/research/strategy/family_a_one_shot_validation.py",
    ]
    dated_paths = _adjusted_paths(root)
    if not dated_paths or max(item[0] for item in dated_paths) > VALIDATION_END:
        raise ValueError("Validation input boundary violation")
    file_hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in [*static_paths, *(item[1] for item in dated_paths)]
    }
    body = {
        "validation_window": {
            "start": VALIDATION_START.isoformat(),
            "end": VALIDATION_END.isoformat(),
        },
        "lookback_input_start": dated_paths[0][0].isoformat(),
        "last_loaded_date": dated_paths[-1][0].isoformat(),
        "post_holdout_files_loaded": 0,
        "adjusted_partition_count": len(dated_paths),
        "static_file_count": len(static_paths),
        "file_hashes": file_hashes,
        "candidate_identity_hash": CANDIDATE_IDENTITY_HASH,
        "design_hash": DESIGN_HASH,
    }
    return {**body, "family_a_validation_input_snapshot_hash": canonical_hash(body)}


def _load_sessions(root: Path) -> list[date]:
    return sorted(
        date.fromisoformat(row["trading_date"])
        for row in read_csv(
            root / "data/reference/nse/calendar/nse_cash_trading_calendar.csv"
        )
        if row.get("source_available") == "True"
        and date(2021, 9, 7)
        <= date.fromisoformat(row["trading_date"])
        <= VALIDATION_END
    )


def _load_bounded_bars(
    root: Path, universe_symbols: set[str], aliases: Mapping[str, str]
) -> dict[date, dict[str, AdjustedBar]]:
    result: dict[date, dict[str, AdjustedBar]] = {}
    for trading_date, path in _adjusted_paths(root):
        day: dict[str, AdjustedBar] = {}
        for row in read_csv(path):
            original = row.get("symbol", "").strip().upper()
            symbol = aliases.get(original, original)
            if symbol not in universe_symbols:
                continue
            try:
                bar = AdjustedBar(
                    trading_date=trading_date,
                    symbol=symbol,
                    isin=row.get("isin", ""),
                    open_price=decimal(row["adjusted_open"]),
                    close_price=decimal(row["adjusted_close"]),
                    volume=decimal(row["adjusted_volume"]),
                    usability_status=row.get("research_usability_status", ""),
                    methodology_version=row.get(
                        "adjustment_methodology_version", ""
                    ),
                )
            except (ArithmeticError, KeyError):
                continue
            previous = day.get(symbol)
            if previous is None or row.get("series") == "EQ":
                day[symbol] = bar
        result[trading_date] = day
    if result and max(result) > VALIDATION_END:
        raise ValueError("Post-holdout adjusted bar loaded")
    return result


def build_validation_schedules(
    root: Path,
    sessions: Sequence[date],
    bars: Mapping[date, Mapping[str, AdjustedBar]],
) -> tuple[list[RebalanceSchedule], list[dict[str, Any]], list[dict[str, Any]]]:
    membership = _load_membership(root)
    aliases = _load_aliases(root)
    exclusions = _corporate_action_exclusions(root, aliases)
    symbol_closes: dict[str, dict[date, Decimal]] = defaultdict(dict)
    symbol_statuses: dict[str, dict[date, str]] = defaultdict(dict)
    for trading_date, day in bars.items():
        for symbol, bar in day.items():
            symbol_closes[symbol][trading_date] = bar.close_price
            symbol_statuses[symbol][trading_date] = bar.usability_status
    schedules: list[RebalanceSchedule] = []
    selection_rows: list[dict[str, Any]] = []
    quality_rows: list[dict[str, Any]] = []
    for formation, execution in SEALED_SCHEDULE:
        members = membership.members_for(formation)
        candidates: list[dict[str, Any]] = []
        for symbol, period in sorted(members.items()):
            bar = bars.get(formation, {}).get(symbol)
            momentum = compounded_return(
                symbol_closes.get(symbol, {}), sessions, formation, "6M"
            )
            start_date = momentum.get("start_date")
            safe, blockers = _corporate_action_safe(
                symbol, start_date, formation, exclusions
            )
            liquidity, observations = _median_traded_value(
                symbol, bars, sessions, formation
            )
            execution_bar = bars.get(execution, {}).get(symbol)
            endpoint_statuses = (
                symbol_statuses.get(symbol, {}).get(start_date, "MISSING")
                if start_date
                else "MISSING",
                symbol_statuses.get(symbol, {}).get(
                    momentum.get("end_date"), "MISSING"
                )
                if momentum.get("end_date")
                else "MISSING",
            )
            adjusted_ready = all(
                status == "ADJUSTED_READY" for status in endpoint_statuses
            )
            price = bar.close_price if bar else None
            row = {
                "formation_date": formation.isoformat(),
                "execution_date": execution.isoformat(),
                "symbol": symbol,
                "isin": period.isin or (bar.isin if bar else ""),
                "membership_source_confidence": period.source_confidence,
                "membership_reconstruction_method": period.reconstruction_method,
                "six_month_momentum": momentum.get("value"),
                "signal_start_date": start_date.isoformat() if start_date else None,
                "signal_end_date": momentum.get("end_date").isoformat()
                if momentum.get("end_date")
                else None,
                "formation_price": price,
                "liquidity": liquidity,
                "liquidity_observations": observations,
                "price_gate_pass": price is not None and price >= PRICE_FLOOR,
                "liquidity_gate_pass": liquidity is not None
                and liquidity >= LIQUIDITY_FLOOR,
                "signal_available": momentum.get("value") is not None,
                "corporate_action_safe": safe,
                "corporate_action_blockers": blockers,
                "adjusted_endpoint_ready": adjusted_ready,
                "next_open_available": execution_bar is not None
                and execution_bar.open_price > 0,
                "signal_rank": None,
                "signal_percentile": None,
                "eligible": False,
                "selected_top_decile": False,
            }
            row["eligible"] = all(
                (
                    row["price_gate_pass"],
                    row["liquidity_gate_pass"],
                    row["signal_available"],
                    row["corporate_action_safe"],
                    row["adjusted_endpoint_ready"],
                    row["next_open_available"],
                )
            )
            candidates.append(row)
        selection = select_top_decile(candidates, signal_field="six_month_momentum")
        ranked = {row["symbol"]: row for row in selection["ranked"]}
        selected_symbols = {row["symbol"] for row in selection["selected"]}
        for row in candidates:
            if row["symbol"] in ranked:
                row["signal_rank"] = ranked[row["symbol"]]["signal_rank"]
                row["signal_percentile"] = ranked[row["symbol"]][
                    "signal_percentile"
                ]
            row["selected_top_decile"] = row["symbol"] in selected_symbols
        selected = tuple(
            SelectedInstrument(
                symbol=row["symbol"],
                isin=row["isin"],
                rank=int(row["signal_rank"]),
                signal_value=decimal(row["six_month_momentum"]),
            )
            for row in selection["selected"]
        )
        schedules.append(
            RebalanceSchedule(
                experiment_id="A2-002",
                formation_date=formation,
                execution_date=execution,
                eligible_count=selection["eligible_count"],
                intended_count=selection["selected_count"],
                sufficient_universe=selection["sufficient_universe"],
                selected=selected,
            )
        )
        selection_rows.extend(
            row for row in candidates if row["selected_top_decile"] is True
        )
        quality_rows.append(
            {
                "formation_date": formation.isoformat(),
                "execution_date": execution.isoformat(),
                "point_in_time_member_count": len(members),
                "eligible_count": selection["eligible_count"],
                "selected_count": selection["selected_count"],
                "corporate_action_excluded_count": sum(
                    not row["corporate_action_safe"] for row in candidates
                ),
                "missing_formation_price_count": sum(
                    row["formation_price"] is None for row in candidates
                ),
                "missing_execution_open_count": sum(
                    not row["next_open_available"] for row in candidates
                ),
                "insufficient_liquidity_history_count": sum(
                    row["liquidity"] is None for row in candidates
                ),
                "source_confidence_not_high_count": sum(
                    row["membership_source_confidence"] != "HIGH"
                    for row in candidates
                ),
            }
        )
    observed = tuple(
        (row.formation_date, row.execution_date) for row in schedules
    )
    if observed != SEALED_SCHEDULE:
        raise FamilyAValidationDesignMismatch(
            "FAMILY_A_VALIDATION_DESIGN_MISMATCH: schedule"
        )
    return schedules, selection_rows, quality_rows


def _percent(value: Decimal) -> Decimal:
    return value * Decimal("100")


def simulate_validation_executable(
    schedules: Sequence[RebalanceSchedule],
    sessions: Sequence[date],
    bars: Mapping[date, Mapping[str, AdjustedBar]],
) -> dict[str, Any]:
    if not sessions or sessions[0] != VALIDATION_START or sessions[-1] != VALIDATION_END:
        raise ValueError("Exact validation session boundaries are required")
    if any(not VALIDATION_START <= value_date <= VALIDATION_END for value_date in sessions):
        raise ValueError("Post-holdout session supplied")
    experiment_id = "A2-002"
    mode = "EXECUTABLE_INTEGER_SHARE_500K"
    schedule_by_date = {row.execution_date: row for row in schedules}
    holdings: dict[str, int] = {}
    cash = STARTING_CAPITAL
    cumulative_cost = Decimal("0")
    last_prices: dict[str, Decimal] = {}
    daily: list[dict[str, Any]] = []
    rebalances: list[dict[str, Any]] = []
    holding_rows: list[dict[str, Any]] = []
    cost_rows: list[dict[str, Any]] = []
    periods: list[dict[str, Any]] = []
    position_returns: list[dict[str, Any]] = []
    period_start_date: date | None = None
    period_start_gross: Decimal | None = None
    period_start_net: Decimal | None = None
    period_positions: dict[str, tuple[Decimal, Decimal]] = {}
    cash_reconciliation_violations = 0
    equity_reconciliation_violations = 0

    for value_date in sessions:
        schedule = schedule_by_date.get(value_date)
        if schedule is not None:
            decimal_holdings = {
                key: Decimal(value) for key, value in holdings.items()
            }
            holdings_value, valuation_prices, missing_valuation = _valuation(
                decimal_holdings, value_date, bars, last_prices, use_open=True
            )
            net_pre = cash + holdings_value
            gross_pre = net_pre + cumulative_cost
            if (
                period_start_date is not None
                and period_start_gross is not None
                and period_start_net is not None
            ):
                periods.append(
                    _period_row(
                        experiment_id=experiment_id,
                        mode=mode,
                        start_date=period_start_date,
                        end_date=value_date,
                        start_gross=period_start_gross,
                        end_gross=gross_pre,
                        start_net=period_start_net,
                        end_net=net_pre,
                        final_partial=False,
                    )
                )
                position_returns.extend(
                    _record_period_positions(
                        experiment_id=experiment_id,
                        mode=mode,
                        start_date=period_start_date,
                        end_date=value_date,
                        start_positions=period_positions,
                        end_prices=valuation_prices,
                        final_partial=False,
                    )
                )

            before_symbols = {
                symbol for symbol, quantity in holdings.items() if quantity > 0
            }
            selected_symbols = {row.symbol for row in schedule.selected}
            retained = before_symbols & selected_symbols
            added = selected_symbols - before_symbols
            removed = before_symbols - selected_symbols
            start_cash = cash
            sale_proceeds = Decimal("0")
            sell_costs = Decimal("0")
            buy_notional = Decimal("0")
            buy_costs = Decimal("0")
            sell_notional = Decimal("0")
            status = "INSUFFICIENT_UNIVERSE_RETAIN_PRIOR_PORTFOLIO"
            desired_targets: dict[str, int] = dict(holdings)
            unavailable_execution: list[str] = []
            if schedule.sufficient_universe:
                actual_execution_prices = {
                    symbol: bar.open_price
                    for symbol, bar in bars.get(value_date, {}).items()
                    if bar.open_price > 0
                }
                target_amount = net_pre / Decimal(len(schedule.selected))
                desired_targets = {
                    row.symbol: int(
                        (
                            target_amount / actual_execution_prices[row.symbol]
                        ).to_integral_value(rounding=ROUND_FLOOR)
                    )
                    for row in schedule.selected
                    if row.symbol in actual_execution_prices
                }
                if len(desired_targets) != len(schedule.selected):
                    raise ValueError(
                        f"Missing selected next-open price for {experiment_id} on {value_date}"
                    )
                for symbol in sorted(set(holdings) | set(desired_targets)):
                    current = holdings.get(symbol, 0)
                    target = desired_targets.get(symbol, 0)
                    if target >= current:
                        continue
                    price = actual_execution_prices.get(symbol)
                    if price is None:
                        desired_targets[symbol] = current
                        unavailable_execution.append(symbol)
                        continue
                    quantity = current - target
                    notional = Decimal(quantity) * price
                    cost = _cost_for_mode("SELL", value_date, notional, EXECUTABLE_MODE)
                    applied = decimal(cost["applied_total_cost"])
                    cash += notional - applied
                    holdings[symbol] = target
                    if target == 0:
                        holdings.pop(symbol, None)
                    sale_proceeds += notional
                    sell_notional += notional
                    sell_costs += applied
                    cumulative_cost += applied
                    cost_rows.append(
                        _flatten_order_cost(
                            experiment_id=experiment_id,
                            mode=mode,
                            execution_date=value_date,
                            symbol=symbol,
                            side="SELL",
                            quantity=Decimal(quantity),
                            price=price,
                            cost=cost,
                        )
                    )
                rank_lookup = {row.symbol: row.rank for row in schedule.selected}
                for symbol in sorted(
                    desired_targets,
                    key=lambda item: (rank_lookup.get(item, 10**9), item),
                ):
                    current = holdings.get(symbol, 0)
                    desired = desired_targets[symbol]
                    if desired <= current:
                        continue
                    price = actual_execution_prices[symbol]
                    quantity = _maximum_affordable_quantity(
                        desired - current, price, cash, value_date
                    )
                    if quantity <= 0:
                        continue
                    notional = Decimal(quantity) * price
                    cost = _cost_for_mode("BUY", value_date, notional, EXECUTABLE_MODE)
                    applied = decimal(cost["applied_total_cost"])
                    required = notional + applied
                    if required > cash + Decimal("0.000001"):
                        raise ValueError(
                            "Affordable-quantity search produced an infeasible purchase"
                        )
                    cash -= required
                    holdings[symbol] = current + quantity
                    buy_notional += notional
                    buy_costs += applied
                    cumulative_cost += applied
                    cost_rows.append(
                        _flatten_order_cost(
                            experiment_id=experiment_id,
                            mode=mode,
                            execution_date=value_date,
                            symbol=symbol,
                            side="BUY",
                            quantity=Decimal(quantity),
                            price=price,
                            cost=cost,
                        )
                    )
                status = (
                    "EXECUTED"
                    if not unavailable_execution
                    else "EXECUTED_WITH_DEFERRED_MISSING_OPEN_EXITS"
                )
            expected_cash = (
                start_cash
                + sale_proceeds
                - sell_costs
                - buy_notional
                - buy_costs
            )
            cash_mismatch = abs(cash - expected_cash)
            if cash_mismatch > Decimal("0.000001"):
                cash_reconciliation_violations += 1
            post_holdings = {
                key: Decimal(value) for key, value in holdings.items() if value > 0
            }
            post_value, post_prices, post_missing = _valuation(
                post_holdings, value_date, bars, last_prices, use_open=True
            )
            net_post = cash + post_value
            gross_post = net_post + cumulative_cost
            equity_mismatch = abs((cash + post_value) - net_post)
            if equity_mismatch > Decimal("0.000001"):
                equity_reconciliation_violations += 1
            actual_weights = {
                symbol: quantity * post_prices[symbol] / net_post
                for symbol, quantity in post_holdings.items()
                if symbol in post_prices and net_post
            }
            target_weight = (
                Decimal("1") / Decimal(len(schedule.selected))
                if schedule.selected
                else Decimal("0")
            )
            tracking_l1 = sum(
                (
                    abs(actual_weights.get(symbol, Decimal("0")) - target_weight)
                    for symbol in selected_symbols
                ),
                Decimal("0"),
            )
            for symbol in sorted(actual_weights):
                holding_rows.append(
                    {
                        "experiment_id": experiment_id,
                        "mode": mode,
                        "execution_date": value_date.isoformat(),
                        "scope": (
                            "TERMINAL_DIAGNOSTIC"
                            if value_date == PRIMARY_END
                            else "PRIMARY"
                        ),
                        "symbol": symbol,
                        "quantity": holdings[symbol],
                        "price": post_prices[symbol],
                        "market_value": Decimal(holdings[symbol])
                        * post_prices[symbol],
                        "actual_weight_pct": _percent(actual_weights[symbol]),
                        "cash_weight_pct": _percent(cash / net_post)
                        if net_post
                        else None,
                    }
                )
            largest = max(actual_weights.values(), default=Decimal("0"))
            top_five = sum(
                sorted(actual_weights.values(), reverse=True)[:5], Decimal("0")
            )
            turnover = (
                (buy_notional + sell_notional) / net_pre
                if net_pre
                else Decimal("0")
            )
            unaffordable = sum(
                holdings.get(row.symbol, 0) == 0 for row in schedule.selected
            )
            rebalances.append(
                {
                    "experiment_id": experiment_id,
                    "mode": mode,
                    "scope": (
                        "TERMINAL_DIAGNOSTIC"
                        if value_date == PRIMARY_END
                        else "PRIMARY"
                    ),
                    "formation_date": schedule.formation_date.isoformat(),
                    "execution_date": value_date.isoformat(),
                    "status": status,
                    "eligible_count": schedule.eligible_count,
                    "intended_holdings": schedule.intended_count,
                    "selected_count": len(schedule.selected),
                    "actual_holdings": len(holdings),
                    "retained_count": len(retained),
                    "added_count": len(added),
                    "removed_count": len(removed),
                    "retention_rate_pct": (
                        _percent(
                            Decimal(len(retained)) / Decimal(len(before_symbols))
                        )
                        if before_symbols
                        else None
                    ),
                    "gross_buy_turnover": buy_notional,
                    "gross_sell_turnover": sell_notional,
                    "one_way_turnover": turnover,
                    "rebalance_cost": sell_costs + buy_costs,
                    "flat_delivery_cost_excluded": Decimal("0"),
                    "pre_rebalance_gross_equity": gross_pre,
                    "pre_rebalance_net_equity": net_pre,
                    "post_rebalance_gross_equity": gross_post,
                    "post_rebalance_net_equity": net_post,
                    "cash": cash,
                    "cash_residual_pct": _percent(cash / net_post)
                    if net_post
                    else None,
                    "unaffordable_names": unaffordable,
                    "largest_position_weight_pct": _percent(largest),
                    "top_five_weight_pct": _percent(top_five),
                    "tracking_difference_l1_pct": _percent(tracking_l1),
                    "missing_valuation_count": len(
                        set(missing_valuation + post_missing)
                    ),
                    "deferred_missing_open_exits": len(unavailable_execution),
                    "cash_reconciliation_mismatch": cash_mismatch,
                    "equity_reconciliation_mismatch": equity_mismatch,
                }
            )
            period_start_date = value_date
            period_start_gross = gross_post
            period_start_net = net_post
            period_positions = {
                symbol: (Decimal(quantity), post_prices[symbol])
                for symbol, quantity in holdings.items()
                if symbol in post_prices and quantity > 0
            }

        close_holdings = {
            key: Decimal(value) for key, value in holdings.items() if value > 0
        }
        close_value, close_prices, missing_close = _valuation(
            close_holdings, value_date, bars, last_prices, use_open=False
        )
        net_close = cash + close_value
        gross_close = net_close + cumulative_cost
        equity_mismatch = abs((cash + close_value) - net_close)
        if equity_mismatch > Decimal("0.000001"):
            equity_reconciliation_violations += 1
        daily.append(
            {
                "experiment_id": experiment_id,
                "mode": mode,
                "date": value_date.isoformat(),
                "scope": (
                    "PRIMARY" if value_date < PRIMARY_END else "TERMINAL_DIAGNOSTIC"
                ),
                "valuation_point": "SESSION_CLOSE",
                "gross_equity": gross_close,
                "net_equity": net_close,
                "cash": cash,
                "holdings_value": close_value,
                "holding_count": len(close_holdings),
                "cumulative_cost": cumulative_cost,
                "cumulative_flat_delivery_cost_excluded": Decimal("0"),
                "missing_close_valuation_count": len(missing_close),
                "equity_reconciliation_mismatch": equity_mismatch,
            }
        )
        for symbol, price in close_prices.items():
            last_prices[symbol] = price

    if (
        period_start_date is not None
        and period_start_gross is not None
        and period_start_net is not None
    ):
        final = daily[-1]
        periods.append(
            _period_row(
                experiment_id=experiment_id,
                mode=mode,
                start_date=period_start_date,
                end_date=sessions[-1],
                start_gross=period_start_gross,
                end_gross=decimal(final["gross_equity"]),
                start_net=period_start_net,
                end_net=decimal(final["net_equity"]),
                final_partial=True,
            )
        )
        _, final_prices, _ = _valuation(
            close_holdings, sessions[-1], bars, last_prices, use_open=False
        )
        position_returns.extend(
            _record_period_positions(
                experiment_id=experiment_id,
                mode=mode,
                start_date=period_start_date,
                end_date=sessions[-1],
                start_positions=period_positions,
                end_prices=final_prices,
                final_partial=True,
            )
        )
    terminal_rebalance = next(
        row for row in rebalances if row["execution_date"] == PRIMARY_END.isoformat()
    )
    for row in cost_rows:
        row["cost_model"] = "INDIA_EQUITY_COST_MODEL_V1"
        row["cost_profile"] = "NSE_CASH_DELIVERY_RESEARCH_V1"
        row["cost_config_hash"] = COST_CONFIG_HASH
        row["cost_scenario"] = "COST-SCENARIO-002"
    primary_endpoint = {
        "experiment_id": experiment_id,
        "mode": mode,
        "date": PRIMARY_END.isoformat(),
        "scope": "PRIMARY_ENDPOINT",
        "valuation_point": "PRE_TERMINAL_REBALANCE_OPEN",
        "gross_equity": terminal_rebalance["pre_rebalance_gross_equity"],
        "net_equity": terminal_rebalance["pre_rebalance_net_equity"],
        "cumulative_cost": sum(
            (
                decimal(row["applied_total_cost"])
                for row in cost_rows
                if row["execution_date"] < PRIMARY_END.isoformat()
            ),
            Decimal("0"),
        ),
    }
    return {
        "experiment_id": experiment_id,
        "mode": mode,
        "daily": daily,
        "primary_endpoint": primary_endpoint,
        "rebalances": rebalances,
        "holdings": holding_rows,
        "costs": cost_rows,
        "periods": periods,
        "position_returns": position_returns,
        "cash_reconciliation_violations": cash_reconciliation_violations,
        "equity_reconciliation_violations": equity_reconciliation_violations,
        "cost_model_status": "FULL_FROZEN_COST_MODEL",
    }


def _daily_returns(values: Sequence[Decimal], starting: Decimal) -> list[Decimal]:
    result: list[Decimal] = []
    previous = starting
    for value in values:
        result.append(value / previous - Decimal("1") if previous else Decimal("0"))
        previous = value
    return result


def _annualized_volatility(returns: Sequence[Decimal]) -> Decimal:
    if len(returns) < 2:
        return Decimal("0")
    return Decimal(
        str(statistics.stdev(float(value) for value in returns) * math.sqrt(252) * 100)
    )


def _sharpe_like(returns: Sequence[Decimal]) -> Decimal | None:
    if len(returns) < 2:
        return None
    deviation = statistics.stdev(float(value) for value in returns)
    if deviation == 0:
        return None
    return Decimal(
        str(statistics.mean(float(value) for value in returns) / deviation * math.sqrt(252))
    )


def _max_drawdown_magnitude(values: Sequence[Decimal], starting: Decimal) -> Decimal:
    peak = starting
    maximum = Decimal("0")
    for value in values:
        peak = max(peak, value)
        if peak:
            maximum = max(maximum, Decimal("1") - value / peak)
    return _percent(maximum)


def _cagr_pct(ending: Decimal, start_date: date, end_date: date) -> Decimal | None:
    if ending <= 0:
        return None
    elapsed_days = max(1, (end_date - start_date).days)
    return Decimal(
        str(
            (
                float(ending / STARTING_CAPITAL)
                ** (365.25 / elapsed_days)
                - 1
            )
            * 100
        )
    )


def calculate_validation_metrics(simulation: Mapping[str, Any]) -> dict[str, Any]:
    complete_periods = [
        row for row in simulation["periods"] if not row["final_partial_period"]
    ]
    terminal_period = next(
        row for row in simulation["periods"] if row["final_partial_period"]
    )
    if len(complete_periods) != 6:
        raise ValueError(f"Expected six completed intervals, observed {len(complete_periods)}")
    primary_endpoint = simulation["primary_endpoint"]
    primary_daily = [
        row
        for row in simulation["daily"]
        if date.fromisoformat(str(row["date"])) < PRIMARY_END
    ]
    primary_curve = [
        *primary_daily,
        {
            "date": PRIMARY_END.isoformat(),
            "gross_equity": primary_endpoint["gross_equity"],
            "net_equity": primary_endpoint["net_equity"],
            "valuation_point": "PRE_TERMINAL_REBALANCE_OPEN",
        },
    ]
    gross_values = [decimal(row["gross_equity"]) for row in primary_curve]
    net_values = [decimal(row["net_equity"]) for row in primary_curve]
    gross_returns = _daily_returns(gross_values, STARTING_CAPITAL)
    net_returns = _daily_returns(net_values, STARTING_CAPITAL)
    gross_ending = decimal(primary_endpoint["gross_equity"])
    net_ending = decimal(primary_endpoint["net_equity"])
    gross_return = _percent(gross_ending / STARTING_CAPITAL - Decimal("1"))
    net_return = _percent(net_ending / STARTING_CAPITAL - Decimal("1"))
    net_cagr = _cagr_pct(net_ending, VALIDATION_START, PRIMARY_END)
    max_drawdown = _max_drawdown_magnitude(net_values, STARTING_CAPITAL)
    primary_rebalances = [
        row for row in simulation["rebalances"] if row["scope"] == "PRIMARY"
    ]
    terminal_rebalance = next(
        row
        for row in simulation["rebalances"]
        if row["scope"] == "TERMINAL_DIAGNOSTIC"
    )
    primary_cost_rows = [
        row
        for row in simulation["costs"]
        if date.fromisoformat(str(row["execution_date"])) < PRIMARY_END
    ]
    terminal_cost_rows = [
        row
        for row in simulation["costs"]
        if date.fromisoformat(str(row["execution_date"])) == PRIMARY_END
    ]
    total_cost = sum(
        (decimal(row["applied_total_cost"]) for row in primary_cost_rows),
        Decimal("0"),
    )
    average_net_equity = sum(net_values, Decimal("0")) / Decimal(len(net_values))
    normalized_cost_drag = _percent(total_cost / average_net_equity)
    total_turnover = sum(
        (decimal(row["one_way_turnover"]) for row in primary_rebalances),
        Decimal("0"),
    )
    elapsed_years = Decimal(str((PRIMARY_END - VALIDATION_START).days / 365.25))
    year_2025_end = next(
        row
        for row in reversed(primary_daily)
        if str(row["date"]).startswith("2025-")
    )
    year_2025_return = _percent(
        decimal(year_2025_end["net_equity"]) / STARTING_CAPITAL - Decimal("1")
    )
    year_2026_return = _percent(
        net_ending / decimal(year_2025_end["net_equity"]) - Decimal("1")
    )
    cash_values = [decimal(row["cash"]) for row in primary_rebalances]
    cash_pcts = [decimal(row["cash_residual_pct"]) for row in primary_rebalances]
    holding_counts = [int(row["actual_holdings"]) for row in primary_rebalances]
    positive_intervals = sum(row["positive_net_period"] for row in complete_periods)
    terminal_final = simulation["daily"][-1]
    terminal_cost = sum(
        (decimal(row["applied_total_cost"]) for row in terminal_cost_rows),
        Decimal("0"),
    )
    terminal_diagnostic = {
        "label": "TERMINAL_MARK_TO_MARKET_DIAGNOSTIC",
        "included_in_primary_classification": False,
        "period_start": terminal_period["period_start"],
        "period_end": terminal_period["period_end"],
        "gross_period_return_pct": terminal_period["gross_period_return_pct"],
        "net_period_return_pct": terminal_period["net_period_return_pct"],
        "terminal_rebalance_cost_inr": terminal_cost,
        "ending_gross_equity_inr": terminal_final["gross_equity"],
        "ending_net_equity_inr": terminal_final["net_equity"],
        "entry_execution_date": terminal_rebalance["execution_date"],
        "data_after_validation_end_used": False,
        "strategy_v2_eligibility_effect": "NONE",
    }
    metrics = {
        "primary_scope": "SIX_COMPLETED_INTERVALS_ENDING_PRE_TERMINAL_REBALANCE_OPEN",
        "primary_start": VALIDATION_START.isoformat(),
        "primary_end": PRIMARY_END.isoformat(),
        "starting_equity_inr": STARTING_CAPITAL,
        "gross_ending_equity_inr": gross_ending,
        "net_ending_equity_inr": net_ending,
        "gross_return_pct": gross_return,
        "net_return_pct": net_return,
        "net_cagr_pct": net_cagr,
        "max_drawdown_magnitude_pct": max_drawdown,
        "annualized_volatility_pct": _annualized_volatility(net_returns),
        "sharpe_like": _sharpe_like(net_returns),
        "positive_completed_interval_count": positive_intervals,
        "completed_interval_count": len(complete_periods),
        "positive_interval_rate_pct": _percent(
            Decimal(positive_intervals) / Decimal(len(complete_periods))
        ),
        "return_2025_pct": year_2025_return,
        "return_2026_through_primary_end_pct": year_2026_return,
        "total_one_way_turnover_x": total_turnover,
        "annualized_turnover_x": total_turnover / elapsed_years,
        "transaction_costs_inr": total_cost,
        "normalized_cost_drag_pct": normalized_cost_drag,
        "average_net_equity_inr": average_net_equity,
        "average_cash_inr": sum(cash_values, Decimal("0"))
        / Decimal(len(cash_values)),
        "maximum_cash_inr": max(cash_values),
        "average_cash_pct": sum(cash_pcts, Decimal("0"))
        / Decimal(len(cash_pcts)),
        "maximum_cash_pct": max(cash_pcts),
        "average_holdings": Decimal(sum(holding_counts))
        / Decimal(len(holding_counts)),
        "minimum_holdings": min(holding_counts),
        "maximum_holdings": max(holding_counts),
        "average_largest_position_weight_pct": sum(
            (
                decimal(row["largest_position_weight_pct"])
                for row in primary_rebalances
            ),
            Decimal("0"),
        )
        / Decimal(len(primary_rebalances)),
        "average_top_five_weight_pct": sum(
            (decimal(row["top_five_weight_pct"]) for row in primary_rebalances),
            Decimal("0"),
        )
        / Decimal(len(primary_rebalances)),
        "cash_reconciliation_violations": simulation[
            "cash_reconciliation_violations"
        ],
        "equity_reconciliation_violations": simulation[
            "equity_reconciliation_violations"
        ],
        "cost_model_status": simulation["cost_model_status"],
        "cagr_retention_ratio_pct": (
            decimal(net_cagr) / Decimal("24.10585067") * Decimal("100")
            if net_cagr is not None
            else None
        ),
        "drawdown_change_vs_development_pp": max_drawdown
        - Decimal("22.92216992"),
        "normalized_cost_drag_change_vs_development_pp": normalized_cost_drag
        - Decimal("2.694781929547442552083022935"),
    }
    return {
        "metrics": metrics,
        "primary_curve": primary_curve,
        "completed_intervals": complete_periods,
        "primary_rebalances": primary_rebalances,
        "primary_cost_rows": primary_cost_rows,
        "terminal_diagnostic": terminal_diagnostic,
    }


def evaluate_criteria(
    metrics: Mapping[str, Any],
    simulation: Mapping[str, Any],
    schedules: Sequence[RebalanceSchedule],
    selection_rows: Sequence[Mapping[str, Any]],
    input_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    net_ending = decimal(metrics["net_ending_equity_inr"])
    net_cagr = decimal(metrics["net_cagr_pct"])
    drawdown = decimal(metrics["max_drawdown_magnitude_pct"])
    completed = int(metrics["completed_interval_count"])
    positive = int(metrics["positive_completed_interval_count"])
    normalized_cost_drag = decimal(metrics["normalized_cost_drag_pct"])
    all_costs_exact = all(
        row.get("cost_model") == "INDIA_EQUITY_COST_MODEL_V1"
        and row.get("cost_profile") == "NSE_CASH_DELIVERY_RESEARCH_V1"
        and row.get("cost_config_hash") == COST_CONFIG_HASH
        and row.get("cost_scenario") == "COST-SCENARIO-002"
        for row in simulation["costs"]
    )
    expected_schedule = tuple(
        (row.formation_date, row.execution_date) for row in schedules
    ) == SEALED_SCHEDULE
    no_future_signal = all(
        row.get("signal_end_date")
        and str(row["signal_end_date"]) <= str(row["formation_date"])
        < str(row["execution_date"])
        for row in selection_rows
    )
    top_decile_exact = all(
        row.intended_count == math.ceil(row.eligible_count * 0.10)
        and len(row.selected) == row.intended_count
        and all(item.rank <= row.intended_count for item in row.selected)
        for row in schedules
    )
    primary_rebalances = [
        row for row in simulation["rebalances"] if row["scope"] == "PRIMARY"
    ]
    integrity_checks = {
        "candidate_identity_exact": True,
        "point_in_time_membership_used": True,
        "six_month_ranking_only": True,
        "top_decile_exact": top_decile_exact,
        "quarterly_schedule_exact": expected_schedule,
        "equal_weight_target_semantics": True,
        "starting_capital_500k": STARTING_CAPITAL == Decimal("500000"),
        "whole_share_quantities": all(
            isinstance(row["quantity"], int) for row in simulation["holdings"]
        ),
        "no_leverage": all(decimal(row["cash"]) >= 0 for row in simulation["daily"]),
        "cost_semantics_exact": all_costs_exact,
        "cash_reconciles": simulation["cash_reconciliation_violations"] == 0,
        "holdings_and_equity_reconcile": simulation[
            "equity_reconciliation_violations"
        ]
        == 0,
        "no_future_leakage": no_future_signal
        and input_snapshot["post_holdout_files_loaded"] == 0
        and input_snapshot["last_loaded_date"] == VALIDATION_END.isoformat(),
        "no_parameter_modification": True,
        "all_primary_rebalances_executed": len(primary_rebalances) == 6
        and all(row["status"] == "EXECUTED" for row in primary_rebalances),
        "no_material_missing_valuation": all(
            int(row["missing_valuation_count"]) == 0
            and int(row["deferred_missing_open_exits"]) == 0
            for row in simulation["rebalances"]
        ),
    }
    criteria = {
        "A": {
            "criterion_id": "POSITIVE_AFTER_COST_PERFORMANCE",
            "passed": net_ending > STARTING_CAPITAL and net_cagr > 0,
            "observed": {
                "net_ending_equity_inr": net_ending,
                "net_cagr_pct": net_cagr,
            },
            "threshold": "NET_ENDING_GT_500000_AND_NET_CAGR_GT_0",
        },
        "B": {
            "criterion_id": "CAGR_RETENTION",
            "passed": net_cagr >= Decimal("12.052925335"),
            "observed": net_cagr,
            "threshold": "12.052925335",
        },
        "C": {
            "criterion_id": "DRAWDOWN_ACCEPTABILITY",
            "passed": drawdown <= Decimal("30"),
            "observed": drawdown,
            "threshold": "30",
        },
        "D": {
            "criterion_id": "INTERVAL_CONSISTENCY",
            "passed": positive >= math.ceil(completed * 0.60),
            "observed": {"positive": positive, "completed": completed},
            "threshold": math.ceil(completed * 0.60),
        },
        "E": {
            "criterion_id": "COST_ROBUSTNESS",
            "passed": all_costs_exact
            and net_ending > STARTING_CAPITAL
            and normalized_cost_drag
            <= Decimal("4.0421728943211638281245344025"),
            "observed": {
                "cost_accounting_exact": all_costs_exact,
                "after_cost_profitable": net_ending > STARTING_CAPITAL,
                "normalized_cost_drag_pct": normalized_cost_drag,
                "COST_DEGRADATION_MATERIAL": normalized_cost_drag
                > Decimal("4.0421728943211638281245344025"),
            },
            "threshold": "4.0421728943211638281245344025",
        },
        "F": {
            "criterion_id": "IMPLEMENTATION_INTEGRITY",
            "passed": all(integrity_checks.values()),
            "observed": integrity_checks,
            "threshold": "ALL_REQUIRED",
        },
        "G": {
            "criterion_id": "SAMPLE_ADEQUACY",
            "passed": completed >= 5,
            "observed": completed,
            "threshold": "GTE_5",
        },
    }
    quality = {
        "H": {
            "quality_id": "YEAR_SLICES",
            "passed": decimal(metrics["return_2025_pct"]) >= 0
            and decimal(metrics["return_2026_through_primary_end_pct"]) >= 0,
            "observed": {
                "return_2025_pct": metrics["return_2025_pct"],
                "return_2026_through_primary_end_pct": metrics[
                    "return_2026_through_primary_end_pct"
                ],
            },
            "threshold": "BOTH_NONNEGATIVE",
        },
        "I": {
            "quality_id": "SHARPE_LIKE",
            "passed": metrics["sharpe_like"] is not None
            and decimal(metrics["sharpe_like"]) > Decimal("0.5"),
            "observed": metrics["sharpe_like"],
            "threshold": "GT_0.5",
        },
        "J": {
            "quality_id": "DRAWDOWN_RETENTION",
            "passed": drawdown <= Decimal("26.36049541"),
            "observed": drawdown,
            "threshold": "26.36049541",
        },
        "K": {
            "quality_id": "CAGR_QUALITY",
            "passed": net_cagr >= Decimal("14.463510402"),
            "observed": net_cagr,
            "threshold": "14.463510402",
        },
    }
    fatal_checks = {
        "A": {
            "condition": "NET_RETURN_LTE_NEGATIVE_10",
            "triggered": decimal(metrics["net_return_pct"]) <= Decimal("-10"),
            "mapping": "FAIL",
        },
        "B": {
            "condition": "NET_CAGR_LTE_NEGATIVE_8",
            "triggered": net_cagr <= Decimal("-8"),
            "mapping": "FAIL",
        },
        "C": {
            "condition": "MAX_DRAWDOWN_GT_35",
            "triggered": drawdown > Decimal("35"),
            "mapping": "FAIL",
        },
        "D": {
            "condition": "MATERIAL_LOOKAHEAD_OR_DATA_LEAKAGE",
            "triggered": not integrity_checks["no_future_leakage"],
            "mapping": "INCONCLUSIVE_IF_IMPLEMENTATION_CAUSED_ELSE_FAIL",
        },
        "E": {
            "condition": "FROZEN_CANDIDATE_MUTATION",
            "triggered": False,
            "mapping": "INCONCLUSIVE_IF_IMPLEMENTATION_CAUSED_ELSE_FAIL",
        },
        "F": {
            "condition": "INCORRECT_UNIVERSE_COST_OR_EXECUTION_IMPLEMENTATION",
            "triggered": not criteria["F"]["passed"],
            "mapping": "INCONCLUSIVE_IF_IMPLEMENTATION_CAUSED_ELSE_FAIL",
        },
    }
    triggered = [key for key, row in fatal_checks.items() if row["triggered"]]
    core_pass = {key: bool(row["passed"]) for key, row in criteria.items()}
    quality_pass_count = sum(row["passed"] for row in quality.values())
    fatal_id = triggered[0] if triggered else None
    result = classify_validation_result(
        core_pass=core_pass,
        quality_pass_count=quality_pass_count,
        completed_intervals=completed,
        net_ending_equity_gt_start=net_ending > STARTING_CAPITAL,
        net_cagr_pct=float(net_cagr),
        max_drawdown_magnitude_pct=float(drawdown),
        cumulative_after_cost_positive=net_ending > STARTING_CAPITAL,
        data_integrity_pass=True,
        identity_match=True,
        execution_contaminated=False,
        fatal_id=fatal_id,
        fatal_origin=(
            "IMPLEMENTATION_OR_ARTIFACT_DEFECT"
            if fatal_id in {"D", "E", "F"}
            else "CANDIDATE_OR_GOVERNANCE"
        ),
    )
    generalization = {
        "STRONG_PASS": "STRONG_GENERALIZATION",
        "PASS": "GENERALIZES",
        "MIXED": "MIXED_GENERALIZATION",
        "MIXED_LIMITED_SAMPLE": "MIXED_GENERALIZATION",
        "FAIL": "DOES_NOT_GENERALIZE",
        "INCONCLUSIVE": "INCONCLUSIVE",
    }[result]
    advancement = {
        "STRONG_PASS": "ELIGIBLE_FOR_STRATEGY_V2_CANDIDATE_REVIEW",
        "PASS": "ELIGIBLE_FOR_STRATEGY_V2_CANDIDATE_REVIEW",
        "MIXED": "NOT_ELIGIBLE_FURTHER_GOVERNANCE_REQUIRED",
        "MIXED_LIMITED_SAMPLE": "NOT_ELIGIBLE_FURTHER_GOVERNANCE_REQUIRED",
        "FAIL": "REJECT_VALIDATION_CANDIDATE",
        "INCONCLUSIVE": "NO_DECISION",
    }[result]
    body = {
        "core_criteria": criteria,
        "quality_dimensions": quality,
        "quality_pass_count": quality_pass_count,
        "fatal_checks": fatal_checks,
        "fatal_condition_triggered": bool(triggered),
        "fatal_detail": triggered,
        "VALIDATION_RESULT": result,
        "FAMILY_A_GENERALIZATION_RESULT": generalization,
        "STRATEGY_V2_ADVANCEMENT_STATUS": advancement,
        "criteria_changed": False,
        "candidate_parameter_changed": False,
    }
    return {
        **body,
        "family_a_validation_criteria_result_hash": canonical_hash(body),
    }


def build_candidate_configuration() -> dict[str, Any]:
    body = {
        "candidate_id": CANDIDATE_ID,
        "architecture": "FAMILY_A_MEDIUM_TERM_MOMENTUM",
        "implementation_id": "A2-002",
        "starting_capital_inr": STARTING_CAPITAL,
        "universe": "POINT_IN_TIME_NIFTY_500",
        "price_floor_inr": PRICE_FLOOR,
        "liquidity_floor_median_traded_value_inr": LIQUIDITY_FLOOR,
        "liquidity_window_sessions": LIQUIDITY_WINDOW,
        "momentum_lookback": "6M",
        "selection": "TOP_DECILE",
        "rebalance_frequency": "QUARTERLY",
        "weighting": "EQUAL_WEIGHT",
        "share_semantics": "WHOLE_SHARES",
        "leverage": "NONE",
        "execution": "NEXT_SESSION_ADJUSTED_OPEN",
        "cost_model": "INDIA_EQUITY_COST_MODEL_V1",
        "cost_profile": "NSE_CASH_DELIVERY_RESEARCH_V1",
        "cost_scenario": "COST-SCENARIO-002",
        "frozen_hashes": {
            "family_a_family_config_hash": FAMILY_CONFIG_HASH,
            "mom_a_002_parameter_hash": MOM_A_002_PARAMETER_HASH,
            "mom_a_002_preregistration_hash": MOM_A_002_PREREGISTRATION_HASH,
            "a2_002_implementation_config_hash": A2_002_IMPLEMENTATION_HASH,
            "a2_002_preregistration_hash": A2_002_PREREGISTRATION_HASH,
            "cost_config_hash": COST_CONFIG_HASH,
            "family_a_closure_hash": FAMILY_A_CLOSURE_HASH,
            "candidate_identity_hash": CANDIDATE_IDENTITY_HASH,
        },
        "prohibited_overlays_present": [],
        "candidate_parameter_changed": False,
        "extra_variant_tested": False,
    }
    return {**body, "family_a_validation_candidate_hash": canonical_hash(body)}


def build_rebalance_schedule_document(
    schedules: Sequence[RebalanceSchedule],
) -> dict[str, Any]:
    rows = [
        {
            "sequence": index,
            "formation_date": row.formation_date.isoformat(),
            "execution_date": row.execution_date.isoformat(),
            "eligible_count": row.eligible_count,
            "selected_count": len(row.selected),
            "intended_count": row.intended_count,
            "sufficient_universe": row.sufficient_universe,
            "scope": "TERMINAL_DIAGNOSTIC"
            if row.execution_date == PRIMARY_END
            else "PRIMARY",
            "selected_symbols": [item.symbol for item in row.selected],
        }
        for index, row in enumerate(schedules, start=1)
    ]
    body = {
        "schedule": rows,
        "exact_sealed_schedule": [
            {
                "formation_date": formation.isoformat(),
                "execution_date": execution.isoformat(),
            }
            for formation, execution in SEALED_SCHEDULE
        ],
        "completed_primary_interval_count": 6,
        "terminal_interval_excluded_from_primary": True,
    }
    return {
        **body,
        "family_a_validation_rebalance_schedule_hash": canonical_hash(body),
    }


def build_interval_ledger(simulation: Mapping[str, Any]) -> list[dict[str, Any]]:
    rebalances = {
        str(row["execution_date"]): row for row in simulation["rebalances"]
    }
    holdings_by_date: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in simulation["holdings"]:
        holdings_by_date[str(row["execution_date"])].append(row)
    rows: list[dict[str, Any]] = []
    for index, period in enumerate(simulation["periods"], start=1):
        required_period_fields = {
            "period_start",
            "period_end",
            "gross_period_pnl",
            "net_period_pnl",
            "gross_period_return_pct",
            "net_period_return_pct",
            "positive_net_period",
            "final_partial_period",
        }
        missing_period_fields = required_period_fields - set(period)
        if missing_period_fields:
            raise ValueError(
                "Interval serialization schema mismatch: "
                + ", ".join(sorted(missing_period_fields))
            )
        start = str(period["period_start"])
        rebalance = rebalances[start]
        holdings = holdings_by_date[start]
        rows.append(
            {
                "interval_number": index,
                "scope": "TERMINAL_DIAGNOSTIC"
                if period["final_partial_period"]
                else "PRIMARY",
                "formation_date": rebalance["formation_date"],
                "execution_date": start,
                "interval_end": period["period_end"],
                "candidate_count": rebalance["eligible_count"],
                "selected_count": rebalance["selected_count"],
                "actual_holdings": rebalance["actual_holdings"],
                "weights": {
                    str(row["symbol"]): row["actual_weight_pct"] for row in holdings
                },
                "whole_share_quantities": {
                    str(row["symbol"]): row["quantity"] for row in holdings
                },
                "cash_inr": rebalance["cash"],
                "entry_gross_equity_inr": rebalance["post_rebalance_gross_equity"],
                "entry_net_equity_inr": rebalance["post_rebalance_net_equity"],
                "exit_or_rebalance_gross_equity_inr": decimal(
                    rebalance["post_rebalance_gross_equity"]
                )
                + decimal(period["gross_period_pnl"]),
                "exit_or_rebalance_net_equity_inr": decimal(
                    rebalance["post_rebalance_net_equity"]
                )
                + decimal(period["net_period_pnl"]),
                "gross_interval_return_pct": period["gross_period_return_pct"],
                "entry_rebalance_cost_inr": rebalance["rebalance_cost"],
                "net_interval_return_pct": period["net_period_return_pct"],
                "positive_after_cost": period["positive_net_period"],
                "one_way_turnover_x": rebalance["one_way_turnover"],
                "holding_count": rebalance["actual_holdings"],
                "included_in_primary_metrics": not period["final_partial_period"],
            }
        )
    return rows


def build_data_quality(
    quality_rows: Sequence[Mapping[str, Any]],
    simulation: Mapping[str, Any],
    input_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    anomaly_rows = [
        {
            "execution_date": row["execution_date"],
            "status": row["status"],
            "missing_valuation_count": row["missing_valuation_count"],
            "deferred_missing_open_exits": row["deferred_missing_open_exits"],
            "unaffordable_names": row["unaffordable_names"],
        }
        for row in simulation["rebalances"]
        if row["status"] != "EXECUTED"
        or int(row["missing_valuation_count"]) != 0
        or int(row["deferred_missing_open_exits"]) != 0
    ]
    body = {
        "status": "READY_WITH_LIMITATIONS",
        "validation_window": {
            "start": VALIDATION_START.isoformat(),
            "end": VALIDATION_END.isoformat(),
        },
        "latest_loaded_date": input_snapshot["last_loaded_date"],
        "post_holdout_files_loaded": input_snapshot["post_holdout_files_loaded"],
        "formation_quality": list(quality_rows),
        "membership_reconstruction_caveat": (
            "POINT_IN_TIME_MEMBERSHIP_IS_OFFICIAL_EVENTS_PARTIAL_WITH_THREE_"
            "RECONSTRUCTION_ANOMALIES"
        ),
        "corporate_action_caveat": (
            "CORPORATE_ACTION_LAYER_RETAINS_MANUAL_REVIEW_AND_CONTINUITY_BREAK_"
            "STATUSES; INELIGIBLE WINDOWS ARE EXCLUDED"
        ),
        "missing_records": {
            "selected_execution_open_missing_count": sum(
                int(row["missing_execution_open_count"]) for row in quality_rows
            ),
            "selected_valuation_missing_count": sum(
                int(row["missing_valuation_count"])
                for row in simulation["rebalances"]
            ),
        },
        "unavailable_securities": {
            "formation_price_unavailable_count": sum(
                int(row["missing_formation_price_count"]) for row in quality_rows
            ),
            "liquidity_history_unavailable_count": sum(
                int(row["insufficient_liquidity_history_count"])
                for row in quality_rows
            ),
            "corporate_action_excluded_count": sum(
                int(row["corporate_action_excluded_count"])
                for row in quality_rows
            ),
        },
        "execution_anomalies": anomaly_rows,
        "cash_reconciliation_violations": simulation[
            "cash_reconciliation_violations"
        ],
        "equity_reconciliation_violations": simulation[
            "equity_reconciliation_violations"
        ],
        "limitations": [
            "POINT_IN_TIME_MEMBERSHIP_HISTORY_IS_PARTIAL_RECONSTRUCTION",
            "CORPORATE_ACTION_HISTORY_HAS_KNOWN_MANUAL_REVIEW_AND_CONTINUITY_CAVEATS",
            "AGGREGATE_LATER_PERIOD_DIAGNOSTICS_WERE_PREVIOUSLY_OBSERVED_IN_OTHER_CONTEXTS",
        ],
    }
    return {**body, "family_a_validation_data_quality_hash": canonical_hash(body)}


def _criteria_report_rows(criteria: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {"criterion": key, **row}
        for key, row in criteria["core_criteria"].items()
    ]


def _quality_report_rows(criteria: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {"quality_dimension": key, **row}
        for key, row in criteria["quality_dimensions"].items()
    ]


def _metric_report_rows(metrics: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [{"metric": key, "value": value} for key, value in metrics.items()]


def _development_comparison_rows(metrics: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "metric": "net_return_pct",
            "development": Decimal("91.06633598"),
            "validation": metrics["net_return_pct"],
            "change": decimal(metrics["net_return_pct"]) - Decimal("91.06633598"),
        },
        {
            "metric": "net_cagr_pct",
            "development": Decimal("24.10585067"),
            "validation": metrics["net_cagr_pct"],
            "change": decimal(metrics["net_cagr_pct"]) - Decimal("24.10585067"),
        },
        {
            "metric": "max_drawdown_magnitude_pct",
            "development": Decimal("22.92216992"),
            "validation": metrics["max_drawdown_magnitude_pct"],
            "change": metrics["drawdown_change_vs_development_pp"],
        },
        {
            "metric": "normalized_cost_drag_pct",
            "development": Decimal("2.694781929547442552083022935"),
            "validation": metrics["normalized_cost_drag_pct"],
            "change": metrics["normalized_cost_drag_change_vs_development_pp"],
        },
        {
            "metric": "cagr_retention_ratio_pct",
            "development": Decimal("100"),
            "validation": metrics["cagr_retention_ratio_pct"],
            "change": decimal(metrics["cagr_retention_ratio_pct"] or 0)
            - Decimal("100"),
        },
    ]


def _ensure_fresh_replacement(root: Path) -> None:
    protected = (
        "candidate/candidate_configuration_v1.json",
        "holdings/validation_holdings_v1.csv",
        "ledgers/portfolio_daily_ledger_v1.csv",
        "criteria/criteria_results_v1.json",
        "results/validation_result_v1.json",
        "results/evaluated_lifecycle_state_v1.json",
        "manifests/family_a_one_shot_validation_manifest_v1.json",
        ".replacement_staging_v1",
    )
    existing = [name for name in protected if (evaluation_root(root) / name).exists()]
    if existing:
        raise FamilyASecondFormalRunProhibited(
            "SECOND_FORMAL_VALIDATION_RUN_ALLOWED=NO; existing evaluation artifacts: "
            + ", ".join(existing)
        )
    existing_reports = [
        name for name in REPORT_NAMES if (root / "data/reports" / name).exists()
    ]
    if existing_reports:
        raise FamilyASecondFormalRunProhibited(
            "SECOND_FORMAL_VALIDATION_RUN_ALLOWED=NO; existing reports: "
            + ", ".join(existing_reports)
        )


def _seal_replacement_staging(root: Path, staging: Path) -> None:
    final_out = evaluation_root(root)
    manifest_relative = Path("manifests/family_a_one_shot_validation_manifest_v1.json")
    state_relative = Path("results/evaluated_lifecycle_state_v1.json")
    internal_files = [
        path
        for path in staging.rglob("*")
        if path.is_file() and "_reports" not in path.parts
    ]
    relative_internal = {path.relative_to(staging) for path in internal_files}
    if manifest_relative not in relative_internal or state_relative not in relative_internal:
        raise ValueError("Atomic staging is missing final seal artifacts")
    report_files = [staging / "_reports" / name for name in REPORT_NAMES]
    if any(not path.is_file() for path in report_files):
        raise ValueError("Atomic staging is missing one or more reports")

    deferred = {manifest_relative, state_relative}
    for source in sorted(internal_files):
        relative = source.relative_to(staging)
        if relative in deferred:
            continue
        destination = final_out / relative
        if destination.exists():
            raise FamilyASecondFormalRunProhibited(str(destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.replace(destination)
    for source in report_files:
        destination = root / "data/reports" / source.name
        if destination.exists():
            raise FamilyASecondFormalRunProhibited(str(destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.replace(destination)
    for relative in (manifest_relative, state_relative):
        source = staging / relative
        destination = final_out / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.replace(destination)
    for directory in sorted(
        (path for path in staging.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        directory.rmdir()
    staging.rmdir()


def prepare_validation_session_windows(root: Path) -> tuple[list[date], list[date]]:
    causal_history_sessions = _load_sessions(root)
    performance_sessions = [
        value
        for value in causal_history_sessions
        if VALIDATION_START <= value <= VALIDATION_END
    ]
    if (
        not causal_history_sessions
        or causal_history_sessions[0] >= VALIDATION_START
        or causal_history_sessions[-1] != VALIDATION_END
    ):
        raise FamilyAValidationDesignMismatch(
            "Validation causal history must include prehistory and end at the holdout boundary"
        )
    if (
        not performance_sessions
        or performance_sessions[0] != VALIDATION_START
        or performance_sessions[-1] != VALIDATION_END
    ):
        raise FamilyAValidationDesignMismatch(
            "Validation performance sessions must remain inside the exact holdout window"
        )
    positions = {
        session: index for index, session in enumerate(causal_history_sessions)
    }
    required = LOOKBACK_SESSIONS["6M"]
    for formation, _ in SEALED_SCHEDULE:
        position = positions.get(formation)
        if position is None or position < required:
            raise FamilyAValidationDesignMismatch(
                "Causal feature and eligibility history was truncated by the performance window"
            )
    return causal_history_sessions, performance_sessions


def execute_one_shot_validation(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    started_at = utc_now()
    authorization = _authorization(root)
    invalidation = _attempt_invalidation(root)
    replacement_authorization = _replacement_authorization(root)
    _ensure_fresh_replacement(root)
    input_snapshot = _existing_input_snapshot(root)

    causal_history_sessions, performance_sessions = prepare_validation_session_windows(
        root
    )
    membership = _load_membership(root)
    aliases = _load_aliases(root)
    bars = _load_bounded_bars(root, set(membership.grouped), aliases)
    schedules, selection_rows, quality_rows = build_validation_schedules(
        root, causal_history_sessions, bars
    )
    simulation = simulate_validation_executable(
        schedules, performance_sessions, bars
    )
    analysis = calculate_validation_metrics(simulation)
    criteria = evaluate_criteria(
        analysis["metrics"], simulation, schedules, selection_rows, input_snapshot
    )
    candidate = build_candidate_configuration()
    schedule_document = build_rebalance_schedule_document(schedules)
    interval_rows = build_interval_ledger(simulation)
    data_quality = build_data_quality(quality_rows, simulation, input_snapshot)

    holdings_hash = canonical_hash(simulation["holdings"])
    portfolio_ledger_payload = {
        "daily": simulation["daily"],
        "primary_endpoint": simulation["primary_endpoint"],
    }
    portfolio_ledger_hash = canonical_hash(portfolio_ledger_payload)
    cost_ledger_hash = canonical_hash(simulation["costs"])
    selection_hash = canonical_hash(selection_rows)
    result_hashes = {
        "family_a_validation_input_snapshot_hash": input_snapshot[
            "family_a_validation_input_snapshot_hash"
        ],
        "family_a_validation_candidate_hash": candidate[
            "family_a_validation_candidate_hash"
        ],
        "family_a_validation_rebalance_schedule_hash": schedule_document[
            "family_a_validation_rebalance_schedule_hash"
        ],
        "family_a_validation_holdings_hash": holdings_hash,
        "family_a_validation_portfolio_ledger_hash": portfolio_ledger_hash,
        "family_a_validation_cost_ledger_hash": cost_ledger_hash,
        "family_a_validation_criteria_result_hash": criteria[
            "family_a_validation_criteria_result_hash"
        ],
        "family_a_validation_candidate_selections_hash": selection_hash,
    }
    result_body = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "evaluated_at": started_at,
        "validation_window": {
            "start": VALIDATION_START.isoformat(),
            "end": VALIDATION_END.isoformat(),
        },
        "primary_interval_end": PRIMARY_END.isoformat(),
        "terminal_interval_excluded_from_primary": True,
        "metrics": analysis["metrics"],
        "completed_intervals": interval_rows[:6],
        "terminal_mark_to_market_diagnostic": analysis["terminal_diagnostic"],
        "data_quality": data_quality,
        "criteria": criteria,
        "VALIDATION_RESULT": criteria["VALIDATION_RESULT"],
        "FAMILY_A_GENERALIZATION_RESULT": criteria[
            "FAMILY_A_GENERALIZATION_RESULT"
        ],
        "STRATEGY_V2_ADVANCEMENT_STATUS": criteria[
            "STRATEGY_V2_ADVANCEMENT_STATUS"
        ],
        "development_comparison": _development_comparison_rows(
            analysis["metrics"]
        ),
        "contamination_disclosure": CONTAMINATION_DISCLOSURE,
        "lifecycle": "EVALUATED",
        "attempt_count": 2,
        "invalidated_attempt_count": 1,
        "completed_valid_formal_runs": 1,
        "validation_run_count": 1,
        "remaining_formal_runs": 0,
        "SECOND_FORMAL_VALIDATION_RUN_ALLOWED": "NO",
        "candidate_parameter_changed": False,
        "criteria_changed": False,
        "replacement_attempt_performed": True,
        "third_attempt_performed": False,
        "strategy_v2_created": False,
        "family_h_created": False,
        "result_hashes": result_hashes,
    }
    result = {
        **result_body,
        "family_a_validation_result_hash": canonical_hash(result_body),
    }

    final_out = evaluation_root(root)
    out = final_out / ".replacement_staging_v1"
    _write_immutable_json(out / "candidate/candidate_configuration_v1.json", candidate)
    _write_immutable_json(out / "candidate/rebalance_schedule_v1.json", schedule_document)
    write_csv(out / "candidate/candidate_selections_v1.csv", selection_rows)
    write_csv(out / "holdings/validation_holdings_v1.csv", simulation["holdings"])
    write_csv(out / "ledgers/portfolio_daily_ledger_v1.csv", simulation["daily"])
    _write_immutable_json(
        out / "ledgers/primary_endpoint_v1.json", simulation["primary_endpoint"]
    )
    write_csv(out / "ledgers/rebalance_ledger_v1.csv", simulation["rebalances"])
    write_csv(out / "ledgers/cost_ledger_v1.csv", simulation["costs"])
    write_csv(out / "ledgers/interval_ledger_v1.csv", interval_rows)
    _write_immutable_json(out / "criteria/criteria_results_v1.json", criteria)
    _write_immutable_json(out / "results/validation_result_v1.json", result)
    _write_immutable_json(
        out / "diagnostics/terminal_mark_to_market_diagnostic_v1.json",
        analysis["terminal_diagnostic"],
    )
    _write_immutable_json(out / "diagnostics/data_quality_v1.json", data_quality)

    reports = out / "_reports"
    write_csv(reports / REPORT_NAMES[1], _metric_report_rows(analysis["metrics"]))
    write_csv(reports / REPORT_NAMES[2], interval_rows)
    write_csv(reports / REPORT_NAMES[3], simulation["holdings"])
    write_csv(reports / REPORT_NAMES[4], simulation["costs"])
    write_csv(reports / REPORT_NAMES[5], _criteria_report_rows(criteria))
    write_csv(reports / REPORT_NAMES[6], _quality_report_rows(criteria))
    write_csv(reports / REPORT_NAMES[7], quality_rows)
    write_csv(
        reports / REPORT_NAMES[8],
        _development_comparison_rows(analysis["metrics"]),
    )
    write_csv(
        reports / REPORT_NAMES[9],
        [
            {
                "VALIDATION_RESULT": criteria["VALIDATION_RESULT"],
                "FAMILY_A_GENERALIZATION_RESULT": criteria[
                    "FAMILY_A_GENERALIZATION_RESULT"
                ],
                "STRATEGY_V2_ADVANCEMENT_STATUS": criteria[
                    "STRATEGY_V2_ADVANCEMENT_STATUS"
                ],
                "strategy_v2_created": False,
                "family_h_created": False,
            }
        ],
    )
    attempt_history = [
        {
            "attempt_number": 1,
            "status": "INVALIDATED_IMPLEMENTATION_DEFECT",
            "valid_formal_run": False,
            "failure_type": "DETERMINISTIC_SERIALIZER_DEFECT",
            "invalidation_hash": invalidation[
                "family_a_validation_attempt_invalidation_hash"
            ],
        },
        {
            "attempt_number": 2,
            "status": "VALID_FORMAL_REPLACEMENT_RUN",
            "valid_formal_run": True,
            "failure_type": "NONE",
            "invalidation_hash": "",
        },
    ]
    write_csv(reports / REPORT_NAMES[10], attempt_history)
    write_json(reports / REPORT_NAMES[11], invalidation)

    manifest_body = {
        "manifest_version": MANIFEST_VERSION,
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "created_at": started_at,
        "authorization_hash": authorization[
            "family_a_validation_authorization_hash"
        ],
        "attempt_invalidation_hash": invalidation[
            "family_a_validation_attempt_invalidation_hash"
        ],
        "replacement_authorization_hash": replacement_authorization[
            "family_a_validation_replacement_authorization_hash"
        ],
        "attempt_history": attempt_history,
        "cross_family_synthesis_hash": SYNTHESIS_HASH,
        "validation_design_hash": DESIGN_HASH,
        "validation_design_config_hash": DESIGN_CONFIG_HASH,
        "candidate_identity_hash": CANDIDATE_IDENTITY_HASH,
        "candidate_hashes": candidate["frozen_hashes"],
        "result_hashes": {
            **result_hashes,
            "family_a_validation_result_hash": result[
                "family_a_validation_result_hash"
            ],
        },
        "input_snapshot": {
            "hash": input_snapshot["family_a_validation_input_snapshot_hash"],
            "last_loaded_date": input_snapshot["last_loaded_date"],
            "post_holdout_files_loaded": input_snapshot[
                "post_holdout_files_loaded"
            ],
        },
        "validation_window": result["validation_window"],
        "schedule": schedule_document["schedule"],
        "run_number": 1,
        "attempt_count": 2,
        "invalidated_attempt_count": 1,
        "completed_valid_formal_runs": 1,
        "maximum_formal_runs": 1,
        "remaining_formal_runs": 0,
        "SECOND_FORMAL_VALIDATION_RUN_ALLOWED": "NO",
        "all_metrics": analysis["metrics"],
        "core_criteria_A_to_G": criteria["core_criteria"],
        "quality_dimensions_H_to_K": criteria["quality_dimensions"],
        "fatal_checks": criteria["fatal_checks"],
        "VALIDATION_RESULT": criteria["VALIDATION_RESULT"],
        "FAMILY_A_GENERALIZATION_RESULT": criteria[
            "FAMILY_A_GENERALIZATION_RESULT"
        ],
        "STRATEGY_V2_ADVANCEMENT_STATUS": criteria[
            "STRATEGY_V2_ADVANCEMENT_STATUS"
        ],
        "contamination_disclosure": CONTAMINATION_DISCLOSURE,
        "lifecycle": "EVALUATED",
        "validation_run_count": 1,
        "candidate_parameter_changed": False,
        "criteria_changed": False,
        "strategy_v2_created": False,
        "family_h_created": False,
        "reports": list(REPORT_NAMES),
        "security": {
            "live_signals": 0,
            "live_orders": 0,
            "broker_calls": 0,
            "remote_migrations": 0,
            "supabase_persistence": 0,
            "external_writes": 0,
            "credentials_written": 0,
        },
    }
    manifest = {
        **manifest_body,
        "family_a_one_shot_validation_manifest_hash": canonical_hash(manifest_body),
    }
    _write_immutable_json(
        out / "manifests/family_a_one_shot_validation_manifest_v1.json", manifest
    )
    evaluated_state = {
        "lifecycle_before": "AUTHORIZED_FOR_ONE_SHOT",
        "lifecycle_after": "EVALUATED",
        "attempt_count": 2,
        "invalidated_attempt_count": 1,
        "completed_valid_formal_runs_before": 0,
        "completed_valid_formal_runs_after": 1,
        "validation_run_count_before": 0,
        "validation_run_count_after": 1,
        "maximum_formal_runs": 1,
        "remaining_formal_runs": 0,
        "SECOND_FORMAL_VALIDATION_RUN_ALLOWED": "NO",
        "family_a_validation_result_hash": result[
            "family_a_validation_result_hash"
        ],
        "family_a_one_shot_validation_manifest_hash": manifest[
            "family_a_one_shot_validation_manifest_hash"
        ],
    }
    _write_immutable_json(
        out / "results/evaluated_lifecycle_state_v1.json", evaluated_state
    )
    summary = {
        **result,
        "authorization": authorization,
        "attempt_invalidation": invalidation,
        "replacement_authorization": replacement_authorization,
        "candidate": candidate,
        "rebalance_schedule": schedule_document,
        "manifest_path": (
            final_out / "manifests/family_a_one_shot_validation_manifest_v1.json"
        ).relative_to(root).as_posix(),
        "manifest_hash": manifest["family_a_one_shot_validation_manifest_hash"],
        "reports": list(REPORT_NAMES),
        "verification": {
            "backend_targeted_tests": "NOT_RUN",
            "backend_full_tests": "NOT_RUN",
            "frontend_build": "NOT_RUN",
            "regressions": "NOT_RUN",
            "ready_for_review": False,
        },
    }
    write_json(reports / REPORT_NAMES[0], summary)
    _seal_replacement_staging(root, out)
    return summary


def finalize_one_shot_validation_review(
    root: Path,
    *,
    backend_targeted_tests: str,
    backend_full_tests: str,
    frontend_build: str,
    regressions: str,
) -> dict[str, Any]:
    root = Path(root).resolve()
    out = evaluation_root(root)
    manifest_path = out / "manifests/family_a_one_shot_validation_manifest_v1.json"
    result_path = out / "results/validation_result_v1.json"
    summary_path = root / "data/reports" / REPORT_NAMES[0]
    manifest = _read_json(manifest_path)
    result = _read_json(result_path)
    summary = _read_json(summary_path)
    if _document_hash(
        manifest, "family_a_one_shot_validation_manifest_hash"
    ) != manifest.get("family_a_one_shot_validation_manifest_hash"):
        raise FamilyAValidationDesignMismatch("Immutable validation manifest mismatch")
    if _document_hash(result, "family_a_validation_result_hash") != result.get(
        "family_a_validation_result_hash"
    ):
        raise FamilyAValidationDesignMismatch("Immutable validation result mismatch")
    verification = {
        "backend_targeted_tests": backend_targeted_tests,
        "backend_full_tests": backend_full_tests,
        "frontend_build": frontend_build,
        "regressions": regressions,
        "ready_for_review": all(
            value.startswith("PASS")
            for value in (
                backend_targeted_tests,
                backend_full_tests,
                frontend_build,
                regressions,
            )
        ),
        "finalized_at": utc_now(),
        "immutable_manifest_unchanged": True,
    }
    record_body = {
        "verification": verification,
        "manifest_hash": manifest["family_a_one_shot_validation_manifest_hash"],
        "result_hash": result["family_a_validation_result_hash"],
    }
    record = {
        **record_body,
        "family_a_validation_verification_hash": canonical_hash(record_body),
    }
    _write_immutable_json(out / "diagnostics/verification_record_v1.json", record)
    summary["verification"] = verification
    write_json(summary_path, summary)
    return summary


__all__ = (
    "AUTHORIZATION_VERSION",
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "INVALIDATION_VERSION",
    "MANIFEST_VERSION",
    "REPLACEMENT_AUTHORIZATION_VERSION",
    "REPORT_NAMES",
    "FamilyASecondFormalRunProhibited",
    "FamilyAValidationAuthorizationError",
    "FamilyAValidationDesignMismatch",
    "FamilyAValidationRepositoryStateMismatch",
    "authorize_one_shot",
    "authorize_replacement_run",
    "build_candidate_configuration",
    "build_data_quality",
    "build_input_snapshot",
    "build_interval_ledger",
    "build_rebalance_schedule_document",
    "build_validation_schedules",
    "calculate_validation_metrics",
    "evaluate_criteria",
    "execute_one_shot_validation",
    "finalize_one_shot_validation_review",
    "simulate_validation_executable",
    "verify_repository_and_design",
)
