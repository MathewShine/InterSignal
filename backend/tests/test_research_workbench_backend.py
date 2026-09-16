from __future__ import annotations

import ast
import inspect
from datetime import timedelta
from pathlib import Path

import pytest

from app.platform.hashing import canonical_hash, file_sha256
from app.platform.models import (
    EvidenceClassification,
    EvidenceLevel,
    StrategyLifecycle,
)
from app.platform.repositories import JsonFilePlatformRepository
from app.research_workbench import (
    ArtifactNotFound,
    EvidenceNotFound,
    FamilySortField,
    InvalidWorkbenchQuery,
    LineageNodeNotFound,
    ResearchConclusionClassification,
    ResearchFamilyNotFound,
    ResearchFamilyQuery,
    ResearchWorkbenchService,
    StrategyNotFound,
    WorkbenchIntegrityError,
)
from app.research_workbench.builder import (
    COMMAND_PROFILE,
    COMMAND_VERSION,
    FOUNDATION_PATHS,
    MANIFEST_VERSION,
    PLATFORM_CHARTER_HASH,
    PLATFORM_FOUNDATION_HASH,
    REQUIRED_CHECKPOINT,
)


ROOT = Path(__file__).resolve().parents[2]
PLATFORM_ROOT = ROOT / "data/platform"


@pytest.fixture
def workbench() -> ResearchWorkbenchService:
    repository = JsonFilePlatformRepository(PLATFORM_ROOT)
    return ResearchWorkbenchService.from_repository(repository)


def test_command_identity_is_frozen() -> None:
    assert COMMAND_VERSION == "INTERSIGNAL_RESEARCH_WORKBENCH_BACKEND_V1"
    assert COMMAND_PROFILE == "RESEARCH_QUERY_AND_VIEW_MODEL_FOUNDATION_V1"
    assert MANIFEST_VERSION == "INTERSIGNAL_RESEARCH_WORKBENCH_BACKEND_MANIFEST_V1"
    assert REQUIRED_CHECKPOINT == "1ccb93afabad936a79eb1c1131194652f80ec3c1"
    assert PLATFORM_FOUNDATION_HASH == (
        "ec270dcb640116fe56709c784b4ca915bd794b0a96847e11fb561460dfed877f"
    )
    assert PLATFORM_CHARTER_HASH == (
        "3bdf3224c6ca21c06c261bf673b76e164e6d0788b204b2875122dad878d9263b"
    )


def test_family_matrix_returns_all_seeded_families_deterministically(
    workbench: ResearchWorkbenchService,
) -> None:
    rows = workbench.list_research_families()
    assert [row.family_id for row in rows] == list("ABCDEFG")
    assert len(rows) == 7
    assert all(row.strategy_count == 1 for row in rows)


def test_family_matrix_has_required_lifecycle_and_conclusions(
    workbench: ResearchWorkbenchService,
) -> None:
    rows = {row.family_id: row for row in workbench.list_research_families()}
    assert (rows["A"].lifecycle_status, rows["A"].current_status) == (
        StrategyLifecycle.REJECTED,
        "CLOSED_NOT_ADVANCED",
    )
    assert rows["B"].current_status == "NO_INCREMENTAL_EDGE"
    assert (rows["C"].lifecycle_status, rows["C"].current_status) == (
        StrategyLifecycle.PAUSED,
        "REUSABLE_SIGNAL_ONLY",
    )
    assert rows["D"].lifecycle_status == StrategyLifecycle.DATA_BLOCKED
    assert rows["E"].current_status == "NEGATIVE_DEVELOPMENT"
    assert rows["F"].lifecycle_status == StrategyLifecycle.SOURCE_BLOCKED
    assert rows["G"].current_status == "NEGATIVE_OVERLAY"
    assert not any(row.production_candidate for row in rows.values())


def test_family_detail_is_complete(workbench: ResearchWorkbenchService) -> None:
    detail = workbench.get_family_detail("FAMILY_A")
    assert detail.family_id == "A"
    assert len(detail.strategies) == 1
    assert len(detail.evidence) == 3
    assert detail.events
    assert detail.artifacts
    assert detail.lineage_references
    assert detail.research_conclusion.classification == (
        ResearchConclusionClassification.CLOSED_NOT_ADVANCED
    )


def test_strategy_detail_groups_every_evidence_classification(
    workbench: ResearchWorkbenchService,
) -> None:
    detail = workbench.get_strategy_detail("FAMILY_A")
    assert detail.strategy_record.strategy_id == "FAMILY_A"
    assert detail.lifecycle_history
    assert detail.config_hashes
    assert detail.preregistration_hashes
    assert set(detail.evidence_by_classification) == set(EvidenceClassification)
    assert len(
        detail.evidence_by_classification[
            EvidenceClassification.VALIDATION_EVIDENCE
        ]
    ) == 1
    assert len(
        detail.evidence_by_classification[
            EvidenceClassification.POST_OUTCOME_EVIDENCE
        ]
    ) == 1


def test_global_evidence_summary_keeps_all_classifications_separate(
    workbench: ResearchWorkbenchService,
) -> None:
    summary = workbench.export_research_workbench_snapshot().evidence_summary
    assert summary.positive_evidence_count == 3
    assert summary.negative_evidence_count == 3
    assert summary.blocked_research_count == 2
    assert summary.validation_evidence_count == 1
    assert summary.post_outcome_evidence_count == 1
    assert summary.data_infrastructure_evidence_count == 1
    assert summary.total_count == 11


def test_family_a_formal_and_post_outcome_results_remain_distinct(
    workbench: ResearchWorkbenchService,
) -> None:
    validation = workbench.get_validation_summary("A")
    assert validation.formal_result == "INCONCLUSIVE"
    assert validation.generalization_result == "UNSUPPORTIVE"
    assert validation.post_outcome_result == "UNSUPPORTIVE"
    assert validation.advancement_status == "CLOSED_NOT_ADVANCED"
    assert validation.pristine_holdout is False
    assert validation.run_count == 2
    formal = workbench.list_evidence(
        family_id="A",
        classification=EvidenceClassification.VALIDATION_EVIDENCE,
    )
    post = workbench.list_evidence(
        family_id="A",
        classification=EvidenceClassification.POST_OUTCOME_EVIDENCE,
    )
    assert [row.evidence_id for row in formal] == [
        "EVIDENCE-A-FORMAL-VALIDATION-001"
    ]
    assert [row.evidence_id for row in post] == [
        "EDGE-NEGATIVE-A-LATER-PERIOD-GENERALIZATION-001"
    ]


def test_family_d_is_data_blocked_not_strategy_failed(
    workbench: ResearchWorkbenchService,
) -> None:
    blocked = workbench.get_blocked_research("D")
    assert blocked is not None
    assert blocked.block_type == "DATA_BLOCKED"
    assert blocked.data_or_source == "DATA"
    assert blocked.reason == "intraday continuity below frozen threshold"
    assert blocked.related_evidence == ("EVIDENCE-D-DATA-BLOCKED-001",)


def test_family_f_is_source_blocked_not_strategy_failed(
    workbench: ResearchWorkbenchService,
) -> None:
    blocked = workbench.get_blocked_research("F")
    assert blocked is not None
    assert blocked.block_type == "SOURCE_BLOCKED"
    assert blocked.data_or_source == "SOURCE"
    assert blocked.reason == "authorized catalyst historical source unavailable"
    assert blocked.related_evidence == (
        "DATA-EVIDENCE-F-NSE-ANNOUNCEMENTS-001",
        "EVIDENCE-F-SOURCE-BLOCKED-001",
    )


def test_seed_evidence_examples_are_queryable(
    workbench: ResearchWorkbenchService,
) -> None:
    c = workbench.list_evidence(
        family_id="C", classification=EvidenceClassification.POSITIVE_EVIDENCE
    )
    assert {row.evidence_id for row in c} == {
        "EVIDENCE-C-COMPRESSION-001",
        "EDGE-EVIDENCE-C-COMPRESSION-001",
    }
    blocked = workbench.list_evidence(
        classification=EvidenceClassification.BLOCKED_RESEARCH
    )
    assert {row.strategy_linkage for row in blocked} == {"FAMILY_D", "FAMILY_F"}


def test_evidence_level_filter(workbench: ResearchWorkbenchService) -> None:
    infrastructure = workbench.list_evidence(
        level=EvidenceLevel.DATA_INFRASTRUCTURE_LEVEL
    )
    assert len(infrastructure) == 3
    assert {row.strategy_linkage for row in infrastructure} == {
        "FAMILY_D",
        "FAMILY_F",
    }


def test_timelines_come_from_registry_events_and_are_chronological(
    workbench: ResearchWorkbenchService,
) -> None:
    family = workbench.get_family_timeline("A")
    strategy = workbench.get_strategy_timeline("FAMILY_A")
    assert family == strategy
    assert family
    assert [row.timestamp for row in family] == sorted(
        row.timestamp for row in family
    )
    assert all(row.metadata["registry_entity_type"] for row in family)


def test_artifact_queries_traverse_only_registered_references(
    workbench: ResearchWorkbenchService,
) -> None:
    family = workbench.list_family_artifacts("A")
    strategy = workbench.list_strategy_artifacts("FAMILY_A")
    formal = workbench.list_evidence_artifacts(
        "EVIDENCE-A-FORMAL-VALIDATION-001"
    )
    assert family == strategy
    assert len(family) == 5
    assert len(formal) == 1
    assert formal[0].artifact_id == "ART-9985ba3814509c70595ff78a"
    assert all(row.reference.startswith("data/") for row in family)


def test_lineage_trace_is_bounded_and_deterministic(
    workbench: ResearchWorkbenchService,
) -> None:
    artifact = workbench.list_evidence_artifacts(
        "EVIDENCE-C-COMPRESSION-001"
    )[0]
    first = workbench.trace_research_lineage(artifact.lineage_node_id)
    second = workbench.trace_research_lineage(artifact.lineage_node_id)
    assert first == second
    assert first.summary.integrity_status.value == "HEALTHY"
    assert first.summary.downstream_count >= 1
    assert first.summary.root_sources == (artifact.lineage_node_id,)
    with pytest.raises(WorkbenchIntegrityError):
        workbench.trace_research_lineage(artifact.lineage_node_id, max_nodes=1)


def test_family_filters_cover_required_dimensions(
    workbench: ResearchWorkbenchService,
) -> None:
    assert [
        row.family_id
        for row in workbench.list_research_families(
            lifecycle=StrategyLifecycle.DATA_BLOCKED
        )
    ] == ["D"]
    assert {
        row.family_id
        for row in workbench.list_research_families(
            evidence_classification=EvidenceClassification.BLOCKED_RESEARCH
        )
    } == {"D", "F"}
    assert {
        row.family_id
        for row in workbench.list_research_families(
            evidence_level=EvidenceLevel.SIGNAL_LEVEL
        )
    } == {"C"}
    assert {
        row.family_id
        for row in workbench.list_research_families(blocked_state=True)
    } == {"D", "F"}
    assert [
        row.family_id
        for row in workbench.list_research_families(
            validation_state="INCONCLUSIVE"
        )
    ] == ["A"]
    assert [
        row.family_id
        for row in workbench.list_research_families(
            family_status="REUSABLE_SIGNAL_ONLY"
        )
    ] == ["C"]


def test_date_filters_are_inclusive(workbench: ResearchWorkbenchService) -> None:
    rows = workbench.list_research_families()
    latest = rows[0].latest_activity_at
    assert len(
        workbench.list_research_families(start_at=latest, end_at=latest)
    ) == 7
    assert not workbench.list_research_families(
        start_at=latest + timedelta(microseconds=1)
    )


@pytest.mark.parametrize(
    "sort_by,key",
    [
        (FamilySortField.NAME, lambda row: row.family_name.casefold()),
        (FamilySortField.LATEST_ACTIVITY, lambda row: row.latest_activity_at),
        (FamilySortField.STATUS, lambda row: row.current_status),
        (FamilySortField.FAMILY_CODE, lambda row: row.family_id),
    ],
)
def test_stable_sorting(
    workbench: ResearchWorkbenchService, sort_by: FamilySortField, key: object
) -> None:
    rows = workbench.list_research_families(sort_by=sort_by)
    assert list(map(key, rows)) == sorted(map(key, rows))


def test_deterministic_pagination(workbench: ResearchWorkbenchService) -> None:
    query = ResearchFamilyQuery(limit=3, offset=2)
    page = workbench.query_research_families(query)
    assert [row.family_id for row in page.items] == ["C", "D", "E"]
    assert page.limit == 3
    assert page.offset == 2
    assert page.total_count == 7


def test_invalid_queries_raise_stable_domain_error(
    workbench: ResearchWorkbenchService,
) -> None:
    with pytest.raises(InvalidWorkbenchQuery):
        workbench.query_research_families(ResearchFamilyQuery(limit=0))
    with pytest.raises(InvalidWorkbenchQuery):
        workbench.query_research_families(ResearchFamilyQuery(offset=-1))
    with pytest.raises(InvalidWorkbenchQuery):
        workbench.list_research_families(sort_by="unknown")


def test_programme_summary_matches_frozen_state(
    workbench: ResearchWorkbenchService,
) -> None:
    summary = workbench.get_programme_summary()
    assert summary.strategy_research_status == "PAUSED"
    assert summary.a_to_g_cycle_status == "COMPLETE_NO_VALIDATED_STRATEGY"
    assert summary.validated_strategy_count == 0
    assert summary.production_candidate_count == 0
    assert summary.strategy_v2_status == "NOT_CREATED"
    assert summary.family_h_status == "NOT_PLANNED"
    assert summary.paper_readiness == "NOT_READY"
    assert summary.live_readiness == "NOT_READY"
    assert summary.primary_programme == "PRODUCT_PLATFORM_PROGRAM"
    assert summary.secondary_programme == "FORWARD_DATA_PROGRAM"


def test_family_conclusions_are_explicit_and_non_promotable(
    workbench: ResearchWorkbenchService,
) -> None:
    expected = {
        "A": "CLOSED_NOT_ADVANCED",
        "B": "NO_INCREMENTAL_EDGE",
        "C": "REUSABLE_SIGNAL_ONLY",
        "D": "DATA_BLOCKED",
        "E": "NEGATIVE_DEVELOPMENT",
        "F": "SOURCE_BLOCKED",
        "G": "NEGATIVE_OVERLAY",
    }
    for family, classification in expected.items():
        conclusion = workbench.get_research_conclusion(family)
        assert conclusion.classification.value == classification
        assert conclusion.basis
        assert conclusion.advancement_allowed is False


def test_snapshot_is_deterministic_and_self_hashed(
    workbench: ResearchWorkbenchService,
) -> None:
    first = workbench.export_research_workbench_snapshot()
    second = workbench.export_research_workbench_snapshot()
    assert first == second
    assert first.snapshot_hash == canonical_hash(
        first.model_dump(mode="python", exclude={"snapshot_hash"})
    )
    assert len(first.families) == 7
    assert len(first.strategy_summaries) == 7
    assert len(first.blocked_studies) == 2


def test_integrity_summary_is_clean(workbench: ResearchWorkbenchService) -> None:
    integrity = workbench.require_integrity()
    assert integrity.status.value == "HEALTHY"
    assert integrity.broken_strategy_refs == 0
    assert integrity.broken_evidence_refs == 0
    assert integrity.broken_artifact_refs == 0
    assert integrity.broken_lineage_refs == 0
    assert integrity.cycle_count == 0
    assert integrity.duplicate_ids == 0
    assert integrity.hash_mismatches == 0


def test_service_has_no_public_mutation_surface() -> None:
    public_methods = {
        name
        for name, value in inspect.getmembers(
            ResearchWorkbenchService, predicate=inspect.isfunction
        )
        if not name.startswith("_")
    }
    forbidden_prefixes = (
        "add",
        "append",
        "create",
        "delete",
        "mutate",
        "record",
        "register",
        "transition",
        "update",
        "write",
    )
    assert not {
        name for name in public_methods if name.startswith(forbidden_prefixes)
    }


def test_error_model_is_stable(workbench: ResearchWorkbenchService) -> None:
    with pytest.raises(ResearchFamilyNotFound):
        workbench.get_family_detail("Z")
    with pytest.raises(StrategyNotFound):
        workbench.get_strategy_detail("MISSING")
    with pytest.raises(EvidenceNotFound):
        workbench.get_evidence_detail("MISSING")
    with pytest.raises(ArtifactNotFound):
        workbench.get_artifact_summary("MISSING")
    with pytest.raises(LineageNodeNotFound):
        workbench.trace_research_lineage("MISSING")


def test_foundation_artifacts_still_match_the_frozen_manifest() -> None:
    manifest = __import__("json").loads(
        (
            PLATFORM_ROOT
            / "manifests/intersignal_platform_foundation_manifest_v1.json"
        ).read_text(encoding="utf-8")
    )
    expected = manifest["proof_existing_research_unchanged"]["file_hashes_after"]
    assert manifest["platform_foundation_hash"] == PLATFORM_FOUNDATION_HASH
    assert manifest["platform_charter_hash"] == PLATFORM_CHARTER_HASH
    assert manifest["counts"]["production_candidate_count"] == 0
    assert manifest["counts"]["validated_production_strategy_count"] == 0
    assert all((ROOT / path).is_file() for path in FOUNDATION_PATHS)
    assert all(file_sha256(ROOT / path) == digest for path, digest in expected.items())


def test_generated_workbench_artifacts_and_manifest() -> None:
    import json

    snapshot_path = PLATFORM_ROOT / "workbench/research_workbench_snapshot_v1.json"
    integrity_path = PLATFORM_ROOT / "workbench/research_workbench_integrity_v1.json"
    manifest_path = (
        PLATFORM_ROOT
        / "manifests/intersignal_research_workbench_backend_manifest_v1.json"
    )
    assert snapshot_path.is_file()
    assert integrity_path.is_file()
    assert manifest_path.is_file()
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    integrity = json.loads(integrity_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert snapshot["snapshot_hash"] == canonical_hash(
        {key: value for key, value in snapshot.items() if key != "snapshot_hash"}
    )
    assert integrity["integrity"]["status"] == "HEALTHY"
    assert manifest["manifest_version"] == MANIFEST_VERSION
    assert manifest["research_workbench_backend_hash"] == canonical_hash(
        {
            key: value
            for key, value in manifest.items()
            if key != "research_workbench_backend_hash"
        }
    )
    assert manifest["foundation_artifacts_unchanged"]["unchanged"] is True
    assert manifest["counts"]["families"] == 7
    assert manifest["counts"]["production_candidate_count"] == 0


def test_no_ui_broker_network_research_or_execution_path() -> None:
    from app.research_workbench import builder, service

    trees = [ast.parse(inspect.getsource(module)) for module in (service, builder)]
    imported_roots = {
        alias.name.split(".")[0]
        for tree in trees
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        (node.module or "").split(".")[0]
        for tree in trees
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for tree in trees
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Attribute, ast.Name))
    }
    forbidden_calls = {
        "place_order(",
        "submit_order(",
        "connect_broker(",
        "execute_one_shot_validation(",
        "execute_post_outcome_remediated_validation(",
        "create_client(",
    }
    forbidden_calls = {item.removesuffix("(") for item in forbidden_calls}
    assert not imported_roots & {"requests", "httpx", "supabase"}
    assert not called & forbidden_calls
