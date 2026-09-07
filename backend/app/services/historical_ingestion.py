from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

from app.db.repositories import (
    DailyCandleRepository,
    InstrumentRepository,
    IntradayCandleRepository,
)
from app.models.ingestion import (
    DailyCandle,
    ImportStatus,
    ImportSummary,
    ImportType,
    IngestionIssue,
    InstrumentRecord,
    IntradayCandle,
    PersistenceResult,
    ProviderReadResult,
    ValidationResult,
)
from app.providers.historical.base import HistoricalDataProvider
from app.services.data_quality import HistoricalDataValidator


class HistoricalIngestionService:
    def __init__(
        self,
        *,
        instrument_repository: InstrumentRepository | None = None,
        daily_candle_repository: DailyCandleRepository | None = None,
        intraday_candle_repository: IntradayCandleRepository | None = None,
        validator: HistoricalDataValidator | None = None,
    ) -> None:
        self.instrument_repository = instrument_repository
        self.daily_candle_repository = daily_candle_repository
        self.intraday_candle_repository = intraday_candle_repository
        self.validator = validator or HistoricalDataValidator()

    async def ingest_instruments(
        self,
        provider: HistoricalDataProvider,
        *,
        dry_run: bool = True,
    ) -> ImportSummary:
        read_result = await provider.list_instruments()
        validation_result = self._deduplicate_instruments(read_result.records)
        persistence = PersistenceResult()

        if not dry_run:
            self._require_repository(self.instrument_repository, "instrument_repository")
            persistence = await self.instrument_repository.upsert_many(
                validation_result.valid_records
            )

        return self.summarize_import(
            provider=provider,
            import_type=ImportType.INSTRUMENTS,
            read_result=read_result,
            validation_result=validation_result,
            persistence_result=persistence,
            dry_run=dry_run,
        )

    async def ingest_daily_candles(
        self,
        provider: HistoricalDataProvider,
        *,
        start: date | None = None,
        end: date | None = None,
        dry_run: bool = True,
    ) -> ImportSummary:
        read_result = await provider.get_daily_candles(start=start, end=end)
        validation_result = self.validator.validate_daily_candles(read_result.records)
        persistence = PersistenceResult()

        if not dry_run:
            self._require_repository(self.instrument_repository, "instrument_repository")
            self._require_repository(self.daily_candle_repository, "daily_candle_repository")
            instrument_ids = await self._upsert_and_resolve_instruments(
                validation_result.valid_records,
                provider=provider.name,
            )
            persistence = await self.daily_candle_repository.upsert_many(
                validation_result.valid_records,
                instrument_ids=instrument_ids,
            )

        return self.summarize_import(
            provider=provider,
            import_type=ImportType.DAILY_CANDLES,
            read_result=read_result,
            validation_result=validation_result,
            persistence_result=persistence,
            dry_run=dry_run,
        )

    async def ingest_intraday_candles(
        self,
        provider: HistoricalDataProvider,
        *,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
        dry_run: bool = True,
    ) -> ImportSummary:
        read_result = await provider.get_intraday_candles(
            interval=interval,
            start=start,
            end=end,
        )
        validation_result = self.validator.validate_intraday_candles(read_result.records)
        persistence = PersistenceResult()

        if not dry_run:
            self._require_repository(self.instrument_repository, "instrument_repository")
            self._require_repository(self.intraday_candle_repository, "intraday_candle_repository")
            instrument_ids = await self._upsert_and_resolve_instruments(
                validation_result.valid_records,
                provider=provider.name,
            )
            persistence = await self.intraday_candle_repository.upsert_many(
                validation_result.valid_records,
                instrument_ids=instrument_ids,
            )

        return self.summarize_import(
            provider=provider,
            import_type=ImportType.INTRADAY_CANDLES,
            read_result=read_result,
            validation_result=validation_result,
            persistence_result=persistence,
            dry_run=dry_run,
        )

    def validate_batch(
        self,
        records: Iterable[DailyCandle] | Iterable[IntradayCandle],
        *,
        mode: str,
    ) -> ValidationResult:
        if mode == "daily":
            return self.validator.validate_daily_candles(records)
        if mode == "intraday":
            return self.validator.validate_intraday_candles(records)
        raise ValueError(f"Unsupported validation mode: {mode}")

    def summarize_import(
        self,
        *,
        provider: HistoricalDataProvider,
        import_type: ImportType,
        read_result: ProviderReadResult,
        validation_result: ValidationResult,
        persistence_result: PersistenceResult,
        dry_run: bool,
    ) -> ImportSummary:
        errors = [*read_result.errors, *validation_result.errors]
        warnings = validation_result.warnings
        status = self._status_for(dry_run=dry_run, errors=errors, rows_valid=validation_result.valid_count)

        return ImportSummary(
            provider=provider.name,
            import_type=import_type,
            source_reference=read_result.source_reference,
            dry_run=dry_run,
            status=status,
            rows_read=read_result.rows_read,
            rows_valid=validation_result.valid_count,
            rows_inserted=0 if dry_run else persistence_result.rows_inserted,
            rows_updated=0 if dry_run else persistence_result.rows_updated,
            rows_skipped=validation_result.duplicate_count + persistence_result.rows_skipped,
            rows_rejected=len(errors),
            warnings_count=len(warnings),
            errors_count=len(errors),
            warnings=warnings,
            errors=errors,
            metadata=read_result.metadata,
        )

    def _deduplicate_instruments(
        self,
        records: list[InstrumentRecord],
    ) -> ValidationResult[InstrumentRecord]:
        seen = set()
        valid = []
        warnings: list[IngestionIssue] = []

        for index, record in enumerate(records, start=1):
            if record.key in seen:
                warnings.append(
                    IngestionIssue(
                        severity="warning",
                        code="duplicate_instrument",
                        message="Duplicate instrument skipped within this import batch.",
                        row_reference=f"record:{index}",
                    )
                )
                continue
            seen.add(record.key)
            valid.append(record)

        return ValidationResult(
            valid_records=valid,
            warnings=warnings,
            duplicate_count=len(warnings),
        )

    async def _upsert_and_resolve_instruments(
        self,
        candles: Iterable[DailyCandle] | Iterable[IntradayCandle],
        *,
        provider: str,
    ):
        instrument_records = [
            InstrumentRecord(
                exchange=candle.exchange,
                trading_symbol=candle.trading_symbol,
                company_name=candle.trading_symbol,
                instrument_type="EQUITY",
                provider=provider,
            )
            for candle in candles
        ]
        deduplicated = self._deduplicate_instruments(instrument_records)
        await self.instrument_repository.upsert_many(deduplicated.valid_records)
        return await self.instrument_repository.get_id_map(deduplicated.valid_records)

    def _status_for(
        self,
        *,
        dry_run: bool,
        errors: list[IngestionIssue],
        rows_valid: int,
    ) -> ImportStatus:
        if dry_run:
            return ImportStatus.DRY_RUN
        if errors and rows_valid:
            return ImportStatus.PARTIAL
        if errors:
            return ImportStatus.FAILED
        return ImportStatus.COMPLETED

    def _require_repository(self, repository, name: str) -> None:
        if repository is None:
            raise RuntimeError(f"{name} is required when dry_run is false")

