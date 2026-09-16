from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Mapping, Sequence

from app.platform.hashing import deterministic_id
from app.portfolio_os.errors import InsufficientPosition, InvalidTransaction
from app.portfolio_os.models import (
    CashLedgerResult,
    Holding,
    HoldingsRebuildResult,
    PortfolioMetrics,
    PortfolioPerformancePoint,
    PortfolioTransaction,
    PositionLot,
    SecurityReference,
    TransactionType,
    ZERO,
)


@dataclass
class _OpenLot:
    buy_transaction_id: str
    security_id: str
    account_id: str
    quantity: Decimal
    remaining_quantity: Decimal
    entry_price: Decimal
    entry_date: object
    strategy_id: str | None
    source_transaction_ids: list[str] = field(default_factory=list)


def calculate_cash_ledger(
    portfolio_id: str,
    transactions: Sequence[PortfolioTransaction],
    *,
    as_of: datetime,
) -> CashLedgerResult:
    balances: dict[str, Decimal] = defaultdict(lambda: ZERO)
    accounts: dict[str, Decimal] = defaultdict(lambda: ZERO)
    eligible = [
        row
        for row in transactions
        if row.portfolio_id == portfolio_id and row.trade_date <= as_of.date()
    ]
    for transaction in sorted(
        eligible,
        key=lambda row: (row.trade_date, row.settlement_date, row.transaction_id),
    ):
        balances[transaction.currency] += transaction.net_amount
        accounts[transaction.account_id] += transaction.net_amount
    return CashLedgerResult(
        portfolio_id=portfolio_id,
        as_of=as_of,
        balances=dict(sorted(balances.items())),
        account_balances=dict(sorted(accounts.items())),
        transaction_count=len(eligible),
    )


class FIFOAccountingEngine:
    """Deterministic FIFO accounting with buy costs embedded in lot basis."""

    def rebuild(
        self,
        *,
        portfolio_id: str,
        transactions: Sequence[PortfolioTransaction],
        securities: Mapping[str, SecurityReference],
        prices: Mapping[str, Decimal],
        as_of: datetime,
        source: str,
    ) -> HoldingsRebuildResult:
        eligible = sorted(
            (
                row
                for row in transactions
                if row.portfolio_id == portfolio_id
                and row.trade_date <= as_of.date()
                and row.transaction_type
                in {TransactionType.BUY, TransactionType.SELL}
            ),
            key=lambda row: (row.trade_date, row.settlement_date, row.transaction_id),
        )
        open_lots: dict[tuple[str, str], list[_OpenLot]] = defaultdict(list)
        realized: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for transaction in eligible:
            security_id = transaction.security_id
            if security_id is None or security_id not in securities:
                raise InvalidTransaction(
                    f"Transaction references unknown security: {security_id}"
                )
            key = (transaction.account_id, security_id)
            if transaction.transaction_type == TransactionType.BUY:
                all_in_cost = (
                    transaction.gross_amount + transaction.fees + transaction.taxes
                )
                entry_price = all_in_cost / transaction.quantity
                open_lots[key].append(
                    _OpenLot(
                        buy_transaction_id=transaction.transaction_id,
                        security_id=security_id,
                        account_id=transaction.account_id,
                        quantity=transaction.quantity,
                        remaining_quantity=transaction.quantity,
                        entry_price=entry_price,
                        entry_date=transaction.trade_date,
                        strategy_id=transaction.strategy_id,
                        source_transaction_ids=[transaction.transaction_id],
                    )
                )
                continue
            available = sum(
                (lot.remaining_quantity for lot in open_lots[key]), ZERO
            )
            if transaction.quantity > available:
                raise InsufficientPosition(
                    f"SELL {transaction.transaction_id} quantity {transaction.quantity} "
                    f"exceeds available {available}"
                )
            remaining_to_sell = transaction.quantity
            consumed_cost = ZERO
            for lot in open_lots[key]:
                if remaining_to_sell <= ZERO:
                    break
                consumed = min(lot.remaining_quantity, remaining_to_sell)
                consumed_cost += consumed * lot.entry_price
                lot.remaining_quantity -= consumed
                lot.source_transaction_ids.append(transaction.transaction_id)
                remaining_to_sell -= consumed
            proceeds = transaction.gross_amount - transaction.fees - transaction.taxes
            realized[transaction.currency] += proceeds - consumed_cost

        holdings: list[Holding] = []
        lots: list[PositionLot] = []
        for (account_id, security_id), security_lots in sorted(open_lots.items()):
            active = [lot for lot in security_lots if lot.remaining_quantity > ZERO]
            if not active:
                continue
            security = securities[security_id]
            if security_id not in prices:
                raise InvalidTransaction(f"Missing price for security: {security_id}")
            quantity = sum((lot.remaining_quantity for lot in active), ZERO)
            cost_basis = sum(
                (lot.remaining_quantity * lot.entry_price for lot in active), ZERO
            )
            current_price = Decimal(prices[security_id])
            market_value = quantity * current_price
            unrealized = market_value - cost_basis
            transaction_ids = sorted(
                {item for lot in active for item in lot.source_transaction_ids}
            )
            holding_id = deterministic_id(
                "HLD",
                portfolio_id,
                account_id,
                security_id,
                as_of,
                transaction_ids,
            )
            strategy_values: dict[str, Decimal] = defaultdict(lambda: ZERO)
            for lot in active:
                if lot.strategy_id:
                    strategy_values[lot.strategy_id] += (
                        lot.remaining_quantity * current_price
                    )
                lots.append(
                    PositionLot(
                        lot_id=deterministic_id(
                            "LOT", lot.buy_transaction_id, as_of, lot.remaining_quantity
                        ),
                        holding_id=holding_id,
                        security_id=security_id,
                        quantity=lot.quantity,
                        entry_price=lot.entry_price,
                        entry_date=lot.entry_date,
                        remaining_quantity=lot.remaining_quantity,
                        cost_basis=lot.remaining_quantity * lot.entry_price,
                        source_transaction_ids=tuple(lot.source_transaction_ids),
                        strategy_id=lot.strategy_id,
                        metadata={"lot_policy": "FIFO"},
                    )
                )
            holdings.append(
                Holding(
                    holding_id=holding_id,
                    portfolio_id=portfolio_id,
                    account_id=account_id,
                    security_id=security_id,
                    quantity=quantity,
                    average_cost=cost_basis / quantity,
                    current_price=current_price,
                    market_value=market_value,
                    cost_basis=cost_basis,
                    unrealized_pnl=unrealized,
                    unrealized_pnl_pct=(unrealized / cost_basis),
                    currency=security.currency,
                    as_of=as_of,
                    source=source,
                    strategy_attribution=dict(sorted(strategy_values.items())),
                    metadata={
                        "instrument_type": security.instrument_type.value,
                        "sector": security.metadata.get("sector"),
                        "industry": security.metadata.get("industry"),
                        "lot_policy": "FIFO",
                    },
                )
            )
        return HoldingsRebuildResult(
            portfolio_id=portfolio_id,
            as_of=as_of,
            lots=tuple(sorted(lots, key=lambda row: row.lot_id)),
            holdings=tuple(sorted(holdings, key=lambda row: row.holding_id)),
            realized_pnl=dict(sorted(realized.items())),
            transaction_ids=tuple(row.transaction_id for row in eligible),
        )


def calculate_portfolio_metrics(
    portfolio_id: str,
    points: Sequence[PortfolioPerformancePoint],
    transactions: Sequence[PortfolioTransaction],
) -> PortfolioMetrics:
    ordered = sorted(points, key=lambda row: row.date)
    if not ordered:
        raise ValueError("At least one performance point is required")
    totals = [row.equity + row.cash for row in ordered]
    initial = totals[0]
    final = totals[-1]
    total_return = (final / initial - Decimal("1")) if initial else ZERO
    days = (ordered[-1].date - ordered[0].date).days
    cagr = None
    if days > 0 and initial > ZERO and final >= ZERO:
        years = days / 365.25
        cagr = Decimal(str(math.pow(float(final / initial), 1 / years) - 1))
    peak = totals[0]
    max_drawdown = ZERO
    for total in totals:
        peak = max(peak, total)
        if peak > ZERO:
            max_drawdown = min(max_drawdown, total / peak - Decimal("1"))
    returns = [row.daily_return for row in ordered[1:]]
    if returns:
        mean = sum(returns, ZERO) / Decimal(len(returns))
        variance = sum(((item - mean) ** 2 for item in returns), ZERO) / Decimal(
            len(returns)
        )
        volatility = Decimal(str(math.sqrt(float(variance)) * math.sqrt(252)))
        positive_rate = Decimal(sum(item > ZERO for item in returns)) / Decimal(
            len(returns)
        )
    else:
        volatility = ZERO
        positive_rate = ZERO
    relevant = [row for row in transactions if row.portfolio_id == portfolio_id]
    traded = sum(
        (
            row.gross_amount
            for row in relevant
            if row.transaction_type in {TransactionType.BUY, TransactionType.SELL}
        ),
        ZERO,
    )
    average_value = sum(totals, ZERO) / Decimal(len(totals))
    turnover = traded / average_value if average_value else ZERO
    costs = sum((row.fees + row.taxes for row in relevant), ZERO)
    utilizations = [
        row.invested_value / (row.equity + row.cash)
        if row.equity + row.cash
        else ZERO
        for row in ordered
    ]
    return PortfolioMetrics(
        portfolio_id=portfolio_id,
        total_return=total_return,
        cagr=cagr,
        max_drawdown=max_drawdown,
        volatility=volatility,
        positive_period_rate=positive_rate,
        turnover=turnover,
        costs=costs,
        cash_utilization=sum(utilizations, ZERO) / Decimal(len(utilizations)),
        period_start=ordered[0].date,
        period_end=ordered[-1].date,
    )


__all__ = (
    "FIFOAccountingEngine",
    "calculate_cash_ledger",
    "calculate_portfolio_metrics",
)
