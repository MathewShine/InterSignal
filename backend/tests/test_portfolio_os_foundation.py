from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.platform.hashing import canonical_hash
from app.portfolio_os.accounting import (
    FIFOAccountingEngine,
    calculate_cash_ledger,
    calculate_portfolio_metrics,
)
from app.portfolio_os.builder import (
    COMMAND_PROFILE,
    COMMAND_VERSION,
    MANIFEST_VERSION,
    MANUAL_PORTFOLIO_ID,
    PLATFORM_FOUNDATION_HASH,
    RESEARCH_PORTFOLIO_ID,
    RESEARCH_WORKBENCH_HASH,
    REQUIRED_CHECKPOINT,
    verify_portfolio_os_inputs,
)
from app.portfolio_os.errors import (
    AccountNotFound,
    CurrencyMismatch,
    InsufficientPosition,
    InvalidPortfolioState,
    InvalidTransaction,
    PortfolioNotFound,
    SecurityNotFound,
)
from app.portfolio_os.models import (
    AccountProvider,
    AccountStatus,
    AccountType,
    BenchmarkReference,
    BrokerSyncState,
    CashBalance,
    CorporateActionType,
    ExposureSnapshot,
    GoalStatus,
    InstrumentType,
    IntegrityStatus,
    Portfolio,
    PortfolioAccount,
    PortfolioBenchmarkComparison,
    PortfolioGoal,
    PortfolioPerformancePoint,
    PortfolioRiskSnapshot,
    PortfolioStatus,
    PortfolioTransaction,
    PortfolioType,
    PortfolioValuation,
    RiskFlag,
    SecurityReference,
    TransactionType,
    ZERO,
)
from app.portfolio_os.repositories import (
    AccountRepository,
    BenchmarkRepository,
    DuplicatePortfolioIdentity,
    HoldingRepository,
    InMemoryPortfolioOSRepository,
    JsonFilePortfolioOSRepository,
    PortfolioEventRepository,
    PortfolioRepository,
    RiskRepository,
    TransactionRepository,
    ValuationRepository,
)
from app.portfolio_os.service import PortfolioOSService


PROJECT_ROOT = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc)


def _portfolio(
    portfolio_id: str = "PORT-TEST-001",
    *,
    currency: str = "INR",
    portfolio_type: PortfolioType = PortfolioType.MANUAL,
) -> Portfolio:
    return Portfolio(
        portfolio_id=portfolio_id,
        name="Synthetic Test Portfolio",
        portfolio_type=portfolio_type,
        base_currency=currency,
        market_scope=("SYNTHETIC",),
        status=PortfolioStatus.RESEARCH_ONLY,
        created_at=T0,
        updated_at=T0,
        metadata={"synthetic": True, "live": False},
    )


def _account(
    portfolio_id: str = "PORT-TEST-001",
    *,
    account_id: str = "ACCT-TEST-001",
    currency: str = "INR",
    instrument_account: AccountType = AccountType.BROKERAGE,
) -> PortfolioAccount:
    return PortfolioAccount(
        account_id=account_id,
        portfolio_id=portfolio_id,
        account_type=instrument_account,
        provider=AccountProvider.MANUAL,
        provider_account_reference=f"SYNTH-{account_id}",
        currency=currency,
        status=AccountStatus.ACTIVE,
        created_at=T0 + timedelta(minutes=1),
        broker_sync_state=BrokerSyncState.NEVER_SYNCED,
        metadata={"synthetic": True},
    )


def _security(
    security_id: str = "SEC-TEST-001",
    *,
    currency: str = "INR",
    instrument_type: InstrumentType = InstrumentType.EQUITY,
) -> SecurityReference:
    return SecurityReference(
        security_id=security_id,
        market="SYNTHETIC",
        exchange="SYNTHETIC",
        symbol=security_id,
        instrument_type=instrument_type,
        currency=currency,
        name=f"Synthetic {security_id}",
        metadata={"sector": "Synthetic Sector", "industry": "Synthetic Industry"},
    )


def _transaction(
    transaction_id: str,
    transaction_type: TransactionType,
    *,
    portfolio_id: str = "PORT-TEST-001",
    account_id: str = "ACCT-TEST-001",
    security_id: str | None = "SEC-TEST-001",
    quantity: str = "10",
    price: str = "10",
    fees: str = "0",
    taxes: str = "0",
    trade_date: date = date(2026, 9, 16),
    currency: str = "INR",
) -> PortfolioTransaction:
    quantity_value = Decimal(quantity)
    price_value = Decimal(price)
    fees_value = Decimal(fees)
    taxes_value = Decimal(taxes)
    gross = quantity_value * price_value
    if transaction_type == TransactionType.BUY:
        net = -(gross + fees_value + taxes_value)
    elif transaction_type == TransactionType.SELL:
        net = gross - fees_value - taxes_value
    else:
        net = gross
    return PortfolioTransaction(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        account_id=account_id,
        security_id=security_id,
        transaction_type=transaction_type,
        quantity=quantity_value,
        price=price_value,
        gross_amount=gross,
        fees=fees_value,
        taxes=taxes_value,
        net_amount=net,
        currency=currency,
        trade_date=trade_date,
        settlement_date=trade_date,
        source="SYNTHETIC_TEST",
        metadata={"synthetic": True},
    )


def _deposit(
    transaction_id: str = "TXN-DEPOSIT-001",
    *,
    portfolio_id: str = "PORT-TEST-001",
    account_id: str = "ACCT-TEST-001",
    amount: str = "1000",
    currency: str = "INR",
) -> PortfolioTransaction:
    return PortfolioTransaction(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        account_id=account_id,
        transaction_type=TransactionType.DEPOSIT,
        gross_amount=Decimal(amount),
        net_amount=Decimal(amount),
        currency=currency,
        trade_date=date(2026, 9, 16),
        settlement_date=date(2026, 9, 16),
        source="SYNTHETIC_TEST",
    )


def _service_with_identity(
    *,
    repository: InMemoryPortfolioOSRepository | None = None,
    portfolio: Portfolio | None = None,
    account: PortfolioAccount | None = None,
    security: SecurityReference | None = None,
) -> tuple[PortfolioOSService, InMemoryPortfolioOSRepository]:
    store = repository or InMemoryPortfolioOSRepository()
    service = PortfolioOSService.from_repository(store)
    portfolio_value = portfolio or _portfolio()
    account_value = account or _account(portfolio_value.portfolio_id)
    security_value = security or _security()
    service.create_portfolio(
        portfolio_value, actor="TEST", reason="synthetic test portfolio"
    )
    service.register_account(
        account_value,
        actor="TEST",
        reason="synthetic test account",
        event_timestamp=T0 + timedelta(minutes=1),
    )
    service.register_security(
        portfolio_value.portfolio_id,
        security_value,
        actor="TEST",
        reason="synthetic test security",
        event_timestamp=T0 + timedelta(minutes=2),
    )
    return service, store


def _complete_service() -> PortfolioOSService:
    service, _ = _service_with_identity()
    deposit = _deposit()
    buy = _transaction(
        "TXN-BUY-001", TransactionType.BUY, quantity="10", price="10", fees="1"
    )
    service.record_transaction(
        deposit,
        actor="TEST",
        reason="fund account",
        event_timestamp=T0 + timedelta(minutes=3),
    )
    service.record_transaction(
        buy,
        actor="TEST",
        reason="synthetic buy",
        event_timestamp=T0 + timedelta(minutes=4),
    )
    service.record_cash_balance(
        CashBalance(
            account_id="ACCT-TEST-001",
            currency="INR",
            available_cash=Decimal("899"),
            settled_cash=Decimal("899"),
            as_of=T0 + timedelta(minutes=5),
            source="SYNTHETIC_TEST",
        ),
        actor="TEST",
        reason="reconciled cash",
    )
    rebuild = service.rebuild_holdings(
        "PORT-TEST-001",
        prices={"SEC-TEST-001": Decimal("12")},
        as_of=T0 + timedelta(minutes=6),
        source="SYNTHETIC_TEST",
        actor="TEST",
        reason="rebuild test holdings",
    )
    service.record_valuation(
        PortfolioValuation(
            portfolio_id="PORT-TEST-001",
            as_of=T0 + timedelta(minutes=7),
            gross_market_value=Decimal("120"),
            cash=Decimal("899"),
            net_liquidation_value=Decimal("1019"),
            cost_basis=Decimal("101"),
            realized_pnl=ZERO,
            unrealized_pnl=Decimal("19"),
            total_pnl=Decimal("19"),
            currency="INR",
            source="SYNTHETIC_TEST",
        ),
        actor="TEST",
        reason="valuation",
    )
    assert rebuild.holdings[0].cost_basis == Decimal("101")
    return service


def test_command_identity_and_checkpoint_are_exact() -> None:
    assert COMMAND_VERSION == "INTERSIGNAL_PORTFOLIO_OS_FOUNDATION_V1"
    assert COMMAND_PROFILE == "PORTFOLIO_ACCOUNT_HOLDINGS_TRANSACTION_RISK_DOMAIN_V1"
    assert MANIFEST_VERSION == "INTERSIGNAL_PORTFOLIO_OS_FOUNDATION_MANIFEST_V1"
    assert REQUIRED_CHECKPOINT == "f990c3c96d9b8a619953041006affb986914fc5c"
    assert PLATFORM_FOUNDATION_HASH == "ec270dcb640116fe56709c784b4ca915bd794b0a96847e11fb561460dfed877f"
    assert RESEARCH_WORKBENCH_HASH == "c0c1ba634f584b4532e99e4f015be83e7e0c069eafb3cd5ca6a1fc7cfaf8f52b"


def test_input_verifier_accepts_current_checkpoint_and_prior_hashes() -> None:
    result = verify_portfolio_os_inputs(PROJECT_ROOT)
    assert result["head"] == REQUIRED_CHECKPOINT
    assert result["foundation"]["platform_foundation_hash"] == PLATFORM_FOUNDATION_HASH
    assert result["workbench"]["research_workbench_backend_hash"] == RESEARCH_WORKBENCH_HASH


def test_portfolio_account_security_cash_and_identifiers() -> None:
    portfolio = _portfolio()
    account = _account()
    security = _security()
    cash = CashBalance(
        account_id=account.account_id,
        currency="inr",
        available_cash=Decimal("50"),
        settled_cash=Decimal("55"),
        reserved_cash=Decimal("5"),
        as_of=T0,
        source="SYNTHETIC_TEST",
    )
    assert portfolio.portfolio_id == "PORT-TEST-001"
    assert account.provider == AccountProvider.MANUAL
    assert account.broker_sync_state == BrokerSyncState.NEVER_SYNCED
    assert security.currency == "INR"
    assert cash.currency == "INR"


def test_cash_rejects_invalid_reservation() -> None:
    with pytest.raises(ValidationError):
        CashBalance(
            account_id="A",
            currency="INR",
            available_cash=Decimal("100"),
            settled_cash=Decimal("100"),
            reserved_cash=Decimal("1"),
            as_of=T0,
            source="TEST",
        )


def test_buy_and_sell_transaction_arithmetic_is_guarded() -> None:
    buy = _transaction(
        "TXN-BUY", TransactionType.BUY, quantity="4", price="25", fees="2", taxes="1"
    )
    sell = _transaction(
        "TXN-SELL", TransactionType.SELL, quantity="4", price="30", fees="2", taxes="1"
    )
    assert buy.net_amount == Decimal("-103")
    assert sell.net_amount == Decimal("117")
    data = buy.model_dump(mode="python")
    data["net_amount"] = Decimal("-100")
    with pytest.raises(ValidationError):
        PortfolioTransaction.model_validate(data)


def test_transaction_types_and_corporate_action_placeholders_are_complete() -> None:
    required = {
        "BUY", "SELL", "DIVIDEND", "INTEREST", "FEE", "TAX", "DEPOSIT",
        "WITHDRAWAL", "TRANSFER_IN", "TRANSFER_OUT", "CORPORATE_ACTION",
        "ADJUSTMENT", "REVERSAL",
    }
    assert {item.value for item in TransactionType} == required
    assert {item.value for item in CorporateActionType} == {
        "SPLIT", "BONUS", "DIVIDEND", "RIGHTS", "MERGER_DEMERGER_ADJUSTMENT"
    }


def test_fifo_realized_unrealized_and_multi_lot_cost_basis() -> None:
    transactions = [
        _transaction("B1", TransactionType.BUY, quantity="10", price="10", trade_date=date(2026, 9, 14)),
        _transaction("B2", TransactionType.BUY, quantity="10", price="20", trade_date=date(2026, 9, 15)),
        _transaction("S1", TransactionType.SELL, quantity="15", price="30", trade_date=date(2026, 9, 16)),
    ]
    result = FIFOAccountingEngine().rebuild(
        portfolio_id="PORT-TEST-001",
        transactions=transactions,
        securities={"SEC-TEST-001": _security()},
        prices={"SEC-TEST-001": Decimal("40")},
        as_of=T0,
        source="SYNTHETIC_TEST",
    )
    assert result.realized_pnl == {"INR": Decimal("250")}
    assert len(result.lots) == 1
    assert result.lots[0].remaining_quantity == Decimal("5")
    assert result.lots[0].cost_basis == Decimal("100")
    assert result.holdings[0].quantity == Decimal("5")
    assert result.holdings[0].market_value == Decimal("200")
    assert result.holdings[0].unrealized_pnl == Decimal("100")


def test_fifo_rejects_sell_above_available_quantity() -> None:
    transactions = [
        _transaction("B1", TransactionType.BUY, quantity="2", price="10"),
        _transaction("S1", TransactionType.SELL, quantity="3", price="12"),
    ]
    with pytest.raises(InsufficientPosition):
        FIFOAccountingEngine().rebuild(
            portfolio_id="PORT-TEST-001",
            transactions=transactions,
            securities={"SEC-TEST-001": _security()},
            prices={"SEC-TEST-001": Decimal("12")},
            as_of=T0,
            source="SYNTHETIC_TEST",
        )


def test_cash_ledger_supports_deposit_buy_sell_fees_taxes_and_dividend() -> None:
    records = [
        _deposit(amount="1000"),
        _transaction("BUY", TransactionType.BUY, quantity="10", price="10", fees="1", taxes="1"),
        _transaction("SELL", TransactionType.SELL, quantity="2", price="15", fees="1", taxes="1"),
        PortfolioTransaction(
            transaction_id="DIV",
            portfolio_id="PORT-TEST-001",
            account_id="ACCT-TEST-001",
            transaction_type=TransactionType.DIVIDEND,
            gross_amount=Decimal("5"),
            net_amount=Decimal("5"),
            currency="INR",
            trade_date=date(2026, 9, 16),
            settlement_date=date(2026, 9, 16),
            source="SYNTHETIC_TEST",
        ),
    ]
    ledger = calculate_cash_ledger("PORT-TEST-001", records, as_of=T0)
    assert ledger.balances == {"INR": Decimal("931")}
    assert ledger.account_balances == {"ACCT-TEST-001": Decimal("931")}
    assert ledger.transaction_count == 4


def test_required_repository_interfaces_have_in_memory_implementation() -> None:
    repository = InMemoryPortfolioOSRepository()
    interfaces = (
        PortfolioRepository,
        AccountRepository,
        TransactionRepository,
        HoldingRepository,
        ValuationRepository,
        RiskRepository,
        BenchmarkRepository,
        PortfolioEventRepository,
    )
    assert all(isinstance(repository, interface) for interface in interfaces)


def test_service_reads_writes_holdings_rebuild_and_append_only_events() -> None:
    service = _complete_service()
    assert service.get_portfolio("PORT-TEST-001").portfolio_id == "PORT-TEST-001"
    assert len(service.list_portfolios()) == 1
    assert len(service.get_accounts("PORT-TEST-001")) == 1
    assert len(service.get_transactions("PORT-TEST-001")) == 2
    assert service.get_holdings("PORT-TEST-001")[0].quantity == Decimal("10")
    assert service.get_lots("PORT-TEST-001")[0].entry_price == Decimal("10.1")
    assert service.get_valuation("PORT-TEST-001").total_pnl == Decimal("19")
    events = service.get_portfolio_events("PORT-TEST-001")
    assert len(events) == 8
    assert events[0].event_type.value == "PORTFOLIO_CREATED"
    assert all(events[index].timestamp <= events[index + 1].timestamp for index in range(len(events) - 1))


def test_service_stable_not_found_errors() -> None:
    service = PortfolioOSService.from_repository(InMemoryPortfolioOSRepository())
    with pytest.raises(PortfolioNotFound):
        service.get_portfolio("MISSING")
    service.create_portfolio(_portfolio(), actor="TEST", reason="create")
    with pytest.raises(AccountNotFound):
        service.record_cash_balance(
            CashBalance(
                account_id="MISSING", currency="INR", available_cash=ZERO,
                settled_cash=ZERO, as_of=T0, source="TEST"
            ),
            actor="TEST", reason="missing account"
        )
    with pytest.raises(SecurityNotFound):
        service._security("MISSING")


def test_append_only_repositories_reject_duplicate_identity() -> None:
    repository = InMemoryPortfolioOSRepository()
    repository.append_transaction(_deposit())
    with pytest.raises(DuplicatePortfolioIdentity):
        repository.append_transaction(_deposit())


def test_reversal_requires_correction_linkage() -> None:
    service, _ = _service_with_identity()
    reversal = PortfolioTransaction(
        transaction_id="REV-001",
        portfolio_id="PORT-TEST-001",
        account_id="ACCT-TEST-001",
        transaction_type=TransactionType.REVERSAL,
        net_amount=Decimal("100"),
        currency="INR",
        trade_date=date(2026, 9, 16),
        settlement_date=date(2026, 9, 16),
        source="SYNTHETIC_TEST",
    )
    with pytest.raises(InvalidTransaction):
        service.record_transaction(
            reversal, actor="TEST", reason="invalid reversal", event_timestamp=T0 + timedelta(minutes=3)
        )


def test_cash_and_valuation_reconciliation_is_healthy() -> None:
    service = _complete_service()
    result = service.reconcile("PORT-TEST-001", as_of=T0 + timedelta(minutes=8))
    assert result.status == IntegrityStatus.HEALTHY
    assert result.cash_consistent
    assert result.positions_consistent
    assert result.transaction_totals_consistent
    assert result.cost_basis_consistent
    assert result.valuation_consistent
    assert result.errors == ()


def test_valuation_snapshot_is_immutable_and_hashed() -> None:
    snapshot = _complete_service().create_valuation_snapshot("PORT-TEST-001")
    assert snapshot.snapshot_id.startswith("VSNP-")
    assert len(snapshot.snapshot_hash) == 64
    with pytest.raises(ValidationError):
        snapshot.snapshot_hash = "changed"


def test_exposure_and_risk_snapshots_are_available() -> None:
    service = _complete_service()
    exposure = service.calculate_exposure("PORT-TEST-001", as_of=T0 + timedelta(minutes=8))
    service.record_exposure(
        exposure, actor="TEST", reason="exposure", event_timestamp=T0 + timedelta(minutes=8)
    )
    risk = PortfolioRiskSnapshot(
        portfolio_id="PORT-TEST-001",
        as_of=T0 + timedelta(minutes=9),
        drawdown=ZERO,
        volatility=Decimal("0.1"),
        concentration=max(exposure.security_concentration.values()),
        top_1_weight=max(exposure.security_concentration.values()),
        top_5_weight=sum(exposure.security_concentration.values(), ZERO),
        cash_pct=exposure.cash_pct or ZERO,
        turnover=Decimal("0.1"),
        cost_drag=Decimal("0.001"),
        gross_exposure=exposure.gross_exposure,
        net_exposure=exposure.net_exposure,
        risk_flags=exposure.risk_flags,
    )
    service.record_risk_snapshot(risk, actor="TEST", reason="risk")
    assert isinstance(service.get_exposure("PORT-TEST-001"), ExposureSnapshot)
    assert service.get_risk("PORT-TEST-001") == risk


def test_multi_currency_state_flags_fx_and_blocks_unconverted_valuation() -> None:
    portfolio = _portfolio(currency="INR")
    account = _account(currency="USD")
    security = _security(currency="USD")
    service, _ = _service_with_identity(
        portfolio=portfolio, account=account, security=security
    )
    service.record_transaction(
        _deposit(currency="USD"),
        actor="TEST", reason="USD deposit", event_timestamp=T0 + timedelta(minutes=3)
    )
    service.record_cash_balance(
        CashBalance(
            account_id=account.account_id, currency="USD", available_cash=Decimal("1000"),
            settled_cash=Decimal("1000"), as_of=T0 + timedelta(minutes=4), source="TEST"
        ),
        actor="TEST", reason="USD cash"
    )
    exposure = service.calculate_exposure(portfolio.portfolio_id, as_of=T0 + timedelta(minutes=5))
    assert RiskFlag.FX_CONVERSION_REQUIRED in exposure.risk_flags
    reconciliation = service.reconcile(portfolio.portfolio_id, as_of=T0 + timedelta(minutes=5))
    assert RiskFlag.FX_CONVERSION_REQUIRED in reconciliation.risk_flags
    with pytest.raises(CurrencyMismatch):
        service.record_valuation(
            PortfolioValuation(
                portfolio_id=portfolio.portfolio_id,
                as_of=T0 + timedelta(minutes=6),
                gross_market_value=ZERO,
                cash=Decimal("1000"),
                net_liquidation_value=Decimal("1000"),
                cost_basis=ZERO,
                realized_pnl=ZERO,
                unrealized_pnl=ZERO,
                total_pnl=ZERO,
                currency="INR",
                source="TEST",
            ),
            actor="TEST", reason="requires FX"
        )


def test_performance_metrics_are_deterministic() -> None:
    points = [
        PortfolioPerformancePoint(
            portfolio_id="P", date=date(2026, 1, 1), equity=Decimal("50"),
            cash=Decimal("50"), invested_value=Decimal("50"), daily_return=ZERO,
            cumulative_return=ZERO
        ),
        PortfolioPerformancePoint(
            portfolio_id="P", date=date(2027, 1, 1), equity=Decimal("90"),
            cash=Decimal("20"), invested_value=Decimal("90"), daily_return=Decimal("0.1"),
            cumulative_return=Decimal("0.1")
        ),
    ]
    metrics = calculate_portfolio_metrics("P", points, [])
    assert metrics.total_return == Decimal("0.1")
    assert metrics.max_drawdown == ZERO
    assert metrics.positive_period_rate == Decimal("1")
    assert metrics.costs == ZERO


def test_benchmark_comparison_and_linkage() -> None:
    service, _ = _service_with_identity()
    benchmark = BenchmarkReference(
        benchmark_id="BMK-TEST", name="Synthetic Index", market="SYNTHETIC",
        currency="INR", source="SYNTHETIC_TEST", version="V1"
    )
    service.link_benchmark(
        "PORT-TEST-001", benchmark, actor="TEST", reason="benchmark",
        event_timestamp=T0 + timedelta(minutes=3)
    )
    comparison = PortfolioBenchmarkComparison(
        portfolio_id="PORT-TEST-001", benchmark_id=benchmark.benchmark_id,
        portfolio_return=Decimal("0.1"), benchmark_return=Decimal("0.08"),
        active_return=Decimal("0.02"), relative_drawdown=Decimal("-0.01"),
        tracking_difference=Decimal("0.02"), period_start=date(2026, 1, 1),
        period_end=date(2026, 9, 16)
    )
    service.record_benchmark_comparison(
        comparison, actor="TEST", reason="comparison", event_timestamp=T0 + timedelta(minutes=4)
    )
    assert service.get_benchmark_comparison("PORT-TEST-001") == comparison
    assert service.get_portfolio("PORT-TEST-001").benchmark_ids == ("BMK-TEST",)


def test_attribution_is_deterministic_and_reports_costs() -> None:
    service = _complete_service()
    attribution = service.calculate_attribution(
        "PORT-TEST-001", period_start=date(2026, 9, 1), period_end=date(2026, 9, 30)
    )
    assert attribution.security_attribution == {"SEC-TEST-001": Decimal("19")}
    assert attribution.sector_attribution == {"Synthetic Sector": Decimal("19")}
    assert attribution.transaction_cost_attribution == Decimal("-1")
    assert attribution.total_contribution == Decimal("18")


def test_mutual_fund_goal_and_broker_sync_compatibility() -> None:
    portfolio = _portfolio(portfolio_type=PortfolioType.INVESTMENT)
    account = _account(instrument_account=AccountType.MUTUAL_FUND)
    security = _security(instrument_type=InstrumentType.MUTUAL_FUND)
    service, _ = _service_with_identity(
        portfolio=portfolio, account=account, security=security
    )
    goal = PortfolioGoal(
        goal_id="GOAL-TEST", portfolio_id=portfolio.portfolio_id, name="Synthetic goal",
        target_amount=Decimal("10000"), target_date=date(2030, 1, 1), currency="INR",
        status=GoalStatus.ACTIVE, metadata={"recommendation": False}
    )
    service.add_goal(
        goal, actor="TEST", reason="goal", event_timestamp=T0 + timedelta(minutes=3)
    )
    assert service.get_goals(portfolio.portfolio_id) == [goal]
    assert service.get_accounts(portfolio.portfolio_id)[0].broker_sync_state == BrokerSyncState.NEVER_SYNCED
    assert security.instrument_type == InstrumentType.MUTUAL_FUND


def test_strategy_evidence_and_lineage_links_are_optional_but_guarded() -> None:
    repository = InMemoryPortfolioOSRepository()
    service = PortfolioOSService.from_repository(
        repository,
        valid_strategy_ids={"STRAT-OK"},
        valid_evidence_ids={"EVID-OK"},
        valid_lineage_node_ids={"LIN-OK"},
    )
    service.create_portfolio(_portfolio(), actor="TEST", reason="create")
    service.register_account(
        _account(), actor="TEST", reason="account", event_timestamp=T0 + timedelta(minutes=1)
    )
    service.register_security(
        "PORT-TEST-001", _security(), actor="TEST", reason="security",
        event_timestamp=T0 + timedelta(minutes=2)
    )
    transaction = _transaction("BAD-LINK", TransactionType.BUY).model_copy(
        update={"strategy_id": "STRAT-MISSING"}
    )
    with pytest.raises(InvalidTransaction):
        service.record_transaction(
            transaction, actor="TEST", reason="bad link", event_timestamp=T0 + timedelta(minutes=3)
        )
    plain = _transaction("NO-LINK", TransactionType.BUY)
    service.record_transaction(
        plain, actor="TEST", reason="optional links", event_timestamp=T0 + timedelta(minutes=3)
    )
    assert service.get_transactions("PORT-TEST-001")[0].strategy_id is None


def test_jsonl_repository_round_trip(tmp_path: Path) -> None:
    root = tmp_path / "portfolio_os"
    repository = JsonFilePortfolioOSRepository(root)
    service, _ = _service_with_identity(repository=repository)
    service.record_transaction(
        _deposit(), actor="TEST", reason="deposit", event_timestamp=T0 + timedelta(minutes=3)
    )
    restored = PortfolioOSService.from_repository(JsonFilePortfolioOSRepository(root))
    assert restored.get_portfolio("PORT-TEST-001").account_ids == ("ACCT-TEST-001",)
    assert restored.get_accounts("PORT-TEST-001")[0].provider == AccountProvider.MANUAL
    assert restored.get_transactions("PORT-TEST-001")[0].transaction_id == "TXN-DEPOSIT-001"
    assert len(restored.get_portfolio_events("PORT-TEST-001")) == 4


def test_snapshot_export_and_integrity_are_healthy() -> None:
    service = _complete_service()
    snapshot = service.export_portfolio_os_snapshot()
    assert snapshot.integrity.status == IntegrityStatus.HEALTHY
    assert snapshot.integrity.broken_refs == 0
    assert snapshot.integrity.negative_holding_violations == 0
    assert snapshot.integrity.cash_reconciliation_errors == 0
    assert snapshot.integrity.duplicate_transaction_ids == 0
    assert snapshot.integrity.valuation_mismatches == 0
    assert snapshot.integrity.event_sequence_errors == 0
    assert len(snapshot.snapshot_hash) == 64


def test_generated_seed_has_exactly_two_synthetic_portfolios_and_healthy_integrity() -> None:
    repository = JsonFilePortfolioOSRepository(PROJECT_ROOT / "data/platform/portfolio_os")
    service = PortfolioOSService.from_repository(repository)
    portfolios = service.list_portfolios()
    assert {row.portfolio_id for row in portfolios} == {
        RESEARCH_PORTFOLIO_ID,
        MANUAL_PORTFOLIO_ID,
    }
    assert all(row.metadata["synthetic"] is True for row in portfolios)
    assert all(not row.strategy_ids for row in portfolios)
    integrity = service.get_integrity_summary()
    assert integrity.status == IntegrityStatus.HEALTHY
    assert sum(len(service.get_transactions(row.portfolio_id)) for row in portfolios) == 5


def test_generated_manifest_hash_reports_and_docs() -> None:
    path = PROJECT_ROOT / "data/platform/manifests/intersignal_portfolio_os_foundation_manifest_v1.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    recorded = manifest.pop("portfolio_os_foundation_hash")
    assert recorded == canonical_hash(manifest)
    assert manifest["integrity"]["status"] == "HEALTHY"
    assert manifest["counts"]["portfolios"] == 2
    assert manifest["prior_artifacts_unchanged"]["unchanged"] is True
    for report in manifest["reports"]:
        assert (PROJECT_ROOT / "data/reports" / report).is_file()
    for document in manifest["documentation"]:
        assert (PROJECT_ROOT / document).is_file()


def test_generated_artifacts_have_zero_live_or_broker_semantics() -> None:
    manifest = json.loads(
        (PROJECT_ROOT / "data/platform/manifests/intersignal_portfolio_os_foundation_manifest_v1.json").read_text(encoding="utf-8")
    )
    assert manifest["security"] == {
        "broker_calls": 0,
        "credentials_written": 0,
        "external_writes": 0,
        "live_orders": 0,
        "live_signals": 0,
        "migrations": 0,
        "network_required": False,
        "supabase_writes": 0,
    }
    assert manifest["ui_implemented"] is False
    assert manifest["broker_connected"] is False
    assert manifest["real_time_feed_added"] is False
    assert manifest["strategy_v2_created"] is False
    assert manifest["paper_trading_started"] is False
    assert manifest["live_trading_started"] is False


def test_archived_portfolio_cannot_be_reactivated() -> None:
    service, _ = _service_with_identity()
    service.change_portfolio_status(
        "PORT-TEST-001", PortfolioStatus.ARCHIVED, actor="TEST", reason="archive",
        event_timestamp=T0 + timedelta(minutes=3)
    )
    with pytest.raises(InvalidPortfolioState):
        service.change_portfolio_status(
            "PORT-TEST-001", PortfolioStatus.ACTIVE, actor="TEST", reason="reactivate",
            event_timestamp=T0 + timedelta(minutes=4)
        )
