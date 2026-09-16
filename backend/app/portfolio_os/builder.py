from __future__ import annotations

import csv
import json
import subprocess
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.platform.hashing import HASH_VERSION, canonical_hash, file_sha256, normalize_for_hash
from app.portfolio_os.models import (
    AccountProvider,
    AccountStatus,
    AccountType,
    BenchmarkReference,
    BrokerSyncState,
    CashBalance,
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
    SecurityReference,
    TransactionType,
    ZERO,
)
from app.portfolio_os.repositories import JsonFilePortfolioOSRepository
from app.portfolio_os.service import PortfolioOSService
from app.research_workbench.builder import FOUNDATION_PATHS


COMMAND = "Step 04.03 / Command 01"
COMMAND_VERSION = "INTERSIGNAL_PORTFOLIO_OS_FOUNDATION_V1"
COMMAND_PROFILE = "PORTFOLIO_ACCOUNT_HOLDINGS_TRANSACTION_RISK_DOMAIN_V1"
MANIFEST_VERSION = "INTERSIGNAL_PORTFOLIO_OS_FOUNDATION_MANIFEST_V1"
INTEGRITY_VERSION = "INTERSIGNAL_PORTFOLIO_OS_INTEGRITY_V1"
REQUIRED_CHECKPOINT = "f990c3c96d9b8a619953041006affb986914fc5c"
PLATFORM_FOUNDATION_HASH = (
    "ec270dcb640116fe56709c784b4ca915bd794b0a96847e11fb561460dfed877f"
)
RESEARCH_WORKBENCH_HASH = (
    "c0c1ba634f584b4532e99e4f015be83e7e0c069eafb3cd5ca6a1fc7cfaf8f52b"
)

PRIOR_ARTIFACT_PATHS = FOUNDATION_PATHS + (
    "data/platform/manifests/intersignal_research_workbench_backend_manifest_v1.json",
    "data/platform/workbench/research_workbench_integrity_v1.json",
    "data/platform/workbench/research_workbench_snapshot_v1.json",
    "data/reports/research_workbench_backend_v1_summary.json",
    "data/reports/research_workbench_backend_v1_families.csv",
    "data/reports/research_workbench_backend_v1_evidence.csv",
    "data/reports/research_workbench_backend_v1_blocked.csv",
    "data/reports/research_workbench_backend_v1_integrity.csv",
    "docs/research-workbench-backend-v1.md",
    "docs/research-workbench-view-models-v1.md",
)

REPORT_NAMES = (
    "portfolio_os_foundation_v1_summary.json",
    "portfolio_os_foundation_v1_portfolios.csv",
    "portfolio_os_foundation_v1_holdings.csv",
    "portfolio_os_foundation_v1_transactions.csv",
    "portfolio_os_foundation_v1_integrity.csv",
)
DOCUMENTATION_PATHS = (
    "docs/portfolio-os-domain-model-v1.md",
    "docs/portfolio-os-accounting-v1.md",
    "docs/portfolio-os-risk-analytics-v1.md",
)

RESEARCH_PORTFOLIO_ID = "PORT-RESEARCH-SYNTHETIC-001"
MANUAL_PORTFOLIO_ID = "PORT-MANUAL-INVESTMENT-SYNTHETIC-001"
BASE_TIME = datetime(2026, 9, 16, 20, 0, tzinfo=timezone.utc)


class PortfolioOSInputMismatch(RuntimeError):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any] | object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            normalize_for_hash(payload),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return value


def _git_head(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.strip()


def _document_hash(document: Mapping[str, Any], field: str) -> str:
    return canonical_hash({key: value for key, value in document.items() if key != field})


def _file_hashes(root: Path, paths: Sequence[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for relative in paths:
        path = root / relative
        if not path.is_file():
            raise PortfolioOSInputMismatch(f"Missing required prior artifact: {relative}")
        values[relative] = file_sha256(path)
    return values


def _jsonl_ids(path: Path, field: str) -> set[str]:
    values: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            values.add(str(json.loads(line)[field]))
    return values


def verify_portfolio_os_inputs(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    head = _git_head(root)
    if head != REQUIRED_CHECKPOINT:
        raise PortfolioOSInputMismatch(
            f"Expected checkpoint {REQUIRED_CHECKPOINT}, found {head}"
        )
    foundation_path = (
        root / "data/platform/manifests/intersignal_platform_foundation_manifest_v1.json"
    )
    foundation = _read_json(foundation_path)
    if (
        foundation.get("platform_foundation_hash") != PLATFORM_FOUNDATION_HASH
        or _document_hash(foundation, "platform_foundation_hash")
        != PLATFORM_FOUNDATION_HASH
    ):
        raise PortfolioOSInputMismatch("Step 04.01 platform foundation hash mismatch")
    workbench_path = (
        root
        / "data/platform/manifests/intersignal_research_workbench_backend_manifest_v1.json"
    )
    workbench = _read_json(workbench_path)
    if (
        workbench.get("research_workbench_backend_hash") != RESEARCH_WORKBENCH_HASH
        or _document_hash(workbench, "research_workbench_backend_hash")
        != RESEARCH_WORKBENCH_HASH
    ):
        raise PortfolioOSInputMismatch("Step 04.02 Research Workbench hash mismatch")
    return {
        "head": head,
        "foundation": foundation,
        "workbench": workbench,
        "strategy_ids": _jsonl_ids(
            root / "data/platform/registry/strategies.jsonl", "strategy_id"
        ),
        "evidence_ids": _jsonl_ids(
            root / "data/platform/registry/evidence.jsonl", "evidence_id"
        ),
        "lineage_node_ids": _jsonl_ids(
            root / "data/platform/lineage/nodes.jsonl", "node_id"
        ),
    }


def _time(minutes: int) -> datetime:
    return BASE_TIME + timedelta(minutes=minutes)


def _seed_research_portfolio(service: PortfolioOSService) -> None:
    portfolio = Portfolio(
        portfolio_id=RESEARCH_PORTFOLIO_ID,
        name="Synthetic Research Portfolio",
        portfolio_type=PortfolioType.RESEARCH,
        base_currency="INR",
        market_scope=("SYNTHETIC",),
        status=PortfolioStatus.RESEARCH_ONLY,
        created_at=_time(0),
        updated_at=_time(0),
        metadata={
            "synthetic": True,
            "live_strategy_semantics": False,
            "purpose": "offline platform verification",
        },
    )
    service.create_portfolio(
        portfolio, actor="SYSTEM_SEED", reason="Create synthetic research fixture"
    )
    account = PortfolioAccount(
        account_id="ACCT-RESEARCH-SIMULATED-001",
        portfolio_id=portfolio.portfolio_id,
        account_type=AccountType.RESEARCH,
        provider=AccountProvider.SIMULATED,
        provider_account_reference="SYNTHETIC-NON-BROKER-RESEARCH",
        currency="INR",
        status=AccountStatus.ACTIVE,
        created_at=_time(1),
        broker_sync_state=BrokerSyncState.NEVER_SYNCED,
        metadata={"synthetic": True, "broker_connection": False},
    )
    service.register_account(
        account,
        actor="SYSTEM_SEED",
        reason="Attach synthetic research account",
        event_timestamp=_time(1),
    )
    security = SecurityReference(
        security_id="SEC-SYNTH-EQUITY-001",
        market="SYNTHETIC",
        exchange="SYNTHETIC",
        symbol="SYN-EQ-001",
        instrument_type=InstrumentType.EQUITY,
        currency="INR",
        name="Synthetic Equity One",
        metadata={"sector": "Synthetic Technology", "industry": "Synthetic Software"},
    )
    service.register_security(
        portfolio.portfolio_id,
        security,
        actor="SYSTEM_SEED",
        reason="Register synthetic equity identity",
        event_timestamp=_time(2),
    )
    transactions = (
        PortfolioTransaction(
            transaction_id="TXN-RESEARCH-DEPOSIT-001",
            portfolio_id=portfolio.portfolio_id,
            account_id=account.account_id,
            transaction_type=TransactionType.DEPOSIT,
            gross_amount=Decimal("100000"),
            net_amount=Decimal("100000"),
            currency="INR",
            trade_date=date(2026, 9, 15),
            settlement_date=date(2026, 9, 15),
            source="SYNTHETIC_FIXTURE",
            metadata={"synthetic": True},
        ),
        PortfolioTransaction(
            transaction_id="TXN-RESEARCH-BUY-001",
            portfolio_id=portfolio.portfolio_id,
            account_id=account.account_id,
            security_id=security.security_id,
            transaction_type=TransactionType.BUY,
            quantity=Decimal("10"),
            price=Decimal("1000"),
            gross_amount=Decimal("10000"),
            fees=Decimal("10"),
            taxes=Decimal("10"),
            net_amount=Decimal("-10020"),
            currency="INR",
            trade_date=date(2026, 9, 16),
            settlement_date=date(2026, 9, 16),
            source="SYNTHETIC_FIXTURE",
            metadata={"synthetic": True, "signal_generated": False},
        ),
    )
    for offset, transaction in enumerate(transactions, start=3):
        service.record_transaction(
            transaction,
            actor="SYSTEM_SEED",
            reason="Record deterministic synthetic transaction",
            event_timestamp=_time(offset),
        )
    service.record_cash_balance(
        CashBalance(
            account_id=account.account_id,
            currency="INR",
            available_cash=Decimal("89980"),
            settled_cash=Decimal("89980"),
            as_of=_time(5),
            source="SYNTHETIC_RECONCILIATION",
            metadata={"synthetic": True},
        ),
        actor="SYSTEM_SEED",
        reason="Record reconciled synthetic cash",
    )
    rebuild = service.rebuild_holdings(
        portfolio.portfolio_id,
        prices={security.security_id: Decimal("1100")},
        as_of=_time(6),
        source="SYNTHETIC_MARK",
        actor="SYSTEM_SEED",
        reason="Build deterministic FIFO holdings",
    )
    for offset, point in enumerate(
        (
            PortfolioPerformancePoint(
                portfolio_id=portfolio.portfolio_id,
                date=date(2026, 9, 15),
                equity=ZERO,
                cash=Decimal("100000"),
                invested_value=ZERO,
                daily_return=ZERO,
                cumulative_return=ZERO,
                metadata={"synthetic": True},
            ),
            PortfolioPerformancePoint(
                portfolio_id=portfolio.portfolio_id,
                date=date(2026, 9, 16),
                equity=Decimal("11000"),
                cash=Decimal("89980"),
                invested_value=Decimal("10020"),
                daily_return=Decimal("0.0098"),
                cumulative_return=Decimal("0.0098"),
                benchmark_value=Decimal("100600"),
                metadata={"synthetic": True},
            ),
        ),
        start=7,
    ):
        service.record_performance_point(
            point,
            actor="SYSTEM_SEED",
            reason="Record synthetic performance point",
            event_timestamp=_time(offset),
        )
    service.record_valuation(
        PortfolioValuation(
            portfolio_id=portfolio.portfolio_id,
            as_of=_time(9),
            gross_market_value=Decimal("11000"),
            cash=Decimal("89980"),
            net_liquidation_value=Decimal("100980"),
            cost_basis=Decimal("10020"),
            realized_pnl=rebuild.realized_pnl.get("INR", ZERO),
            unrealized_pnl=Decimal("980"),
            total_pnl=Decimal("980"),
            currency="INR",
            source="SYNTHETIC_MARK",
            metadata={"synthetic": True},
        ),
        actor="SYSTEM_SEED",
        reason="Record synthetic point-in-time valuation",
    )
    exposure = service.calculate_exposure(portfolio.portfolio_id, as_of=_time(10))
    service.record_exposure(
        exposure,
        actor="SYSTEM_SEED",
        reason="Record synthetic exposure snapshot",
    )
    metrics = service.calculate_metrics(portfolio.portfolio_id)
    service.record_risk_snapshot(
        PortfolioRiskSnapshot(
            portfolio_id=portfolio.portfolio_id,
            as_of=_time(11),
            drawdown=metrics.max_drawdown,
            volatility=metrics.volatility,
            concentration=max(exposure.security_concentration.values(), default=ZERO),
            top_1_weight=max(exposure.security_concentration.values(), default=ZERO),
            top_5_weight=sum(
                sorted(exposure.security_concentration.values(), reverse=True)[:5], ZERO
            ),
            cash_pct=exposure.cash_pct or ZERO,
            turnover=metrics.turnover,
            cost_drag=metrics.costs / Decimal("100980"),
            gross_exposure=exposure.gross_exposure,
            net_exposure=exposure.net_exposure,
            risk_flags=exposure.risk_flags,
            metadata={"synthetic": True, "recommendation": None},
        ),
        actor="SYSTEM_SEED",
        reason="Record non-advisory synthetic risk state",
    )
    benchmark = BenchmarkReference(
        benchmark_id="BMK-SYNTH-RESEARCH-001",
        name="Synthetic Research Index",
        market="SYNTHETIC",
        currency="INR",
        source="SYNTHETIC_FIXTURE",
        version="V1",
        metadata={"synthetic": True, "alpha_claim": False},
    )
    service.link_benchmark(
        portfolio.portfolio_id,
        benchmark,
        actor="SYSTEM_SEED",
        reason="Link synthetic comparison reference",
        event_timestamp=_time(12),
    )
    service.record_benchmark_comparison(
        PortfolioBenchmarkComparison(
            portfolio_id=portfolio.portfolio_id,
            benchmark_id=benchmark.benchmark_id,
            portfolio_return=Decimal("0.0098"),
            benchmark_return=Decimal("0.006"),
            active_return=Decimal("0.0038"),
            relative_drawdown=ZERO,
            tracking_difference=Decimal("0.0038"),
            period_start=date(2026, 9, 15),
            period_end=date(2026, 9, 16),
            metadata={"synthetic": True, "alpha_claim": False},
        ),
        actor="SYSTEM_SEED",
        reason="Record synthetic benchmark comparison",
        event_timestamp=_time(13),
    )
    attribution = service.calculate_attribution(
        portfolio.portfolio_id,
        period_start=date(2026, 9, 15),
        period_end=date(2026, 9, 16),
    )
    service.record_attribution(
        attribution,
        actor="SYSTEM_SEED",
        reason="Record simple deterministic attribution",
        event_timestamp=_time(14),
    )


def _seed_manual_portfolio(service: PortfolioOSService) -> None:
    portfolio = Portfolio(
        portfolio_id=MANUAL_PORTFOLIO_ID,
        name="Synthetic Manual Investment Portfolio",
        portfolio_type=PortfolioType.MANUAL,
        base_currency="INR",
        market_scope=("SYNTHETIC",),
        status=PortfolioStatus.ACTIVE,
        created_at=_time(20),
        updated_at=_time(20),
        metadata={
            "synthetic": True,
            "manual_entry": True,
            "live_strategy_semantics": False,
        },
    )
    service.create_portfolio(
        portfolio, actor="SYSTEM_SEED", reason="Create synthetic manual fixture"
    )
    account = PortfolioAccount(
        account_id="ACCT-MANUAL-INVESTMENT-001",
        portfolio_id=portfolio.portfolio_id,
        account_type=AccountType.MUTUAL_FUND,
        provider=AccountProvider.MANUAL,
        provider_account_reference="SYNTHETIC-MANUAL-MF",
        currency="INR",
        status=AccountStatus.ACTIVE,
        created_at=_time(21),
        broker_sync_state=BrokerSyncState.NEVER_SYNCED,
        metadata={"synthetic": True, "broker_connection": False, "sip_logic": False},
    )
    service.register_account(
        account,
        actor="SYSTEM_SEED",
        reason="Attach synthetic manual investment account",
        event_timestamp=_time(21),
    )
    security = SecurityReference(
        security_id="SEC-SYNTH-MF-001",
        market="SYNTHETIC",
        exchange="SYNTHETIC-MF",
        symbol="SYN-MF-001",
        isin="SYNTHETICISIN001",
        instrument_type=InstrumentType.MUTUAL_FUND,
        currency="INR",
        name="Synthetic Mutual Fund One",
        metadata={"sector": "Diversified", "industry": "Mutual Fund"},
    )
    service.register_security(
        portfolio.portfolio_id,
        security,
        actor="SYSTEM_SEED",
        reason="Register synthetic mutual-fund identity",
        event_timestamp=_time(22),
    )
    transactions = (
        PortfolioTransaction(
            transaction_id="TXN-MANUAL-DEPOSIT-001",
            portfolio_id=portfolio.portfolio_id,
            account_id=account.account_id,
            transaction_type=TransactionType.DEPOSIT,
            gross_amount=Decimal("50000"),
            net_amount=Decimal("50000"),
            currency="INR",
            trade_date=date(2026, 9, 14),
            settlement_date=date(2026, 9, 14),
            source="SYNTHETIC_MANUAL_FIXTURE",
            metadata={"synthetic": True},
        ),
        PortfolioTransaction(
            transaction_id="TXN-MANUAL-BUY-001",
            portfolio_id=portfolio.portfolio_id,
            account_id=account.account_id,
            security_id=security.security_id,
            transaction_type=TransactionType.BUY,
            quantity=Decimal("100"),
            price=Decimal("100"),
            gross_amount=Decimal("10000"),
            fees=Decimal("5"),
            net_amount=Decimal("-10005"),
            currency="INR",
            trade_date=date(2026, 9, 15),
            settlement_date=date(2026, 9, 15),
            source="SYNTHETIC_MANUAL_FIXTURE",
            metadata={"synthetic": True, "sip": False},
        ),
        PortfolioTransaction(
            transaction_id="TXN-MANUAL-SELL-001",
            portfolio_id=portfolio.portfolio_id,
            account_id=account.account_id,
            security_id=security.security_id,
            transaction_type=TransactionType.SELL,
            quantity=Decimal("20"),
            price=Decimal("120"),
            gross_amount=Decimal("2400"),
            fees=Decimal("2"),
            net_amount=Decimal("2398"),
            currency="INR",
            trade_date=date(2026, 9, 16),
            settlement_date=date(2026, 9, 16),
            source="SYNTHETIC_MANUAL_FIXTURE",
            metadata={"synthetic": True},
        ),
    )
    for offset, transaction in enumerate(transactions, start=23):
        service.record_transaction(
            transaction,
            actor="SYSTEM_SEED",
            reason="Record deterministic manual transaction",
            event_timestamp=_time(offset),
        )
    service.record_cash_balance(
        CashBalance(
            account_id=account.account_id,
            currency="INR",
            available_cash=Decimal("42393"),
            settled_cash=Decimal("42393"),
            as_of=_time(26),
            source="SYNTHETIC_RECONCILIATION",
            metadata={"synthetic": True},
        ),
        actor="SYSTEM_SEED",
        reason="Record reconciled manual cash",
    )
    rebuild = service.rebuild_holdings(
        portfolio.portfolio_id,
        prices={security.security_id: Decimal("125")},
        as_of=_time(27),
        source="SYNTHETIC_MARK",
        actor="SYSTEM_SEED",
        reason="Build deterministic FIFO mutual-fund holdings",
    )
    service.add_goal(
        PortfolioGoal(
            goal_id="GOAL-SYNTH-MANUAL-001",
            portfolio_id=portfolio.portfolio_id,
            name="Synthetic Long-Term Goal",
            target_amount=Decimal("100000"),
            target_date=date(2030, 12, 31),
            currency="INR",
            status=GoalStatus.ACTIVE,
            metadata={"synthetic": True, "recommendation_logic": False},
        ),
        actor="SYSTEM_SEED",
        reason="Attach synthetic manual goal",
        event_timestamp=_time(28),
    )
    for offset, point in enumerate(
        (
            PortfolioPerformancePoint(
                portfolio_id=portfolio.portfolio_id,
                date=date(2026, 9, 14),
                equity=ZERO,
                cash=Decimal("50000"),
                invested_value=ZERO,
                daily_return=ZERO,
                cumulative_return=ZERO,
                metadata={"synthetic": True},
            ),
            PortfolioPerformancePoint(
                portfolio_id=portfolio.portfolio_id,
                date=date(2026, 9, 16),
                equity=Decimal("10000"),
                cash=Decimal("42393"),
                invested_value=Decimal("8004"),
                daily_return=Decimal("0.04786"),
                cumulative_return=Decimal("0.04786"),
                benchmark_value=Decimal("51000"),
                metadata={"synthetic": True},
            ),
        ),
        start=29,
    ):
        service.record_performance_point(
            point,
            actor="SYSTEM_SEED",
            reason="Record synthetic manual performance point",
            event_timestamp=_time(offset),
        )
    realized = rebuild.realized_pnl.get("INR", ZERO)
    service.record_valuation(
        PortfolioValuation(
            portfolio_id=portfolio.portfolio_id,
            as_of=_time(31),
            gross_market_value=Decimal("10000"),
            cash=Decimal("42393"),
            net_liquidation_value=Decimal("52393"),
            cost_basis=Decimal("8004"),
            realized_pnl=realized,
            unrealized_pnl=Decimal("1996"),
            total_pnl=realized + Decimal("1996"),
            currency="INR",
            source="SYNTHETIC_MARK",
            metadata={"synthetic": True},
        ),
        actor="SYSTEM_SEED",
        reason="Record synthetic manual valuation",
    )
    exposure = service.calculate_exposure(portfolio.portfolio_id, as_of=_time(32))
    service.record_exposure(
        exposure,
        actor="SYSTEM_SEED",
        reason="Record synthetic manual exposure",
    )
    metrics = service.calculate_metrics(portfolio.portfolio_id)
    service.record_risk_snapshot(
        PortfolioRiskSnapshot(
            portfolio_id=portfolio.portfolio_id,
            as_of=_time(33),
            drawdown=metrics.max_drawdown,
            volatility=metrics.volatility,
            concentration=max(exposure.security_concentration.values(), default=ZERO),
            top_1_weight=max(exposure.security_concentration.values(), default=ZERO),
            top_5_weight=sum(
                sorted(exposure.security_concentration.values(), reverse=True)[:5], ZERO
            ),
            cash_pct=exposure.cash_pct or ZERO,
            turnover=metrics.turnover,
            cost_drag=metrics.costs / Decimal("52393"),
            gross_exposure=exposure.gross_exposure,
            net_exposure=exposure.net_exposure,
            risk_flags=exposure.risk_flags,
            metadata={"synthetic": True, "recommendation": None},
        ),
        actor="SYSTEM_SEED",
        reason="Record non-advisory manual risk state",
    )
    benchmark = BenchmarkReference(
        benchmark_id="BMK-SYNTH-MANUAL-001",
        name="Synthetic Manual Investment Index",
        market="SYNTHETIC",
        currency="INR",
        source="SYNTHETIC_FIXTURE",
        version="V1",
        metadata={"synthetic": True, "alpha_claim": False},
    )
    service.link_benchmark(
        portfolio.portfolio_id,
        benchmark,
        actor="SYSTEM_SEED",
        reason="Link synthetic manual benchmark",
        event_timestamp=_time(34),
    )
    service.record_benchmark_comparison(
        PortfolioBenchmarkComparison(
            portfolio_id=portfolio.portfolio_id,
            benchmark_id=benchmark.benchmark_id,
            portfolio_return=Decimal("0.04786"),
            benchmark_return=Decimal("0.02"),
            active_return=Decimal("0.02786"),
            relative_drawdown=ZERO,
            tracking_difference=Decimal("0.02786"),
            period_start=date(2026, 9, 14),
            period_end=date(2026, 9, 16),
            metadata={"synthetic": True, "alpha_claim": False},
        ),
        actor="SYSTEM_SEED",
        reason="Record synthetic manual benchmark comparison",
        event_timestamp=_time(35),
    )
    attribution = service.calculate_attribution(
        portfolio.portfolio_id,
        period_start=date(2026, 9, 14),
        period_end=date(2026, 9, 16),
    )
    service.record_attribution(
        attribution,
        actor="SYSTEM_SEED",
        reason="Record simple deterministic manual attribution",
        event_timestamp=_time(36),
    )


def _artifact_hashes(root: Path) -> dict[str, str]:
    artifact_root = root / "data/platform/portfolio_os"
    return {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in sorted(artifact_root.rglob("*"))
        if path.is_file()
    }


def _write_reports(root: Path, service: PortfolioOSService, summary: dict[str, Any]) -> None:
    reports = root / "data/reports"
    _write_json(reports / REPORT_NAMES[0], summary)
    portfolio_rows = []
    holding_rows = []
    transaction_rows = []
    for portfolio in service.list_portfolios():
        portfolio_row = portfolio.model_dump(mode="json")
        for field in (
            "market_scope",
            "benchmark_ids",
            "account_ids",
            "strategy_ids",
            "goal_ids",
            "metadata",
        ):
            portfolio_row[field] = _csv_value(portfolio_row[field])
        portfolio_rows.append(portfolio_row)
        for holding in service.get_holdings(portfolio.portfolio_id):
            row = holding.model_dump(mode="json")
            row["strategy_attribution"] = _csv_value(row["strategy_attribution"])
            row["metadata"] = _csv_value(row["metadata"])
            holding_rows.append(row)
        for transaction in service.get_transactions(portfolio.portfolio_id):
            row = transaction.model_dump(mode="json")
            row["metadata"] = _csv_value(row["metadata"])
            transaction_rows.append(row)
    _write_csv(
        reports / REPORT_NAMES[1],
        tuple(portfolio_rows[0]) if portfolio_rows else (),
        portfolio_rows,
    )
    _write_csv(
        reports / REPORT_NAMES[2],
        tuple(holding_rows[0]) if holding_rows else (),
        holding_rows,
    )
    _write_csv(
        reports / REPORT_NAMES[3],
        tuple(transaction_rows[0]) if transaction_rows else (),
        transaction_rows,
    )
    integrity_row = service.get_integrity_summary().model_dump(mode="json")
    integrity_row["metadata"] = _csv_value(integrity_row["metadata"])
    _write_csv(
        reports / REPORT_NAMES[4], tuple(integrity_row), [integrity_row]
    )


def build_portfolio_os_foundation(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    inputs = verify_portfolio_os_inputs(root)
    before = _file_hashes(root, PRIOR_ARTIFACT_PATHS)
    portfolio_root = root / "data/platform/portfolio_os"
    if portfolio_root.exists() and any(portfolio_root.rglob("*.jsonl")):
        raise PortfolioOSInputMismatch(
            "Portfolio OS JSONL seed already exists; refusing to append duplicate fixtures"
        )
    repository = JsonFilePortfolioOSRepository(portfolio_root)
    service = PortfolioOSService.from_repository(
        repository,
        valid_strategy_ids=inputs["strategy_ids"],
        valid_evidence_ids=inputs["evidence_ids"],
        valid_lineage_node_ids=inputs["lineage_node_ids"],
    )
    _seed_research_portfolio(service)
    _seed_manual_portfolio(service)
    integrity = service.get_integrity_summary()
    if integrity.status != IntegrityStatus.HEALTHY:
        raise PortfolioOSInputMismatch(
            f"Synthetic Portfolio OS integrity is not HEALTHY: {integrity.model_dump(mode='json')}"
        )
    snapshot = service.export_portfolio_os_snapshot()
    _write_json(
        portfolio_root / "portfolio_os_snapshot_v1.json",
        snapshot.model_dump(mode="json"),
    )
    integrity_payload: dict[str, Any] = {
        "integrity_version": INTEGRITY_VERSION,
        "generated_at": snapshot.generated_at,
        "integrity": integrity.model_dump(mode="json"),
        "platform_foundation_hash": PLATFORM_FOUNDATION_HASH,
        "research_workbench_backend_hash": RESEARCH_WORKBENCH_HASH,
    }
    integrity_payload["integrity_hash"] = canonical_hash(integrity_payload)
    _write_json(
        portfolio_root / "portfolio_os_integrity_v1.json", integrity_payload
    )
    after = _file_hashes(root, PRIOR_ARTIFACT_PATHS)
    if before != after:
        raise PortfolioOSInputMismatch("Prior platform artifacts changed during build")
    artifact_hashes = _artifact_hashes(root)
    counts = {
        "portfolios": len(snapshot.portfolios),
        "accounts": len(snapshot.accounts),
        "holdings": len(snapshot.holdings),
        "cash_balances": len(snapshot.cash),
        "risk_snapshots": len(snapshot.risk),
        "benchmarks": len(snapshot.benchmarks),
        "transactions": sum(
            len(service.get_transactions(row.portfolio_id)) for row in snapshot.portfolios
        ),
        "events": sum(
            len(service.get_portfolio_events(row.portfolio_id)) for row in snapshot.portfolios
        ),
        "live_signals": 0,
        "live_orders": 0,
        "broker_calls": 0,
    }
    manifest: dict[str, Any] = {
        "manifest_version": MANIFEST_VERSION,
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "required_checkpoint": REQUIRED_CHECKPOINT,
        "platform_foundation_hash": PLATFORM_FOUNDATION_HASH,
        "research_workbench_backend_hash": RESEARCH_WORKBENCH_HASH,
        "hashing_method": HASH_VERSION,
        "created_at": snapshot.generated_at,
        "snapshot_hash": snapshot.snapshot_hash,
        "integrity_hash": integrity_payload["integrity_hash"],
        "integrity": integrity.model_dump(mode="json"),
        "component_hashes": {
            "portfolios_hash": canonical_hash(snapshot.portfolios),
            "accounts_hash": canonical_hash(snapshot.accounts),
            "holdings_hash": canonical_hash(snapshot.holdings),
            "cash_hash": canonical_hash(snapshot.cash),
            "risk_hash": canonical_hash(snapshot.risk),
            "benchmarks_hash": canonical_hash(snapshot.benchmarks),
        },
        "artifact_file_hashes": artifact_hashes,
        "counts": counts,
        "prior_artifacts_unchanged": {
            "unchanged": before == after,
            "file_hashes_before": before,
            "file_hashes_after": after,
        },
        "synthetic_seed": {
            "portfolio_ids": [RESEARCH_PORTFOLIO_ID, MANUAL_PORTFOLIO_ID],
            "contains_real_user_data": False,
            "contains_strategy_signals": False,
        },
        "documentation": list(DOCUMENTATION_PATHS),
        "reports": list(REPORT_NAMES),
        "security": {
            "network_required": False,
            "credentials_written": 0,
            "external_writes": 0,
            "live_signals": 0,
            "live_orders": 0,
            "broker_calls": 0,
            "migrations": 0,
            "supabase_writes": 0,
        },
        "ui_implemented": False,
        "broker_connected": False,
        "real_time_feed_added": False,
        "strategy_v2_created": False,
        "paper_trading_started": False,
        "live_trading_started": False,
    }
    manifest["portfolio_os_foundation_hash"] = canonical_hash(manifest)
    manifest_path = (
        root
        / "data/platform/manifests/intersignal_portfolio_os_foundation_manifest_v1.json"
    )
    _write_json(manifest_path, manifest)
    summary: dict[str, Any] = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "required_checkpoint": REQUIRED_CHECKPOINT,
        "platform_foundation_hash": PLATFORM_FOUNDATION_HASH,
        "research_workbench_backend_hash": RESEARCH_WORKBENCH_HASH,
        "portfolio_os_foundation_hash": manifest["portfolio_os_foundation_hash"],
        "snapshot_hash": snapshot.snapshot_hash,
        "integrity_hash": integrity_payload["integrity_hash"],
        "integrity": integrity.model_dump(mode="json"),
        "counts": counts,
        "prior_artifacts_unchanged": manifest["prior_artifacts_unchanged"],
        "reports": list(REPORT_NAMES),
        "documentation": list(DOCUMENTATION_PATHS),
        "verification": {
            "backend_targeted_tests": "PENDING",
            "backend_full_tests": "PENDING",
            "frontend_build": "PENDING",
            "regressions": "PENDING",
            "ready_for_review": False,
        },
    }
    _write_reports(root, service, summary)
    return summary


def finalize_portfolio_os_foundation(
    root: Path,
    *,
    backend_targeted_tests: str,
    backend_full_tests: str,
    frontend_build: str,
    regressions: str,
) -> dict[str, Any]:
    root = Path(root).resolve()
    manifest_path = (
        root
        / "data/platform/manifests/intersignal_portfolio_os_foundation_manifest_v1.json"
    )
    manifest = _read_json(manifest_path)
    if manifest["portfolio_os_foundation_hash"] != _document_hash(
        manifest, "portfolio_os_foundation_hash"
    ):
        raise PortfolioOSInputMismatch("Portfolio OS manifest hash mismatch")
    if _file_hashes(root, PRIOR_ARTIFACT_PATHS) != manifest[
        "prior_artifacts_unchanged"
    ]["file_hashes_after"]:
        raise PortfolioOSInputMismatch("Prior platform artifacts changed")
    summary_path = root / "data/reports" / REPORT_NAMES[0]
    summary = _read_json(summary_path)
    verification = {
        "backend_targeted_tests": backend_targeted_tests,
        "backend_full_tests": backend_full_tests,
        "frontend_build": frontend_build,
        "regressions": regressions,
    }
    verification["ready_for_review"] = all(
        value.startswith("PASS") for value in verification.values()
    )
    summary["verification"] = verification
    _write_json(summary_path, summary)
    return verification


__all__ = (
    "COMMAND",
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "MANIFEST_VERSION",
    "PLATFORM_FOUNDATION_HASH",
    "RESEARCH_WORKBENCH_HASH",
    "REQUIRED_CHECKPOINT",
    "PortfolioOSInputMismatch",
    "build_portfolio_os_foundation",
    "finalize_portfolio_os_foundation",
    "verify_portfolio_os_inputs",
)
