from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, Mapping


class MarketDataProvider(ABC):
    @abstractmethod
    async def get_quote(self, symbol: str) -> Mapping[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def get_historical_candles(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[Mapping[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def subscribe_ticks(self, symbols: list[str]) -> AsyncIterator[Mapping[str, Any]]:
        raise NotImplementedError

