from fastapi import APIRouter, Depends, Request, Response

from app.market_api.factory import build_market_intelligence_service
from app.market_api.models import MarketSnapshot
from app.market_api.service import MarketIntelligenceService


router = APIRouter(prefix="/market", tags=["market"])


def get_market_intelligence_service(request: Request) -> MarketIntelligenceService:
    return build_market_intelligence_service(request.app.state.settings)


@router.get("/snapshot", response_model=MarketSnapshot)
def market_snapshot(
    response: Response,
    service: MarketIntelligenceService = Depends(get_market_intelligence_service),
) -> MarketSnapshot:
    response.headers["Cache-Control"] = "no-store"
    return service.get_snapshot()


__all__ = ("get_market_intelligence_service", "router")
