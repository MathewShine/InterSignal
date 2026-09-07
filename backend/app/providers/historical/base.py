from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Any

from app.models.ingestion import (
    DailyCandle,
    InstrumentRecord,
    IntradayCandle,
    ProviderReadResult,
)


class ProviderNotConfiguredError(RuntimeError):
    """Raised when a provider needs credentials or settings that are absent."""


class ProviderNotImplementedError(NotImplementedError):
    """Raised for provider capabilities intentionally deferred to later steps."""


class HistoricalDataProvider(ABC):
    name: str

    @abstractmethod
    async def list_instruments(self) -> ProviderReadResult[InstrumentRecord]:
        raise NotImplementedError

    @abstractmethod
    async def get_daily_candles(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> ProviderReadResult[DailyCandle]:
        raise NotImplementedError

    @abstractmethod
    async def get_intraday_candles(
        self,
        *,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> ProviderReadResult[IntradayCandle]:
        raise NotImplementedError

    @abstractmethod
    def supports_interval(self, interval: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_provider_metadata(self) -> dict[str, Any]:
        raise NotImplementedError

