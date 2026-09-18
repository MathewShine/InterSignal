from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.research_api.factory import build_research_application_service
from app.research_api.models import (
    ResearchBlockedResponse,
    ResearchEvidenceDetailResponse,
    ResearchEvidenceResponse,
    ResearchFamiliesResponse,
    ResearchFamilyDetailResponse,
    ResearchOverviewResponse,
    ResearchTimelineResponse,
    ResearchValidationResponse,
)
from app.research_api.service import ResearchApplicationService
from app.research_workbench.errors import EvidenceNotFound, ResearchFamilyNotFound


router = APIRouter(prefix="/research", tags=["research"])


def get_research_application_service(request: Request) -> ResearchApplicationService:
    return build_research_application_service(request.app.state.settings.home_data_root)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get("/overview", response_model=ResearchOverviewResponse)
def research_overview(
    response: Response,
    service: ResearchApplicationService = Depends(get_research_application_service),
) -> ResearchOverviewResponse:
    _no_store(response)
    return service.get_overview()


@router.get("/families", response_model=ResearchFamiliesResponse)
def research_families(
    response: Response,
    service: ResearchApplicationService = Depends(get_research_application_service),
) -> ResearchFamiliesResponse:
    _no_store(response)
    return service.get_families()


@router.get("/families/{family_id}", response_model=ResearchFamilyDetailResponse)
def research_family_detail(
    family_id: str,
    response: Response,
    service: ResearchApplicationService = Depends(get_research_application_service),
) -> ResearchFamilyDetailResponse:
    _no_store(response)
    try:
        return service.get_family(family_id)
    except ResearchFamilyNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research family not found.",
        ) from error


@router.get("/evidence", response_model=ResearchEvidenceResponse)
def research_evidence(
    response: Response,
    service: ResearchApplicationService = Depends(get_research_application_service),
) -> ResearchEvidenceResponse:
    _no_store(response)
    return service.get_evidence()


@router.get("/evidence/{evidence_id}", response_model=ResearchEvidenceDetailResponse)
def research_evidence_detail(
    evidence_id: str,
    response: Response,
    service: ResearchApplicationService = Depends(get_research_application_service),
) -> ResearchEvidenceDetailResponse:
    _no_store(response)
    try:
        return service.get_evidence_detail(evidence_id)
    except EvidenceNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research evidence not found.",
        ) from error


@router.get("/validation", response_model=ResearchValidationResponse)
def research_validation(
    response: Response,
    service: ResearchApplicationService = Depends(get_research_application_service),
) -> ResearchValidationResponse:
    _no_store(response)
    return service.get_validation()


@router.get("/blocked", response_model=ResearchBlockedResponse)
def research_blocked(
    response: Response,
    service: ResearchApplicationService = Depends(get_research_application_service),
) -> ResearchBlockedResponse:
    _no_store(response)
    return service.get_blocked()


@router.get("/timeline", response_model=ResearchTimelineResponse)
def research_timeline(
    response: Response,
    service: ResearchApplicationService = Depends(get_research_application_service),
) -> ResearchTimelineResponse:
    _no_store(response)
    return service.get_timeline()


__all__ = ("get_research_application_service", "router")
