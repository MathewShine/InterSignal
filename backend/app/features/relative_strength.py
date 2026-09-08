from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True, slots=True)
class BenchmarkObservation:
    trading_date: date
    close: Decimal


class BenchmarkProvider:
    name = "benchmark_provider"

    def is_available(self) -> bool:
        raise NotImplementedError

    def return_for(self, trading_date: date, window: int) -> Decimal | None:
        raise NotImplementedError


class UnavailableBenchmarkProvider(BenchmarkProvider):
    name = "UNAVAILABLE_OFFICIAL_BENCHMARK_HISTORY"

    def __init__(self, reason: str = "Official benchmark close history is not present locally.") -> None:
        self.reason = reason

    def is_available(self) -> bool:
        return False

    def return_for(self, trading_date: date, window: int) -> Decimal | None:
        return None


def resolve_benchmark_provider(data_dir: Path) -> BenchmarkProvider:
    candidates = (
        data_dir / "reference" / "indices" / "nifty50_daily.csv",
        data_dir / "reference" / "indices" / "nifty500_daily.csv",
    )
    if any(path.exists() for path in candidates):
        return UnavailableBenchmarkProvider(
            "A candidate benchmark file exists, but Command 01 has no approved benchmark parser yet."
        )
    return UnavailableBenchmarkProvider()
