from typing import Protocol
from uuid import UUID

from app.db.repositories.common import require_supabase_client, serialize_record
from app.db.supabase import SupabaseClientFactory
from app.models.ingestion import InstrumentRecord, PersistenceResult

InstrumentKey = tuple[str, str]


class InstrumentRepository(Protocol):
    async def upsert_many(self, records: list[InstrumentRecord]) -> PersistenceResult:
        ...

    async def get_id_map(self, records: list[InstrumentRecord]) -> dict[InstrumentKey, UUID]:
        ...


class SupabaseInstrumentRepository:
    def __init__(self, factory: SupabaseClientFactory) -> None:
        self.factory = factory

    async def upsert_many(self, records: list[InstrumentRecord]) -> PersistenceResult:
        if not records:
            return PersistenceResult()

        client = require_supabase_client(self.factory)
        payload = [
            serialize_record(
                {
                    "provider_symbol": record.provider_symbol,
                    "exchange": record.exchange,
                    "trading_symbol": record.trading_symbol,
                    "company_name": record.company_name,
                    "isin": record.isin,
                    "sector": record.sector,
                    "industry": record.industry,
                    "instrument_type": record.instrument_type,
                    "nifty500_member": record.nifty500_member,
                    "active": True,
                }
            )
            for record in records
        ]

        response = client.table("instruments").upsert(
            payload,
            on_conflict="exchange,trading_symbol",
        ).execute()
        affected = len(response.data or payload)
        return PersistenceResult(rows_inserted=affected)

    async def get_id_map(self, records: list[InstrumentRecord]) -> dict[InstrumentKey, UUID]:
        if not records:
            return {}

        client = require_supabase_client(self.factory)
        symbols = sorted({record.trading_symbol for record in records})
        response = client.table("instruments").select(
            "id,exchange,trading_symbol"
        ).in_("trading_symbol", symbols).execute()

        requested_keys = {record.key for record in records}
        id_map: dict[InstrumentKey, UUID] = {}
        for item in response.data or []:
            key = (item["exchange"], item["trading_symbol"])
            if key in requested_keys:
                id_map[key] = UUID(item["id"])

        return id_map

