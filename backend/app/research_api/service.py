from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import TypeVar

from app.research_api.models import (
    ArtifactView,
    BlockedResearchView,
    EvidenceCountsView,
    EvidenceDetailView,
    EvidenceView,
    FamilyView,
    LineageEdgeView,
    LineageNodeView,
    LineageView,
    NarrativeSectionView,
    ProgrammeView,
    ResearchAvailability,
    ResearchBlockedResponse,
    ResearchEvidenceDetailResponse,
    ResearchEvidenceResponse,
    ResearchFamiliesResponse,
    ResearchFamilyDetailResponse,
    ResearchMeta,
    ResearchOverviewResponse,
    ResearchTimelineResponse,
    ResearchValidationResponse,
    TimelineEventView,
    ValidationRecordView,
)
from app.research_workbench.models import (
    BlockedResearchSummary,
    EvidenceSummary,
    ResearchArtifactSummary,
    ResearchEvidenceDetail,
    ResearchFamilySummary,
    ResearchProgrammeSummary,
    ResearchTimelineEvent,
)
from app.research_workbench.service import ResearchWorkbenchService


T = TypeVar("T")


_FAMILY_PRESENTATION: dict[str, dict[str, object]] = {
    "A": {
        "setup": "Medium-term cross-sectional momentum",
        "stage": "Closed",
        "status_label": "Closed",
        "decision_status": "REJECTED_FOR_CURRENT_CYCLE",
        "decision_label": "Not advanced this cycle",
        "evidence_state": "Historical positive evidence; later-period evidence unsupportive",
        "validation_label": "Formal: Inconclusive · Post-remediation: Fail",
        "findings": (
            "Formal validation remains INCONCLUSIVE because an implementation logic defect invalidated the pristine one-shot evaluation.",
            "The separate post-remediation evaluation returned FAIL with an UNSUPPORTIVE interpretation.",
            "The 2025–26 holdout is contaminated and is not fresh validation evidence.",
        ),
        "hypothesis": "A causal six-month cross-sectional momentum ranking can identify a robust quarterly portfolio after realistic implementation costs.",
        "sections": (
            ("overview", "Overview", "Strong historical development evidence did not generalize; the family is closed and not advanced for the current cycle.", "NEUTRAL"),
            ("hypothesis", "Hypothesis", "Quarterly six-month cross-sectional momentum over the point-in-time Nifty 500 universe, implemented with frozen liquidity, cost and whole-share rules.", "NEUTRAL"),
            ("development", "Development result", "Development evidence was historically strong, but development performance is not production approval.", "POSITIVE"),
            ("formal-validation", "Formal validation", "INCONCLUSIVE — an implementation logic defect invalidated the pristine one-shot evaluation. The formal result remains Inconclusive.", "CAUTION"),
            ("implementation-defect", "Implementation defect", "Causal prehistory was truncated at the validation boundary, creating false corporate-action eligibility failures in early intervals.", "NEGATIVE"),
            ("remediation", "Remediation", "The implementation defect was corrected without changing the frozen candidate parameters.", "NEUTRAL"),
            ("post-remediation", "Post-remediation evaluation", "FAIL / UNSUPPORTIVE — a separate, non-pristine post-outcome evaluation that does not replace the formal one-shot result.", "NEGATIVE"),
            ("final-decision", "Final decision", "CLOSED_NOT_ADVANCED / REJECTED_FOR_CURRENT_CYCLE. No candidate review or Strategy V2 was authorized.", "NEUTRAL"),
            ("future-model-selection", "Future-model-selection note", "2025–26 holdout contaminated. Do not present this period as fresh validation evidence in future selection work.", "CAUTION"),
        ),
    },
    "B": {
        "setup": "Relative + absolute momentum filters",
        "stage": "Closed",
        "status_label": "Closed",
        "decision_status": "PAUSED_NO_VALIDATION_CANDIDATE",
        "decision_label": "No validation candidate",
        "evidence_state": "Negative development evidence",
        "validation_label": "Not accessed",
        "findings": (
            "B001 was redundant.",
            "B002's initial strength was traced to a history-availability artifact.",
            "Post-remediation incremental evidence was sparse and weak.",
        ),
        "hypothesis": "Absolute momentum filters may add incremental evidence to the relative momentum control.",
        "sections": (
            ("overview", "Overview", "The tested relative-plus-absolute momentum construction showed no clear incremental edge.", "NEUTRAL"),
            ("b001", "B001", "Redundant: all frozen top-decile candidates already passed the positive-return rule.", "NEGATIVE"),
            ("b002", "B002", "Initial strength was primarily explained by history availability; clean remediation left sparse, weak evidence.", "NEGATIVE"),
            ("decision", "Final decision", "Closed without a validation candidate. No Strategy V2 was created.", "NEUTRAL"),
        ),
    },
    "C": {
        "setup": "Breakout continuation",
        "stage": "Paused",
        "status_label": "Reusable evidence only",
        "decision_status": "PAUSED_NO_VALIDATION_CANDIDATE",
        "decision_label": "No portfolio-ready candidate",
        "evidence_state": "Reusable signal-level evidence retained",
        "validation_label": "Not accessed",
        "findings": (
            "Pre-breakout compression <=8% improved event-level quality.",
            "Capacity and ranking implementation failed to produce a portfolio-ready candidate.",
            "EDGE-EVIDENCE-C-COMPRESSION-001 is retained evidence, not a production strategy.",
        ),
        "hypothesis": "Breakout continuation quality may improve when the preceding price range is tightly compressed.",
        "sections": (
            ("overview", "Overview", "Breakout continuation retained one reusable signal-level finding but no portfolio-ready candidate.", "POSITIVE"),
            ("evidence", "Reusable evidence", "Compression <=8% improved event-level quality in development.", "POSITIVE"),
            ("implementation", "Portfolio limitation", "Capacity and ranking implementation failed; event evidence did not translate into a viable executable portfolio.", "NEGATIVE"),
            ("decision", "Final decision", "Paused with no validation candidate. The retained evidence is not a production strategy.", "NEUTRAL"),
        ),
    },
    "D": {
        "setup": "Opening range / stocks-in-play",
        "stage": "Blocked",
        "status_label": "Blocked by data quality",
        "decision_status": "PAUSED_DATA_BLOCKED_PENDING_BETTER_INTRADAY_SOURCE",
        "decision_label": "Awaiting better intraday source",
        "evidence_state": "Data blocker",
        "validation_label": "Not accessed",
        "findings": (
            "Exact prior-20 intraday continuity reached only 77.826%.",
            "217 required symbol-session defects remain unresolved.",
            "Performance was not evaluated; this is not a strategy failure.",
        ),
        "hypothesis": "Opening-range behavior in stocks-in-play may support a causal intraday continuation study when continuity is sufficient.",
        "sections": (
            ("overview", "Overview", "Research is blocked by data quality, not by a strategy failure.", "CAUTION"),
            ("continuity", "Continuity gate", "Exact prior-20 continuity is 77.826%, below the frozen 95% threshold; 217 defects remain unresolved.", "CAUTION"),
            ("impact", "Impact", "A trustworthy formal performance evaluation cannot be run on the current intraday source.", "NEUTRAL"),
            ("resolution", "Required resolution", "Resume only with a better intraday source that meets the frozen continuity requirement.", "NEUTRAL"),
        ),
    },
    "E": {
        "setup": "Pullback / reclaim",
        "stage": "Paused",
        "status_label": "Paused",
        "decision_status": "PAUSED_NO_VALIDATION_CANDIDATE",
        "decision_label": "No validation candidate",
        "evidence_state": "Negative evidence",
        "validation_label": "Not accessed",
        "findings": (
            "The control result was negative.",
            "The SMA50 treatment was worse.",
            "Negative evidence is retained without generalizing beyond the frozen test.",
        ),
        "hypothesis": "A pullback-and-reclaim continuation structure may improve outcome quality after costs.",
        "sections": (
            ("overview", "Overview", "The pullback/reclaim control was negative and the treatment was worse.", "NEGATIVE"),
            ("control", "Control", "The executable control did not support advancement after costs.", "NEGATIVE"),
            ("treatment", "Treatment", "The tested SMA50 structure treatment underperformed the control.", "NEGATIVE"),
            ("decision", "Final decision", "PAUSED_NO_VALIDATION_CANDIDATE. Negative evidence is retained.", "NEUTRAL"),
        ),
    },
    "F": {
        "setup": "Catalyst momentum feasibility",
        "stage": "Blocked",
        "status_label": "Blocked pending authorized source",
        "decision_status": "PAUSED_PENDING_AUTHORIZED_CATALYST_SOURCE",
        "decision_label": "Awaiting source authorization",
        "evidence_state": "Source blocker; technical feasibility retained",
        "validation_label": "Not accessed",
        "findings": (
            "Technical timestamp feasibility was promising in a bounded pilot.",
            "Historical automation and licensing remain unresolved.",
            "No performance study or performance conclusion exists.",
        ),
        "hypothesis": "Causally timestamped corporate catalysts may support a later momentum study when an authorized historical source exists.",
        "sections": (
            ("overview", "Overview", "Technical timestamp feasibility is promising, but historical source authorization remains unresolved.", "CAUTION"),
            ("feasibility", "Technical feasibility", "The bounded source pilot demonstrated timestamp, linkage, identity and reproducibility feasibility.", "POSITIVE"),
            ("blocker", "Source blocker", "Historical acquisition automation and licensing are unresolved.", "CAUTION"),
            ("decision", "Current decision", "PAUSED_PENDING_AUTHORIZED_CATALYST_SOURCE. No performance claim is made.", "NEUTRAL"),
        ),
    },
    "G": {
        "setup": "Quarterly 6M momentum + Nifty 500 SMA200 gate",
        "stage": "Closed",
        "status_label": "Closed",
        "decision_status": "PAUSED_NO_VALIDATION_CANDIDATE",
        "decision_label": "No validation candidate",
        "evidence_state": "Negative overlay evidence",
        "validation_label": "Not accessed",
        "findings": (
            "Control CAGR 24.11% versus treatment CAGR 11.95%.",
            "Maximum drawdown worsened from 22.92% to 30.73%.",
            "The gate missed two large positive quarters.",
        ),
        "hypothesis": "A quarterly Nifty 500 close-above-SMA200 gate may reduce drawdown in the frozen six-month momentum portfolio.",
        "sections": (
            ("overview", "Overview", "The exact quarterly SMA200 participation gate was not supported for advancement.", "NEGATIVE"),
            ("comparison", "Control versus treatment", "Control CAGR was 24.11%; treatment CAGR was 11.95%. Drawdown worsened from 22.92% to 30.73%.", "NEGATIVE"),
            ("missed-periods", "Missed participation", "The treatment stayed in cash for two large positive control quarters.", "NEGATIVE"),
            ("decision", "Final decision", "Closed without a validation candidate; EDGE-NEGATIVE-G-SMA200-GATE-001 is retained as negative evidence.", "NEUTRAL"),
        ),
    },
}


_BLOCKED_DETAILS = {
    "D": {
        "label": "Data blocker",
        "reason": "Intraday continuity is below the required threshold (77.826%; 217 unresolved defects).",
        "impact": "Cannot perform a trustworthy formal evaluation.",
        "required": "A better intraday source meeting the frozen continuity threshold.",
        "state": "PAUSED_DATA_BLOCKED_PENDING_BETTER_INTRADAY_SOURCE",
    },
    "F": {
        "label": "Source authorization blocker",
        "reason": "Historical catalyst source authorization and licensing are unresolved.",
        "impact": "Cannot execute a robust historical catalyst study.",
        "required": "An authorized historical announcement source.",
        "state": "PAUSED_PENDING_AUTHORIZED_CATALYST_SOURCE",
    },
}


class ResearchApplicationService:
    """Read-only UI projection over the canonical Research Workbench service."""

    def __init__(
        self,
        workbench: ResearchWorkbenchService,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._workbench = workbench
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _generated_at(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _meta(*unavailable: str) -> ResearchMeta:
        return ResearchMeta(unavailable_sections=tuple(sorted(unavailable)))

    @staticmethod
    def _programme(value: ResearchProgrammeSummary) -> ProgrammeView:
        return ProgrammeView(
            status=value.strategy_research_status,
            cycle_status=value.a_to_g_cycle_status,
            validated_strategy_count=value.validated_strategy_count,
            production_candidate_count=value.production_candidate_count,
            strategy_v2_status=value.strategy_v2_status,
            family_h_status=value.family_h_status,
            paper_readiness=value.paper_readiness,
            live_readiness=value.live_readiness,
            primary_programme=value.primary_programme,
            secondary_programme=value.secondary_programme,
        )

    @staticmethod
    def _counts(value: EvidenceSummary) -> EvidenceCountsView:
        return EvidenceCountsView(
            positive=value.positive_evidence_count,
            negative=value.negative_evidence_count,
            blocked=value.blocked_research_count,
            validation=value.validation_evidence_count,
            post_outcome=value.post_outcome_evidence_count,
            data_infrastructure=value.data_infrastructure_evidence_count,
            total=value.total_count,
        )

    def _family(self, value: ResearchFamilySummary) -> FamilyView:
        view = _FAMILY_PRESENTATION[value.family_id]
        decision_status = str(view["decision_status"])
        evidence = self._workbench.list_evidence(family_id=value.family_id)
        artifacts = self._workbench.list_family_artifacts(value.family_id)
        return FamilyView(
            family_id=value.family_id,
            name=value.family_name,
            setup=str(view["setup"]),
            description=str(value.metadata.get("description") or value.family_name),
            stage=str(view["stage"]),
            current_status=value.current_status,
            current_status_label=str(view["status_label"]),
            decision_status=decision_status,
            decision_label=str(view["decision_label"]),
            evidence_state=str(view["evidence_state"]),
            validation_state=value.validation_status,
            validation_label=str(view["validation_label"]),
            blocker=value.block_reason,
            evidence_counts=ResearchApplicationService._counts(value.evidence_summary),
            latest_activity_at=value.latest_activity_at,
            production_candidate=value.production_candidate,
            key_findings=tuple(str(item) for item in view["findings"]),
            search_terms=tuple(
                sorted(
                    {
                        *(item.evidence_id for item in evidence),
                        *(item.title for item in evidence),
                        *(item.artifact_id for item in artifacts),
                        *(item.name for item in artifacts),
                    }
                )
            ),
            action_path=f"/app/research/families/{value.family_id}",
        )

    @staticmethod
    def _artifact(value: ResearchArtifactSummary) -> ArtifactView:
        return ArtifactView(
            artifact_id=value.artifact_id,
            name=value.name,
            artifact_type=value.artifact_type,
            version=value.version,
            integrity=value.immutability_status,
            created_at=value.created_at,
            lineage_node_id=value.lineage_node_id,
        )

    def _evidence(self, value: ResearchEvidenceDetail) -> EvidenceView:
        family_id = value.strategy_linkage.removeprefix("FAMILY_")
        artifacts = self._workbench.list_evidence_artifacts(value.evidence_id)
        updated_at = max(
            (item.created_at for item in artifacts),
            default=self._generated_at(),
        )
        source = ", ".join(item.name for item in artifacts) or "Platform evidence registry"
        if value.level.value == "SIGNAL_LEVEL" and value.status.value == "RESEARCH_ONLY":
            relevance = "Reusable signal evidence · not production strategy"
        elif value.classification.value in {"NEGATIVE_EVIDENCE", "POST_OUTCOME_EVIDENCE"}:
            relevance = "Decision evidence · not for production"
        elif value.classification.value in {"BLOCKED_RESEARCH", "DATA_INFRASTRUCTURE_EVIDENCE"}:
            relevance = "Research feasibility only · no performance claim"
        else:
            relevance = "Historical research only · not production approval"
        return EvidenceView(
            evidence_id=value.evidence_id,
            family_id=family_id,
            title=value.title,
            summary=value.description,
            classification=value.classification.value,
            evidence_type=value.level.value,
            status=value.status.value,
            production_relevance=relevance,
            source=source,
            updated_at=updated_at,
            artifact_ids=value.artifact_linkage,
            lineage_node_ids=value.lineage_linkage,
            limitations=value.limitations,
            action_path=f"/app/research/evidence/{value.evidence_id}",
        )

    @staticmethod
    def _blocked(value: BlockedResearchSummary) -> BlockedResearchView:
        details = _BLOCKED_DETAILS[value.family_id]
        return BlockedResearchView(
            family_id=value.family_id,
            blocker_type=value.block_type,
            blocker_label=str(details["label"]),
            reason=str(details["reason"]),
            impact=str(details["impact"]),
            required_resolution=str(details["required"]),
            status=value.status,
            current_state=str(details["state"]),
            related_evidence=value.related_evidence,
            related_artifacts=value.related_artifacts,
            action_path=f"/app/research/families/{value.family_id}",
        )

    @staticmethod
    def _timeline(value: ResearchTimelineEvent) -> TimelineEventView:
        entity_type = str(value.metadata.get("registry_entity_type", "RESEARCH"))
        entity_id = str(value.metadata.get("registry_entity_id", ""))
        evidence_id = entity_id if entity_type == "EVIDENCE_RECORD" else None
        result = {
            "REGISTERED": "Registered",
            "TRANSITIONED": "State updated",
            "DEPRECATED": "Deprecated",
            "SUPERSEDED": "Superseded",
        }.get(value.event_type, "Recorded")
        return TimelineEventView(
            event_id=value.event_id,
            occurred_at=value.timestamp,
            family_id=value.family_id,
            event=value.reason,
            category=entity_type.replace("_", " ").title(),
            result=result,
            related_artifacts=value.related_artifacts,
            related_evidence=evidence_id,
        )

    def _lineage(self, node_ids: Sequence[str]) -> LineageView:
        nodes: dict[str, LineageNodeView] = {}
        edges: dict[tuple[str, str, str], LineageEdgeView] = {}
        for node_id in sorted(set(node_ids)):
            trace = self._workbench.trace_research_lineage(node_id)
            for node in trace.nodes:
                nodes[node.node_id] = LineageNodeView(
                    node_id=node.node_id,
                    stage=node.stage.value,
                    source_system=node.source_system,
                    entity_type=node.entity_type,
                    status=node.status.value,
                )
            for edge in trace.edges:
                key = (
                    edge.parent_node_id,
                    edge.child_node_id,
                    edge.relationship_type.value,
                )
                edges[key] = LineageEdgeView(
                    parent_node_id=edge.parent_node_id,
                    child_node_id=edge.child_node_id,
                    relationship=edge.relationship_type.value,
                )
        return LineageView(
            nodes=tuple(nodes[key] for key in sorted(nodes)),
            edges=tuple(edges[key] for key in sorted(edges)),
        )

    def _validation_for_family(self, family_id: str) -> tuple[ValidationRecordView, ...]:
        family = family_id.upper()
        detail = self._workbench.get_family_detail(family)
        evidence = {item.evidence_id: item for item in detail.evidence}
        action = f"/app/research/families/{family}#validation"
        if family == "A":
            formal = evidence["EVIDENCE-A-FORMAL-VALIDATION-001"]
            post = evidence["EDGE-NEGATIVE-A-LATER-PERIOD-GENERALIZATION-001"]
            return (
                ValidationRecordView(
                    record_id=formal.evidence_id,
                    family_id="A",
                    validation_type="Formal one-shot",
                    period=formal.effective_period or "2025–26",
                    outcome="INCONCLUSIVE",
                    interpretation="Inconclusive",
                    integrity="IMPLEMENTATION_DEFECT",
                    pristine_intent=True,
                    notes="Implementation logic defect invalidated the pristine one-shot evaluation; this is not a formal fail.",
                    artifact_ids=formal.artifact_linkage,
                    action_path=action,
                ),
                ValidationRecordView(
                    record_id=post.evidence_id,
                    family_id="A",
                    validation_type="Post-remediation evaluation",
                    period=post.effective_period or "2025–26",
                    outcome="FAIL",
                    interpretation="UNSUPPORTIVE",
                    integrity="NON_PRISTINE",
                    pristine_intent=False,
                    notes="Separate post-outcome evidence; the contaminated holdout does not replace formal validation.",
                    artifact_ids=post.artifact_linkage,
                    action_path=action,
                ),
            )

        outcomes = {
            "B": ("Development remediation", "SPARSE / WEAK", "No incremental edge", "DEVELOPMENT"),
            "C": ("Development evaluation", "MIXED", "Reusable signal only", "DEVELOPMENT"),
            "D": ("Data readiness gate", "NOT_ACCESSED", "Blocked by data quality", "BLOCKED"),
            "E": ("Development evaluation", "NEGATIVE", "Control negative; treatment worse", "DEVELOPMENT"),
            "F": ("Source readiness gate", "NOT_ACCESSED", "Blocked pending authorized source", "BLOCKED"),
            "G": ("Development evaluation", "NOT_SUPPORTED", "Negative overlay evidence", "DEVELOPMENT"),
        }
        kind, outcome, interpretation, integrity = outcomes[family]
        return (
            ValidationRecordView(
                record_id=f"FAMILY-{family}-EVALUATION",
                family_id=family,
                validation_type=kind,
                period="DEVELOPMENT",
                outcome=outcome,
                interpretation=interpretation,
                integrity=integrity,
                pristine_intent=None,
                notes=str(_FAMILY_PRESENTATION[family]["findings"][0]),
                artifact_ids=tuple(item.artifact_id for item in detail.artifacts),
                action_path=action,
            ),
        )

    def get_overview(self) -> ResearchOverviewResponse:
        unavailable: list[str] = []

        def read(name: str, operation: Callable[[], T], fallback: T) -> T:
            try:
                return operation()
            except Exception:
                unavailable.append(name)
                return fallback

        programme = read("programme", self._workbench.get_programme_summary, None)
        families = read("families", self._workbench.list_research_families, ())
        evidence = read("evidence", self._workbench.list_evidence, ())
        blocked = read("blocked", self._workbench.list_blocked_research, ())
        timeline: list[ResearchTimelineEvent] = []
        try:
            for family in families:
                timeline.extend(self._workbench.get_family_timeline(family.family_id))
        except Exception:
            unavailable.append("timeline")
            timeline = []
        canonical_retained = tuple(
            item for item in evidence if item.evidence_id == "EDGE-EVIDENCE-C-COMPRESSION-001"
        )
        status = ResearchAvailability.PARTIAL if unavailable else ResearchAvailability.AVAILABLE
        return ResearchOverviewResponse(
            generated_at=self._generated_at(),
            status=status,
            reason="RESEARCH_SECTIONS_UNAVAILABLE" if unavailable else None,
            programme=self._programme(programme) if programme is not None else None,
            family_count=len(families),
            reusable_evidence_count=len(canonical_retained),
            blocked_study_count=len(blocked),
            production_ready_count=sum(item.production_candidate for item in families),
            families=tuple(self._family(item) for item in families),
            retained_evidence=tuple(self._evidence(item) for item in canonical_retained),
            blocked=tuple(self._blocked(item) for item in blocked),
            recent_activity=tuple(
                self._timeline(item)
                for item in sorted(
                    {item.event_id: item for item in timeline}.values(),
                    key=lambda row: (row.timestamp, row.event_id),
                    reverse=True,
                )[:8]
            ),
            meta=self._meta(*unavailable),
        )

    def get_families(self) -> ResearchFamiliesResponse:
        items = tuple(self._family(item) for item in self._workbench.list_research_families())
        return ResearchFamiliesResponse(
            generated_at=self._generated_at(),
            status=ResearchAvailability.AVAILABLE,
            items=items,
            total_count=len(items),
            meta=self._meta(),
        )

    def get_family(self, family_id: str) -> ResearchFamilyDetailResponse:
        detail = self._workbench.get_family_detail(family_id)
        summary = next(
            item
            for item in self._workbench.list_research_families()
            if item.family_id == detail.family_id
        )
        presentation = _FAMILY_PRESENTATION[detail.family_id]
        return ResearchFamilyDetailResponse(
            generated_at=self._generated_at(),
            status=ResearchAvailability.AVAILABLE,
            family=self._family(summary),
            hypothesis=str(presentation["hypothesis"]),
            sections=tuple(
                NarrativeSectionView(
                    section_id=section_id,
                    title=title,
                    summary=text,
                    tone=tone,
                )
                for section_id, title, text, tone in presentation["sections"]
            ),
            evidence=tuple(self._evidence(item) for item in detail.evidence),
            validation=self._validation_for_family(detail.family_id),
            timeline=tuple(self._timeline(item) for item in detail.events),
            artifacts=tuple(self._artifact(item) for item in detail.artifacts),
            lineage=self._lineage(detail.lineage_references),
            limitations=detail.known_limitations,
            meta=self._meta(),
        )

    def get_evidence(self) -> ResearchEvidenceResponse:
        items = tuple(self._evidence(item) for item in self._workbench.list_evidence())
        return ResearchEvidenceResponse(
            generated_at=self._generated_at(),
            status=ResearchAvailability.AVAILABLE,
            items=items,
            total_count=len(items),
            meta=self._meta(),
        )

    def get_evidence_detail(self, evidence_id: str) -> ResearchEvidenceDetailResponse:
        detail = self._workbench.get_evidence_detail(evidence_id)
        base = self._evidence(detail)
        artifacts = self._workbench.list_evidence_artifacts(evidence_id)
        family = base.family_id
        disposition = str(_FAMILY_PRESENTATION[family]["decision_label"])
        return ResearchEvidenceDetailResponse(
            generated_at=self._generated_at(),
            status=ResearchAvailability.AVAILABLE,
            evidence=EvidenceDetailView(
                **base.model_dump(),
                research_context=str(_FAMILY_PRESENTATION[family]["setup"]),
                current_disposition=disposition,
                effective_period=detail.effective_period,
                confidence=detail.confidence,
                supporting_artifacts=tuple(self._artifact(item) for item in artifacts),
                lineage=self._lineage(detail.lineage_linkage),
            ),
            meta=self._meta(),
        )

    def get_validation(self) -> ResearchValidationResponse:
        items = tuple(
            row
            for family in "ABCDEFG"
            for row in self._validation_for_family(family)
        )
        return ResearchValidationResponse(
            generated_at=self._generated_at(),
            status=ResearchAvailability.AVAILABLE,
            items=items,
            total_count=len(items),
            meta=self._meta(),
        )

    def get_blocked(self) -> ResearchBlockedResponse:
        items = tuple(self._blocked(item) for item in self._workbench.list_blocked_research())
        return ResearchBlockedResponse(
            generated_at=self._generated_at(),
            status=ResearchAvailability.AVAILABLE,
            items=items,
            total_count=len(items),
            meta=self._meta(),
        )

    def get_timeline(self) -> ResearchTimelineResponse:
        events: dict[str, ResearchTimelineEvent] = {}
        for family in self._workbench.list_research_families():
            for event in self._workbench.get_family_timeline(family.family_id):
                events[event.event_id] = event
        items = tuple(
            self._timeline(item)
            for item in sorted(
                events.values(),
                key=lambda row: (row.timestamp, row.event_id),
                reverse=True,
            )
        )
        return ResearchTimelineResponse(
            generated_at=self._generated_at(),
            status=ResearchAvailability.AVAILABLE,
            items=items,
            total_count=len(items),
            meta=self._meta(),
        )


__all__ = ("ResearchApplicationService",)
