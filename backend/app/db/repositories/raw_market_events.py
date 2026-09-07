from typing import Any, Protocol

from app.db.repositories.common import require_supabase_client, serialize_record
from app.db.supabase import SupabaseClientFactory
from app.models.ingestion import PersistenceResult


class RawMarketEventRepository(Protocol):
    async def insert_many(self, records: list[dict[str, Any]]) -> PersistenceResult:
        ...


class SupabaseRawMarketEventRepository:
    def __init__(self, factory: SupabaseClientFactory) -> None:
        self.factory = factory

    async def insert_many(self, records: list[dict[str, Any]]) -> PersistenceResult:
        if not records:
            return PersistenceResult()

        client = require_supabase_client(self.factory)
        payload = [serialize_record(record) for record in records]
        response = client.table("raw_market_events").insert(payload).execute()
        affected = len(response.data or payload)
        return PersistenceResult(rows_inserted=affected)

