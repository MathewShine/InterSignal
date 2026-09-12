from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import time
from decimal import Decimal
from typing import Any

from app.research.temporal_validation.config import canonical_hash, json_ready

INTRADAY_RESEARCH_ARCHITECTURE_VERSION = "INTRADAY_RESEARCH_ARCHITECTURE_V1"
CANONICAL_INTRADAY_PROFILE = "NSE_CASH_INTRADAY_5M_V1"
EXECUTION_ORDERING_VERSION = "EXECUTION_ORDERING_V1"
SESSION_VERSION = "NSE_CASH_SESSION_V1"
BAR_QUALITY_VERSION = "INTRADAY_BAR_QUALITY_V1"
OPENING_RANGE_VERSION = "OPENING_RANGE_V1"
VWAP_VERSION = "SESSION_VWAP_FROM_5M_V1"
FIRST_TOUCH_ENGINE_VERSION = "INTRADAY_FIRST_TOUCH_ENGINE_V1"
NORMALIZATION_VERSION = "INTRADAY_NORMALIZATION_V1"

ASIA_KOLKATA_NAME = "Asia/Kolkata"
CANONICAL_INTERVAL = "5m"
DERIVED_INTERVALS = ("10m", "15m")
NORMAL_SESSION_START = time(9, 15)
NORMAL_SESSION_END = time(15, 30)
EXPECTED_FIVE_MINUTE_BARS = 75

STRICT = "STRICT"
LENIENT = "LENIENT"


@dataclass(frozen=True, slots=True)
class IntradayResearchConfig:
    architecture_version: str = INTRADAY_RESEARCH_ARCHITECTURE_VERSION
    profile: str = CANONICAL_INTRADAY_PROFILE
    execution_ordering_version: str = EXECUTION_ORDERING_VERSION
    session_version: str = SESSION_VERSION
    quality_version: str = BAR_QUALITY_VERSION
    normalization_version: str = NORMALIZATION_VERSION
    exchange: str = "NSE"
    exchange_timezone: str = ASIA_KOLKATA_NAME
    base_interval: str = CANONICAL_INTERVAL
    derived_intervals: tuple[str, ...] = DERIVED_INTERVALS
    normal_session_start: time = NORMAL_SESSION_START
    normal_session_end: time = NORMAL_SESSION_END
    expected_five_minute_bars: int = EXPECTED_FIVE_MINUTE_BARS
    causal_quality_policy: str = STRICT
    material_missing_bar_count: int = 1
    opening_range_windows_minutes: tuple[int, ...] = (5, 10, 15, 30)
    confirmation_windows_minutes: tuple[int, ...] = (5, 10, 15)
    vwap_price_method: str = "TYPICAL_PRICE_HIGH_LOW_CLOSE_DIV_3"
    corporate_action_policy: str = "RAW_OBSERVED_WITH_REFERENCE_METADATA_NO_AUTO_ADJUSTMENT"
    preferred_bulk_format: str = "PARQUET"
    limit_fill_assumption: str = "ASSUMED_FILLED_ON_TOUCH"
    validation_state: str = "SEALED"
    performance_on_validation_dates: str = "PROHIBITED"
    live_execution_enabled: bool = False

    def snapshot(self) -> dict[str, Any]:
        value = asdict(self)
        value["normal_session_start"] = self.normal_session_start.isoformat()
        value["normal_session_end"] = self.normal_session_end.isoformat()
        return json_ready(value)

    def config_hash(self) -> str:
        return canonical_hash(self.snapshot())


DEFAULT_INTRADAY_CONFIG = IntradayResearchConfig()
EXPECTED_INTRADAY_CONFIG_HASH = "d3683195aaa81962c8919ff17bfe8b2dc6e21c981deda833facd0c6dd910698a"


STORAGE_ESTIMATE = {
    "symbols": 500,
    "bars_per_normal_session": EXPECTED_FIVE_MINUTE_BARS,
    "sessions_per_year": 250,
    "years": 5,
    "estimated_rows": 500 * EXPECTED_FIVE_MINUTE_BARS * 250 * 5,
    "compressed_bytes_per_row_low": 64,
    "compressed_bytes_per_row_high": 160,
    "compressed_gib_low": Decimal(500 * EXPECTED_FIVE_MINUTE_BARS * 250 * 5 * 64) / Decimal(1024**3),
    "compressed_gib_high": Decimal(500 * EXPECTED_FIVE_MINUTE_BARS * 250 * 5 * 160) / Decimal(1024**3),
    "planning_range_gib_with_metadata": "4-10 GiB",
}
