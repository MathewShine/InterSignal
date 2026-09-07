from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from typing import Iterable

from pydantic import BaseModel, Field

from app.models.ingestion import (
    DailyCandle,
    IngestionIssue,
    IntradayCandle,
    ValidationResult,
)


class DataQualityConfig(BaseModel):
    extreme_move_warning_threshold: Decimal = Decimal("0.20")
    supported_intraday_intervals: set[str] = Field(
        default_factory=lambda: {"1m", "2m", "3m", "5m", "10m", "15m", "30m", "1h", "4h"}
    )


class HistoricalDataValidator:
    def __init__(self, config: DataQualityConfig | None = None) -> None:
        self.config = config or DataQualityConfig()

    def validate_daily_candles(
        self,
        records: Iterable[DailyCandle],
    ) -> ValidationResult[DailyCandle]:
        return self._validate_candles(list(records), mode="daily")

    def validate_intraday_candles(
        self,
        records: Iterable[IntradayCandle],
    ) -> ValidationResult[IntradayCandle]:
        result = self._validate_candles(list(records), mode="intraday")
        result.warnings.extend(self._find_intraday_gaps(result.valid_records))
        return result

    def _validate_candles(
        self,
        records: list[DailyCandle] | list[IntradayCandle],
        *,
        mode: str,
    ) -> ValidationResult:
        valid_records = []
        errors: list[IngestionIssue] = []
        warnings: list[IngestionIssue] = []
        duplicate_count = 0
        seen_keys = set()

        for index, record in enumerate(records, start=1):
            row_reference = f"record:{index}"
            record_errors = self._validate_required(record, row_reference)
            record_errors.extend(self._validate_ohlc(record, row_reference))
            record_warnings = self._warnings_for_candle(record, row_reference)

            if mode == "intraday":
                record_errors.extend(self._validate_intraday(record, row_reference))

            dedupe_key = record.dedupe_key
            if dedupe_key in seen_keys:
                duplicate_count += 1
                record_warnings.append(
                    IngestionIssue(
                        severity="warning",
                        code="duplicate_row",
                        message="Duplicate candle row skipped within this import batch.",
                        row_reference=row_reference,
                    )
                )
            else:
                seen_keys.add(dedupe_key)

            errors.extend(record_errors)
            warnings.extend(record_warnings)

            if not record_errors and dedupe_key in seen_keys and not any(
                warning.code == "duplicate_row" for warning in record_warnings
            ):
                valid_records.append(record)

        return ValidationResult(
            valid_records=valid_records,
            errors=errors,
            warnings=warnings,
            duplicate_count=duplicate_count,
        )

    def _validate_required(
        self,
        record: DailyCandle | IntradayCandle,
        row_reference: str,
    ) -> list[IngestionIssue]:
        errors = []
        if not record.exchange:
            errors.append(self._error("missing_exchange", "Exchange is required.", row_reference))
        if not record.trading_symbol:
            errors.append(self._error("missing_symbol", "Trading symbol is required.", row_reference))
        if not record.source:
            errors.append(self._error("missing_source", "Source is required.", row_reference))
        return errors

    def _validate_ohlc(
        self,
        record: DailyCandle | IntradayCandle,
        row_reference: str,
    ) -> list[IngestionIssue]:
        errors = []
        prices = {
            "open": record.open,
            "high": record.high,
            "low": record.low,
            "close": record.close,
        }

        for field_name, value in prices.items():
            if value < 0:
                errors.append(
                    self._error(
                        "negative_price",
                        f"{field_name} price must be non-negative.",
                        row_reference,
                    )
                )

        if record.volume < 0:
            errors.append(self._error("negative_volume", "Volume must be non-negative.", row_reference))

        if record.high < record.open:
            errors.append(self._error("invalid_ohlc", "High must be >= open.", row_reference))
        if record.high < record.close:
            errors.append(self._error("invalid_ohlc", "High must be >= close.", row_reference))
        if record.high < record.low:
            errors.append(self._error("invalid_ohlc", "High must be >= low.", row_reference))
        if record.low > record.open:
            errors.append(self._error("invalid_ohlc", "Low must be <= open.", row_reference))
        if record.low > record.close:
            errors.append(self._error("invalid_ohlc", "Low must be <= close.", row_reference))

        return errors

    def _validate_intraday(
        self,
        record: IntradayCandle,
        row_reference: str,
    ) -> list[IngestionIssue]:
        errors = []
        if record.timestamp.tzinfo is None or record.timestamp.utcoffset() is None:
            errors.append(
                self._error(
                    "naive_timestamp",
                    "Intraday timestamp must be timezone-aware.",
                    row_reference,
                )
            )
        if record.interval not in self.config.supported_intraday_intervals:
            errors.append(
                self._error(
                    "unsupported_interval",
                    f"Unsupported intraday interval: {record.interval}.",
                    row_reference,
                )
            )
        return errors

    def _warnings_for_candle(
        self,
        record: DailyCandle | IntradayCandle,
        row_reference: str,
    ) -> list[IngestionIssue]:
        warnings = []
        if record.volume == 0:
            warnings.append(
                IngestionIssue(
                    severity="warning",
                    code="zero_volume",
                    message="Zero volume candle encountered.",
                    row_reference=row_reference,
                )
            )

        reference_price = record.open if record.open > 0 else record.close
        if reference_price > 0:
            movement = (record.high - record.low) / reference_price
            if movement > self.config.extreme_move_warning_threshold:
                warnings.append(
                    IngestionIssue(
                        severity="warning",
                        code="extreme_candle_move",
                        message="One-candle high/low movement exceeded the configured warning threshold.",
                        row_reference=row_reference,
                    )
                )

        return warnings

    def _find_intraday_gaps(self, records: list[IntradayCandle]) -> list[IngestionIssue]:
        warnings: list[IngestionIssue] = []
        grouped: dict[tuple[str, str, str, str], list[IntradayCandle]] = defaultdict(list)

        for record in records:
            grouped[
                (
                    record.exchange,
                    record.trading_symbol,
                    record.interval,
                    record.source,
                )
            ].append(record)

        for key, group in grouped.items():
            expected_delta = self._interval_to_timedelta(key[2])
            if expected_delta is None:
                continue

            sorted_group = sorted(group, key=lambda candle: candle.timestamp)
            for previous, current in zip(sorted_group, sorted_group[1:]):
                if current.timestamp - previous.timestamp > expected_delta:
                    warnings.append(
                        IngestionIssue(
                            severity="warning",
                            code="intraday_gap",
                            message="Gap detected in expected intraday candle sequence.",
                            row_reference=f"{previous.timestamp.isoformat()}->{current.timestamp.isoformat()}",
                        )
                    )

        return warnings

    def _interval_to_timedelta(self, interval: str) -> timedelta | None:
        if interval.endswith("m"):
            try:
                return timedelta(minutes=int(interval[:-1]))
            except ValueError:
                return None
        return None

    def _error(self, code: str, message: str, row_reference: str) -> IngestionIssue:
        return IngestionIssue(
            severity="error",
            code=code,
            message=message,
            row_reference=row_reference,
        )
