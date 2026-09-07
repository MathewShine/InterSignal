from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.db.supabase import SupabaseClientFactory


class RepositoryNotConfiguredError(RuntimeError):
    pass


def require_supabase_client(factory: SupabaseClientFactory):
    client = factory.get_client()
    if client is None:
        raise RepositoryNotConfiguredError(
            "Supabase is not configured. Use dry-run mode or provide credentials."
        )
    return client


def serialize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def serialize_record(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: serialize_value(value) for key, value in payload.items()}

