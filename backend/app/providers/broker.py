from abc import ABC, abstractmethod
from typing import Any, Mapping


class BrokerProvider(ABC):
    @abstractmethod
    async def place_order(self, order: Mapping[str, Any]) -> Mapping[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def modify_order(
        self,
        order_id: str,
        changes: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def cancel_order(self, order_id: str) -> Mapping[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def get_orders(self) -> list[Mapping[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def get_positions(self) -> list[Mapping[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def get_funds(self) -> Mapping[str, Any]:
        raise NotImplementedError

