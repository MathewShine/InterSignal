from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Mapping

from app.platform.hashing import canonical_hash, deterministic_id
from app.portfolio_os.accounting import (
    FIFOAccountingEngine,
    calculate_cash_ledger,
    calculate_portfolio_metrics,
)
from app.portfolio_os.errors import (
    AccountNotFound,
    CurrencyMismatch,
    InvalidPortfolioState,
    InvalidTransaction,
    PortfolioNotFound,
    SecurityNotFound,
)
from app.portfolio_os.models import (
    BenchmarkReference,
    CashBalance,
    ExposureSnapshot,
    Holding,
    HoldingsRebuildResult,
    IntegrityStatus,
    Portfolio,
    PortfolioAccount,
    PortfolioAttribution,
    PortfolioBenchmarkComparison,
    PortfolioEvent,
    PortfolioEventType,
    PortfolioGoal,
    PortfolioMetrics,
    PortfolioOSIntegritySummary,
    PortfolioOSSnapshot,
    PortfolioPerformancePoint,
    PortfolioReconciliationResult,
    PortfolioRiskSnapshot,
    PortfolioStatus,
    PortfolioType,
    PortfolioTransaction,
    PortfolioValuation,
    RiskFlag,
    SecurityReference,
    TransactionType,
    ValuationSnapshot,
    ZERO,
)
from app.portfolio_os.repositories import (
    AccountRepository,
    BenchmarkRepository,
    HoldingRepository,
    PortfolioEventRepository,
    PortfolioRepository,
    RiskRepository,
    TransactionRepository,
    ValuationRepository,
)


TOLERANCE = Decimal("0.000001")
SNAPSHOT_VERSION = "INTERSIGNAL_PORTFOLIO_OS_SNAPSHOT_V1"


def select_primary_portfolio(portfolios: Iterable[Portfolio]) -> Portfolio:
    """Return the stable product-primary portfolio without changing portfolio math."""
    rows = list(portfolios)
    if not rows:
        raise PortfolioNotFound("No portfolio is configured")
    priority = {PortfolioType.MANUAL: 0, PortfolioType.RESEARCH: 1}
    return sorted(
        rows,
        key=lambda row: (priority.get(row.portfolio_type, 99), row.portfolio_id),
    )[0]


class PortfolioOSService:
    """Guarded broker-neutral orchestration over append-only Portfolio OS stores."""

    def __init__(
        self,
        *,
        portfolios: PortfolioRepository,
        accounts: AccountRepository,
        transactions: TransactionRepository,
        holdings: HoldingRepository,
        valuations: ValuationRepository,
        risks: RiskRepository,
        benchmarks: BenchmarkRepository,
        events: PortfolioEventRepository,
        valid_strategy_ids: Iterable[str] | None = None,
        valid_evidence_ids: Iterable[str] | None = None,
        valid_lineage_node_ids: Iterable[str] | None = None,
    ) -> None:
        self._portfolios = portfolios
        self._accounts = accounts
        self._transactions = transactions
        self._holdings = holdings
        self._valuations = valuations
        self._risks = risks
        self._benchmarks = benchmarks
        self._events = events
        self._valid_strategy_ids = (
            frozenset(valid_strategy_ids) if valid_strategy_ids is not None else None
        )
        self._valid_evidence_ids = (
            frozenset(valid_evidence_ids) if valid_evidence_ids is not None else None
        )
        self._valid_lineage_node_ids = (
            frozenset(valid_lineage_node_ids)
            if valid_lineage_node_ids is not None
            else None
        )
        self._fifo = FIFOAccountingEngine()

    @classmethod
    def from_repository(
        cls,
        repository: object,
        **kwargs: object,
    ) -> "PortfolioOSService":
        required = (
            PortfolioRepository,
            AccountRepository,
            TransactionRepository,
            HoldingRepository,
            ValuationRepository,
            RiskRepository,
            BenchmarkRepository,
            PortfolioEventRepository,
        )
        if not all(isinstance(repository, interface) for interface in required):
            raise TypeError("Repository does not implement all Portfolio OS interfaces")
        return cls(
            portfolios=repository,
            accounts=repository,
            transactions=repository,
            holdings=repository,
            valuations=repository,
            risks=repository,
            benchmarks=repository,
            events=repository,
            **kwargs,
        )

    @staticmethod
    def _now(value: datetime | None) -> datetime:
        result = value or datetime.now(timezone.utc)
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError("event timestamp must be timezone-aware")
        return result.astimezone(timezone.utc)

    def _portfolio(self, portfolio_id: str) -> Portfolio:
        portfolio = self._portfolios.get_portfolio(portfolio_id)
        if portfolio is None:
            raise PortfolioNotFound(portfolio_id)
        return portfolio

    def _account(self, account_id: str) -> PortfolioAccount:
        account = self._accounts.get_account(account_id)
        if account is None:
            raise AccountNotFound(account_id)
        return account

    def _security(self, security_id: str) -> SecurityReference:
        security = self._holdings.get_security(security_id)
        if security is None:
            raise SecurityNotFound(security_id)
        return security

    @staticmethod
    def _updated_portfolio(portfolio: Portfolio, **updates: object) -> Portfolio:
        return Portfolio.model_validate(
            {**portfolio.model_dump(mode="python"), **updates}
        )

    def _check_link(self, kind: str, value: str | None) -> None:
        if value is None:
            return
        allowed = {
            "strategy": self._valid_strategy_ids,
            "evidence": self._valid_evidence_ids,
            "lineage": self._valid_lineage_node_ids,
        }[kind]
        if allowed is not None and value not in allowed:
            raise InvalidTransaction(f"Unknown {kind} reference: {value}")

    def _record_event(
        self,
        *,
        portfolio_id: str,
        event_type: PortfolioEventType,
        entity_type: str,
        entity_id: str,
        actor: str,
        timestamp: datetime | None,
        reason: str,
        metadata: Mapping[str, object] | None = None,
    ) -> PortfolioEvent:
        occurred_at = self._now(timestamp)
        event = PortfolioEvent(
            event_id=deterministic_id(
                "PEVT",
                portfolio_id,
                event_type,
                entity_type,
                entity_id,
                occurred_at,
                reason,
            ),
            portfolio_id=portfolio_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            actor=actor,
            timestamp=occurred_at,
            reason=reason,
            metadata=dict(metadata or {}),
        )
        self._events.append_portfolio_event(event)
        return event

    # Read operations required by the Step 04.03 contract.
    def get_portfolio(self, portfolio_id: str) -> Portfolio:
        return self._portfolio(portfolio_id)

    def list_portfolios(self) -> list[Portfolio]:
        return self._portfolios.list_portfolios()

    def get_accounts(self, portfolio_id: str) -> list[PortfolioAccount]:
        self._portfolio(portfolio_id)
        return self._accounts.list_accounts(portfolio_id)

    def get_holdings(self, portfolio_id: str) -> list[Holding]:
        self._portfolio(portfolio_id)
        return self._holdings.get_holdings(portfolio_id)

    def get_security(self, security_id: str) -> SecurityReference:
        return self._security(security_id)

    def get_transactions(self, portfolio_id: str) -> list[PortfolioTransaction]:
        self._portfolio(portfolio_id)
        return self._transactions.list_transactions(portfolio_id)

    def get_valuation(self, portfolio_id: str) -> PortfolioValuation | None:
        self._portfolio(portfolio_id)
        return self._valuations.get_valuation(portfolio_id)

    def get_risk(self, portfolio_id: str) -> PortfolioRiskSnapshot | None:
        self._portfolio(portfolio_id)
        return self._risks.get_risk(portfolio_id)

    def get_performance(self, portfolio_id: str) -> list[PortfolioPerformancePoint]:
        self._portfolio(portfolio_id)
        return self._valuations.list_performance(portfolio_id)

    def get_benchmark_comparison(
        self, portfolio_id: str
    ) -> PortfolioBenchmarkComparison | None:
        self._portfolio(portfolio_id)
        return self._benchmarks.get_benchmark_comparison(portfolio_id)

    def get_benchmark(self, benchmark_id: str) -> BenchmarkReference:
        benchmark = self._benchmarks.get_benchmark(benchmark_id)
        if benchmark is None:
            raise InvalidPortfolioState(f"Benchmark not found: {benchmark_id}")
        return benchmark

    def get_attribution(self, portfolio_id: str) -> PortfolioAttribution | None:
        self._portfolio(portfolio_id)
        return self._valuations.get_attribution(portfolio_id)

    def get_portfolio_history(self, portfolio_id: str) -> list[Portfolio]:
        self._portfolio(portfolio_id)
        return self._portfolios.get_portfolio_history(portfolio_id)

    def get_cash_balances(self, portfolio_id: str) -> list[CashBalance]:
        self._portfolio(portfolio_id)
        return self._accounts.list_cash_balances(portfolio_id)

    def get_lots(self, portfolio_id: str):
        self._portfolio(portfolio_id)
        return self._holdings.get_lots(portfolio_id)

    def get_goals(self, portfolio_id: str) -> list[PortfolioGoal]:
        self._portfolio(portfolio_id)
        return self._portfolios.list_goals(portfolio_id)

    def get_exposure(self, portfolio_id: str) -> ExposureSnapshot | None:
        self._portfolio(portfolio_id)
        return self._valuations.get_exposure(portfolio_id)

    def get_portfolio_events(self, portfolio_id: str) -> list[PortfolioEvent]:
        self._portfolio(portfolio_id)
        return self._events.list_portfolio_events(portfolio_id)

    # Guarded write operations.
    def create_portfolio(
        self,
        portfolio: Portfolio,
        *,
        actor: str,
        reason: str,
        event_timestamp: datetime | None = None,
    ) -> Portfolio:
        if self._portfolios.get_portfolio(portfolio.portfolio_id) is not None:
            raise InvalidPortfolioState(
                f"Portfolio already exists: {portfolio.portfolio_id}"
            )
        for strategy_id in portfolio.strategy_ids:
            self._check_link("strategy", strategy_id)
        self._portfolios.append_portfolio(portfolio)
        self._record_event(
            portfolio_id=portfolio.portfolio_id,
            event_type=PortfolioEventType.PORTFOLIO_CREATED,
            entity_type="Portfolio",
            entity_id=portfolio.portfolio_id,
            actor=actor,
            timestamp=event_timestamp or portfolio.created_at,
            reason=reason,
        )
        return portfolio

    def register_account(
        self,
        account: PortfolioAccount,
        *,
        actor: str,
        reason: str,
        event_timestamp: datetime | None = None,
    ) -> PortfolioAccount:
        portfolio = self._portfolio(account.portfolio_id)
        if account.currency != portfolio.base_currency:
            # The account is allowed; valuation will remain blocked until FX exists.
            metadata = {"risk_flag": RiskFlag.FX_CONVERSION_REQUIRED.value}
        else:
            metadata = {}
        occurred_at = self._now(event_timestamp or account.created_at)
        if occurred_at <= portfolio.updated_at:
            raise InvalidPortfolioState(
                "Account link timestamp must follow the current portfolio state"
            )
        self._accounts.add_account(account)
        account_ids = tuple(sorted({*portfolio.account_ids, account.account_id}))
        self._portfolios.append_portfolio(
            self._updated_portfolio(
                portfolio, account_ids=account_ids, updated_at=occurred_at
            )
        )
        self._record_event(
            portfolio_id=portfolio.portfolio_id,
            event_type=PortfolioEventType.ACCOUNT_LINKED,
            entity_type="PortfolioAccount",
            entity_id=account.account_id,
            actor=actor,
            timestamp=occurred_at,
            reason=reason,
            metadata=metadata,
        )
        return account

    def register_security(
        self,
        portfolio_id: str,
        security: SecurityReference,
        *,
        actor: str,
        reason: str,
        event_timestamp: datetime | None = None,
    ) -> SecurityReference:
        self._portfolio(portfolio_id)
        self._holdings.add_security(security)
        self._record_event(
            portfolio_id=portfolio_id,
            event_type=PortfolioEventType.MANUAL_ADJUSTMENT,
            entity_type="SecurityReference",
            entity_id=security.security_id,
            actor=actor,
            timestamp=event_timestamp,
            reason=reason,
        )
        return security

    def record_transaction(
        self,
        transaction: PortfolioTransaction,
        *,
        actor: str,
        reason: str,
        event_timestamp: datetime | None = None,
    ) -> PortfolioTransaction:
        portfolio = self._portfolio(transaction.portfolio_id)
        account = self._account(transaction.account_id)
        if account.portfolio_id != portfolio.portfolio_id:
            raise InvalidTransaction("Transaction account belongs to another portfolio")
        if transaction.security_id is not None:
            security = self._security(transaction.security_id)
            if security.currency != transaction.currency:
                raise CurrencyMismatch(
                    "Transaction and security currencies must match without FX conversion"
                )
        self._check_link("strategy", transaction.strategy_id)
        self._check_link("evidence", transaction.evidence_id)
        self._check_link("lineage", transaction.lineage_node_id)
        if transaction.transaction_type == TransactionType.REVERSAL and not (
            transaction.external_reference
            or transaction.metadata.get("reverses_transaction_id")
        ):
            raise InvalidTransaction("REVERSAL must identify the corrected transaction")
        self._transactions.append_transaction(transaction)
        self._record_event(
            portfolio_id=portfolio.portfolio_id,
            event_type=PortfolioEventType.TRANSACTION_RECORDED,
            entity_type="PortfolioTransaction",
            entity_id=transaction.transaction_id,
            actor=actor,
            timestamp=event_timestamp,
            reason=reason,
            metadata={"transaction_type": transaction.transaction_type.value},
        )
        return transaction

    def record_cash_balance(
        self,
        balance: CashBalance,
        *,
        actor: str,
        reason: str,
        event_timestamp: datetime | None = None,
    ) -> CashBalance:
        account = self._account(balance.account_id)
        if balance.currency != account.currency:
            raise CurrencyMismatch("Cash balance currency must match account currency")
        self._check_link("lineage", balance.lineage_node_id)
        self._accounts.append_cash_balance(balance)
        self._record_event(
            portfolio_id=account.portfolio_id,
            event_type=PortfolioEventType.MANUAL_ADJUSTMENT,
            entity_type="CashBalance",
            entity_id=f"{balance.account_id}:{balance.as_of.isoformat()}",
            actor=actor,
            timestamp=event_timestamp or balance.as_of,
            reason=reason,
        )
        return balance

    def rebuild_holdings(
        self,
        portfolio_id: str,
        *,
        prices: Mapping[str, Decimal],
        as_of: datetime,
        source: str,
        actor: str,
        reason: str,
        event_timestamp: datetime | None = None,
    ) -> HoldingsRebuildResult:
        self._portfolio(portfolio_id)
        transactions = self._transactions.list_transactions(portfolio_id)
        security_ids = {
            row.security_id for row in transactions if row.security_id is not None
        }
        securities = {security_id: self._security(security_id) for security_id in security_ids}
        result = self._fifo.rebuild(
            portfolio_id=portfolio_id,
            transactions=transactions,
            securities=securities,
            prices=prices,
            as_of=as_of,
            source=source,
        )
        self._holdings.append_holdings_snapshot(
            portfolio_id, result.holdings, result.lots
        )
        self._record_event(
            portfolio_id=portfolio_id,
            event_type=PortfolioEventType.HOLDING_REBUILT,
            entity_type="HoldingsRebuildResult",
            entity_id=deterministic_id("HRB", portfolio_id, as_of),
            actor=actor,
            timestamp=event_timestamp or as_of,
            reason=reason,
            metadata={
                "lot_policy": result.lot_policy.value,
                "holding_count": len(result.holdings),
                "lot_count": len(result.lots),
            },
        )
        return result

    def record_valuation(
        self,
        valuation: PortfolioValuation,
        *,
        actor: str,
        reason: str,
        event_timestamp: datetime | None = None,
    ) -> PortfolioValuation:
        portfolio = self._portfolio(valuation.portfolio_id)
        if valuation.currency != portfolio.base_currency:
            raise CurrencyMismatch("Valuation currency must match portfolio base currency")
        currencies = self._portfolio_currencies(portfolio.portfolio_id)
        if any(currency != portfolio.base_currency for currency in currencies):
            raise CurrencyMismatch(
                "Mixed-currency valuation requires an FX conversion engine"
            )
        self._check_link("lineage", valuation.lineage_node_id)
        self._valuations.append_valuation(valuation)
        self._record_event(
            portfolio_id=portfolio.portfolio_id,
            event_type=PortfolioEventType.VALUATION_CREATED,
            entity_type="PortfolioValuation",
            entity_id=f"{portfolio.portfolio_id}:{valuation.as_of.isoformat()}",
            actor=actor,
            timestamp=event_timestamp or valuation.as_of,
            reason=reason,
        )
        return valuation

    def create_valuation_snapshot(self, portfolio_id: str) -> ValuationSnapshot:
        valuation = self.get_valuation(portfolio_id)
        if valuation is None:
            raise InvalidPortfolioState("No valuation exists for portfolio")
        payload = {
            "valuation": valuation,
            "holding_ids": tuple(row.holding_id for row in self.get_holdings(portfolio_id)),
            "cash_balance_accounts": tuple(
                row.account_id for row in self.get_cash_balances(portfolio_id)
            ),
        }
        return ValuationSnapshot(
            snapshot_id=deterministic_id("VSNP", portfolio_id, valuation.as_of),
            valuation=valuation,
            holding_ids=payload["holding_ids"],
            cash_balance_accounts=payload["cash_balance_accounts"],
            snapshot_hash=canonical_hash(payload),
        )

    def record_risk_snapshot(
        self,
        risk: PortfolioRiskSnapshot,
        *,
        actor: str,
        reason: str,
        event_timestamp: datetime | None = None,
    ) -> PortfolioRiskSnapshot:
        self._portfolio(risk.portfolio_id)
        self._check_link("lineage", risk.lineage_node_id)
        self._risks.append_risk(risk)
        self._record_event(
            portfolio_id=risk.portfolio_id,
            event_type=PortfolioEventType.RISK_SNAPSHOT_CREATED,
            entity_type="PortfolioRiskSnapshot",
            entity_id=f"{risk.portfolio_id}:{risk.as_of.isoformat()}",
            actor=actor,
            timestamp=event_timestamp or risk.as_of,
            reason=reason,
        )
        return risk

    def link_benchmark(
        self,
        portfolio_id: str,
        benchmark: BenchmarkReference,
        *,
        actor: str,
        reason: str,
        event_timestamp: datetime | None = None,
    ) -> BenchmarkReference:
        portfolio = self._portfolio(portfolio_id)
        occurred_at = self._now(event_timestamp)
        if occurred_at <= portfolio.updated_at:
            raise InvalidPortfolioState(
                "Benchmark link timestamp must follow the current portfolio state"
            )
        self._benchmarks.add_benchmark(benchmark)
        self._portfolios.append_portfolio(
            self._updated_portfolio(
                portfolio,
                benchmark_ids=tuple(
                    sorted({*portfolio.benchmark_ids, benchmark.benchmark_id})
                ),
                updated_at=occurred_at,
            )
        )
        self._record_event(
            portfolio_id=portfolio_id,
            event_type=PortfolioEventType.BENCHMARK_LINKED,
            entity_type="BenchmarkReference",
            entity_id=benchmark.benchmark_id,
            actor=actor,
            timestamp=occurred_at,
            reason=reason,
        )
        return benchmark

    def change_portfolio_status(
        self,
        portfolio_id: str,
        status: PortfolioStatus,
        *,
        actor: str,
        reason: str,
        event_timestamp: datetime | None = None,
    ) -> Portfolio:
        portfolio = self._portfolio(portfolio_id)
        if portfolio.status == PortfolioStatus.ARCHIVED:
            raise InvalidPortfolioState("Archived portfolios cannot change status")
        occurred_at = self._now(event_timestamp)
        if occurred_at <= portfolio.updated_at:
            raise InvalidPortfolioState("Status timestamp must follow current state")
        updated = self._updated_portfolio(
            portfolio, status=status, updated_at=occurred_at
        )
        self._portfolios.append_portfolio(updated)
        self._record_event(
            portfolio_id=portfolio_id,
            event_type=PortfolioEventType.STATUS_CHANGED,
            entity_type="Portfolio",
            entity_id=portfolio_id,
            actor=actor,
            timestamp=occurred_at,
            reason=reason,
            metadata={"from": portfolio.status.value, "to": status.value},
        )
        return updated

    # Supporting writes used to construct complete offline snapshots.
    def add_goal(
        self,
        goal: PortfolioGoal,
        *,
        actor: str,
        reason: str,
        event_timestamp: datetime | None = None,
    ) -> PortfolioGoal:
        portfolio = self._portfolio(goal.portfolio_id)
        occurred_at = self._now(event_timestamp)
        if goal.currency != portfolio.base_currency:
            raise CurrencyMismatch("Goal currency must match portfolio base currency")
        if occurred_at <= portfolio.updated_at:
            raise InvalidPortfolioState("Goal timestamp must follow current state")
        self._portfolios.add_goal(goal)
        self._portfolios.append_portfolio(
            self._updated_portfolio(
                portfolio,
                goal_ids=tuple(sorted({*portfolio.goal_ids, goal.goal_id})),
                updated_at=occurred_at,
            )
        )
        self._record_event(
            portfolio_id=goal.portfolio_id,
            event_type=PortfolioEventType.MANUAL_ADJUSTMENT,
            entity_type="PortfolioGoal",
            entity_id=goal.goal_id,
            actor=actor,
            timestamp=occurred_at,
            reason=reason,
        )
        return goal

    def record_exposure(
        self,
        exposure: ExposureSnapshot,
        *,
        actor: str,
        reason: str,
        event_timestamp: datetime | None = None,
    ) -> ExposureSnapshot:
        self._portfolio(exposure.portfolio_id)
        self._valuations.append_exposure(exposure)
        self._record_event(
            portfolio_id=exposure.portfolio_id,
            event_type=PortfolioEventType.RISK_SNAPSHOT_CREATED,
            entity_type="ExposureSnapshot",
            entity_id=f"{exposure.portfolio_id}:{exposure.as_of.isoformat()}",
            actor=actor,
            timestamp=event_timestamp or exposure.as_of,
            reason=reason,
        )
        return exposure

    def record_performance_point(
        self,
        point: PortfolioPerformancePoint,
        *,
        actor: str,
        reason: str,
        event_timestamp: datetime | None = None,
    ) -> PortfolioPerformancePoint:
        self._portfolio(point.portfolio_id)
        self._check_link("lineage", point.lineage_node_id)
        self._valuations.append_performance_point(point)
        self._record_event(
            portfolio_id=point.portfolio_id,
            event_type=PortfolioEventType.VALUATION_CREATED,
            entity_type="PortfolioPerformancePoint",
            entity_id=f"{point.portfolio_id}:{point.date.isoformat()}",
            actor=actor,
            timestamp=event_timestamp,
            reason=reason,
        )
        return point

    def record_attribution(
        self,
        attribution: PortfolioAttribution,
        *,
        actor: str,
        reason: str,
        event_timestamp: datetime | None = None,
    ) -> PortfolioAttribution:
        portfolio = self._portfolio(attribution.portfolio_id)
        if attribution.currency != portfolio.base_currency:
            raise CurrencyMismatch("Attribution currency must match portfolio base currency")
        self._valuations.append_attribution(attribution)
        self._record_event(
            portfolio_id=attribution.portfolio_id,
            event_type=PortfolioEventType.VALUATION_CREATED,
            entity_type="PortfolioAttribution",
            entity_id=deterministic_id(
                "ATTR",
                attribution.portfolio_id,
                attribution.period_start,
                attribution.period_end,
            ),
            actor=actor,
            timestamp=event_timestamp,
            reason=reason,
        )
        return attribution

    def record_benchmark_comparison(
        self,
        comparison: PortfolioBenchmarkComparison,
        *,
        actor: str,
        reason: str,
        event_timestamp: datetime | None = None,
    ) -> PortfolioBenchmarkComparison:
        portfolio = self._portfolio(comparison.portfolio_id)
        if comparison.benchmark_id not in portfolio.benchmark_ids:
            raise InvalidPortfolioState("Benchmark is not linked to portfolio")
        self._benchmarks.append_benchmark_comparison(comparison)
        self._record_event(
            portfolio_id=comparison.portfolio_id,
            event_type=PortfolioEventType.VALUATION_CREATED,
            entity_type="PortfolioBenchmarkComparison",
            entity_id=deterministic_id(
                "BCMP",
                comparison.portfolio_id,
                comparison.benchmark_id,
                comparison.period_start,
                comparison.period_end,
            ),
            actor=actor,
            timestamp=event_timestamp,
            reason=reason,
        )
        return comparison

    def calculate_cash_ledger(
        self, portfolio_id: str, *, as_of: datetime
    ):
        self._portfolio(portfolio_id)
        return calculate_cash_ledger(
            portfolio_id,
            self._transactions.list_transactions(portfolio_id),
            as_of=as_of,
        )

    def calculate_metrics(self, portfolio_id: str) -> PortfolioMetrics:
        self._portfolio(portfolio_id)
        return calculate_portfolio_metrics(
            portfolio_id,
            self._valuations.list_performance(portfolio_id),
            self._transactions.list_transactions(portfolio_id),
        )

    def calculate_attribution(
        self, portfolio_id: str, *, period_start, period_end
    ) -> PortfolioAttribution:
        portfolio = self._portfolio(portfolio_id)
        security: dict[str, Decimal] = defaultdict(lambda: ZERO)
        strategy: dict[str, Decimal] = defaultdict(lambda: ZERO)
        sector: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for holding in self._holdings.get_holdings(portfolio_id):
            security[holding.security_id] += holding.unrealized_pnl
            if holding.strategy_attribution:
                total = sum(holding.strategy_attribution.values(), ZERO)
                if total:
                    for strategy_id, value in holding.strategy_attribution.items():
                        strategy[strategy_id] += holding.unrealized_pnl * value / total
            sector_name = str(holding.metadata.get("sector") or "UNCLASSIFIED")
            sector[sector_name] += holding.unrealized_pnl
        costs = -sum(
            (
                row.fees + row.taxes
                for row in self._transactions.list_transactions(portfolio_id)
                if period_start <= row.trade_date <= period_end
            ),
            ZERO,
        )
        total = sum(security.values(), ZERO) + costs
        return PortfolioAttribution(
            portfolio_id=portfolio_id,
            period_start=period_start,
            period_end=period_end,
            currency=portfolio.base_currency,
            security_attribution=dict(sorted(security.items())),
            strategy_attribution=dict(sorted(strategy.items())),
            sector_attribution=dict(sorted(sector.items())),
            transaction_cost_attribution=costs,
            total_contribution=total,
            metadata={"method": "deterministic_unrealized_plus_costs_v1"},
        )

    def calculate_exposure(
        self, portfolio_id: str, *, as_of: datetime
    ) -> ExposureSnapshot:
        portfolio = self._portfolio(portfolio_id)
        holdings = self._holdings.get_holdings(portfolio_id)
        cash_rows = self._accounts.list_cash_balances(portfolio_id)
        gross = sum((abs(row.market_value) for row in holdings), ZERO)
        net = sum((row.market_value for row in holdings), ZERO)
        cash = sum((row.available_cash for row in cash_rows), ZERO)
        nlv = net + cash

        def weights(values: Mapping[str, Decimal]) -> dict[str, Decimal]:
            return {
                key: value / nlv if nlv else ZERO
                for key, value in sorted(values.items())
            }

        security_values = {row.security_id: row.market_value for row in holdings}
        sector_values: dict[str, Decimal] = defaultdict(lambda: ZERO)
        strategy_values: dict[str, Decimal] = defaultdict(lambda: ZERO)
        account_values: dict[str, Decimal] = defaultdict(lambda: ZERO)
        currency_values: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for row in holdings:
            sector_values[str(row.metadata.get("sector") or "UNCLASSIFIED")] += row.market_value
            account_values[row.account_id] += row.market_value
            currency_values[row.currency] += row.market_value
            for strategy_id, value in row.strategy_attribution.items():
                strategy_values[strategy_id] += value
        for row in cash_rows:
            account_values[row.account_id] += row.available_cash
            currency_values[row.currency] += row.available_cash
        flags: list[RiskFlag] = []
        if any(currency != portfolio.base_currency for currency in currency_values):
            flags.append(RiskFlag.FX_CONVERSION_REQUIRED)
        concentration = max(weights(security_values).values(), default=ZERO)
        if concentration > Decimal("0.40"):
            flags.append(RiskFlag.CONCENTRATION_HIGH)
        cash_pct = cash / nlv if nlv else None
        if cash_pct is not None and cash_pct < Decimal("0.05"):
            flags.append(RiskFlag.CASH_LOW)
        return ExposureSnapshot(
            portfolio_id=portfolio_id,
            as_of=as_of,
            gross_exposure=gross / nlv if nlv else ZERO,
            net_exposure=net / nlv if nlv else ZERO,
            cash_pct=cash_pct,
            security_concentration=weights(security_values),
            sector_exposure=weights(sector_values),
            strategy_exposure=weights(strategy_values),
            account_exposure=weights(account_values),
            currency_exposure=weights(currency_values),
            risk_flags=tuple(sorted(set(flags), key=lambda item: item.value)),
            metadata={"currency_conversion_applied": False},
        )

    def _portfolio_currencies(self, portfolio_id: str) -> set[str]:
        currencies = {row.currency for row in self._accounts.list_cash_balances(portfolio_id)}
        currencies.update(row.currency for row in self._holdings.get_holdings(portfolio_id))
        currencies.update(
            row.currency for row in self._transactions.list_transactions(portfolio_id)
        )
        return currencies

    def reconcile(
        self, portfolio_id: str, *, as_of: datetime | None = None
    ) -> PortfolioReconciliationResult:
        portfolio = self._portfolio(portfolio_id)
        timestamp = self._now(as_of)
        transactions = self._transactions.list_transactions(portfolio_id)
        ledger = calculate_cash_ledger(portfolio_id, transactions, as_of=timestamp)
        errors: list[str] = []
        flags: list[RiskFlag] = []
        cash_consistent = True
        for account in self._accounts.list_accounts(portfolio_id):
            recorded = self._accounts.get_latest_cash_balance(account.account_id)
            expected = ledger.account_balances.get(account.account_id, ZERO)
            if recorded is None or abs(recorded.settled_cash - expected) > TOLERANCE:
                cash_consistent = False
                errors.append(f"cash:{account.account_id}:expected={expected}")
        holdings = self._holdings.get_holdings(portfolio_id)
        positions_consistent = all(row.quantity >= ZERO for row in holdings)
        trade_security_ids = {
            row.security_id
            for row in transactions
            if row.transaction_type in {TransactionType.BUY, TransactionType.SELL}
        }
        if trade_security_ids and not holdings:
            positions_consistent = False
        if not positions_consistent:
            errors.append("positions:missing_or_negative")
        transaction_totals_consistent = all(
            row.account_id in portfolio.account_ids
            and row.settlement_date >= row.trade_date
            for row in transactions
        )
        if not transaction_totals_consistent:
            errors.append("transactions:invalid_reference_or_dates")
        lots = self._holdings.get_lots(portfolio_id)
        lot_costs: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for lot in lots:
            lot_costs[lot.holding_id] += lot.cost_basis
        cost_basis_consistent = all(
            abs(lot_costs.get(row.holding_id, ZERO) - row.cost_basis) <= TOLERANCE
            for row in holdings
        )
        if not cost_basis_consistent:
            errors.append("positions:cost_basis_mismatch")
        valuation = self._valuations.get_valuation(portfolio_id)
        valuation_consistent = True
        if valuation is not None:
            gross = sum((row.market_value for row in holdings), ZERO)
            cash = sum(
                (row.available_cash for row in self._accounts.list_cash_balances(portfolio_id)),
                ZERO,
            )
            cost = sum((row.cost_basis for row in holdings), ZERO)
            unrealized = sum((row.unrealized_pnl for row in holdings), ZERO)
            valuation_consistent = all(
                abs(left - right) <= TOLERANCE
                for left, right in (
                    (valuation.gross_market_value, gross),
                    (valuation.cash, cash),
                    (valuation.cost_basis, cost),
                    (valuation.unrealized_pnl, unrealized),
                )
            )
            if not valuation_consistent:
                errors.append("valuation:component_mismatch")
        currencies = self._portfolio_currencies(portfolio_id)
        if any(currency != portfolio.base_currency for currency in currencies):
            flags.append(RiskFlag.FX_CONVERSION_REQUIRED)
        ok = all(
            (
                cash_consistent,
                positions_consistent,
                transaction_totals_consistent,
                cost_basis_consistent,
                valuation_consistent,
            )
        )
        return PortfolioReconciliationResult(
            portfolio_id=portfolio_id,
            as_of=timestamp,
            cash_consistent=cash_consistent,
            positions_consistent=positions_consistent,
            transaction_totals_consistent=transaction_totals_consistent,
            cost_basis_consistent=cost_basis_consistent,
            valuation_consistent=valuation_consistent,
            errors=tuple(errors),
            risk_flags=tuple(flags),
            status=IntegrityStatus.HEALTHY if ok else IntegrityStatus.ERROR,
        )

    def get_integrity_summary(self) -> PortfolioOSIntegritySummary:
        portfolios = self._portfolios.list_portfolios()
        portfolio_ids = {row.portfolio_id for row in portfolios}
        accounts = [
            account
            for portfolio_id in portfolio_ids
            for account in self._accounts.list_accounts(portfolio_id)
        ]
        account_ids = {row.account_id for row in accounts}
        securities = {row.security_id for row in self._holdings.list_securities()}
        broken_refs = 0
        negative = 0
        cash_errors = 0
        valuation_errors = 0
        event_errors = 0
        transaction_ids: list[str] = []
        for portfolio in portfolios:
            broken_refs += len(set(portfolio.account_ids) - account_ids)
            for account in self._accounts.list_accounts(portfolio.portfolio_id):
                broken_refs += int(account.portfolio_id != portfolio.portfolio_id)
            transactions = self._transactions.list_transactions(portfolio.portfolio_id)
            transaction_ids.extend(row.transaction_id for row in transactions)
            for transaction in transactions:
                broken_refs += int(transaction.account_id not in account_ids)
                broken_refs += int(
                    transaction.security_id is not None
                    and transaction.security_id not in securities
                )
                broken_refs += self._link_error_count(transaction)
            holdings = self._holdings.get_holdings(portfolio.portfolio_id)
            negative += sum(row.quantity < ZERO for row in holdings)
            broken_refs += sum(
                row.account_id not in account_ids or row.security_id not in securities
                for row in holdings
            )
            reconciliation = self.reconcile(portfolio.portfolio_id)
            cash_errors += int(not reconciliation.cash_consistent)
            valuation_errors += int(not reconciliation.valuation_consistent)
            history = self._events.list_portfolio_events(portfolio.portfolio_id)
            if not history or history[0].event_type != PortfolioEventType.PORTFOLIO_CREATED:
                event_errors += 1
            event_errors += sum(
                history[index].timestamp < history[index - 1].timestamp
                for index in range(1, len(history))
            )
        duplicates = sum(count - 1 for count in Counter(transaction_ids).values() if count > 1)
        values = (
            broken_refs,
            negative,
            cash_errors,
            duplicates,
            valuation_errors,
            event_errors,
        )
        return PortfolioOSIntegritySummary(
            broken_refs=broken_refs,
            negative_holding_violations=negative,
            cash_reconciliation_errors=cash_errors,
            duplicate_transaction_ids=duplicates,
            valuation_mismatches=valuation_errors,
            event_sequence_errors=event_errors,
            status=IntegrityStatus.HEALTHY
            if not any(values)
            else IntegrityStatus.ERROR,
            metadata={"portfolio_count": len(portfolios)},
        )

    def _link_error_count(self, transaction: PortfolioTransaction) -> int:
        checks = (
            (transaction.strategy_id, self._valid_strategy_ids),
            (transaction.evidence_id, self._valid_evidence_ids),
            (transaction.lineage_node_id, self._valid_lineage_node_ids),
        )
        return sum(value is not None and allowed is not None and value not in allowed for value, allowed in checks)

    def export_portfolio_os_snapshot(self) -> PortfolioOSSnapshot:
        portfolios = tuple(self._portfolios.list_portfolios())
        accounts = tuple(
            account
            for portfolio in portfolios
            for account in self._accounts.list_accounts(portfolio.portfolio_id)
        )
        holdings = tuple(
            holding
            for portfolio in portfolios
            for holding in self._holdings.get_holdings(portfolio.portfolio_id)
        )
        cash = tuple(
            row
            for portfolio in portfolios
            for row in self._accounts.list_cash_balances(portfolio.portfolio_id)
        )
        risk = tuple(
            row
            for portfolio in portfolios
            if (row := self._risks.get_risk(portfolio.portfolio_id)) is not None
        )
        benchmarks = tuple(self._benchmarks.list_benchmarks())
        integrity = self.get_integrity_summary()
        all_events = [
            event
            for portfolio in portfolios
            for event in self._events.list_portfolio_events(portfolio.portfolio_id)
        ]
        generated_at = max(
            (event.timestamp for event in all_events),
            default=max(
                (portfolio.updated_at for portfolio in portfolios),
                default=datetime(1970, 1, 1, tzinfo=timezone.utc),
            ),
        )
        payload = {
            "snapshot_version": SNAPSHOT_VERSION,
            "generated_at": generated_at,
            "portfolios": portfolios,
            "accounts": accounts,
            "holdings": holdings,
            "cash": cash,
            "risk": risk,
            "benchmarks": benchmarks,
            "integrity": integrity,
        }
        return PortfolioOSSnapshot(
            **payload,
            snapshot_hash=canonical_hash(payload),
        )


__all__ = ("PortfolioOSService", "SNAPSHOT_VERSION", "select_primary_portfolio")
