from __future__ import annotations

import ast
import inspect
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.platform import (
    ArtifactRegistryRepository,
    ArtifactType,
    DuplicateIdentityError,
    EvidenceClassification,
    EvidenceLevel,
    EvidenceRecord,
    EvidenceRegistryRepository,
    EvidenceStatus,
    InMemoryPlatformRepository,
    InvalidLifecycleTransition,
    JsonFilePlatformRepository,
    LineageCycleError,
    LineageRelationship,
    LineageRepository,
    LineageStage,
    MissingReferenceError,
    PlatformRegistryService,
    ProvenanceRecord,
    RegistryEventRepository,
    StrategyLifecycle,
    StrategyRecord,
    StrategyRegistryRepository,
    build_artifact_record,
    build_lineage_edge,
    build_lineage_node,
    canonical_hash,
    deterministic_id,
    file_sha256,
    validate_transition,
)
from app.platform import seeding
from app.platform.hashing import HASH_VERSION, canonical_json
from app.platform.models import RegistryEventType


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = seeding.output_root(ROOT)
NOW = datetime(2026, 9, 16, 18, 0, tzinfo=timezone.utc)
HASH_A = "a" * 64
HASH_B = "b" * 64


def _node(key: str, *, stage: LineageStage = LineageStage.SOURCE):
    return build_lineage_node(
        stage=stage,
        entity_type="TEST_ENTITY",
        entity_key=key,
        version="V1",
        content_hash=HASH_A,
        created_at=NOW,
        source_system="OFFLINE_TEST",
    )


def _strategy(
    strategy_id: str = "TEST_STRATEGY",
    status: StrategyLifecycle = StrategyLifecycle.IDEA,
    *,
    updated_at: datetime = NOW,
    metadata: dict | None = None,
) -> StrategyRecord:
    return StrategyRecord(
        strategy_id=strategy_id,
        strategy_family="TEST",
        name="Test strategy",
        version="V1",
        description="Offline domain test record.",
        lifecycle_status=status,
        config_hash=HASH_A,
        preregistration_hash=None,
        implementation_hash=None,
        created_at=NOW,
        updated_at=updated_at,
        promotion_allowed=False,
        validation_status="NOT_ACCESSED",
        production_status="NOT_READY",
        metadata=metadata or {},
    )


def _service(repository: InMemoryPlatformRepository | JsonFilePlatformRepository):
    return PlatformRegistryService.from_repository(repository)


def _manifest() -> dict:
    return json.loads(
        (
            OUTPUT
            / "manifests/intersignal_platform_foundation_manifest_v1.json"
        ).read_text(encoding="utf-8")
    )


def test_lineage_stage_enum_is_exact_and_stable() -> None:
    assert tuple(item.value for item in LineageStage) == (
        "SOURCE",
        "RAW",
        "NORMALIZED",
        "DERIVED",
        "FEATURE",
        "CANDIDATE",
        "SIGNAL",
        "POSITION",
        "TRADE",
        "OUTCOME",
        "EVIDENCE",
    )


def test_deterministic_hashing_normalizes_keys_timestamps_and_exclusions() -> None:
    first = {"b": 2, "a": 1, "at": NOW, "volatile": "one"}
    second = {"at": NOW.astimezone(timezone(timedelta(hours=5, minutes=30))), "a": 1, "volatile": "two", "b": 2}
    assert HASH_VERSION == "INTERSIGNAL_CANONICAL_SHA256_V1"
    assert canonical_hash(first, exclude_fields=frozenset({"volatile"})) == canonical_hash(
        second, exclude_fields=frozenset({"volatile"})
    )
    assert canonical_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'
    assert deterministic_id("TEST", "A", 1) == deterministic_id("TEST", "A", 1)


def test_lineage_node_and_edge_ids_are_deterministic() -> None:
    first = _node("same")
    second = _node("same")
    child = _node("child", stage=LineageStage.EVIDENCE)
    assert first.node_id == second.node_id
    assert build_lineage_edge(
        parent_node_id=first.node_id,
        child_node_id=child.node_id,
        relationship_type=LineageRelationship.DERIVED_FROM,
        created_at=NOW,
    ).edge_id == build_lineage_edge(
        parent_node_id=first.node_id,
        child_node_id=child.node_id,
        relationship_type=LineageRelationship.DERIVED_FROM,
        created_at=NOW + timedelta(days=1),
    ).edge_id


def test_domain_validation_rejects_missing_hashes_naive_time_and_self_cycle() -> None:
    with pytest.raises(ValidationError):
        build_lineage_node(
            stage=LineageStage.SOURCE,
            entity_type="TEST",
            entity_key="missing-hash",
            version="V1",
            content_hash="",
            created_at=NOW,
            source_system="TEST",
        )
    with pytest.raises(ValidationError):
        ProvenanceRecord(
            source_name="test",
            source_type="fixture",
            source_reference="fixture://one",
            source_version="V1",
            retrieved_at=datetime(2026, 1, 1),
            license_classification="TEST_ONLY",
            raw_hash=HASH_A,
        )
    with pytest.raises(ValidationError):
        build_lineage_edge(
            parent_node_id="same",
            child_node_id="same",
            relationship_type=LineageRelationship.DERIVED_FROM,
            created_at=NOW,
        )


def test_lineage_repository_rejects_broken_duplicate_and_cyclic_edges() -> None:
    repository = InMemoryPlatformRepository()
    first = _node("first")
    second = _node("second", stage=LineageStage.DERIVED)
    third = _node("third", stage=LineageStage.EVIDENCE)
    for node in (first, second, third):
        repository.add_lineage_node(node)
    edge_1 = build_lineage_edge(
        parent_node_id=first.node_id,
        child_node_id=second.node_id,
        relationship_type=LineageRelationship.DERIVED_FROM,
        created_at=NOW,
    )
    edge_2 = build_lineage_edge(
        parent_node_id=second.node_id,
        child_node_id=third.node_id,
        relationship_type=LineageRelationship.COMPUTED_FROM,
        created_at=NOW,
    )
    repository.add_lineage_edge(edge_1)
    repository.add_lineage_edge(edge_2)
    with pytest.raises(DuplicateIdentityError):
        repository.add_lineage_edge(edge_1)
    with pytest.raises(LineageCycleError):
        repository.add_lineage_edge(
            build_lineage_edge(
                parent_node_id=third.node_id,
                child_node_id=first.node_id,
                relationship_type=LineageRelationship.SUPERSEDES,
                created_at=NOW,
            )
        )
    with pytest.raises(MissingReferenceError):
        repository.add_lineage_edge(
            build_lineage_edge(
                parent_node_id="missing",
                child_node_id=first.node_id,
                relationship_type=LineageRelationship.DERIVED_FROM,
                created_at=NOW,
            )
        )


def test_strategy_lifecycle_and_transition_policy_are_exact() -> None:
    assert tuple(item.value for item in StrategyLifecycle) == (
        "IDEA",
        "PREREGISTERED",
        "DEVELOPMENT_EVALUATED",
        "VALIDATION_CANDIDATE",
        "VALIDATION_EVALUATED",
        "PAUSED",
        "REJECTED",
        "DATA_BLOCKED",
        "SOURCE_BLOCKED",
        "PRODUCTION_CANDIDATE",
    )
    validate_transition(StrategyLifecycle.IDEA, StrategyLifecycle.PREREGISTERED)
    validate_transition(StrategyLifecycle.VALIDATION_EVALUATED, StrategyLifecycle.PAUSED)
    with pytest.raises(InvalidLifecycleTransition):
        validate_transition(
            StrategyLifecycle.IDEA, StrategyLifecycle.PRODUCTION_CANDIDATE
        )
    with pytest.raises(InvalidLifecycleTransition):
        validate_transition(StrategyLifecycle.IDEA, StrategyLifecycle.IDEA)


def test_evidence_classification_level_and_status_are_exact() -> None:
    assert {item.value for item in EvidenceClassification} == {
        "POSITIVE_EVIDENCE",
        "NEGATIVE_EVIDENCE",
        "BLOCKED_RESEARCH",
        "VALIDATION_EVIDENCE",
        "POST_OUTCOME_EVIDENCE",
        "DATA_INFRASTRUCTURE_EVIDENCE",
    }
    assert {item.value for item in EvidenceLevel} == {
        "STRATEGY_LEVEL",
        "SIGNAL_LEVEL",
        "DATA_INFRASTRUCTURE_LEVEL",
        "IMPLEMENTATION_LEVEL",
        "GOVERNANCE_LEVEL",
    }
    assert {item.value for item in EvidenceStatus} == {
        "ACTIVE",
        "HISTORICAL",
        "SUPERSEDED",
        "RESEARCH_ONLY",
        "NOT_VALIDATED",
        "BLOCKED",
    }


def test_models_are_frozen_and_repositories_expose_no_delete_semantics() -> None:
    record = _strategy()
    with pytest.raises(ValidationError):
        record.lifecycle_status = StrategyLifecycle.PAUSED
    repository = InMemoryPlatformRepository()
    service = _service(repository)
    assert not any(name.startswith("delete") for name in dir(repository))
    assert not any(name.startswith("delete") for name in dir(service))


def test_repository_interfaces_are_satisfied_by_both_implementations(
    tmp_path: Path,
) -> None:
    for repository in (
        InMemoryPlatformRepository(),
        JsonFilePlatformRepository(tmp_path / "registry"),
    ):
        assert isinstance(repository, LineageRepository)
        assert isinstance(repository, StrategyRegistryRepository)
        assert isinstance(repository, EvidenceRegistryRepository)
        assert isinstance(repository, ArtifactRegistryRepository)
        assert isinstance(repository, RegistryEventRepository)


def test_every_service_mutation_appends_an_audit_event() -> None:
    repository = InMemoryPlatformRepository()
    service = _service(repository)
    source = service.register_lineage_node(_node("source"), actor="tester", reason="test")
    artifact = service.register_artifact(
        build_artifact_record(
            artifact_type=ArtifactType.RESEARCH_ARTIFACT,
            name="Fixture",
            version="V1",
            path_or_reference="fixture://one",
            content_hash=HASH_A,
            created_at=NOW,
            lineage_node_id=source.node_id,
        ),
        actor="tester",
        reason="test",
    )
    strategy = service.register_strategy(
        _strategy(metadata={"source_artifact_ids": [artifact.artifact_id]}),
        actor="tester",
        reason="test",
    )
    evidence = EvidenceRecord(
        evidence_id="EVIDENCE-TEST-001",
        title="Test evidence",
        description="A test-only evidence record.",
        classification=EvidenceClassification.POSITIVE_EVIDENCE,
        evidence_level=EvidenceLevel.STRATEGY_LEVEL,
        status=EvidenceStatus.RESEARCH_ONLY,
        strategy_id=strategy.strategy_id,
        source_artifact_ids=(artifact.artifact_id,),
        lineage_node_ids=(source.node_id,),
        created_at=NOW,
    )
    service.register_evidence(evidence, actor="tester", reason="test")
    child = service.register_lineage_node(
        _node("child", stage=LineageStage.EVIDENCE),
        actor="tester",
        reason="test",
    )
    service.register_lineage_edge(
        build_lineage_edge(
            parent_node_id=source.node_id,
            child_node_id=child.node_id,
            relationship_type=LineageRelationship.SUPPORTED_BY,
            created_at=NOW,
        ),
        actor="tester",
        reason="test",
    )
    service.record_strategy_transition(
        strategy.strategy_id,
        StrategyLifecycle.PREREGISTERED,
        actor="tester",
        reason="test",
        created_at=NOW + timedelta(seconds=1),
    )
    assert len(repository.list_events()) == 7
    assert repository.list_events()[-1].event_type == RegistryEventType.TRANSITIONED
    assert len(service.get_strategy_history(strategy.strategy_id)) == 2


def test_broken_evidence_references_are_rejected_before_mutation() -> None:
    repository = InMemoryPlatformRepository()
    service = _service(repository)
    service.register_strategy(_strategy(), actor="tester", reason="test")
    record = EvidenceRecord(
        evidence_id="BROKEN",
        title="Broken",
        description="Missing references.",
        classification=EvidenceClassification.BLOCKED_RESEARCH,
        evidence_level=EvidenceLevel.GOVERNANCE_LEVEL,
        status=EvidenceStatus.BLOCKED,
        strategy_id="TEST_STRATEGY",
        source_artifact_ids=("missing",),
        lineage_node_ids=("missing",),
        created_at=NOW,
    )
    with pytest.raises(MissingReferenceError):
        service.register_evidence(record, actor="tester", reason="test")
    assert repository.list_evidence() == []


def test_file_repository_round_trip_preserves_append_only_history(tmp_path: Path) -> None:
    root = tmp_path / "platform"
    repository = JsonFilePlatformRepository(root)
    service = _service(repository)
    service.register_strategy(_strategy(), actor="tester", reason="test")
    service.record_strategy_transition(
        "TEST_STRATEGY",
        StrategyLifecycle.PREREGISTERED,
        actor="tester",
        reason="test",
        created_at=NOW + timedelta(seconds=1),
    )
    reloaded = JsonFilePlatformRepository(root)
    assert len(reloaded.get_strategy_history("TEST_STRATEGY")) == 2
    assert reloaded.get_strategy("TEST_STRATEGY").lifecycle_status == (
        StrategyLifecycle.PREREGISTERED
    )
    assert len(reloaded.list_events()) == 2
    with pytest.raises(DuplicateIdentityError):
        reloaded.append_event(reloaded.list_events()[0])


def test_read_service_traces_parents_and_children() -> None:
    repository = InMemoryPlatformRepository()
    service = _service(repository)
    nodes = [_node("a"), _node("b", stage=LineageStage.DERIVED), _node("c", stage=LineageStage.EVIDENCE)]
    for node in nodes:
        service.register_lineage_node(node, actor="tester", reason="test")
    for parent, child in zip(nodes, nodes[1:]):
        service.register_lineage_edge(
            build_lineage_edge(
                parent_node_id=parent.node_id,
                child_node_id=child.node_id,
                relationship_type=LineageRelationship.DERIVED_FROM,
                created_at=NOW,
            ),
            actor="tester",
            reason="test",
        )
    assert [row.node_id for row in service.get_lineage_parents(nodes[1].node_id)] == [nodes[0].node_id]
    assert {row.node_id for row in service.trace_lineage(nodes[2].node_id)} == {nodes[0].node_id, nodes[1].node_id}
    assert {row.node_id for row in service.trace_lineage(nodes[0].node_id, direction="children")} == {nodes[1].node_id, nodes[2].node_id}


def test_seeded_registry_has_exact_a_to_g_state_and_zero_production() -> None:
    repository = JsonFilePlatformRepository(OUTPUT)
    strategies = {row.strategy_id: row for row in repository.list_strategies()}
    assert set(strategies) == {f"FAMILY_{letter}" for letter in "ABCDEFG"}
    assert {key: row.lifecycle_status for key, row in strategies.items()} == {
        "FAMILY_A": StrategyLifecycle.REJECTED,
        "FAMILY_B": StrategyLifecycle.REJECTED,
        "FAMILY_C": StrategyLifecycle.PAUSED,
        "FAMILY_D": StrategyLifecycle.DATA_BLOCKED,
        "FAMILY_E": StrategyLifecycle.REJECTED,
        "FAMILY_F": StrategyLifecycle.SOURCE_BLOCKED,
        "FAMILY_G": StrategyLifecycle.REJECTED,
    }
    assert all(row.promotion_allowed is False for row in strategies.values())
    manifest = _manifest()
    assert manifest["counts"]["strategies"] == 7
    assert manifest["counts"]["evidence"] == 11
    assert manifest["counts"]["production_candidate_count"] == 0
    assert manifest["counts"]["validated_production_strategy_count"] == 0


def test_family_a_formal_and_post_outcome_evidence_remain_distinct() -> None:
    repository = JsonFilePlatformRepository(OUTPUT)
    formal = repository.get_evidence("EVIDENCE-A-FORMAL-VALIDATION-001")
    post = repository.get_evidence(
        "EDGE-NEGATIVE-A-LATER-PERIOD-GENERALIZATION-001"
    )
    assert formal is not None and post is not None
    assert formal.classification == EvidenceClassification.VALIDATION_EVIDENCE
    assert formal.metadata["formal_validation_status"] == "INCONCLUSIVE"
    assert post.classification == EvidenceClassification.POST_OUTCOME_EVIDENCE
    assert post.metadata["generalization_indication"] == "UNSUPPORTIVE"
    assert formal.source_artifact_ids != post.source_artifact_ids


def test_seed_preserves_c_d_f_and_g_evidence_without_strategy_creation() -> None:
    repository = JsonFilePlatformRepository(OUTPUT)
    c_source = repository.get_evidence("EVIDENCE-C-COMPRESSION-001")
    c_edge = repository.get_evidence("EDGE-EVIDENCE-C-COMPRESSION-001")
    d = repository.get_evidence("EVIDENCE-D-DATA-BLOCKED-001")
    f = repository.get_evidence("EVIDENCE-F-SOURCE-BLOCKED-001")
    f_data = repository.get_evidence("DATA-EVIDENCE-F-NSE-ANNOUNCEMENTS-001")
    g = repository.get_evidence("EDGE-NEGATIVE-G-SMA200-GATE-001")
    assert c_source and c_edge and d and f and f_data and g
    assert c_source.evidence_level == c_edge.evidence_level == EvidenceLevel.SIGNAL_LEVEL
    assert c_edge.status == EvidenceStatus.RESEARCH_ONLY
    assert d.status == EvidenceStatus.BLOCKED
    assert f.status == EvidenceStatus.BLOCKED
    assert f_data.classification == EvidenceClassification.DATA_INFRASTRUCTURE_EVIDENCE
    assert g.classification == EvidenceClassification.NEGATIVE_EVIDENCE
    assert repository.get_strategy("FAMILY_C").lifecycle_status == StrategyLifecycle.PAUSED


def test_current_snapshot_preserves_programme_governance() -> None:
    snapshot = json.loads(
        (OUTPUT / "registry/current_research_snapshot_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert snapshot["strategy_research_programme"] == "PAUSED"
    assert snapshot["a_to_g"] == "COMPLETE_NO_VALIDATED_STRATEGY"
    assert snapshot["strategy_v2"] == "NOT_CREATED"
    assert snapshot["family_h"] == "NOT_PLANNED"
    assert snapshot["paper"] == snapshot["live"] == "NOT_READY"
    assert snapshot["production_candidate_count"] == 0


def test_manifest_hash_reports_storage_and_security_are_complete() -> None:
    manifest = _manifest()
    assert manifest["manifest_version"] == "INTERSIGNAL_PLATFORM_FOUNDATION_MANIFEST_V1"
    assert manifest["command_version"] == "INTERSIGNAL_PLATFORM_FOUNDATION_V1"
    assert manifest["command_profile"] == "DATA_LINEAGE_STRATEGY_EVIDENCE_REGISTRY_V1"
    assert manifest["required_checkpoint"] == seeding.REQUIRED_CHECKPOINT
    assert manifest["platform_charter_hash"] == seeding.PLATFORM_CHARTER_HASH
    assert canonical_hash({key: value for key, value in manifest.items() if key != "platform_foundation_hash"}) == manifest["platform_foundation_hash"]
    assert all((ROOT / "data/reports" / name).is_file() for name in seeding.REPORT_NAMES)
    assert all((ROOT / name).is_file() for name in seeding.DOCUMENTATION_PATHS)
    assert manifest["security"] == {
        "network_required": False,
        "external_writes": 0,
        "credentials_written": 0,
        "live_signals": 0,
        "live_orders": 0,
        "broker_calls": 0,
        "migrations": 0,
        "supabase_writes": 0,
    }


def test_existing_research_artifacts_are_byte_identical() -> None:
    proof = _manifest()["proof_existing_research_unchanged"]
    assert proof["unchanged"] is True
    assert proof["file_hashes_before"] == proof["file_hashes_after"]
    assert {
        relative: file_sha256(ROOT / relative)
        for relative in proof["file_hashes_after"]
    } == proof["file_hashes_after"]


def test_platform_foundation_has_no_ui_broker_network_or_execution_path() -> None:
    modules = (seeding,)
    called: set[str] = set()
    for module in modules:
        tree = ast.parse(inspect.getsource(module))
        called.update(
            node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, (ast.Attribute, ast.Name))
        )
    assert not called & {
        "place_order",
        "submit_order",
        "connect_broker",
        "execute_one_shot_validation",
        "execute_post_outcome_remediated_validation",
        "create_client",
        "request",
        "get",
        "post",
    }
    manifest = _manifest()
    assert manifest["ui_implemented"] is False
    assert manifest["broker_connected"] is False
    assert manifest["real_time_feed_added"] is False
    assert manifest["strategy_v2_created"] is False
    assert manifest["paper_trading_started"] is False
    assert manifest["live_trading_started"] is False
