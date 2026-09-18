from fastapi import APIRouter, Depends, Request, Response

from app.governance_api.factory import build_governance_application_service
from app.governance_api.models import (
    GovernanceAuditResponse,
    GovernanceAuthorizationsResponse,
    GovernanceOverviewResponse,
    GovernancePoliciesResponse,
    GovernanceReadinessResponse,
)
from app.governance_api.service import GovernanceApplicationService


router = APIRouter(prefix="/governance", tags=["governance"])


def get_governance_application_service(request: Request) -> GovernanceApplicationService:
    return build_governance_application_service(request.app.state.settings.home_data_root)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get("/overview", response_model=GovernanceOverviewResponse)
def governance_overview(response: Response, service: GovernanceApplicationService = Depends(get_governance_application_service)) -> GovernanceOverviewResponse:
    _no_store(response)
    return service.get_overview()


@router.get("/readiness", response_model=GovernanceReadinessResponse)
def governance_readiness(response: Response, service: GovernanceApplicationService = Depends(get_governance_application_service)) -> GovernanceReadinessResponse:
    _no_store(response)
    return service.get_readiness()


@router.get("/policies", response_model=GovernancePoliciesResponse)
def governance_policies(response: Response, service: GovernanceApplicationService = Depends(get_governance_application_service)) -> GovernancePoliciesResponse:
    _no_store(response)
    return service.get_policies()


@router.get("/authorizations", response_model=GovernanceAuthorizationsResponse)
def governance_authorizations(response: Response, service: GovernanceApplicationService = Depends(get_governance_application_service)) -> GovernanceAuthorizationsResponse:
    _no_store(response)
    return service.get_authorizations()


@router.get("/audit", response_model=GovernanceAuditResponse)
def governance_audit(response: Response, service: GovernanceApplicationService = Depends(get_governance_application_service)) -> GovernanceAuditResponse:
    _no_store(response)
    return service.get_audit()


__all__ = ("get_governance_application_service", "router")
