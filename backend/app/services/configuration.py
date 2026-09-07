from typing import Any, Protocol


class ConfigurationProvider(Protocol):
    async def get_value(self, key: str) -> Any | None:
        ...

    async def list_values(self, namespace: str | None = None) -> dict[str, Any]:
        ...


class ConfigurationService:
    def __init__(self, provider: ConfigurationProvider | None = None) -> None:
        self.provider = provider

    async def get_value(self, key: str) -> Any | None:
        if self.provider is None:
            return None
        return await self.provider.get_value(key)

    async def list_values(self, namespace: str | None = None) -> dict[str, Any]:
        if self.provider is None:
            return {}
        return await self.provider.list_values(namespace)

