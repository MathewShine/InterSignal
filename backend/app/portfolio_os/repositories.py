from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.platform.hashing import canonical_hash
from app.portfolio_os.models import (
    BenchmarkReference,
    CashBalance,
    ExposureSnapshot,
    Holding,
    Portfolio,
    PortfolioAccount,
    PortfolioAttribution,
    PortfolioBenchmarkComparison,
    PortfolioEvent,
    PortfolioGoal,
    PortfolioOSModel,
    PortfolioPerformancePoint,
    PortfolioRiskSnapshot,
    PortfolioTransaction,
    PortfolioValuation,
    PositionLot,
    SecurityReference,
)


class DuplicatePortfolioIdentity(ValueError):
    pass


class PortfolioAppendOnlyViolation(ValueError):
    pass


@runtime_checkable
class PortfolioRepository(Protocol):
    def append_portfolio(self, record: Portfolio) -> None: ...

    def get_portfolio(self, portfolio_id: str) -> Portfolio | None: ...

    def list_portfolios(self) -> list[Portfolio]: ...

    def get_portfolio_history(self, portfolio_id: str) -> list[Portfolio]: ...

    def add_goal(self, goal: PortfolioGoal) -> None: ...

    def list_goals(self, portfolio_id: str) -> list[PortfolioGoal]: ...


@runtime_checkable
class AccountRepository(Protocol):
    def add_account(self, account: PortfolioAccount) -> None: ...

    def get_account(self, account_id: str) -> PortfolioAccount | None: ...

    def list_accounts(self, portfolio_id: str) -> list[PortfolioAccount]: ...

    def append_cash_balance(self, balance: CashBalance) -> None: ...

    def list_cash_balances(self, portfolio_id: str) -> list[CashBalance]: ...

    def get_latest_cash_balance(self, account_id: str) -> CashBalance | None: ...


@runtime_checkable
class TransactionRepository(Protocol):
    def append_transaction(self, transaction: PortfolioTransaction) -> None: ...

    def get_transaction(self, transaction_id: str) -> PortfolioTransaction | None: ...

    def list_transactions(self, portfolio_id: str) -> list[PortfolioTransaction]: ...


@runtime_checkable
class HoldingRepository(Protocol):
    def add_security(self, security: SecurityReference) -> None: ...

    def get_security(self, security_id: str) -> SecurityReference | None: ...

    def list_securities(self) -> list[SecurityReference]: ...

    def append_holdings_snapshot(
        self,
        portfolio_id: str,
        holdings: tuple[Holding, ...],
        lots: tuple[PositionLot, ...],
    ) -> None: ...

    def get_holdings(self, portfolio_id: str) -> list[Holding]: ...

    def get_lots(self, portfolio_id: str) -> list[PositionLot]: ...


@runtime_checkable
class ValuationRepository(Protocol):
    def append_valuation(self, valuation: PortfolioValuation) -> None: ...

    def get_valuation(self, portfolio_id: str) -> PortfolioValuation | None: ...

    def list_valuations(self, portfolio_id: str) -> list[PortfolioValuation]: ...

    def append_exposure(self, exposure: ExposureSnapshot) -> None: ...

    def get_exposure(self, portfolio_id: str) -> ExposureSnapshot | None: ...

    def append_performance_point(self, point: PortfolioPerformancePoint) -> None: ...

    def list_performance(self, portfolio_id: str) -> list[PortfolioPerformancePoint]: ...

    def append_attribution(self, attribution: PortfolioAttribution) -> None: ...

    def get_attribution(self, portfolio_id: str) -> PortfolioAttribution | None: ...


@runtime_checkable
class RiskRepository(Protocol):
    def append_risk(self, risk: PortfolioRiskSnapshot) -> None: ...

    def get_risk(self, portfolio_id: str) -> PortfolioRiskSnapshot | None: ...


@runtime_checkable
class BenchmarkRepository(Protocol):
    def add_benchmark(self, benchmark: BenchmarkReference) -> None: ...

    def get_benchmark(self, benchmark_id: str) -> BenchmarkReference | None: ...

    def list_benchmarks(self) -> list[BenchmarkReference]: ...

    def append_benchmark_comparison(
        self, comparison: PortfolioBenchmarkComparison
    ) -> None: ...

    def get_benchmark_comparison(
        self, portfolio_id: str
    ) -> PortfolioBenchmarkComparison | None: ...


@runtime_checkable
class PortfolioEventRepository(Protocol):
    def append_portfolio_event(self, event: PortfolioEvent) -> None: ...

    def list_portfolio_events(self, portfolio_id: str) -> list[PortfolioEvent]: ...


class InMemoryPortfolioOSRepository:
    """Append-only in-memory implementation of all Portfolio OS interfaces."""

    def __init__(self) -> None:
        self._portfolio_history: dict[str, list[Portfolio]] = defaultdict(list)
        self._goals: dict[str, PortfolioGoal] = {}
        self._accounts: dict[str, PortfolioAccount] = {}
        self._cash: list[CashBalance] = []
        self._transactions: dict[str, PortfolioTransaction] = {}
        self._securities: dict[str, SecurityReference] = {}
        self._holdings: dict[str, Holding] = {}
        self._lots: dict[str, PositionLot] = {}
        self._valuations: list[PortfolioValuation] = []
        self._exposures: list[ExposureSnapshot] = []
        self._performance: list[PortfolioPerformancePoint] = []
        self._attributions: list[PortfolioAttribution] = []
        self._risks: list[PortfolioRiskSnapshot] = []
        self._benchmarks: dict[str, BenchmarkReference] = {}
        self._comparisons: list[PortfolioBenchmarkComparison] = []
        self._events: dict[str, PortfolioEvent] = {}

    def append_portfolio(self, record: Portfolio) -> None:
        history = self._portfolio_history[record.portfolio_id]
        if history:
            previous = history[-1]
            if canonical_hash(previous) == canonical_hash(record):
                raise DuplicatePortfolioIdentity(
                    f"Duplicate portfolio state: {record.portfolio_id}"
                )
            if record.created_at != previous.created_at:
                raise PortfolioAppendOnlyViolation("Portfolio created_at cannot change")
            if record.updated_at <= previous.updated_at:
                raise PortfolioAppendOnlyViolation(
                    "Portfolio updates require a later updated_at"
                )
        history.append(record)

    def get_portfolio(self, portfolio_id: str) -> Portfolio | None:
        history = self._portfolio_history.get(portfolio_id, [])
        return history[-1] if history else None

    def list_portfolios(self) -> list[Portfolio]:
        return [
            self._portfolio_history[item][-1]
            for item in sorted(self._portfolio_history)
        ]

    def get_portfolio_history(self, portfolio_id: str) -> list[Portfolio]:
        return list(self._portfolio_history.get(portfolio_id, []))

    def add_goal(self, goal: PortfolioGoal) -> None:
        if goal.goal_id in self._goals:
            raise DuplicatePortfolioIdentity(f"Duplicate goal: {goal.goal_id}")
        self._goals[goal.goal_id] = goal

    def list_goals(self, portfolio_id: str) -> list[PortfolioGoal]:
        return sorted(
            (
                row for row in self._goals.values() if row.portfolio_id == portfolio_id
            ),
            key=lambda row: row.goal_id,
        )

    def add_account(self, account: PortfolioAccount) -> None:
        if account.account_id in self._accounts:
            raise DuplicatePortfolioIdentity(f"Duplicate account: {account.account_id}")
        self._accounts[account.account_id] = account

    def get_account(self, account_id: str) -> PortfolioAccount | None:
        return self._accounts.get(account_id)

    def list_accounts(self, portfolio_id: str) -> list[PortfolioAccount]:
        return sorted(
            (
                row
                for row in self._accounts.values()
                if row.portfolio_id == portfolio_id
            ),
            key=lambda row: row.account_id,
        )

    def append_cash_balance(self, balance: CashBalance) -> None:
        previous = [row for row in self._cash if row.account_id == balance.account_id]
        if previous and balance.as_of <= max(row.as_of for row in previous):
            raise PortfolioAppendOnlyViolation(
                "Cash balances require a later as_of timestamp"
            )
        self._cash.append(balance)

    def get_latest_cash_balance(self, account_id: str) -> CashBalance | None:
        rows = [row for row in self._cash if row.account_id == account_id]
        return max(rows, key=lambda row: row.as_of) if rows else None

    def list_cash_balances(self, portfolio_id: str) -> list[CashBalance]:
        return [
            row
            for account in self.list_accounts(portfolio_id)
            if (row := self.get_latest_cash_balance(account.account_id)) is not None
        ]

    def append_transaction(self, transaction: PortfolioTransaction) -> None:
        if transaction.transaction_id in self._transactions:
            raise DuplicatePortfolioIdentity(
                f"Duplicate transaction: {transaction.transaction_id}"
            )
        self._transactions[transaction.transaction_id] = transaction

    def get_transaction(self, transaction_id: str) -> PortfolioTransaction | None:
        return self._transactions.get(transaction_id)

    def list_transactions(self, portfolio_id: str) -> list[PortfolioTransaction]:
        return sorted(
            (
                row
                for row in self._transactions.values()
                if row.portfolio_id == portfolio_id
            ),
            key=lambda row: (row.trade_date, row.settlement_date, row.transaction_id),
        )

    def add_security(self, security: SecurityReference) -> None:
        if security.security_id in self._securities:
            raise DuplicatePortfolioIdentity(
                f"Duplicate security: {security.security_id}"
            )
        self._securities[security.security_id] = security

    def get_security(self, security_id: str) -> SecurityReference | None:
        return self._securities.get(security_id)

    def list_securities(self) -> list[SecurityReference]:
        return [self._securities[item] for item in sorted(self._securities)]

    def append_holdings_snapshot(
        self,
        portfolio_id: str,
        holdings: tuple[Holding, ...],
        lots: tuple[PositionLot, ...],
    ) -> None:
        if any(row.portfolio_id != portfolio_id for row in holdings):
            raise ValueError("Holding portfolio does not match snapshot portfolio")
        for holding in holdings:
            if holding.holding_id in self._holdings:
                raise DuplicatePortfolioIdentity(
                    f"Duplicate holding: {holding.holding_id}"
                )
        for lot in lots:
            if lot.lot_id in self._lots:
                raise DuplicatePortfolioIdentity(f"Duplicate lot: {lot.lot_id}")
        self._holdings.update({row.holding_id: row for row in holdings})
        self._lots.update({row.lot_id: row for row in lots})

    def get_holdings(self, portfolio_id: str) -> list[Holding]:
        rows = [
            row for row in self._holdings.values() if row.portfolio_id == portfolio_id
        ]
        if not rows:
            return []
        latest = max(row.as_of for row in rows)
        return sorted(
            (row for row in rows if row.as_of == latest),
            key=lambda row: row.holding_id,
        )

    def get_lots(self, portfolio_id: str) -> list[PositionLot]:
        holding_ids = {row.holding_id for row in self.get_holdings(portfolio_id)}
        return sorted(
            (row for row in self._lots.values() if row.holding_id in holding_ids),
            key=lambda row: row.lot_id,
        )

    @staticmethod
    def _latest(rows: list, portfolio_id: str):
        matches = [row for row in rows if row.portfolio_id == portfolio_id]
        return max(matches, key=lambda row: row.as_of) if matches else None

    def append_valuation(self, valuation: PortfolioValuation) -> None:
        previous = self.get_valuation(valuation.portfolio_id)
        if previous and valuation.as_of <= previous.as_of:
            raise PortfolioAppendOnlyViolation(
                "Valuations require a later as_of timestamp"
            )
        self._valuations.append(valuation)

    def get_valuation(self, portfolio_id: str) -> PortfolioValuation | None:
        return self._latest(self._valuations, portfolio_id)

    def list_valuations(self, portfolio_id: str) -> list[PortfolioValuation]:
        return sorted(
            (row for row in self._valuations if row.portfolio_id == portfolio_id),
            key=lambda row: row.as_of,
        )

    def append_exposure(self, exposure: ExposureSnapshot) -> None:
        previous = self.get_exposure(exposure.portfolio_id)
        if previous and exposure.as_of <= previous.as_of:
            raise PortfolioAppendOnlyViolation(
                "Exposure snapshots require a later as_of timestamp"
            )
        self._exposures.append(exposure)

    def get_exposure(self, portfolio_id: str) -> ExposureSnapshot | None:
        return self._latest(self._exposures, portfolio_id)

    def append_performance_point(self, point: PortfolioPerformancePoint) -> None:
        if any(
            row.portfolio_id == point.portfolio_id and row.date == point.date
            for row in self._performance
        ):
            raise DuplicatePortfolioIdentity(
                f"Duplicate performance date: {point.portfolio_id}:{point.date}"
            )
        self._performance.append(point)

    def list_performance(self, portfolio_id: str) -> list[PortfolioPerformancePoint]:
        return sorted(
            (row for row in self._performance if row.portfolio_id == portfolio_id),
            key=lambda row: row.date,
        )

    def append_attribution(self, attribution: PortfolioAttribution) -> None:
        if any(
            row.portfolio_id == attribution.portfolio_id
            and row.period_start == attribution.period_start
            and row.period_end == attribution.period_end
            for row in self._attributions
        ):
            raise DuplicatePortfolioIdentity(
                f"Duplicate attribution period: {attribution.portfolio_id}"
            )
        self._attributions.append(attribution)

    def get_attribution(self, portfolio_id: str) -> PortfolioAttribution | None:
        rows = [
            row for row in self._attributions if row.portfolio_id == portfolio_id
        ]
        return max(rows, key=lambda row: row.period_end) if rows else None

    def append_risk(self, risk: PortfolioRiskSnapshot) -> None:
        previous = self.get_risk(risk.portfolio_id)
        if previous and risk.as_of <= previous.as_of:
            raise PortfolioAppendOnlyViolation(
                "Risk snapshots require a later as_of timestamp"
            )
        self._risks.append(risk)

    def get_risk(self, portfolio_id: str) -> PortfolioRiskSnapshot | None:
        return self._latest(self._risks, portfolio_id)

    def add_benchmark(self, benchmark: BenchmarkReference) -> None:
        if benchmark.benchmark_id in self._benchmarks:
            raise DuplicatePortfolioIdentity(
                f"Duplicate benchmark: {benchmark.benchmark_id}"
            )
        self._benchmarks[benchmark.benchmark_id] = benchmark

    def get_benchmark(self, benchmark_id: str) -> BenchmarkReference | None:
        return self._benchmarks.get(benchmark_id)

    def list_benchmarks(self) -> list[BenchmarkReference]:
        return [self._benchmarks[item] for item in sorted(self._benchmarks)]

    def append_benchmark_comparison(
        self, comparison: PortfolioBenchmarkComparison
    ) -> None:
        if any(
            row.portfolio_id == comparison.portfolio_id
            and row.benchmark_id == comparison.benchmark_id
            and row.period_start == comparison.period_start
            and row.period_end == comparison.period_end
            for row in self._comparisons
        ):
            raise DuplicatePortfolioIdentity(
                f"Duplicate benchmark comparison: {comparison.portfolio_id}"
            )
        self._comparisons.append(comparison)

    def get_benchmark_comparison(
        self, portfolio_id: str
    ) -> PortfolioBenchmarkComparison | None:
        rows = [row for row in self._comparisons if row.portfolio_id == portfolio_id]
        return max(rows, key=lambda row: row.period_end) if rows else None

    def append_portfolio_event(self, event: PortfolioEvent) -> None:
        if event.event_id in self._events:
            raise DuplicatePortfolioIdentity(f"Duplicate event: {event.event_id}")
        self._events[event.event_id] = event

    def list_portfolio_events(self, portfolio_id: str) -> list[PortfolioEvent]:
        return sorted(
            (
                row for row in self._events.values() if row.portfolio_id == portfolio_id
            ),
            key=lambda row: (row.timestamp, row.event_id),
        )


class JsonFilePortfolioOSRepository(InMemoryPortfolioOSRepository):
    """Append-only JSONL Portfolio OS repository."""

    _FILES = {
        "portfolios": Path("portfolios/portfolios.jsonl"),
        "goals": Path("portfolios/goals.jsonl"),
        "accounts": Path("accounts/accounts.jsonl"),
        "cash": Path("accounts/cash_balances.jsonl"),
        "transactions": Path("transactions/transactions.jsonl"),
        "securities": Path("holdings/securities.jsonl"),
        "holdings": Path("holdings/holdings.jsonl"),
        "lots": Path("holdings/lots.jsonl"),
        "valuations": Path("valuations/valuations.jsonl"),
        "exposures": Path("valuations/exposures.jsonl"),
        "performance": Path("valuations/performance.jsonl"),
        "attributions": Path("valuations/attributions.jsonl"),
        "risk": Path("risk/risk_snapshots.jsonl"),
        "benchmarks": Path("benchmarks/benchmarks.jsonl"),
        "comparisons": Path("benchmarks/comparisons.jsonl"),
        "events": Path("events/events.jsonl"),
    }

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        super().__init__()
        self._load()

    def _path(self, kind: str) -> Path:
        return self.root / self._FILES[kind]

    def _read_jsonl(self, kind: str) -> list[dict]:
        path = self._path(kind)
        if not path.exists():
            return []
        rows: list[dict] = []
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"Invalid JSONL in {path} at line {line_number}"
                    ) from error
        return rows

    def _load(self) -> None:
        specs = (
            ("portfolios", Portfolio, super().append_portfolio),
            ("goals", PortfolioGoal, super().add_goal),
            ("accounts", PortfolioAccount, super().add_account),
            ("cash", CashBalance, super().append_cash_balance),
            ("transactions", PortfolioTransaction, super().append_transaction),
            ("securities", SecurityReference, super().add_security),
        )
        for kind, model, operation in specs:
            for value in self._read_jsonl(kind):
                operation(model.model_validate(value))
        holdings = tuple(
            Holding.model_validate(value) for value in self._read_jsonl("holdings")
        )
        lots = tuple(
            PositionLot.model_validate(value) for value in self._read_jsonl("lots")
        )
        grouped_holdings: dict[tuple[str, object], list[Holding]] = defaultdict(list)
        for row in holdings:
            grouped_holdings[(row.portfolio_id, row.as_of)].append(row)
        for (portfolio_id, _), rows in sorted(grouped_holdings.items()):
            holding_ids = {row.holding_id for row in rows}
            related_lots = tuple(row for row in lots if row.holding_id in holding_ids)
            super().append_holdings_snapshot(portfolio_id, tuple(rows), related_lots)
        remaining = (
            ("valuations", PortfolioValuation, super().append_valuation),
            ("exposures", ExposureSnapshot, super().append_exposure),
            ("performance", PortfolioPerformancePoint, super().append_performance_point),
            ("attributions", PortfolioAttribution, super().append_attribution),
            ("risk", PortfolioRiskSnapshot, super().append_risk),
            ("benchmarks", BenchmarkReference, super().add_benchmark),
            (
                "comparisons",
                PortfolioBenchmarkComparison,
                super().append_benchmark_comparison,
            ),
            ("events", PortfolioEvent, super().append_portfolio_event),
        )
        for kind, model, operation in remaining:
            for value in self._read_jsonl(kind):
                operation(model.model_validate(value))

    def _append(self, kind: str, model: PortfolioOSModel) -> None:
        path = self._path(kind)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            model.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(payload + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def append_portfolio(self, record: Portfolio) -> None:
        super().append_portfolio(record)
        self._append("portfolios", record)

    def add_goal(self, goal: PortfolioGoal) -> None:
        super().add_goal(goal)
        self._append("goals", goal)

    def add_account(self, account: PortfolioAccount) -> None:
        super().add_account(account)
        self._append("accounts", account)

    def append_cash_balance(self, balance: CashBalance) -> None:
        super().append_cash_balance(balance)
        self._append("cash", balance)

    def append_transaction(self, transaction: PortfolioTransaction) -> None:
        super().append_transaction(transaction)
        self._append("transactions", transaction)

    def add_security(self, security: SecurityReference) -> None:
        super().add_security(security)
        self._append("securities", security)

    def append_holdings_snapshot(
        self,
        portfolio_id: str,
        holdings: tuple[Holding, ...],
        lots: tuple[PositionLot, ...],
    ) -> None:
        super().append_holdings_snapshot(portfolio_id, holdings, lots)
        for row in holdings:
            self._append("holdings", row)
        for row in lots:
            self._append("lots", row)

    def append_valuation(self, valuation: PortfolioValuation) -> None:
        super().append_valuation(valuation)
        self._append("valuations", valuation)

    def append_exposure(self, exposure: ExposureSnapshot) -> None:
        super().append_exposure(exposure)
        self._append("exposures", exposure)

    def append_performance_point(self, point: PortfolioPerformancePoint) -> None:
        super().append_performance_point(point)
        self._append("performance", point)

    def append_attribution(self, attribution: PortfolioAttribution) -> None:
        super().append_attribution(attribution)
        self._append("attributions", attribution)

    def append_risk(self, risk: PortfolioRiskSnapshot) -> None:
        super().append_risk(risk)
        self._append("risk", risk)

    def add_benchmark(self, benchmark: BenchmarkReference) -> None:
        super().add_benchmark(benchmark)
        self._append("benchmarks", benchmark)

    def append_benchmark_comparison(
        self, comparison: PortfolioBenchmarkComparison
    ) -> None:
        super().append_benchmark_comparison(comparison)
        self._append("comparisons", comparison)

    def append_portfolio_event(self, event: PortfolioEvent) -> None:
        super().append_portfolio_event(event)
        self._append("events", event)


__all__ = (
    "AccountRepository",
    "BenchmarkRepository",
    "DuplicatePortfolioIdentity",
    "HoldingRepository",
    "InMemoryPortfolioOSRepository",
    "JsonFilePortfolioOSRepository",
    "PortfolioAppendOnlyViolation",
    "PortfolioEventRepository",
    "PortfolioRepository",
    "RiskRepository",
    "TransactionRepository",
    "ValuationRepository",
)
