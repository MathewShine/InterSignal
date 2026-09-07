from app.providers.historical.base import (
    HistoricalDataProvider,
    ProviderNotConfiguredError,
    ProviderNotImplementedError,
)
from app.providers.historical.csv_provider import (
    CSVColumnMapping,
    CsvHistoricalDataProvider,
)
from app.providers.historical.nse_file_provider import NSEFileProvider

__all__ = [
    "CSVColumnMapping",
    "CsvHistoricalDataProvider",
    "GrowwHistoricalProvider",
    "GrowwHistoricalProviderConfig",
    "HistoricalDataProvider",
    "NSEFileProvider",
    "ProviderNotConfiguredError",
    "ProviderNotImplementedError",
    "GrowwProviderNotConfiguredError",
]


def __getattr__(name):
    if name in {"GrowwHistoricalProvider", "GrowwHistoricalProviderConfig"}:
        from app.providers.groww.historical import (
            GrowwHistoricalProvider,
            GrowwHistoricalProviderConfig,
        )

        return {
            "GrowwHistoricalProvider": GrowwHistoricalProvider,
            "GrowwHistoricalProviderConfig": GrowwHistoricalProviderConfig,
        }[name]

    if name == "GrowwProviderNotConfiguredError":
        from app.providers.groww.exceptions import GrowwProviderNotConfiguredError

        return GrowwProviderNotConfiguredError

    raise AttributeError(name)
