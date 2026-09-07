from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models import (
    Candle,
    CandidateStatus,
    ExecutionMode,
    Instrument,
    MomentumClassification,
    OutcomeLabel,
    StrategyCandidate,
    StrategyConfiguration,
    StrategyConfigurationStatus,
    TradeSignal,
)


def test_instrument_model_represents_provider_agnostic_symbol():
    instrument = Instrument(
        exchange="NSE",
        trading_symbol="INFY",
        company_name="Infosys Limited",
        instrument_type="EQUITY",
    )

    assert instrument.provider_symbol is None
    assert instrument.exchange == "NSE"
    assert instrument.active is True


def test_candle_preserves_decimal_financial_values():
    candle = Candle(
        instrument_id=uuid4(),
        trading_date=date(2026, 9, 7),
        open=Decimal("100.1000"),
        high=Decimal("105.2500"),
        low=Decimal("99.9500"),
        close=Decimal("104.5000"),
        volume=123456,
        traded_value=Decimal("12876543.21"),
        source="research_import",
    )

    assert isinstance(candle.close, Decimal)
    assert candle.close == Decimal("104.5000")
    assert candle.traded_value == Decimal("12876543.21")


def test_candle_rejects_invalid_price_order():
    with pytest.raises(ValidationError):
        Candle(
            instrument_id=uuid4(),
            trading_date=date(2026, 9, 7),
            open=Decimal("100.0000"),
            high=Decimal("99.0000"),
            low=Decimal("101.0000"),
            close=Decimal("100.5000"),
            volume=1,
            source="research_import",
        )


def test_rejected_candidate_requires_rejection_reason():
    with pytest.raises(ValidationError):
        StrategyCandidate(
            instrument_id=uuid4(),
            detected_at=datetime.now(UTC),
            strategy_name="research_only",
            strategy_version="0.0.0",
            execution_mode=ExecutionMode.SWING,
            momentum_classification=MomentumClassification.EMERGING,
            status=CandidateStatus.REJECTED,
        )


def test_candidate_status_and_configuration_representation():
    candidate = StrategyCandidate(
        instrument_id=uuid4(),
        detected_at=datetime.now(UTC),
        strategy_name="research_only",
        strategy_version="0.0.0",
        execution_mode=ExecutionMode.INTRADAY,
        momentum_classification=MomentumClassification.CONFIRMED,
        status=CandidateStatus.WATCH,
        base_score=Decimal("71.2500"),
    )
    config = StrategyConfiguration(
        strategy_name="UNASSIGNED_RESEARCH",
        version="0.0.0",
        status=StrategyConfigurationStatus.DRAFT,
        configuration={"parameters": {}},
    )

    assert candidate.status == CandidateStatus.WATCH
    assert candidate.base_score == Decimal("71.2500")
    assert config.configuration["parameters"] == {}


def test_trade_signal_entry_range_validation_and_outcome_enum():
    with pytest.raises(ValidationError):
        TradeSignal(
            candidate_id=uuid4(),
            generated_at=datetime.now(UTC),
            signal_type="research_signal",
            execution_mode=ExecutionMode.SWING,
            entry_price_low=Decimal("105.0000"),
            entry_price_high=Decimal("100.0000"),
            stop_price=Decimal("95.0000"),
            signal_score=Decimal("80.0000"),
        )

    assert OutcomeLabel.GOOD_REJECTION.value == "GOOD_REJECTION"

