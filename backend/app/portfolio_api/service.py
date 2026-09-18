from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import TypeVar

from app.portfolio_api.models import (
    ActivityView,
    AllocationView,
    BenchmarkView,
    ConcentrationView,
    ExposureItemView,
    HoldingView,
    LotView,
    PerformancePointView,
    PerformanceView,
    PortfolioActivityResponse,
    PortfolioAvailability,
    PortfolioHoldingsResponse,
    PortfolioMeta,
    PortfolioOptionView,
    PortfolioOverviewResponse,
    PortfolioPerformanceResponse,
    PortfolioSummaryView,
    PortfolioView,
)
from app.portfolio_os.errors import PortfolioNotFound
from app.portfolio_os.models import Portfolio, PortfolioEventType
from app.portfolio_os.service import PortfolioOSService, select_primary_portfolio


T = TypeVar("T")


class PortfolioApplicationService:
    """Failure-isolated, read-only projection of canonical Portfolio OS records."""

    def __init__(
        self,
        portfolio_os: PortfolioOSService,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._portfolio_os = portfolio_os
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _generated_at(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Portfolio API clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _source_type(portfolio: Portfolio) -> str:
        return "SYNTHETIC" if portfolio.metadata.get("synthetic") is True else "PLATFORM"

    def _option(self, portfolio: Portfolio) -> PortfolioOptionView:
        return PortfolioOptionView(
            portfolio_id=portfolio.portfolio_id,
            name=portfolio.name,
            portfolio_type=portfolio.portfolio_type.value,
            source_type=self._source_type(portfolio),
        )

    def _portfolio(self, portfolio: Portfolio) -> PortfolioView:
        return PortfolioView(
            **self._option(portfolio).model_dump(),
            currency=portfolio.base_currency,
            status=portfolio.status.value,
        )

    def _selection(
        self, portfolio_id: str | None
    ) -> tuple[list[Portfolio], Portfolio | None]:
        portfolios = self._portfolio_os.list_portfolios()
        if not portfolios:
            return portfolios, None
        if portfolio_id is None:
            return portfolios, select_primary_portfolio(portfolios)
        return portfolios, self._portfolio_os.get_portfolio(portfolio_id)

    @staticmethod
    def _lot_status(quantity: Decimal, remaining: Decimal) -> str:
        if remaining == 0:
            return "FULLY_REALIZED"
        if remaining < quantity:
            return "PARTIALLY_REALIZED"
        return "OPEN"

    def _holdings(self, portfolio_id: str) -> tuple[HoldingView, ...]:
        exposure = self._portfolio_os.get_exposure(portfolio_id)
        weights = exposure.security_concentration if exposure else {}
        lots_by_holding: dict[str, list[LotView]] = {}
        for lot in self._portfolio_os.get_lots(portfolio_id):
            lots_by_holding.setdefault(lot.holding_id, []).append(
                LotView(
                    lot_id=lot.lot_id,
                    acquisition_date=lot.entry_date,
                    quantity=lot.quantity,
                    entry_price=lot.entry_price,
                    cost_basis=lot.cost_basis,
                    remaining_quantity=lot.remaining_quantity,
                    realized_status=self._lot_status(lot.quantity, lot.remaining_quantity),
                )
            )
        rows: list[HoldingView] = []
        for holding in self._portfolio_os.get_holdings(portfolio_id):
            security = self._portfolio_os.get_security(holding.security_id)
            sector = security.metadata.get("sector") or holding.metadata.get("sector")
            industry = security.metadata.get("industry") or holding.metadata.get("industry")
            rows.append(
                HoldingView(
                    holding_id=holding.holding_id,
                    security_id=holding.security_id,
                    symbol=security.symbol,
                    name=security.name,
                    instrument_type=security.instrument_type.value,
                    quantity=holding.quantity,
                    average_cost=holding.average_cost,
                    current_price=holding.current_price,
                    market_value=holding.market_value,
                    cost_basis=holding.cost_basis,
                    weight=weights.get(holding.security_id),
                    unrealized_pnl=holding.unrealized_pnl,
                    unrealized_pnl_pct=holding.unrealized_pnl_pct,
                    sector=str(sector) if sector else None,
                    industry=str(industry) if industry else None,
                    currency=holding.currency,
                    as_of=holding.as_of,
                    lots=tuple(lots_by_holding.get(holding.holding_id, ())),
                )
            )
        return tuple(rows)

    def _summary(self, portfolio_id: str) -> PortfolioSummaryView | None:
        valuation = self._portfolio_os.get_valuation(portfolio_id)
        if valuation is None:
            return None
        exposure = self._portfolio_os.get_exposure(portfolio_id)
        return PortfolioSummaryView(
            portfolio_value=valuation.net_liquidation_value,
            invested=valuation.gross_market_value,
            cash=valuation.cash,
            invested_pct=exposure.gross_exposure if exposure else None,
            cash_pct=exposure.cash_pct if exposure else None,
            cost_basis=valuation.cost_basis,
            realized_pnl=valuation.realized_pnl,
            unrealized_pnl=valuation.unrealized_pnl,
            total_pnl=valuation.total_pnl,
            valuation_timestamp=valuation.as_of,
        )

    def _allocation(self, portfolio_id: str) -> AllocationView | None:
        exposure = self._portfolio_os.get_exposure(portfolio_id)
        if exposure is None:
            return None
        sectors = tuple(
            ExposureItemView(label=label, weight=weight)
            for label, weight in sorted(
                exposure.sector_exposure.items(), key=lambda item: (-item[1], item[0])
            )
        )
        return AllocationView(
            invested_pct=exposure.gross_exposure,
            cash_pct=exposure.cash_pct,
            gross_exposure=exposure.gross_exposure,
            net_exposure=exposure.net_exposure,
            sectors=sectors,
        )

    def _concentration(self, portfolio_id: str) -> ConcentrationView | None:
        risk = self._portfolio_os.get_risk(portfolio_id)
        exposure = self._portfolio_os.get_exposure(portfolio_id)
        holdings = self._portfolio_os.get_holdings(portfolio_id)
        if risk is None and exposure is None:
            return None
        sector_weights = exposure.sector_exposure.values() if exposure else ()
        return ConcentrationView(
            holding_count=len(holdings),
            top_holding_weight=risk.top_1_weight if risk else None,
            top_sector_weight=max(sector_weights, default=None),
            top_five_weight=risk.top_5_weight if risk else None,
            risk_flags=tuple(flag.value for flag in (risk.risk_flags if risk else ())),
        )

    def _benchmark(self, portfolio_id: str) -> BenchmarkView | None:
        comparison = self._portfolio_os.get_benchmark_comparison(portfolio_id)
        if comparison is None:
            return None
        benchmark = self._portfolio_os.get_benchmark(comparison.benchmark_id)
        return BenchmarkView(
            benchmark_id=benchmark.benchmark_id,
            name=benchmark.name,
            portfolio_return=comparison.portfolio_return,
            benchmark_return=comparison.benchmark_return,
            difference=comparison.active_return,
            period_start=comparison.period_start,
            period_end=comparison.period_end,
        )

    def _performance(self, portfolio_id: str) -> PerformanceView:
        valuation = self._portfolio_os.get_valuation(portfolio_id)
        points = tuple(
            PerformancePointView(
                date=row.date,
                equity=row.equity,
                cash=row.cash,
                invested_value=row.invested_value,
                daily_return=row.daily_return,
                cumulative_return=row.cumulative_return,
                benchmark_value=row.benchmark_value,
            )
            for row in self._portfolio_os.get_performance(portfolio_id)
        )
        return PerformanceView(
            realized_pnl=valuation.realized_pnl if valuation else None,
            unrealized_pnl=valuation.unrealized_pnl if valuation else None,
            total_pnl=valuation.total_pnl if valuation else None,
            benchmark=self._benchmark(portfolio_id),
            points=points,
            chart_available=len(points) >= 3,
        )

    def _activity(self, portfolio_id: str) -> tuple[ActivityView, ...]:
        rows: list[ActivityView] = []
        events = self._portfolio_os.get_portfolio_events(portfolio_id)
        transaction_timestamps = {
            event.entity_id: event.timestamp.isoformat().replace("+00:00", "Z")
            for event in events
            if event.event_type is PortfolioEventType.TRANSACTION_RECORDED
        }
        for transaction in self._portfolio_os.get_transactions(portfolio_id):
            security = None
            if transaction.security_id:
                security = self._portfolio_os.get_security(transaction.security_id)
            rows.append(
                ActivityView(
                    activity_id=transaction.transaction_id,
                    occurred_at=transaction_timestamps.get(
                        transaction.transaction_id, transaction.trade_date.isoformat()
                    ),
                    activity_type=transaction.transaction_type.value,
                    security=security.symbol if security else None,
                    quantity=transaction.quantity if transaction.security_id else None,
                    amount=transaction.net_amount,
                    currency=transaction.currency,
                    reference=transaction.transaction_id,
                )
            )
        visible_events = {
            PortfolioEventType.PORTFOLIO_CREATED,
            PortfolioEventType.HOLDING_REBUILT,
            PortfolioEventType.BENCHMARK_LINKED,
        }
        for event in events:
            if event.event_type not in visible_events:
                continue
            rows.append(
                ActivityView(
                    activity_id=event.event_id,
                    occurred_at=event.timestamp.isoformat().replace("+00:00", "Z"),
                    activity_type=event.event_type.value,
                    reference=event.event_id,
                    description=event.reason,
                )
            )
        return tuple(
            sorted(rows, key=lambda row: (row.occurred_at, row.activity_id), reverse=True)
        )

    def _base(self, portfolio_id: str | None):
        portfolios, portfolio = self._selection(portfolio_id)
        return portfolios, portfolio, {
            "generated_at": self._generated_at(),
            "has_portfolio": portfolio is not None,
            "portfolio": self._portfolio(portfolio) if portfolio else None,
            "portfolios": tuple(self._option(row) for row in portfolios),
        }

    @staticmethod
    def _meta(unavailable: list[str]) -> PortfolioMeta:
        return PortfolioMeta(unavailable_sections=tuple(dict.fromkeys(unavailable)))

    def get_overview(self, portfolio_id: str | None = None) -> PortfolioOverviewResponse:
        _, portfolio, base = self._base(portfolio_id)
        if portfolio is None:
            return PortfolioOverviewResponse(
                **base,
                status=PortfolioAvailability.AVAILABLE,
                reason="NO_PORTFOLIO_CONFIGURED",
                meta=self._meta([]),
            )
        unavailable: list[str] = []

        def read(name: str, operation: Callable[[], T], fallback: T) -> T:
            try:
                return operation()
            except Exception:
                unavailable.append(name)
                return fallback

        pid = portfolio.portfolio_id
        summary = read("summary", lambda: self._summary(pid), None)
        holdings = read("holdings", lambda: self._holdings(pid), ())
        allocation = read("allocation", lambda: self._allocation(pid), None)
        concentration = read("concentration", lambda: self._concentration(pid), None)
        benchmark = read("benchmark", lambda: self._benchmark(pid), None)
        performance = read("performance", lambda: self._performance(pid), None)
        activity = read("activity", lambda: self._activity(pid), ())
        return PortfolioOverviewResponse(
            **base,
            status=PortfolioAvailability.PARTIAL if unavailable else PortfolioAvailability.AVAILABLE,
            reason="PORTFOLIO_SECTIONS_UNAVAILABLE" if unavailable else None,
            summary=summary,
            holdings=holdings,
            allocation=allocation,
            concentration=concentration,
            benchmark=benchmark,
            performance=performance,
            recent_activity=activity[:6],
            meta=self._meta(unavailable),
        )

    def get_holdings(self, portfolio_id: str | None = None) -> PortfolioHoldingsResponse:
        _, portfolio, base = self._base(portfolio_id)
        if portfolio is None:
            return PortfolioHoldingsResponse(
                **base,
                status=PortfolioAvailability.AVAILABLE,
                reason="NO_PORTFOLIO_CONFIGURED",
                total_count=0,
                meta=self._meta([]),
            )
        items = self._holdings(portfolio.portfolio_id)
        return PortfolioHoldingsResponse(
            **base,
            status=PortfolioAvailability.AVAILABLE,
            items=items,
            total_count=len(items),
            meta=self._meta([]),
        )

    def get_activity(self, portfolio_id: str | None = None) -> PortfolioActivityResponse:
        _, portfolio, base = self._base(portfolio_id)
        if portfolio is None:
            return PortfolioActivityResponse(
                **base,
                status=PortfolioAvailability.AVAILABLE,
                reason="NO_PORTFOLIO_CONFIGURED",
                total_count=0,
                meta=self._meta([]),
            )
        items = self._activity(portfolio.portfolio_id)
        return PortfolioActivityResponse(
            **base,
            status=PortfolioAvailability.AVAILABLE,
            items=items,
            total_count=len(items),
            meta=self._meta([]),
        )

    def get_performance(self, portfolio_id: str | None = None) -> PortfolioPerformanceResponse:
        _, portfolio, base = self._base(portfolio_id)
        if portfolio is None:
            return PortfolioPerformanceResponse(
                **base,
                status=PortfolioAvailability.AVAILABLE,
                reason="NO_PORTFOLIO_CONFIGURED",
                meta=self._meta([]),
            )
        return PortfolioPerformanceResponse(
            **base,
            status=PortfolioAvailability.AVAILABLE,
            performance=self._performance(portfolio.portfolio_id),
            meta=self._meta([]),
        )


__all__ = ("PortfolioApplicationService", "PortfolioNotFound")
