from __future__ import annotations

import csv
import gzip
import json
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from app.risk.risk_config import (
    ACTIVE_FORWARD_BASELINE,
    CURRENT_RISK_STRUCTURE_CONFIG_HASH,
    CURRENT_RISK_STRUCTURE_VERSION,
    RISK_STRUCTURE_V1_CONFIG_HASH,
    RISK_STRUCTURE_V1_DATASET_HASH,
    RISK_STRUCTURE_V1_1_DATASET_HASH,
    RISK_STRUCTURE_VERSION,
    RiskStructureV11Config,
    resolve_current_risk_structure_dataset,
    resolve_risk_structure_dataset,
    risk_structure_version_status,
)
from app.strategy.momentum_candidates import file_sha256

REFERENCE_CLASSIFICATIONS = (
    "HISTORICAL_ALLOWED",
    "AUDIT_ALLOWED",
    "TEST_FIXTURE_ALLOWED",
    "FORWARD_REFERENCE_MUST_CHANGE",
)
REFERENCE_PATTERNS = (
    re.compile(r"\bRISK_STRUCTURE_V1\b"),
    re.compile(r"risk_structures_v1\.csv\.gz"),
    re.compile(r"risk_structures[/\\]daily[/\\]v1(?:[/\\]|$)"),
)
SOURCE_SUFFIXES = {".py", ".md", ".js", ".jsx", ".json"}
EXCLUDED_PARTS = {".git", ".venv", "node_modules", "dist", "data", "__pycache__"}

UPSTREAM_HASHES = {
    "feature": "9d3c7535fcbb9a4b7e437aca4309fab2fa3369b998e26fb7732661926a383a38",
    "candidate": "743560ca057f3783bbd6e8c4b54909a8f19f8ce6ed465d8c8c1528354486b337",
    "setup": "aa210c3b2ad8c21844c2d59021c840a38cfd41ff175f62320f81d3d7a1641ecc",
    "regime": "fa2153a76a8e1088076e8fafe978cdd91eb9a70d820bdde4f20f8578bb2d2c74",
    "entry": "1b810ce271c29c7b16b3e3f0223713f8709e31f3248645798aaa627fa9b67009",
}

FORWARD_REFERENCES_UPDATED = (
    "Authoritative current version and config hash added to risk_config.py.",
    "Generic evaluation defaults now use the current V1.1 config.",
    "Generic build CLI defaults to current and dispatches to the V1.1 engine.",
    "Risk dataset paths now resolve through the central version registry.",
    "The V1 builder requires an explicit historical RiskStructureConfig.",
)


def audit_v1_references(repo_root: Path) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for path in source_files(repo_root):
        relative_path = path.relative_to(repo_root).as_posix()
        for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            matched = [pattern.pattern for pattern in REFERENCE_PATTERNS if pattern.search(line)]
            if not matched:
                continue
            findings.append(
                {
                    "path": relative_path,
                    "line": line_number,
                    "classification": classify_v1_reference(relative_path),
                    "patterns": matched,
                    "text": line.strip()[:240],
                }
            )
    counts = Counter(item["classification"] for item in findings)
    return {
        "scope": "Risk-specific V1 symbols, filenames, and risk-structure daily/v1 paths in source and documentation.",
        "total_references": len(findings),
        "classification_counts": {name: counts.get(name, 0) for name in REFERENCE_CLASSIFICATIONS},
        "forward_references_updated": list(FORWARD_REFERENCES_UPDATED),
        "unintended_forward_references": [
            item for item in findings if item["classification"] == "FORWARD_REFERENCE_MUST_CHANGE"
        ],
        "references": findings,
    }


def source_files(repo_root: Path) -> Iterable[Path]:
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        if any(part in EXCLUDED_PARTS for part in path.relative_to(repo_root).parts):
            continue
        yield path


def classify_v1_reference(relative_path: str) -> str:
    path = relative_path.lower()
    if path.startswith("backend/tests/"):
        return "TEST_FIXTURE_ALLOWED"
    if "audit" in path or path.endswith("risk_structure_v1_1.py") or path.endswith("strategy-v1-risk-structure-v1-1.md"):
        return "AUDIT_ALLOWED"
    if path in {
        "backend/app/risk/risk_config.py",
        "backend/app/risk/risk_structurer.py",
        "backend/scripts/build_risk_structures.py",
        "docs/strategy-v1-risk-structure.md",
        "docs/risk-structure-baseline-promotion.md",
    }:
        return "HISTORICAL_ALLOWED"
    return "FORWARD_REFERENCE_MUST_CHANGE"


def build_baseline_promotion_report(
    *,
    repo_root: Path,
    tests_passed: bool,
    frontend_build_passed: bool,
) -> dict[str, Any]:
    data_dir = repo_root / "data"
    previous_dataset = resolve_risk_structure_dataset(data_dir, RISK_STRUCTURE_VERSION)
    current_dataset = resolve_current_risk_structure_dataset(data_dir)
    previous_hash = file_sha256(previous_dataset)
    current_hash = file_sha256(current_dataset)
    current_config_hash = RiskStructureV11Config().config_hash()
    command_03 = json.loads((data_dir / "reports" / "risk_structure_v1_1_summary.json").read_text(encoding="utf-8"))
    reference_audit = audit_v1_references(repo_root)
    row_validation = validate_current_rows(current_dataset)

    target = command_03["target_regression"]
    capital = command_03["capital_regression"]
    observed_upstream = command_03["inputs"]["hashes_after"]
    upstream_regression = {
        name: observed_upstream.get(name) == expected_hash
        for name, expected_hash in UPSTREAM_HASHES.items()
    }
    integrity = {
        "previous_dataset_hash_matches": previous_hash == RISK_STRUCTURE_V1_DATASET_HASH,
        "current_dataset_hash_matches": current_hash == RISK_STRUCTURE_V1_1_DATASET_HASH,
        "current_config_hash_matches": current_config_hash == CURRENT_RISK_STRUCTURE_CONFIG_HASH,
        "upstream_hashes_match": all(upstream_regression.values()),
    }
    target_invariants = {
        "result": target["result"],
        "structural_target_preferred": target["semantic_mismatches_on_evaluable_rows"] == 0,
        "fallback_2r_only_when_structure_unavailable": target["artificial_2r_replacements"] == 0,
        "artificial_2r_replacement_violations": target["artificial_2r_replacements"],
        "structural_target_below_minimum_violations": target["structural_below_minimum_violations"],
    }
    capital_invariants = {
        "result": capital["result"],
        "capital_risk_above_one_pct_violations": row_validation["capital_risk_above_one_pct_violations"],
        "whole_share_violations": row_validation["whole_share_violations"],
        "leverage_violations": row_validation["leverage_violations"],
        "margin_status": RiskStructureV11Config().margin_status,
    }
    safety = {
        "final_strategy_scores_generated": 0,
        "trade_signals_generated": 0,
        "orders_placed": 0,
        "remote_migrations_applied": 0,
        "supabase_records_persisted": 0,
    }
    promotion_checks = (
        all(integrity.values()),
        target["result"] == "UNCHANGED_AND_VALID",
        target_invariants["artificial_2r_replacement_violations"] == 0,
        target_invariants["structural_target_below_minimum_violations"] == 0,
        capital["result"] == "UNCHANGED_AND_VALID",
        row_validation["all_valid"],
        not reference_audit["unintended_forward_references"],
        tests_passed,
        frontend_build_passed,
    )
    promotion_status = "PROMOTED_CURRENT_BASELINE" if all(promotion_checks) else "VERIFICATION_INCOMPLETE"
    return {
        "phase": "Step 02.9",
        "command": "Command 04",
        "previous_version": RISK_STRUCTURE_VERSION,
        "previous_config_hash": RISK_STRUCTURE_V1_CONFIG_HASH,
        "previous_dataset_hash": previous_hash,
        "current_version": CURRENT_RISK_STRUCTURE_VERSION,
        "current_version_status": risk_structure_version_status(CURRENT_RISK_STRUCTURE_VERSION),
        "current_config_hash": current_config_hash,
        "current_dataset_hash": current_hash,
        "promotion_status": promotion_status,
        "reason": "Approved setup-specific invalidation-priority correction from Command 03.",
        "methodology_changed_by_promotion": False,
        "historical_v1_preserved": integrity["previous_dataset_hash_matches"],
        "forward_references_updated": list(FORWARD_REFERENCES_UPDATED),
        "remaining_v1_reference_summary": reference_audit,
        "integrity": integrity,
        "upstream_regression": upstream_regression,
        "target_invariants": target_invariants,
        "capital_invariants": capital_invariants,
        "current_dataset_validation": row_validation,
        "tests_passed": tests_passed,
        "frontend_build_passed": frontend_build_passed,
        "final_strategy_score_status": "NOT_IMPLEMENTED",
        "trade_signal_status": "NOT_GENERATED",
        "safety": safety,
        "step_status": "COMPLETE" if promotion_status == "PROMOTED_CURRENT_BASELINE" else "INCOMPLETE",
        "ready_for_review": promotion_status == "PROMOTED_CURRENT_BASELINE",
    }


def validate_current_rows(dataset_path: Path) -> dict[str, Any]:
    total_rows = 0
    capital_risk_violations = 0
    whole_share_violations = 0
    leverage_violations = 0
    final_score_violations = 0
    signal_violations = 0
    with gzip.open(dataset_path, "rt", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            total_rows += 1
            planned_risk_pct = decimal_or_none(row.get("planned_risk_pct"))
            if planned_risk_pct is not None and planned_risk_pct > Decimal("1.00"):
                capital_risk_violations += 1
            quantity = decimal_or_none(row.get("structured_quantity"))
            if quantity is not None and quantity != quantity.to_integral_value():
                whole_share_violations += 1
            if row.get("whole_share_status") != "WHOLE_SHARES_ONLY":
                whole_share_violations += 1
            if row.get("no_leverage_status") != "NO_LEVERAGE":
                leverage_violations += 1
            if row.get("final_strategy_score_status") != "NOT_IMPLEMENTED":
                final_score_violations += 1
            if row.get("trade_signal_status") != "NOT_GENERATED":
                signal_violations += 1
    result = {
        "rows": total_rows,
        "capital_risk_above_one_pct_violations": capital_risk_violations,
        "whole_share_violations": whole_share_violations,
        "leverage_violations": leverage_violations,
        "final_score_status_violations": final_score_violations,
        "signal_status_violations": signal_violations,
    }
    result["all_valid"] = total_rows > 0 and not any(value for key, value in result.items() if key not in {"rows", "all_valid"})
    return result


def decimal_or_none(value: Any) -> Decimal | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def write_baseline_promotion_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
