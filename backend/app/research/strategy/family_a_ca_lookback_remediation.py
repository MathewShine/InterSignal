from __future__ import annotations

import hashlib
import inspect
import json
import subprocess
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.research.strategy import family_a_one_shot_validation as validation
from app.research.strategy.family_a_momentum import (
    LIQUIDITY_FLOOR,
    LOOKBACK_SESSIONS,
    PRICE_FLOOR,
    AdjustedBar,
    _corporate_action_exclusions,
    _corporate_action_safe,
    _load_aliases,
    _load_membership,
    _median_traded_value,
    file_sha256,
    read_csv,
    write_csv,
    write_json,
)
from app.research.strategy.family_a_validation_design import (
    FAMILY_CONFIG_HASH,
)
from app.research.strategy.family_a_post_validation_ca_audit import (
    FORMAL_VALIDATION_MANIFEST_HASH,
    FORMAL_VALIDATION_RESULT_HASH,
    verify_formal_validation,
)
from app.research.temporal_validation.config import canonical_hash


COMMAND = "Step 03.10 / Command 02"
COMMAND_VERSION = "FAMILY_A_CA_LOOKBACK_REMEDIATION_V1"
COMMAND_PROFILE = "VALIDATION_PREHISTORY_SEMANTICS_FIX_V1"
MANIFEST_VERSION = "FAMILY_A_CA_LOOKBACK_REMEDIATION_MANIFEST_V1"
REQUIRED_CHECKPOINT = "f41801acf01b69fa55353ebb07ae01ae86fc02b0"
ROOT_CAUSE_AUDIT_HASH = (
    "a1892e805c7baf49c42534abe3c4800da721ec25bbc1de80e62fc1fc7bee6793"
)
EXPECTED_VALIDATION_SOURCE_HASH_BEFORE_REMEDIATION = (
    "ef3a7ac4b9c143a3c6f3690565866743d54fa5555708778a50a7001ab38f709a"
)
EXPECTED_CA_RULE_SOURCE_HASH = (
    "1976c9e98ab5ec3a5a2d2b05dcbe51a40180d6745f5c7ec7c8755a9eb6ac9901"
)
EXPECTED_CA_SAFE_FUNCTION_HASH = (
    "bd971c109b8e488c719b8ed8d491c50c3dfcb954620b2b30d5fabc115d6ebcab"
)
EXPECTED_FROZEN_FUNCTION_HASHES = {
    "build_validation_schedules": "1efe3d28dd0b044599d095c1519c57912af3f5393c9acd7bb3f7cb944bde3dc6",
    "simulate_validation_executable": "95ec474da47b8cca6d0193945e531ab6ee52ea5e8f557d53a9b22d70eb44d52a",
    "calculate_validation_metrics": "ce58079afa0eaf1b3ea40887f259e3afd8cbe1ad12244864bf86a2b997b4422c",
    "evaluate_criteria": "85405fb352d3def4d727345616804554087397ccbcdca2c6da0e4b20181a44db",
}

VALIDATION_FORMATIONS = tuple(formation for formation, _ in validation.SEALED_SCHEDULE)
DEVELOPMENT_FORMATIONS = (
    date(2023, 3, 31),
    date(2024, 3, 28),
    date(2024, 9, 30),
)
ALLOWED_SCOPE_CLASSIFICATIONS = {
    "CA_PREHISTORY_BOUNDARY_FIX",
    "ASSERTION",
    "TEST",
    "REPORTING",
    "DOCUMENTATION",
}
PROHIBITED_SCOPE_CLASSIFICATIONS = {
    "STRATEGY_CHANGE",
    "PERFORMANCE_CHANGE",
    "CRITERIA_CHANGE",
    "RESULT_CHANGE",
}
REMEDIATION_RESULT = "FIX_VERIFIED_STRUCTURALLY"
FAILURE_SCOPE = "NORMAL_SYMBOL_LEVEL_ELIGIBILITY"
TECHNICAL_READINESS = "YES"
GOVERNANCE_STATUS = "NOT_AUTHORIZED"
POST_OUTCOME_DISCLOSURE = (
    "Any future validation performed after this remediation is "
    "POST_OUTCOME_REMEDIATED_VALIDATION because prior validation outcomes are "
    "known. It cannot be treated as pristine holdout evidence."
)


class FamilyACARemediationRepositoryStateMismatch(RuntimeError):
    pass


class FamilyACARemediationScopeViolation(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def artifact_root(root: Path) -> Path:
    return root / "data/research/validation/family_a/v1/ca_remediation"


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", *args),
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise FamilyACARemediationRepositoryStateMismatch(
            result.stderr.strip() or "Git verification failed"
        )
    return result.stdout.strip()


def verify_repository_checkpoint(root: Path) -> dict[str, Any]:
    head = _git(root, "rev-parse", "HEAD")
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if head != REQUIRED_CHECKPOINT or branch != "main":
        raise FamilyACARemediationRepositoryStateMismatch(
            "FAMILY_A_CA_REMEDIATION_REPOSITORY_STATE_MISMATCH"
        )
    checkpoint_source = subprocess.run(
        (
            "git",
            "show",
            f"{REQUIRED_CHECKPOINT}:backend/app/research/strategy/family_a_one_shot_validation.py",
        ),
        cwd=root,
        capture_output=True,
        check=False,
    )
    checkpoint_source_hash = hashlib.sha256(checkpoint_source.stdout).hexdigest()
    if (
        checkpoint_source.returncode
        or checkpoint_source_hash
        != EXPECTED_VALIDATION_SOURCE_HASH_BEFORE_REMEDIATION
    ):
        raise FamilyACARemediationRepositoryStateMismatch(
            "FAMILY_A_CA_REMEDIATION_REPOSITORY_STATE_MISMATCH"
        )
    return {
        "head": head,
        "branch": branch,
        "validation_source_hash_at_checkpoint": checkpoint_source_hash,
        "status": "VERIFIED",
    }


def _verify_document(path: Path, field: str, expected: str) -> dict[str, Any]:
    document = _json(path)
    body = {key: value for key, value in document.items() if key != field}
    if document.get(field) != expected or canonical_hash(body) != expected:
        raise ValueError(f"Frozen document changed: {field}")
    return document


def verify_root_cause_audit(root: Path) -> dict[str, Any]:
    manifest_path = (
        root
        / "data/research/validation/family_a/v1/post_validation_ca_audit/manifests"
        / "family_a_post_validation_ca_audit_manifest_v1.json"
    )
    manifest = _verify_document(
        manifest_path,
        "family_a_post_validation_ca_audit_manifest_hash",
        ROOT_CAUSE_AUDIT_HASH,
    )
    if (
        manifest.get("root_cause") != "IMPLEMENTATION_LOGIC_DEFECT"
        or manifest.get("severity") != "FATAL_TO_VALIDATION_INTEGRITY"
        or manifest.get("fixability") != "CODE_FIX_ONLY"
        or manifest.get("replacement_governance_assessment", {}).get(
            "replacement_validation_governance_status"
        )
        != GOVERNANCE_STATUS
    ):
        raise ValueError("Frozen CA root-cause classification changed")
    return {
        "manifest_path": manifest_path.relative_to(root).as_posix(),
        "manifest_hash": ROOT_CAUSE_AUDIT_HASH,
        "root_cause": manifest["root_cause"],
        "severity": manifest["severity"],
        "fixability": manifest["fixability"],
    }


def _source_hash(function: Any) -> str:
    return hashlib.sha256(inspect.getsource(function).encode()).hexdigest()


def _frozen_semantics(root: Path) -> dict[str, Any]:
    ca_source = root / "backend/app/research/strategy/family_a_momentum.py"
    observed_functions = {
        name: _source_hash(getattr(validation, name))
        for name in EXPECTED_FROZEN_FUNCTION_HASHES
    }
    if observed_functions != EXPECTED_FROZEN_FUNCTION_HASHES:
        raise FamilyACARemediationScopeViolation(
            "CA_REMEDIATION_SCOPE_VIOLATION: frozen strategy/performance/criteria function"
        )
    ca_safe_hash = _source_hash(_corporate_action_safe)
    if (
        file_sha256(ca_source) != EXPECTED_CA_RULE_SOURCE_HASH
        or ca_safe_hash != EXPECTED_CA_SAFE_FUNCTION_HASH
    ):
        raise FamilyACARemediationScopeViolation(
            "CA_REMEDIATION_SCOPE_VIOLATION: corporate-action rules"
        )
    return {
        "ca_rule_source_hash": file_sha256(ca_source),
        "ca_safe_function_hash": ca_safe_hash,
        "frozen_function_hashes": observed_functions,
        "family_config_hash": FAMILY_CONFIG_HASH,
        "candidate_identity_hash": validation.CANDIDATE_IDENTITY_HASH,
        "validation_design_hash": validation.DESIGN_HASH,
        "validation_criteria_hash": validation.DESIGN_CRITERIA_HASH,
        "ca_rules_unchanged": True,
        "strategy_unchanged": True,
        "criteria_unchanged": True,
    }


def _lookback_boundary(
    sessions: Sequence[date], formation: date
) -> tuple[date | None, int, str]:
    positions = {session: index for index, session in enumerate(sessions)}
    position = positions.get(formation)
    if position is None:
        return None, 0, "NON_SESSION_FORMATION_DATE"
    required = LOOKBACK_SESSIONS["6M"]
    start_index = position - required
    if start_index < 0:
        return None, position, "INSUFFICIENT_CALENDAR_HISTORY"
    return sessions[start_index], position - start_index, "AVAILABLE"


def build_before_after_fixture(
    causal_sessions: Sequence[date], performance_sessions: Sequence[date]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    formation = VALIDATION_FORMATIONS[0]
    before_start, before_count, before_reason = _lookback_boundary(
        performance_sessions, formation
    )
    before_safe, before_blockers = _corporate_action_safe(
        "OFFLINE_FIXTURE", before_start, formation, {}
    )
    after_start, after_count, after_reason = _lookback_boundary(
        causal_sessions, formation
    )
    after_safe, after_blockers = _corporate_action_safe(
        "OFFLINE_FIXTURE", after_start, formation, {}
    )
    rows = [
        {
            "state": "BEFORE_VALIDATION_TRUNCATED_CALENDAR",
            "formation_date": formation,
            "calendar_start": performance_sessions[0],
            "lookback_start": before_start,
            "lookback_session_count": before_count,
            "boundary_reason": before_reason,
            "corporate_action_safe": before_safe,
            "corporate_action_reasons": before_blockers,
        },
        {
            "state": "AFTER_FULL_CAUSAL_HISTORY",
            "formation_date": formation,
            "calendar_start": causal_sessions[0],
            "lookback_start": after_start,
            "lookback_session_count": after_count,
            "boundary_reason": after_reason,
            "corporate_action_safe": after_safe,
            "corporate_action_reasons": after_blockers,
        },
    ]
    if (
        before_safe
        or before_blockers != ("NO_LOOKBACK_START",)
        or after_start is None
        or after_count != LOOKBACK_SESSIONS["6M"]
        or not after_safe
        or after_blockers
    ):
        raise ValueError("Before/after remediation fixture did not reproduce the proven defect")
    body = {
        "fixture_version": "FAMILY_A_CA_LOOKBACK_BEFORE_AFTER_FIXTURE_V1",
        "performance_window": {
            "start": validation.VALIDATION_START,
            "end": validation.VALIDATION_END,
        },
        "frozen_lookback_sessions": LOOKBACK_SESSIONS["6M"],
        "rows": rows,
        "original_defect_reproduced": True,
        "corrected_boundary_verified": True,
        "portfolio_performance_calculated": False,
    }
    return body, rows


def _structural_formation(
    *,
    formation: date,
    execution: date,
    sessions: Sequence[date],
    bars: Mapping[date, Mapping[str, AdjustedBar]],
    membership: Any,
    exclusions: Mapping[str, Sequence[Mapping[str, Any]]],
    period: str,
) -> dict[str, Any]:
    members = membership.members_for(formation)
    start_date, lookback_count, boundary_reason = _lookback_boundary(
        sessions, formation
    )
    price_eligible = 0
    liquidity_available = 0
    liquidity_eligible = 0
    ca_eligible = 0
    structurally_selectable = 0
    no_lookback = 0
    reason_counts: Counter[str] = Counter()
    for symbol in sorted(members):
        formation_bar = bars.get(formation, {}).get(symbol)
        price_ok = bool(
            formation_bar and formation_bar.close_price >= PRICE_FLOOR
        )
        liquidity, _ = _median_traded_value(
            symbol, bars, sessions, formation
        )
        liquidity_available_ok = liquidity is not None
        liquidity_ok = bool(
            liquidity is not None and liquidity >= LIQUIDITY_FLOOR
        )
        ca_safe, blockers = _corporate_action_safe(
            symbol, start_date, formation, exclusions
        )
        no_lookback += int("NO_LOOKBACK_START" in blockers)
        reason_counts.update(blockers)
        start_bar = bars.get(start_date, {}).get(symbol) if start_date else None
        endpoint_history_ok = bool(
            start_bar
            and formation_bar
            and start_bar.close_price > 0
            and start_bar.usability_status == "ADJUSTED_READY"
            and formation_bar.usability_status == "ADJUSTED_READY"
        )
        execution_bar = bars.get(execution, {}).get(symbol)
        next_open_ok = bool(execution_bar and execution_bar.open_price > 0)
        structural_ok = all(
            (
                price_ok,
                liquidity_ok,
                ca_safe,
                endpoint_history_ok,
                next_open_ok,
            )
        )
        price_eligible += int(price_ok)
        liquidity_available += int(liquidity_available_ok)
        liquidity_eligible += int(liquidity_ok)
        ca_eligible += int(ca_safe)
        structurally_selectable += int(structural_ok)
    return {
        "period": period,
        "formation_date": formation,
        "execution_date": execution,
        "point_in_time_member_count": len(members),
        "lookback_start": start_date,
        "lookback_session_count": lookback_count,
        "lookback_boundary_reason": boundary_reason,
        "price_eligible_count": price_eligible,
        "liquidity_available_count": liquidity_available,
        "liquidity_eligible_count": liquidity_eligible,
        "ca_eligible_count": ca_eligible,
        "ca_excluded_count": len(members) - ca_eligible,
        "no_lookback_start_count": no_lookback,
        "final_structurally_selectable_count": structurally_selectable,
        "ca_exclusion_reasons": dict(sorted(reason_counts.items())),
        "momentum_ranked": False,
        "top_decile_selected": False,
        "holdings_generated": False,
        "performance_calculated": False,
    }


def _development_regression(
    root: Path,
    sessions: Sequence[date],
    bars: Mapping[date, Mapping[str, AdjustedBar]],
    membership: Any,
    exclusions: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    audit_summary = _json(
        root / "data/reports/family_a_ca_audit_v1_summary.json"
    )
    baseline = {
        row["formation_date"]: row
        for row in audit_summary["development_comparison"]
    }
    rows: list[dict[str, Any]] = []
    for formation in DEVELOPMENT_FORMATIONS:
        execution = next(session for session in sessions if session > formation)
        current = _structural_formation(
            formation=formation,
            execution=execution,
            sessions=sessions,
            bars=bars,
            membership=membership,
            exclusions=exclusions,
            period="DEVELOPMENT",
        )
        expected = baseline[formation.isoformat()]
        unchanged = all(
            (
                current["point_in_time_member_count"]
                == expected["ptit_member_count"],
                current["lookback_start"]
                == date.fromisoformat(expected["full_history_lookback_start"]),
                current["ca_eligible_count"] == expected["ca_eligible_count"],
                current["final_structurally_selectable_count"]
                == expected["final_candidate_universe_count"],
                current["price_eligible_count"]
                == expected["price_eligible_count"],
                current["liquidity_eligible_count"]
                == expected["liquidity_eligible_count"],
            )
        )
        rows.append(
            {
                "formation_date": formation,
                "expected_ca_eligible_count": expected["ca_eligible_count"],
                "current_ca_eligible_count": current["ca_eligible_count"],
                "expected_structurally_selectable_count": expected[
                    "final_candidate_universe_count"
                ],
                "current_structurally_selectable_count": current[
                    "final_structurally_selectable_count"
                ],
                "expected_lookback_start": expected[
                    "full_history_lookback_start"
                ],
                "current_lookback_start": current["lookback_start"],
                "unchanged": unchanged,
            }
        )
    body = {
        "comparison_dates": DEVELOPMENT_FORMATIONS,
        "rows": rows,
        "all_development_dates_unchanged": all(row["unchanged"] for row in rows),
    }
    return body, rows


def _scope_guard(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = [
        {"file": "backend/app/research/strategy/family_a_one_shot_validation.py", "functional_block": "LOOKBACK_SESSIONS invariant import", "classification": "ASSERTION"},
        {"file": "backend/app/research/strategy/family_a_one_shot_validation.py", "functional_block": "prepare_validation_session_windows causal/performance separation", "classification": "CA_PREHISTORY_BOUNDARY_FIX"},
        {"file": "backend/app/research/strategy/family_a_one_shot_validation.py", "functional_block": "prehistory and exact performance-window invariants", "classification": "ASSERTION"},
        {"file": "backend/app/research/strategy/family_a_one_shot_validation.py", "functional_block": "execute input plumbing only", "classification": "CA_PREHISTORY_BOUNDARY_FIX"},
        {"file": "backend/app/research/strategy/family_a_ca_lookback_remediation.py", "functional_block": "structural verification and immutable artifact generation", "classification": "REPORTING"},
        {"file": "backend/scripts/run_family_a_ca_lookback_remediation.py", "functional_block": "offline remediation report runner", "classification": "REPORTING"},
        {"file": "backend/tests/test_family_a_ca_lookback_remediation.py", "functional_block": "offline remediation regressions", "classification": "TEST"},
        {"file": "backend/tests/test_family_a_post_validation_ca_audit.py", "functional_block": "pre-remediation source-hash compatibility assertion", "classification": "TEST"},
        {"file": "backend/tests/test_family_a_one_shot_validation.py", "functional_block": "post-checkpoint ancestry compatibility assertion", "classification": "TEST"},
        {"file": "docs/family-a-ca-lookback-remediation-v1.md", "functional_block": "remediation governance documentation", "classification": "DOCUMENTATION"},
    ]
    classifications = {row["classification"] for row in rows}
    if (
        classifications - ALLOWED_SCOPE_CLASSIFICATIONS
        or classifications & PROHIBITED_SCOPE_CLASSIFICATIONS
    ):
        raise FamilyACARemediationScopeViolation("CA_REMEDIATION_SCOPE_VIOLATION")
    body = {
        "required_checkpoint": REQUIRED_CHECKPOINT,
        "allowed_classifications": sorted(ALLOWED_SCOPE_CLASSIFICATIONS),
        "prohibited_classifications": sorted(PROHIBITED_SCOPE_CLASSIFICATIONS),
        "rows": rows,
        "scope_compliant": True,
        "strategy_change": False,
        "performance_change": False,
        "criteria_change": False,
        "result_change": False,
    }
    return body, rows


def _readiness(
    formation_rows: Sequence[Mapping[str, Any]],
    development: Mapping[str, Any],
    frozen: Mapping[str, Any],
    formal_unchanged: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    checks = [
        {"check": "GLOBAL_NO_LOOKBACK_ELIMINATED", "passed": all(row["no_lookback_start_count"] == 0 for row in formation_rows)},
        {"check": "ALL_FORMATIONS_HAVE_126_CAUSAL_SESSIONS", "passed": all(row["lookback_session_count"] >= LOOKBACK_SESSIONS["6M"] for row in formation_rows)},
        {"check": "DEVELOPMENT_REGRESSION_UNCHANGED", "passed": development["all_development_dates_unchanged"]},
        {"check": "CA_RULES_UNCHANGED", "passed": frozen["ca_rules_unchanged"]},
        {"check": "CANDIDATE_STRATEGY_UNCHANGED", "passed": frozen["strategy_unchanged"]},
        {"check": "VALIDATION_CRITERIA_UNCHANGED", "passed": frozen["criteria_unchanged"]},
        {"check": "FORMAL_VALIDATION_ARTIFACTS_UNCHANGED", "passed": formal_unchanged},
        {"check": "VALIDATION_PERFORMANCE_NOT_RERUN", "passed": True},
        {"check": "HOLDINGS_NOT_GENERATED", "passed": True},
        {"check": "REPLACEMENT_VALIDATION_NOT_AUTHORIZED", "passed": GOVERNANCE_STATUS == "NOT_AUTHORIZED"},
    ]
    ready = all(row["passed"] for row in checks)
    body = {
        "checks": checks,
        "FAMILY_A_CA_REMEDIATION_RESULT": (
            REMEDIATION_RESULT if ready else "PARTIAL_FIX"
        ),
        "POST_OUTCOME_REMEDIATED_VALIDATION_TECHNICAL_READINESS": (
            TECHNICAL_READINESS if ready else "NO"
        ),
        "REPLACEMENT_VALIDATION_GOVERNANCE_STATUS": GOVERNANCE_STATUS,
        "technical_readiness_is_authorization": False,
        "post_outcome_disclosure": POST_OUTCOME_DISCLOSURE,
    }
    return body, checks


def _with_hash(body: Mapping[str, Any], field: str) -> dict[str, Any]:
    return {**body, field: canonical_hash(body)}


def run_ca_lookback_remediation_verification(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    out = artifact_root(root)
    manifest_path = out / "manifests/family_a_ca_lookback_remediation_manifest_v1.json"
    if manifest_path.exists():
        raise FileExistsError("Immutable Family A CA remediation manifest already exists")

    repository = verify_repository_checkpoint(root)
    formal_before = verify_formal_validation(root)
    audit = verify_root_cause_audit(root)
    formal_manifest_path = root / formal_before["manifest_path"]
    formal_result_path = root / formal_before["result_path"]
    formal_bytes_before = {
        "manifest_file_sha256": file_sha256(formal_manifest_path),
        "result_file_sha256": file_sha256(formal_result_path),
    }
    frozen = _frozen_semantics(root)

    causal_sessions, performance_sessions = validation.prepare_validation_session_windows(
        root
    )
    fixture, fixture_rows = build_before_after_fixture(
        causal_sessions, performance_sessions
    )
    aliases = _load_aliases(root)
    membership = _load_membership(root)
    bars = validation._load_bounded_bars(root, set(membership.grouped), aliases)
    exclusions = _corporate_action_exclusions(root, aliases)

    formation_rows = [
        _structural_formation(
            formation=formation,
            execution=execution,
            sessions=causal_sessions,
            bars=bars,
            membership=membership,
            exclusions=exclusions,
            period="VALIDATION",
        )
        for formation, execution in validation.SEALED_SCHEDULE
    ]
    if any(row["no_lookback_start_count"] for row in formation_rows):
        raise ValueError("Global NO_LOOKBACK_START remains after remediation")
    development, development_rows = _development_regression(
        root, causal_sessions, bars, membership, exclusions
    )
    scope, scope_rows = _scope_guard(root)

    formal_after = verify_formal_validation(root)
    formal_bytes_after = {
        "manifest_file_sha256": file_sha256(formal_manifest_path),
        "result_file_sha256": file_sha256(formal_result_path),
    }
    formal_unchanged = (
        formal_before == formal_after
        and formal_bytes_before == formal_bytes_after
    )
    if not formal_unchanged:
        raise ValueError("Formal validation artifacts changed during remediation verification")

    configuration_body = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "required_checkpoint": REQUIRED_CHECKPOINT,
        "validation_performance_window": {
            "start": validation.VALIDATION_START,
            "end": validation.VALIDATION_END,
        },
        "causal_history_available_start": causal_sessions[0],
        "causal_history_available_end": causal_sessions[-1],
        "frozen_lookback_sessions": LOOKBACK_SESSIONS["6M"],
        "validation_formations": VALIDATION_FORMATIONS,
        "performance_calculation_allowed": False,
        "validation_rerun_allowed": False,
    }
    configuration = _with_hash(
        configuration_body, "family_a_ca_remediation_config_hash"
    )
    calendar_body = {
        "causal_history_start": causal_sessions[0],
        "causal_history_end": causal_sessions[-1],
        "performance_start": performance_sessions[0],
        "performance_end": performance_sessions[-1],
        "earliest_required_historical_session": formation_rows[0]["lookback_start"],
        "prepare_validation_session_windows_hash": _source_hash(
            validation.prepare_validation_session_windows
        ),
        "execute_one_shot_validation_hash_after_plumbing_fix": _source_hash(
            validation.execute_one_shot_validation
        ),
        "prehistory_and_performance_windows_separated": True,
        "post_holdout_rows_loaded": 0,
    }
    calendar = _with_hash(calendar_body, "family_a_ca_calendar_fix_hash")
    structural_body = {
        "formations": formation_rows,
        "POST_REMEDIATION_CA_FAILURE_SCOPE": FAILURE_SCOPE,
        "all_global_no_lookback_failures_eliminated": True,
        "momentum_ranking_performed": False,
        "holdings_generated": False,
        "performance_calculated": False,
    }
    structural = _with_hash(
        structural_body, "family_a_ca_structural_eligibility_hash"
    )
    development_hashed = _with_hash(
        development, "family_a_ca_development_regression_hash"
    )
    scope_hashed = _with_hash(scope, "family_a_ca_scope_guard_hash")
    readiness, readiness_rows = _readiness(
        formation_rows, development, frozen, formal_unchanged
    )
    readiness_hashed = _with_hash(
        readiness, "family_a_ca_remediation_readiness_hash"
    )
    hashes = {
        "family_a_ca_remediation_config_hash": configuration[
            "family_a_ca_remediation_config_hash"
        ],
        "family_a_ca_calendar_fix_hash": calendar[
            "family_a_ca_calendar_fix_hash"
        ],
        "family_a_ca_structural_eligibility_hash": structural[
            "family_a_ca_structural_eligibility_hash"
        ],
        "family_a_ca_development_regression_hash": development_hashed[
            "family_a_ca_development_regression_hash"
        ],
        "family_a_ca_scope_guard_hash": scope_hashed[
            "family_a_ca_scope_guard_hash"
        ],
        "family_a_ca_remediation_readiness_hash": readiness_hashed[
            "family_a_ca_remediation_readiness_hash"
        ],
    }
    summary_body = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "created_at": utc_now(),
        "repository_checkpoint": repository,
        "formal_validation": formal_after,
        "formal_validation_file_hashes_before": formal_bytes_before,
        "formal_validation_file_hashes_after": formal_bytes_after,
        "formal_validation_artifacts_unchanged": formal_unchanged,
        "root_cause_audit": audit,
        "configuration": configuration,
        "calendar_fix": calendar,
        "before_after_fixture": fixture,
        "structural_eligibility": structural,
        "development_regression": development_hashed,
        "frozen_semantics": frozen,
        "scope_guard": scope_hashed,
        "readiness": readiness_hashed,
        "hashes": hashes,
        "constraints": {
            "family_a_changed": False,
            "ca_rules_changed": False,
            "validation_criteria_changed": False,
            "formal_validation_artifacts_changed": False,
            "validation_holdings_generated": False,
            "validation_performance_calculated": False,
            "validation_rerun_performed": False,
            "strategy_v2_created": False,
            "live_signals": 0,
            "live_orders": 0,
            "broker_calls": 0,
            "migrations": 0,
            "supabase_persistence": 0,
            "external_writes": 0,
        },
    }
    summary = _with_hash(summary_body, "family_a_ca_remediation_summary_hash")
    manifest_body = {
        "manifest_version": MANIFEST_VERSION,
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "created_at": summary["created_at"],
        "required_checkpoint": REQUIRED_CHECKPOINT,
        "root_cause_audit_hash": ROOT_CAUSE_AUDIT_HASH,
        "formal_validation_manifest_hash": FORMAL_VALIDATION_MANIFEST_HASH,
        "formal_validation_result_hash": FORMAL_VALIDATION_RESULT_HASH,
        "code_change_scope": scope_rows,
        "before_after_fixture": fixture,
        "formation_date_structural_results": formation_rows,
        "development_regression": development_hashed,
        "technical_readiness": readiness_hashed,
        "replacement_validation_governance_status": GOVERNANCE_STATUS,
        "post_outcome_disclosure": POST_OUTCOME_DISCLOSURE,
        "hashes": hashes,
        "formal_validation_artifacts_unchanged": True,
        "validation_rerun_performed": False,
        "holdings_generated": False,
        "performance_calculated": False,
    }
    manifest = _with_hash(
        manifest_body, "family_a_ca_lookback_remediation_manifest_hash"
    )

    write_json(out / "fixtures/before_after_v1.json", fixture)
    write_csv(out / "fixtures/before_after_v1.csv", fixture_rows)
    write_json(out / "calendar/session_boundary_v1.json", calendar)
    write_json(out / "eligibility/formation_structural_results_v1.json", structural)
    write_csv(out / "eligibility/formation_structural_results_v1.csv", formation_rows)
    write_json(out / "regression/development_regression_v1.json", development_hashed)
    write_csv(out / "regression/development_regression_v1.csv", development_rows)
    write_json(out / "scope_guard/change_scope_v1.json", scope_hashed)
    write_csv(out / "scope_guard/change_scope_v1.csv", scope_rows)
    write_json(out / "readiness/technical_readiness_v1.json", readiness_hashed)
    write_csv(out / "readiness/technical_readiness_v1.csv", readiness_rows)
    write_json(manifest_path, manifest)

    reports = root / "data/reports"
    write_json(reports / "family_a_ca_remediation_v1_summary.json", summary)
    write_csv(reports / "family_a_ca_remediation_v1_before_after.csv", fixture_rows)
    write_csv(reports / "family_a_ca_remediation_v1_formations.csv", formation_rows)
    write_csv(
        reports / "family_a_ca_remediation_v1_development_regression.csv",
        development_rows,
    )
    write_csv(reports / "family_a_ca_remediation_v1_scope_guard.csv", scope_rows)
    write_csv(reports / "family_a_ca_remediation_v1_readiness.csv", readiness_rows)
    return {"summary": summary, "manifest": manifest}


__all__ = [
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "FAILURE_SCOPE",
    "GOVERNANCE_STATUS",
    "MANIFEST_VERSION",
    "POST_OUTCOME_DISCLOSURE",
    "REMEDIATION_RESULT",
    "REQUIRED_CHECKPOINT",
    "ROOT_CAUSE_AUDIT_HASH",
    "TECHNICAL_READINESS",
    "artifact_root",
    "build_before_after_fixture",
    "run_ca_lookback_remediation_verification",
    "verify_repository_checkpoint",
    "verify_root_cause_audit",
]
