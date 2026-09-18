from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.routes.portfolio import get_portfolio_application_service
from app.home.sources import PortfolioOSHomeSource
from app.main import create_app
from app.platform.hashing import file_sha256
from app.portfolio_api.models import INTERSIGNAL_PORTFOLIO_OS_V1
from app.portfolio_api.service import PortfolioApplicationService
from app.portfolio_os.repositories import (
    InMemoryPortfolioOSRepository,
    JsonFilePortfolioOSRepository,
)
from app.portfolio_os.service import PortfolioOSService, select_primary_portfolio


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLATFORM_ROOT = PROJECT_ROOT / "data/platform"
FIXED_TIME = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)


def _portfolio_os(repository=None) -> PortfolioOSService:
    source = repository or JsonFilePortfolioOSRepository(PLATFORM_ROOT / "portfolio_os")
    return PortfolioOSService.from_repository(source)


def _service(portfolio_os=None) -> PortfolioApplicationService:
    return PortfolioApplicationService(
        portfolio_os or _portfolio_os(),
        clock=lambda: FIXED_TIME,
    )


def _client(service: PortfolioApplicationService | None = None) -> TestClient:
    app = create_app()
    if service is not None:
        app.dependency_overrides[get_portfolio_application_service] = lambda: service
    return TestClient(app)


def test_overview_is_versioned_backend_backed_and_synthetic() -> None:
    response = _client(_service()).get("/api/portfolio/overview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == INTERSIGNAL_PORTFOLIO_OS_V1
    assert payload["generated_at"] == "2026-09-18T12:00:00Z"
    assert payload["status"] == "AVAILABLE"
    assert payload["has_portfolio"] is True
    assert payload["portfolio"]["portfolio_id"] == (
        "PORT-MANUAL-INVESTMENT-SYNTHETIC-001"
    )
    assert payload["portfolio"]["source_type"] == "SYNTHETIC"
    assert len(payload["portfolios"]) == 2
    assert payload["meta"]["read_only"] is True
    assert payload["meta"]["broker_integration"] == "NOT_IMPLEMENTED"


def test_overview_matches_portfolio_os_without_recalculation() -> None:
    portfolio_os = _portfolio_os()
    selected = select_primary_portfolio(portfolio_os.list_portfolios())
    valuation = portfolio_os.get_valuation(selected.portfolio_id)
    exposure = portfolio_os.get_exposure(selected.portfolio_id)
    risk = portfolio_os.get_risk(selected.portfolio_id)
    comparison = portfolio_os.get_benchmark_comparison(selected.portfolio_id)
    holdings = portfolio_os.get_holdings(selected.portfolio_id)
    assert valuation and exposure and risk and comparison

    payload = _client(_service(portfolio_os)).get("/api/portfolio/overview").json()
    summary = payload["summary"]
    assert summary["portfolio_value"] == str(valuation.net_liquidation_value)
    assert summary["cash"] == str(valuation.cash)
    assert summary["invested"] == str(valuation.gross_market_value)
    assert summary["realized_pnl"] == str(valuation.realized_pnl)
    assert summary["unrealized_pnl"] == str(valuation.unrealized_pnl)
    assert summary["invested_pct"] == str(exposure.gross_exposure)
    assert payload["benchmark"]["portfolio_return"] == str(
        comparison.portfolio_return
    )
    assert payload["benchmark"]["benchmark_return"] == str(
        comparison.benchmark_return
    )
    assert payload["benchmark"]["difference"] == str(comparison.active_return)
    assert payload["concentration"]["top_holding_weight"] == str(
        risk.top_1_weight
    )
    by_id = {row["holding_id"]: row for row in payload["holdings"]}
    for holding in holdings:
        row = by_id[holding.holding_id]
        assert row["market_value"] == str(holding.market_value)
        assert row["cost_basis"] == str(holding.cost_basis)
        assert row["unrealized_pnl"] == str(holding.unrealized_pnl)
        assert row["weight"] == str(
            exposure.security_concentration[holding.security_id]
        )


def test_home_and_portfolio_use_the_same_primary_value() -> None:
    portfolio_os = _portfolio_os()
    home = PortfolioOSHomeSource(portfolio_os).read()
    overview = _service(portfolio_os).get_overview()
    assert overview.portfolio is not None
    assert overview.summary is not None
    assert home.portfolio_id == overview.portfolio.portfolio_id
    assert home.valuation == overview.summary.portfolio_value
    assert home.cash == overview.summary.cash
    assert home.invested_value == overview.summary.invested


def test_holdings_include_safe_security_metadata_and_fifo_lots() -> None:
    payload = _client(_service()).get("/api/portfolio/holdings").json()
    assert payload["total_count"] == 1
    holding = payload["items"][0]
    assert holding["name"] == "Synthetic Mutual Fund One"
    assert holding["symbol"] == "SYN-MF-001"
    assert holding["sector"] == "Diversified"
    assert holding["lots"][0]["realized_status"] == "PARTIALLY_REALIZED"
    assert set(holding["lots"][0]) == {
        "lot_id",
        "acquisition_date",
        "quantity",
        "entry_price",
        "cost_basis",
        "remaining_quantity",
        "realized_status",
    }


def test_activity_and_performance_are_canonical_read_models() -> None:
    client = _client(_service())
    activity = client.get("/api/portfolio/activity").json()
    types = {row["activity_type"] for row in activity["items"]}
    assert {"BUY", "SELL", "DEPOSIT"} <= types
    assert "PORTFOLIO_CREATED" in types
    sell = next(row for row in activity["items"] if row["activity_type"] == "SELL")
    assert sell["amount"] == "2398"
    assert sell["reference"] == "TXN-MANUAL-SELL-001"

    performance = client.get("/api/portfolio/performance").json()["performance"]
    assert performance["realized_pnl"] == "397.00"
    assert performance["unrealized_pnl"] == "1996"
    assert len(performance["points"]) == 2
    assert performance["chart_available"] is False
    assert performance["benchmark"]["name"] == "Synthetic Manual Investment Index"


def test_portfolio_selector_reads_each_first_class_portfolio() -> None:
    response = _client(_service()).get(
        "/api/portfolio/overview",
        params={"portfolio_id": "PORT-RESEARCH-SYNTHETIC-001"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["portfolio"]["portfolio_type"] == "RESEARCH"
    assert payload["summary"]["portfolio_value"] == "100980"
    assert payload["holdings"][0]["symbol"] == "SYN-EQ-001"


def test_empty_portfolio_is_an_available_honest_state() -> None:
    empty = _service(_portfolio_os(InMemoryPortfolioOSRepository()))
    for path in (
        "/api/portfolio/overview",
        "/api/portfolio/holdings",
        "/api/portfolio/activity",
        "/api/portfolio/performance",
    ):
        response = _client(empty).get(path)
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "AVAILABLE"
        assert payload["has_portfolio"] is False
        assert payload["reason"] == "NO_PORTFOLIO_CONFIGURED"
        assert payload["portfolio"] is None


class _PartiallyFailingPortfolioOS:
    def __init__(self, delegate: PortfolioOSService) -> None:
        self._delegate = delegate

    def get_performance(self, portfolio_id: str):
        raise RuntimeError("private performance failure")

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)


def test_overview_is_failure_isolated_and_sanitized() -> None:
    service = _service(_PartiallyFailingPortfolioOS(_portfolio_os()))
    response = _client(service).get("/api/portfolio/overview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "PARTIAL"
    assert payload["holdings"]
    assert payload["allocation"]
    assert payload["performance"] is None
    assert payload["meta"]["unavailable_sections"] == ["performance"]
    assert "private performance failure" not in response.text


def test_unknown_portfolio_is_a_sanitized_404() -> None:
    response = _client(_service()).get(
        "/api/portfolio/overview", params={"portfolio_id": "UNKNOWN"}
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Portfolio not found."}


def test_all_routes_are_no_store_get_only_and_documented() -> None:
    client = _client(_service())
    paths = (
        "/api/portfolio/overview",
        "/api/portfolio/holdings",
        "/api/portfolio/activity",
        "/api/portfolio/performance",
    )
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["version"] == INTERSIGNAL_PORTFOLIO_OS_V1
        for method in (client.post, client.put, client.patch, client.delete):
            assert method(path).status_code == 405
    assert set(paths) <= set(client.get("/openapi.json").json()["paths"])


def test_http_reads_do_not_modify_portfolio_os_files() -> None:
    root = PLATFORM_ROOT / "portfolio_os"
    files = sorted(path for path in root.rglob("*") if path.is_file())
    before = {path: file_sha256(path) for path in files}
    client = _client(_service())
    for path in (
        "/api/portfolio/overview",
        "/api/portfolio/holdings",
        "/api/portfolio/activity",
        "/api/portfolio/performance",
    ):
        assert client.get(path).status_code == 200
    after = sorted(path for path in root.rglob("*") if path.is_file())
    assert after == files
    assert {path: file_sha256(path) for path in after} == before


def test_response_does_not_expose_secrets_or_private_paths() -> None:
    rendered = _client(_service()).get("/api/portfolio/overview").text.lower()
    forbidden = (
        "api_key",
        "access_token",
        "broker_secret",
        "client_secret",
        "provider_account_reference",
        "c:\\users\\",
        "/users/",
        ".env",
    )
    assert not any(value in rendered for value in forbidden)
