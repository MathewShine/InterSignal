from typing import Protocol
from uuid import UUID

from app.db.repositories.common import require_supabase_client, serialize_record
from app.db.supabase import SupabaseClientFactory
from app.models.ingestion import DailyCandle, IntradayCandle, PersistenceResult

InstrumentKey = tuple[str, str]


class DailyCandleRepository(Protocol):
    async def upsert_many(
        self,
        records: list[DailyCandle],
        *,
        instrument_ids: dict[InstrumentKey, UUID],
    ) -> PersistenceResult:
        ...


class IntradayCandleRepository(Protocol):
    async def upsert_many(
        self,
        records: list[IntradayCandle],
        *,
        instrument_ids: dict[InstrumentKey, UUID],
    ) -> PersistenceResult:
        ...


class SupabaseDailyCandleRepository:
    def __init__(self, factory: SupabaseClientFactory) -> None:
        self.factory = factory

    async def upsert_many(
        self,
        records: list[DailyCandle],
        *,
        instrument_ids: dict[InstrumentKey, UUID],
    ) -> PersistenceResult:
        if not records:
            return PersistenceResult()

        client = require_supabase_client(self.factory)
        payload = [
            serialize_record(
                {
                    "instrument_id": instrument_ids[record.instrument_key],
                    "trading_date": record.trading_date,
                    "open": record.open,
                    "high": record.high,
                    "low": record.low,
                    "close": record.close,
                    "adjusted_close": record.adjusted_close,
                    "volume": record.volume,
                    "traded_value": record.traded_value,
                    "source": record.source,
                }
            )
            for record in records
        ]

        response = client.table("daily_candles").upsert(
            payload,
            on_conflict="instrument_id,trading_date,source",
        ).execute()
        affected = len(response.data or payload)
        return PersistenceResult(rows_inserted=affected)


class SupabaseIntradayCandleRepository:
    def __init__(self, factory: SupabaseClientFactory) -> None:
        self.factory = factory

    async def upsert_many(
        self,
        records: list[IntradayCandle],
        *,
        instrument_ids: dict[InstrumentKey, UUID],
    ) -> PersistenceResult:
        if not records:
            return PersistenceResult()

        client = require_supabase_client(self.factory)
        payload = [
            serialize_record(
                {
                    "instrument_id": instrument_ids[record.instrument_key],
                    "candle_timestamp": record.timestamp,
                    "interval_code": record.interval,
                    "open": record.open,
                    "high": record.high,
                    "low": record.low,
                    "close": record.close,
                    "volume": record.volume,
                    "traded_value": record.traded_value,
                    "vwap": record.vwap,
                    "source": record.source,
                }
            )
            for record in records
        ]

        response = client.table("intraday_candles").upsert(
            payload,
            on_conflict="instrument_id,candle_timestamp,interval_code,source",
        ).execute()
        affected = len(response.data or payload)
        return PersistenceResult(rows_inserted=affected)

