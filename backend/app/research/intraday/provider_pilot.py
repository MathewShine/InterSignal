from __future__ import annotations

import csv
import gzip
import json
import math
import queue
import threading
import time
from collections import defaultdict
from contextlib import redirect_stdout
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import StrEnum
from io import StringIO
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from app.backtesting.portfolio_baseline import (
    portfolio_backtest_regression_hash_checks,
    portfolio_backtest_regression_hashes,
    verify_current_portfolio_backtest_baseline,
)
from app.config.settings import Settings
from app.providers.groww.auth import GrowwAuthService, GrowwCredentials
from app.research.intraday.aggregation import aggregate_bars
from app.research.intraday.architecture import (
    _cost_registry_state,
    _diagnostic_registry_state,
    _temporal_registry_state,
)
from app.research.intraday.calendar import ASIA_KOLKATA, NseCashSessionCalendar
from app.research.intraday.config import DEFAULT_INTRADAY_CONFIG, STORAGE_ESTIMATE
from app.research.intraday.first_touch import evaluate_first_touch
from app.research.intraday.models import (
    AmbiguityPolicy,
    CanonicalIntradayBar,
    DailyBarReference,
    FirstTouch,
    IntradayBarQuality,
    PilotDataStatus,
)
from app.research.intraday.normalization import (
    canonical_bar_row,
    intraday_dataset_hash,
    normalize_rows,
    parse_timestamp,
)
from app.research.intraday.opening_range import calculate_opening_range
from app.research.intraday.quality import assess_session_quality
from app.research.intraday.reconciliation import reconcile_daily_bar
from app.research.intraday.vwap import calculate_session_vwap
from app.research.temporal_validation.config import canonical_hash, json_ready
from app.strategy.momentum_candidates import file_sha256
from app.strategy.outcomes.outcome_baseline import resolve_current_strategy_outcome_dataset


PILOT_VERSION = "REAL_INTRADAY_PROVIDER_PILOT_V1"
PILOT_PROFILE = "NSE_CASH_5M_PROVIDER_PILOT_V1"
CAPABILITY_AUDIT_VERSION = "INTRADAY_PROVIDER_CAPABILITY_AUDIT_V1"
SESSION_USABILITY_VERSION = "REAL_INTRADAY_SESSION_USABILITY_V1"
GROWW_RETRIEVAL_TRANSPORT_VERSION = "GROWW_RETRIEVAL_TRANSPORT_V1_1"
PILOT_SYMBOLS = ("ABCAPITAL", "ALKYLAMINE", "BALRAMCHIN", "COALINDIA", "TITAN")
PILOT_DATES = tuple(date(2022, 1, day) for day in range(3, 8))
DEVELOPMENT_START = date(2022, 1, 1)
DEVELOPMENT_END = date(2024, 12, 31)
MAX_NORMALIZED_ROWS = 10_000
EXPECTED_SYNTHETIC_HASHES = {
    "normalized_5m_hash": "cba10d96349f5dbba48ad60dc6aa058890523d4da99f1ff9109ed590eb07742d",
    "derived_10m_hash": "0090aa374d84be69e823b48a08d9c0a35aa48cd8b0fdcc80cb8189d2c2b2b8cc",
    "derived_15m_hash": "fc1e81be73d1f00c20f5cd5128b9213a8848f5d466d24716e1a811da00f70f2a",
}
REPORT_NAMES = (
    "real_intraday_provider_v1_summary.json",
    "real_intraday_provider_v1_capabilities.csv",
    "real_intraday_provider_v1_instrument_mapping.csv",
    "real_intraday_provider_v1_requests.csv",
    "real_intraday_provider_v1_sessions.csv",
    "real_intraday_provider_v1_quality.csv",
    "real_intraday_provider_v1_daily_reconciliation.csv",
    "real_intraday_provider_v1_opening_range.csv",
    "real_intraday_provider_v1_vwap.csv",
    "real_intraday_provider_v1_first_touch.csv",
    "real_intraday_provider_v1_confirmation_availability.csv",
    "real_intraday_provider_v1_scalability.csv",
    "real_intraday_provider_v1_pilot.csv",
)


class SourceStatus(StrEnum):
    AUTHORITATIVE_PROVIDER_DOCS = "AUTHORITATIVE_PROVIDER_DOCS"
    OFFICIAL_SDK = "OFFICIAL_SDK"
    OFFICIAL_API = "OFFICIAL_API"
    EXISTING_PROJECT_CONFIG = "EXISTING_PROJECT_CONFIG"
    UNKNOWN = "UNKNOWN"
    NOT_SUPPORTED = "NOT_SUPPORTED"


class ResearchRightsStatus(StrEnum):
    CLEAR_FOR_PERSONAL_RESEARCH = "CLEAR_FOR_PERSONAL_RESEARCH"
    USABLE_WITH_RESTRICTIONS = "USABLE_WITH_RESTRICTIONS"
    TERMS_REVIEW_REQUIRED = "TERMS_REVIEW_REQUIRED"
    NOT_PERMITTED = "NOT_PERMITTED"
    UNKNOWN = "UNKNOWN"


class ProviderSelectionResult(StrEnum):
    PROVIDER_SELECTED = "PROVIDER_SELECTED"
    NO_PROVIDER_CAPABLE = "NO_PROVIDER_CAPABLE"
    TERMS_BLOCKED = "TERMS_BLOCKED"
    AUTH_BLOCKED = "AUTH_BLOCKED"
    HISTORY_BLOCKED = "HISTORY_BLOCKED"
    INCONCLUSIVE = "INCONCLUSIVE"


class InstrumentMappingResult(StrEnum):
    CLEAN = "CLEAN"
    CLEAN_WITH_MISSING_ISIN = "CLEAN_WITH_MISSING_ISIN"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    INCONCLUSIVE = "INCONCLUSIVE"


class SessionUsability(StrEnum):
    USABLE_STRICT = "USABLE_STRICT"
    USABLE_WITH_WARNING = "USABLE_WITH_WARNING"
    UNUSABLE = "UNUSABLE"


class RealDataQualityResult(StrEnum):
    CLEAN = "CLEAN"
    USABLE_WITH_MINOR_GAPS = "USABLE_WITH_MINOR_GAPS"
    USABLE_WITH_MATERIAL_GAPS = "USABLE_WITH_MATERIAL_GAPS"
    POOR = "POOR"
    NO_REAL_DATA_INGESTED = "NO_REAL_DATA_INGESTED"
    INCONCLUSIVE = "INCONCLUSIVE"


class ReconciliationClassification(StrEnum):
    MATCH = "MATCH"
    MINOR_SOURCE_DIFFERENCE = "MINOR_SOURCE_DIFFERENCE"
    MATERIAL_PRICE_MISMATCH = "MATERIAL_PRICE_MISMATCH"
    MATERIAL_VOLUME_MISMATCH = "MATERIAL_VOLUME_MISMATCH"
    UNAVAILABLE_DAILY_REFERENCE = "UNAVAILABLE_DAILY_REFERENCE"


class RealReconciliationResult(StrEnum):
    CLEAN = "CLEAN"
    CLEAN_WITH_SOURCE_DIFFERENCES = "CLEAN_WITH_SOURCE_DIFFERENCES"
    MATERIAL_MISMATCH = "MATERIAL_MISMATCH"
    INCONCLUSIVE = "INCONCLUSIVE"


class VwapQualityResult(StrEnum):
    CLEAN = "CLEAN"
    CLEAN_WITH_SOURCE_DIFFERENCES = "CLEAN_WITH_SOURCE_DIFFERENCES"
    UNUSABLE_DUE_TO_VOLUME = "UNUSABLE_DUE_TO_VOLUME"
    NO_PROVIDER_COMPARISON = "NO_PROVIDER_COMPARISON"
    INCONCLUSIVE = "INCONCLUSIVE"


class ProviderReliabilityResult(StrEnum):
    CLEAN = "CLEAN"
    USABLE_WITH_LIMITATIONS = "USABLE_WITH_LIMITATIONS"
    UNRELIABLE = "UNRELIABLE"
    BLOCKED = "BLOCKED"
    INCONCLUSIVE = "INCONCLUSIVE"


class FullIngestionFeasibility(StrEnum):
    FEASIBLE = "FEASIBLE"
    FEASIBLE_WITH_BATCHING = "FEASIBLE_WITH_BATCHING"
    FEASIBLE_BUT_COSTLY = "FEASIBLE_BUT_COSTLY"
    HISTORY_TOO_LIMITED = "HISTORY_TOO_LIMITED"
    RATE_LIMIT_PROHIBITIVE = "RATE_LIMIT_PROHIBITIVE"
    TERMS_BLOCKED = "TERMS_BLOCKED"
    INCONCLUSIVE = "INCONCLUSIVE"


class RealPilotResult(StrEnum):
    PASS = "PASS"
    PASS_WITH_LIMITATIONS = "PASS_WITH_LIMITATIONS"
    FAIL_PROVIDER = "FAIL_PROVIDER"
    FAIL_DATA_QUALITY = "FAIL_DATA_QUALITY"
    FAIL_RECONCILIATION = "FAIL_RECONCILIATION"
    BLOCKED_NO_CREDENTIALS = "BLOCKED_NO_CREDENTIALS"
    BLOCKED_HISTORY = "BLOCKED_HISTORY"
    BLOCKED_TERMS = "BLOCKED_TERMS"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True, slots=True)
class ProviderCapability:
    provider_name: str
    official_api_or_sdk: str
    authentication_required: bool
    market_data_only_possible: bool
    nse_cash_supported: bool
    historical_intraday_supported: bool
    minimum_interval: str
    five_minute_supported: bool
    volume_supported: bool
    vwap_supported: bool
    adjusted_prices_supported: str
    max_history_per_request: str
    overall_history_depth: str
    rate_limit: str
    request_batch_limit: str
    instrument_master_available: bool
    timestamp_timezone: str
    timestamp_definition: str
    data_retention_limit: str
    corporate_action_semantics: str
    official_documentation_reference: str
    licensing_terms_status: str
    research_use_status: str
    redistribution_status: str
    known_limitations: tuple[str, ...]
    pilot_eligibility: str
    evidence_status: str

    def snapshot(self) -> dict[str, Any]:
        return json_ready(asdict(self))


@dataclass(frozen=True, slots=True)
class PilotSpec:
    symbols: tuple[str, ...] = PILOT_SYMBOLS
    dates: tuple[date, ...] = PILOT_DATES
    interval: str = "5m"
    max_provider_requests: int = 7
    expected_requests: int = 7
    max_normalized_rows: int = MAX_NORMALIZED_ROWS

    def validate(self) -> None:
        if not 5 <= len(self.symbols) <= 10:
            raise ValueError("Pilot requires 5-10 symbols")
        if not 5 <= len(self.dates) <= 10:
            raise ValueError("Pilot requires 5-10 sessions")
        if len(set(self.symbols)) != len(self.symbols):
            raise ValueError("Pilot symbols must be unique")
        if len(set(self.dates)) != len(self.dates):
            raise ValueError("Pilot dates must be unique")
        if self.interval != "5m":
            raise ValueError("Pilot interval must be native 5m")
        if any(value < DEVELOPMENT_START or value > DEVELOPMENT_END for value in self.dates):
            raise ValueError("Pilot requests must remain inside DEVELOPMENT")
        if self.max_normalized_rows > MAX_NORMALIZED_ROWS:
            raise ValueError("Pilot row cap cannot exceed 10,000")
        if self.expected_requests > self.max_provider_requests:
            raise ValueError("Expected requests exceed the frozen request budget")


@dataclass(frozen=True, slots=True)
class InstrumentMapping:
    internal_symbol: str
    internal_isin: str | None
    provider_symbol: str
    provider_instrument_id: str | None
    exchange: str
    mapping_source: str
    valid_from: str
    valid_to: str
    mapping_status: str

    def snapshot(self) -> dict[str, Any]:
        return json_ready(asdict(self))


@dataclass(slots=True)
class RequestBudget:
    max_provider_requests: int
    expected_requests: int
    actual_requests: int = 0
    retry_count: int = 0
    request_rows: list[dict[str, Any]] = field(default_factory=list)

    def reserve(self) -> None:
        if self.actual_requests >= self.max_provider_requests:
            raise RuntimeError("Provider request budget exhausted")
        self.actual_requests += 1


class GrowwWallClockTimeoutError(TimeoutError):
    """Raised when an SDK call exceeds the audit-approved total wall-clock bound."""


def run_with_wall_clock_timeout(call: Callable[[], Any], timeout_seconds: float) -> Any:
    """Bound an otherwise blocking SDK call without persisting request credentials.

    The official SDK exposes a requests-style connect/read inactivity timeout but
    no total wall-clock timeout.  A daemon worker lets the ingestion controller
    checkpoint and stop after the configured bound even if the SDK remains
    blocked.  The late result is deliberately discarded and can never be
    accepted into the immutable raw-data layer.
    """

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    results: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)

    def worker() -> None:
        try:
            results.put(("RESULT", call()))
        except BaseException as exc:  # propagate the original provider exception
            results.put(("ERROR", exc))

    thread = threading.Thread(target=worker, name="groww-historical-bounded-call", daemon=True)
    thread.start()
    thread.join(timeout_seconds)
    if thread.is_alive():
        raise GrowwWallClockTimeoutError(
            f"Groww historical request exceeded the configured {timeout_seconds:g}s total wall-clock bound"
        )
    kind, value = results.get_nowait()
    if kind == "ERROR":
        raise value
    return value


class GrowwResearchMarketDataAdapter:
    """Historical-data-only boundary around the official SDK."""

    provider_name = "Groww"
    timestamp_semantics = "BAR_START_FROM_INTERVAL_ALIGNED_OFFICIAL_EXAMPLES_WITH_PROSE_LIMITATION"

    def __init__(
        self,
        *,
        client: Any,
        budget: RequestBudget,
        throttle_seconds: float = 1.0,
        max_retries: int = 3,
        connect_timeout_seconds: float = 10.0,
        read_timeout_seconds: float = 20.0,
        total_timeout_seconds: float = 30.0,
        max_consecutive_timeouts: int = 3,
        call_runner: Callable[[Callable[[], Any], float], Any] = run_with_wall_clock_timeout,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.perf_counter,
    ) -> None:
        if max_retries < 0 or max_retries > 3:
            raise ValueError("max_retries must be between zero and three")
        if min(connect_timeout_seconds, read_timeout_seconds, total_timeout_seconds) <= 0:
            raise ValueError("Groww timeout values must be positive")
        if max_consecutive_timeouts <= 0:
            raise ValueError("max_consecutive_timeouts must be positive")
        self._client = client
        self._budget = budget
        self._throttle_seconds = max(0.0, throttle_seconds)
        self._max_retries = max_retries
        self._connect_timeout_seconds = connect_timeout_seconds
        self._read_timeout_seconds = read_timeout_seconds
        self._total_timeout_seconds = total_timeout_seconds
        self._max_consecutive_timeouts = max_consecutive_timeouts
        self._call_runner = call_runner
        self._sleeper = sleeper
        self._monotonic = monotonic
        self._last_request_at: float | None = None
        self._consecutive_timeouts = 0

    def resolve_instruments(
        self,
        symbols: Sequence[str],
        internal_isins: Mapping[str, str | None],
    ) -> list[InstrumentMapping]:
        started = self._monotonic()
        self._before_request()
        try:
            with redirect_stdout(StringIO()):
                instruments = self._client.get_all_instruments()
            records = instruments.to_dict("records") if hasattr(instruments, "to_dict") else list(instruments)
            status = "SUCCESS"
            category = "OK"
        except Exception as exc:
            status = "FAILED"
            category = classify_provider_failure(exc)
            self._record_request("instrument-master", status, category, started)
            raise
        self._record_request("instrument-master", status, category, started)
        mappings: list[InstrumentMapping] = []
        for symbol in symbols:
            wanted = f"NSE-{symbol}"
            candidates = [
                row
                for row in records
                if str(row.get("exchange", "")).upper() == "NSE"
                and str(row.get("segment", "CASH")).upper() == "CASH"
                and (
                    str(row.get("groww_symbol", "")).upper() == wanted
                    or str(row.get("trading_symbol", "")).upper() == symbol
                )
            ]
            equity = [row for row in candidates if str(row.get("instrument_type", "EQ")).upper() == "EQ"]
            chosen = (equity or candidates)[0] if (equity or candidates) else None
            if chosen is None:
                mappings.append(
                    InstrumentMapping(
                        symbol,
                        internal_isins.get(symbol),
                        wanted,
                        None,
                        "NSE",
                        "OFFICIAL_GROWW_INSTRUMENT_MASTER",
                        "UNKNOWN",
                        "UNKNOWN",
                        "UNRESOLVED",
                    )
                )
                continue
            provider_isin = _optional_text(chosen.get("isin"))
            internal_isin = internal_isins.get(symbol)
            mapping_status = "CLEAN"
            if internal_isin and provider_isin and internal_isin != provider_isin:
                mapping_status = "ISIN_MISMATCH"
            elif not (internal_isin or provider_isin):
                mapping_status = "MISSING_ISIN"
            mappings.append(
                InstrumentMapping(
                    symbol,
                    internal_isin or provider_isin,
                    str(chosen.get("groww_symbol") or wanted),
                    _optional_text(
                        chosen.get("exchange_token")
                        or chosen.get("instrument_token")
                        or chosen.get("token")
                    ),
                    "NSE",
                    "OFFICIAL_GROWW_INSTRUMENT_MASTER",
                    "UNKNOWN",
                    "UNKNOWN",
                    mapping_status,
                )
            )
        return mappings

    def fetch_historical_5m(
        self,
        *,
        mapping: InstrumentMapping,
        start_date: date,
        end_date: date,
        request_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        _validate_development_dates((start_date, end_date))
        if (end_date - start_date).days + 1 > 30:
            raise ValueError("Groww native 5m request exceeds the documented 30-day limit")
        attempt = 0
        while True:
            started = self._monotonic()
            started_at = datetime.now(timezone.utc)
            self._before_request()
            try:
                def sdk_call() -> Any:
                    with redirect_stdout(StringIO()):
                        return self._client.get_historical_candles(
                            exchange=getattr(self._client, "EXCHANGE_NSE", "NSE"),
                            segment=getattr(self._client, "SEGMENT_CASH", "CASH"),
                            groww_symbol=mapping.provider_symbol,
                            start_time=f"{start_date.isoformat()} 09:15:00",
                            end_time=f"{end_date.isoformat()} 15:30:00",
                            candle_interval=getattr(self._client, "CANDLE_INTERVAL_MIN_5", "5minute"),
                            timeout=(self._connect_timeout_seconds, self._read_timeout_seconds),
                        )

                response = self._call_runner(sdk_call, self._total_timeout_seconds)
                if not isinstance(response, dict):
                    raise ValueError("Provider returned a non-object response")
                self._consecutive_timeouts = 0
                self._record_request(
                    request_id,
                    "SUCCESS",
                    "OK",
                    started,
                    attempt,
                    started_at=started_at,
                    row_count=len(response.get("candles", [])),
                )
                return response, self._budget.request_rows[-1]
            except Exception as exc:
                category = "TIMEOUT" if isinstance(exc, GrowwWallClockTimeoutError) else classify_provider_failure(exc)
                retryable = category in {"RATE_LIMIT", "TIMEOUT", "TRANSIENT_NETWORK", "SERVER_ERROR"}
                self._consecutive_timeouts = self._consecutive_timeouts + 1 if category == "TIMEOUT" else 0
                self._record_request(
                    request_id,
                    "FAILED",
                    category,
                    started,
                    attempt,
                    started_at=started_at,
                    exception_category=type(exc).__name__,
                )
                if self._consecutive_timeouts >= self._max_consecutive_timeouts:
                    raise RuntimeError("Groww historical timeout circuit breaker opened") from exc
                if not retryable or attempt >= self._max_retries:
                    raise RuntimeError(f"Historical request failed: {category}") from exc
                attempt += 1
                self._budget.retry_count += 1
                self._sleeper(min(2**attempt, 8))

    def _before_request(self) -> None:
        if self._last_request_at is not None:
            elapsed = self._monotonic() - self._last_request_at
            if elapsed < self._throttle_seconds:
                self._sleeper(self._throttle_seconds - elapsed)
        self._budget.reserve()
        self._last_request_at = self._monotonic()

    def _record_request(
        self,
        request_id: str,
        status: str,
        response_category: str,
        started: float,
        retry_number: int = 0,
        *,
        started_at: datetime | None = None,
        row_count: int | None = None,
        exception_category: str | None = None,
    ) -> None:
        completed_at = datetime.now(timezone.utc)
        self._budget.request_rows.append(
            {
                "request_id": request_id,
                "provider": self.provider_name,
                "endpoint_category": "INSTRUMENT_MASTER" if request_id == "instrument-master" else "HISTORICAL_CANDLES",
                "status": status,
                "response_category": response_category,
                "retry_number": retry_number,
                "latency_ms": round((self._monotonic() - started) * 1000, 3),
                "request_started_at": started_at.isoformat() if started_at else None,
                "request_completed_at": completed_at.isoformat(),
                "row_count": row_count,
                "exception": exception_category,
                "transport_version": GROWW_RETRIEVAL_TRANSPORT_VERSION,
            }
        )


def provider_capability_audit() -> tuple[ProviderCapability, ...]:
    groww_docs = "https://groww.in/trade-api/docs/curl/backtesting"
    groww_instruments = "https://groww.in/trade-api/docs/curl/instruments"
    zerodha_docs = "https://kite.trade/docs/connect/v3/historical/"
    return (
        ProviderCapability(
            "Groww",
            "Official Groww API and installed official growwapi 1.5.0 SDK",
            True,
            True,
            True,
            True,
            "1m",
            True,
            True,
            False,
            "UNKNOWN",
            "30 calendar days for 1m/2m/3m/5m",
            "Equity, index, and FNO data documented from 2020",
            "Historical endpoint overall rate not documented; pilot throttle is 1 request/second",
            "One instrument per candle request",
            True,
            "Asia/Kolkata inferred from NSE-local naive examples and existing adapter contract",
            "BAR_START_FROM_INTERVAL_ALIGNED_OFFICIAL_EXAMPLES; not explicitly defined in prose",
            "UNKNOWN",
            "No adjusted-price or corporate-action treatment documented for historical candles",
            f"{groww_docs} | {groww_instruments}",
            str(ResearchRightsStatus.USABLE_WITH_RESTRICTIONS),
            str(ResearchRightsStatus.USABLE_WITH_RESTRICTIONS),
            "UNKNOWN",
            (
                "Timestamp definition is evidenced by interval-aligned examples but not explicit prose",
                "No provider VWAP",
                "Adjustment, retention, redistribution, and historical endpoint rate details are undocumented",
            ),
            "SELECTED_FOR_TINY_PRIVATE_BACKTESTING_PILOT_WITH_WARNINGS",
            str(SourceStatus.AUTHORITATIVE_PROVIDER_DOCS),
        ),
        ProviderCapability(
            "Zerodha",
            "Official Kite Connect API and official SDKs",
            True,
            True,
            True,
            True,
            "1m",
            True,
            True,
            False,
            "UNKNOWN",
            "Interval-specific limit not stated on the historical endpoint page",
            "Several years; exact earliest NSE cash 5m date not documented on endpoint page",
            "3 historical requests/second",
            "One instrument token per request",
            True,
            "Explicit +0530 timestamps in official examples",
            "BAR_START confirmed by provider-maintained developer forum; endpoint prose is not explicit",
            "UNKNOWN",
            "No adjusted-price or corporate-action treatment documented for cash-equity candles",
            f"{zerodha_docs} | https://kite.trade/docs/connect/v3/market-data-and-instruments/ | https://kite.trade/docs/connect/v3/exceptions/",
            str(ResearchRightsStatus.TERMS_REVIEW_REQUIRED),
            str(ResearchRightsStatus.TERMS_REVIEW_REQUIRED),
            "UNKNOWN",
            (
                "No Kite credentials or adapter configuration exists in this project",
                "Exact retention and redistribution rights require terms review",
            ),
            "AUTH_AND_TERMS_BLOCKED_NOT_CONTACTED",
            str(SourceStatus.AUTHORITATIVE_PROVIDER_DOCS),
        ),
        ProviderCapability(
            "Existing licensed/local provider",
            "Repository provider inventory",
            False,
            True,
            False,
            False,
            "NOT_SUPPORTED",
            False,
            False,
            False,
            "NOT_SUPPORTED",
            "NOT_SUPPORTED",
            "NOT_SUPPORTED",
            "NOT_SUPPORTED",
            "NOT_SUPPORTED",
            False,
            "UNKNOWN",
            "UNKNOWN",
            "UNKNOWN",
            "UNKNOWN",
            "Repository provider configuration only",
            str(ResearchRightsStatus.UNKNOWN),
            str(ResearchRightsStatus.UNKNOWN),
            "UNKNOWN",
            ("Only synthetic/local-fixture intraday support was configured before this command",),
            "NO_REAL_LICENSED_LOCAL_SOURCE_CONFIGURED",
            str(SourceStatus.EXISTING_PROJECT_CONFIG),
        ),
    )


def select_provider(
    capabilities: Sequence[ProviderCapability], *, credentials_present: bool
) -> tuple[str | None, ProviderSelectionResult]:
    groww = next((row for row in capabilities if row.provider_name == "Groww"), None)
    if groww is None:
        return None, ProviderSelectionResult.NO_PROVIDER_CAPABLE
    required = (
        groww.market_data_only_possible,
        groww.nse_cash_supported,
        groww.historical_intraday_supported,
        groww.five_minute_supported,
        groww.volume_supported,
        groww.instrument_master_available,
    )
    if not all(required):
        return None, ProviderSelectionResult.NO_PROVIDER_CAPABLE
    if groww.research_use_status not in {
        str(ResearchRightsStatus.CLEAR_FOR_PERSONAL_RESEARCH),
        str(ResearchRightsStatus.USABLE_WITH_RESTRICTIONS),
    }:
        return None, ProviderSelectionResult.TERMS_BLOCKED
    if not credentials_present:
        return "Groww", ProviderSelectionResult.AUTH_BLOCKED
    return "Groww", ProviderSelectionResult.PROVIDER_SELECTED


def credentials_present(settings: Settings) -> bool:
    return bool(settings.groww_totp_token and settings.groww_totp_secret)


def classify_provider_failure(exc: Exception) -> str:
    value = f"{type(exc).__name__} {exc}".lower()
    if any(token in value for token in ("401", "403", "auth", "token", "permission")):
        return "AUTHENTICATION_FAILURE"
    if "429" in value or "rate limit" in value or "too many" in value:
        return "RATE_LIMIT"
    if any(token in value for token in ("timeout", "connection", "dns", "network")):
        return "TRANSIENT_NETWORK"
    if any(token in value for token in ("500", "502", "503", "504", "server")):
        return "SERVER_ERROR"
    if any(token in value for token in ("not found", "invalid instrument", "unsupported")):
        return "DATA_UNAVAILABLE_OR_INVALID_INSTRUMENT"
    return "PROVIDER_ERROR"


def instrument_mapping_result(mappings: Sequence[InstrumentMapping]) -> InstrumentMappingResult:
    if not mappings:
        return InstrumentMappingResult.INCONCLUSIVE
    clean = sum(row.mapping_status == "CLEAN" for row in mappings)
    missing_isin = sum(row.mapping_status == "MISSING_ISIN" for row in mappings)
    if clean == len(mappings):
        return InstrumentMappingResult.CLEAN
    if clean + missing_isin == len(mappings):
        return InstrumentMappingResult.CLEAN_WITH_MISSING_ISIN
    if clean or missing_isin:
        return InstrumentMappingResult.PARTIAL
    return InstrumentMappingResult.FAILED


def build_real_intraday_provider_pilot(
    *,
    repo_root: Path,
    fetch_real: bool = False,
    reuse_existing: bool = False,
    tests_passed: bool = False,
    frontend_build_passed: bool = False,
    client: Any | None = None,
    settings: Settings | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    root = Path(repo_root)
    data_dir = root / "data"
    spec = PilotSpec()
    spec.validate()
    capabilities = provider_capability_audit()
    capability_hash = canonical_hash([row.snapshot() for row in capabilities])
    configured = settings or Settings()
    has_credentials = credentials_present(configured)
    selected_provider, selection_result = select_provider(
        capabilities, credentials_present=has_credentials
    )
    baseline_before = _baseline_state(data_dir)
    _notify(progress, "Capability audit complete; verifying frozen pilot and baseline guards")

    if reuse_existing:
        existing_manifest_path = data_dir / "research/intraday/v1/real_intraday_pilot_manifest_v1.json"
        if not existing_manifest_path.exists():
            raise FileNotFoundError("No accepted real pilot manifest exists to reuse")
        existing = json.loads(existing_manifest_path.read_text(encoding="utf-8"))
        return _rebuild_from_accepted_outputs(
            root=root,
            existing=existing,
            capabilities=capabilities,
            capability_hash=capability_hash,
            baseline_before=baseline_before,
            tests_passed=tests_passed,
            frontend_build_passed=frontend_build_passed,
            started=started,
        )

    placeholder = _empty_pilot_state()
    placeholder.update(
        {
            "provider": selected_provider,
            "selection_result": str(selection_result),
            "credentials_present": has_credentials,
            "capabilities": [row.snapshot() for row in capabilities],
            "provider_capability_manifest_hash": capability_hash,
        }
    )
    if not fetch_real or selection_result != ProviderSelectionResult.PROVIDER_SELECTED:
        result = (
            str(RealPilotResult.BLOCKED_NO_CREDENTIALS)
            if selection_result == ProviderSelectionResult.AUTH_BLOCKED
            else str(RealPilotResult.INCONCLUSIVE)
        )
        placeholder["real_pilot_result"] = result
        placeholder["runtime_status"] = "DRY_RUN_NO_PROVIDER_CONTACT" if not fetch_real else "CAPABILITY_GATE_BLOCKED"
        return _finalize_reports(
            root=root,
            state=placeholder,
            spec=spec,
            baseline_before=baseline_before,
            tests_passed=tests_passed,
            frontend_build_passed=frontend_build_passed,
            started=started,
        )

    _notify(progress, "Authenticating once and resolving the official instrument master")
    budget = RequestBudget(spec.max_provider_requests, spec.expected_requests)
    if client is None:
        budget.reserve()
        auth_started = time.perf_counter()
        try:
            credentials = GrowwCredentials.from_settings(configured)
            client = GrowwAuthService(credentials=credentials).get_client()
            budget.request_rows.append(
                _request_metric("authentication", "AUTHENTICATION", "SUCCESS", "OK", auth_started)
            )
        except Exception as exc:
            budget.request_rows.append(
                _request_metric(
                    "authentication",
                    "AUTHENTICATION",
                    "FAILED",
                    classify_provider_failure(exc),
                    auth_started,
                )
            )
            placeholder.update(
                {
                    "request_budget": _budget_snapshot(budget),
                    "requests": budget.request_rows,
                    "real_pilot_result": str(RealPilotResult.FAIL_PROVIDER),
                    "provider_reliability_result": str(ProviderReliabilityResult.BLOCKED),
                    "runtime_status": "AUTHENTICATION_FAILED",
                }
            )
            return _finalize_reports(
                root=root,
                state=placeholder,
                spec=spec,
                baseline_before=baseline_before,
                tests_passed=tests_passed,
                frontend_build_passed=frontend_build_passed,
                started=started,
            )
    else:
        budget.reserve()
        budget.request_rows.append(
            {
                "request_id": "authentication",
                "provider": "Groww",
                "endpoint_category": "AUTHENTICATION",
                "status": "MOCK_CLIENT_SUPPLIED",
                "response_category": "OFFLINE_TEST",
                "retry_number": 0,
                "latency_ms": 0,
            }
        )

    adapter = GrowwResearchMarketDataAdapter(client=client, budget=budget)
    outcomes = _load_selected_outcomes(data_dir)
    internal_isins = {row["symbol"]: _optional_text(row.get("isin")) for row in outcomes}
    try:
        mappings = adapter.resolve_instruments(spec.symbols, internal_isins)
    except Exception as exc:
        placeholder.update(
            {
                "request_budget": _budget_snapshot(budget),
                "requests": budget.request_rows,
                "real_pilot_result": str(RealPilotResult.FAIL_PROVIDER),
                "provider_reliability_result": str(ProviderReliabilityResult.BLOCKED),
                "runtime_status": f"INSTRUMENT_MASTER_FAILED_{classify_provider_failure(exc)}",
            }
        )
        return _finalize_reports(
            root=root,
            state=placeholder,
            spec=spec,
            baseline_before=baseline_before,
            tests_passed=tests_passed,
            frontend_build_passed=frontend_build_passed,
            started=started,
        )

    mapping_result = instrument_mapping_result(mappings)
    if mapping_result in {InstrumentMappingResult.PARTIAL, InstrumentMappingResult.FAILED}:
        placeholder.update(
            {
                "mappings": [row.snapshot() for row in mappings],
                "instrument_mapping_result": str(mapping_result),
                "instrument_mapping_hash": canonical_hash([row.snapshot() for row in mappings]),
                "request_budget": _budget_snapshot(budget),
                "requests": budget.request_rows,
                "real_pilot_result": str(RealPilotResult.FAIL_PROVIDER),
                "provider_reliability_result": str(ProviderReliabilityResult.BLOCKED),
                "runtime_status": "INSTRUMENT_MAPPING_FAILED",
            }
        )
        return _finalize_reports(
            root=root,
            state=placeholder,
            spec=spec,
            baseline_before=baseline_before,
            tests_passed=tests_passed,
            frontend_build_passed=frontend_build_passed,
            started=started,
        )

    retrieval_time = datetime.now(timezone.utc)
    retrieval_version = retrieval_time.strftime("%Y%m%dT%H%M%S%fZ")
    raw_dir = data_dir / f"raw/intraday/groww/pilot_v1/retrieval_{retrieval_version}"
    raw_dir.mkdir(parents=True, exist_ok=False)
    raw_payloads: list[dict[str, Any]] = []
    _notify(progress, "Fetching five bounded native-5m requests; no fallback provider is enabled")
    try:
        for index, mapping in enumerate(mappings, start=1):
            request_id = f"REAL-INTRADAY-C04-{index:03d}-{mapping.internal_symbol}"
            response, _metric = adapter.fetch_historical_5m(
                mapping=mapping,
                start_date=min(spec.dates),
                end_date=max(spec.dates),
                request_id=request_id,
            )
            raw_record = {
                "provider": "Groww",
                "request_id": request_id,
                "instrument_id": mapping.provider_instrument_id,
                "symbol": mapping.internal_symbol,
                "provider_symbol": mapping.provider_symbol,
                "requested_interval": "5m",
                "requested_dates": [value.isoformat() for value in spec.dates],
                "requested_start": min(spec.dates).isoformat(),
                "requested_end": max(spec.dates).isoformat(),
                "retrieval_timestamp": retrieval_time.isoformat(),
                "response": response,
            }
            raw_record["raw_hash"] = canonical_hash(
                {key: value for key, value in raw_record.items() if key != "retrieval_timestamp"}
            )
            _write_new_json(raw_dir / f"{request_id}.json", raw_record)
            raw_payloads.append(raw_record)
    except Exception as exc:
        placeholder.update(
            {
                "mappings": [row.snapshot() for row in mappings],
                "instrument_mapping_result": str(mapping_result),
                "instrument_mapping_hash": canonical_hash([row.snapshot() for row in mappings]),
                "request_budget": _budget_snapshot(budget),
                "requests": budget.request_rows,
                "raw_paths": [str(path) for path in sorted(raw_dir.glob("*.json"))],
                "real_pilot_result": str(RealPilotResult.FAIL_PROVIDER),
                "provider_reliability_result": str(ProviderReliabilityResult.BLOCKED),
                "runtime_status": f"REAL_FETCH_FAILED_{classify_provider_failure(exc)}",
            }
        )
        return _finalize_reports(
            root=root,
            state=placeholder,
            spec=spec,
            baseline_before=baseline_before,
            tests_passed=tests_passed,
            frontend_build_passed=frontend_build_passed,
            started=started,
        )

    state = _analyze_accepted_payloads(
        root=root,
        raw_payloads=raw_payloads,
        mappings=mappings,
        outcomes=outcomes,
        budget=budget,
        capability_hash=capability_hash,
        retrieval_time=retrieval_time,
        raw_dir=raw_dir,
    )
    state.update(
        {
            "provider": selected_provider,
            "selection_result": str(selection_result),
            "credentials_present": has_credentials,
            "capabilities": [row.snapshot() for row in capabilities],
        }
    )
    return _finalize_reports(
        root=root,
        state=state,
        spec=spec,
        baseline_before=baseline_before,
        tests_passed=tests_passed,
        frontend_build_passed=frontend_build_passed,
        started=started,
    )


def _analyze_accepted_payloads(
    *,
    root: Path,
    raw_payloads: Sequence[dict[str, Any]],
    mappings: Sequence[InstrumentMapping],
    outcomes: Sequence[dict[str, str]],
    budget: RequestBudget,
    capability_hash: str,
    retrieval_time: datetime,
    raw_dir: Path,
) -> dict[str, Any]:
    spec = PilotSpec()
    calendar = NseCashSessionCalendar.from_trading_dates(
        list(spec.dates), source="FROZEN_NSE_DAILY_REFERENCE_SESSION_UNIVERSE"
    )
    mapping_by_symbol = {row.internal_symbol: row for row in mappings}
    raw_rows: list[dict[str, Any]] = []
    raw_candle_count = 0
    off_session_by_group: dict[tuple[str, date], int] = defaultdict(int)
    for payload in raw_payloads:
        symbol = payload["symbol"]
        mapping = mapping_by_symbol[symbol]
        for candle in _extract_candles(payload["response"]):
            raw_candle_count += 1
            parsed = _provider_candle_row(candle)
            timestamp = parse_timestamp(parsed["timestamp"], allow_naive_exchange_local=True)
            if timestamp.date() not in spec.dates:
                continue
            session = calendar.session_for(timestamp.date())
            aligned = (timestamp - session.opens_at).total_seconds() % 300 == 0
            if not aligned or timestamp < session.opens_at or timestamp + timedelta(minutes=5) > session.closes_at:
                off_session_by_group[(symbol, timestamp.date())] += 1
                continue
            raw_rows.append(
                {
                    "instrument_id": mapping.provider_instrument_id,
                    "symbol": symbol,
                    "isin": mapping.internal_isin,
                    "exchange": "NSE",
                    "trading_date": timestamp.date(),
                    "interval": "5m",
                    "bar_start": timestamp,
                    "source_timestamp": timestamp,
                    "open": parsed["open"],
                    "high": parsed["high"],
                    "low": parsed["low"],
                    "close": parsed["close"],
                    "volume": parsed["volume"],
                    "provider_vwap": parsed.get("provider_vwap"),
                    "corporate_action_reference": {
                        "status": "CHECKED_NO_NEARBY_STRUCTURAL_EVENT",
                        "automatic_adjustment": False,
                    },
                }
            )
    bars = normalize_rows(
        raw_rows,
        calendar=calendar,
        source_provider="GROWW_OFFICIAL_API",
        ingested_at=retrieval_time,
        allow_naive_exchange_local=True,
    )
    if len(bars) > spec.max_normalized_rows:
        raise RuntimeError("Normalized pilot exceeded the frozen 10,000-row cap")
    derived_10m = aggregate_bars(bars, target_minutes=10, calendar=calendar)
    derived_15m = aggregate_bars(bars, target_minutes=15, calendar=calendar)
    normalized_path = root / "data/normalized/intraday/5m/real_provider_pilot_v1/normalized_5m.csv.gz"
    derived_10m_path = root / "data/derived/intraday/10m/real_provider_pilot_v1/derived_10m.csv.gz"
    derived_15m_path = root / "data/derived/intraday/15m/real_provider_pilot_v1/derived_15m.csv.gz"
    _write_gzip_csv(normalized_path, [canonical_bar_row(row) for row in bars])
    _write_gzip_csv(derived_10m_path, [canonical_bar_row(row) for row in derived_10m])
    _write_gzip_csv(derived_15m_path, [canonical_bar_row(row) for row in derived_15m])

    grouped: dict[tuple[str, date], list[CanonicalIntradayBar]] = defaultdict(list)
    for bar in bars:
        grouped[(bar.symbol, bar.trading_date)].append(bar)
    session_rows: list[dict[str, Any]] = []
    quality_rows: list[dict[str, Any]] = []
    opening_rows: list[dict[str, Any]] = []
    vwap_rows: list[dict[str, Any]] = []
    reconciliation_rows: list[dict[str, Any]] = []
    strict_groups: dict[tuple[str, date], list[CanonicalIntradayBar]] = {}
    daily_references = _load_daily_references(root / "data", spec.symbols, spec.dates)
    for symbol in spec.symbols:
        for trading_date in spec.dates:
            rows = grouped.get((symbol, trading_date), [])
            if not rows:
                session_rows.append(
                    _missing_session_row(symbol, trading_date, calendar.expected_bar_count(trading_date))
                )
                quality_rows.append(
                    {"symbol": symbol, "trading_date": trading_date, "quality_issue": "NO_ROWS", "count": 1}
                )
                reconciliation_rows.append(
                    _unavailable_reconciliation_row(symbol, trading_date, "NO_INTRADAY_ROWS")
                )
                continue
            quality = assess_session_quality(rows, calendar=calendar)
            usability = (
                SessionUsability.USABLE_STRICT
                if quality.strict_usable
                else SessionUsability.USABLE_WITH_WARNING
                if quality.lenient_usable
                else SessionUsability.UNUSABLE
            )
            flags = list(quality.statuses)
            session_rows.append(
                {
                    "symbol": symbol,
                    "trading_date": trading_date,
                    "expected_bars": quality.expected_bars,
                    "actual_bars": quality.actual_bars,
                    "missing_bars": quality.missing_bars,
                    "duplicate_bars": quality.duplicate_bars,
                    "out_of_order": str(IntradayBarQuality.OUT_OF_ORDER) in quality.statuses,
                    "invalid_ohlc": str(IntradayBarQuality.OHLC_INVALID) in quality.statuses,
                    "negative_volume": str(IntradayBarQuality.NEGATIVE_VOLUME) in quality.statuses,
                    "off_session_rows": off_session_by_group.get((symbol, trading_date), 0),
                    "coverage_pct": quality.coverage_pct,
                    "quality_status": ";".join(flags),
                    "session_usability_version": SESSION_USABILITY_VERSION,
                    "usability": str(usability),
                    "timestamp_definition_warning": "OFFICIAL_PROSE_NOT_EXPLICIT",
                }
            )
            for status in flags:
                quality_rows.append(
                    {"symbol": symbol, "trading_date": trading_date, "quality_issue": status, "count": 1}
                )
            if quality.strict_usable:
                strict_groups[(symbol, trading_date)] = rows
                for minutes in (5, 10, 15, 30):
                    opening_rows.append(json_ready(asdict(calculate_opening_range(rows, window_minutes=minutes, calendar=calendar))))
                for point in calculate_session_vwap(rows, session_quality=quality):
                    vwap_rows.append(json_ready(asdict(point)))
            daily = daily_references.get((symbol, trading_date))
            reconciliation_rows.append(_reconciliation_row(rows, daily))

    first_touch_rows = _first_touch_rows(outcomes, grouped, calendar)
    confirmation_rows = _confirmation_rows(outcomes, strict_groups)
    quality_result = _quality_result(session_rows)
    reconciliation_result = _overall_reconciliation(reconciliation_rows)
    successful_history_requests = sum(
        row["status"] == "SUCCESS" and row["endpoint_category"] == "HISTORICAL_CANDLES"
        for row in budget.request_rows
    )
    reliability = (
        ProviderReliabilityResult.CLEAN
        if successful_history_requests == len(spec.symbols) and budget.retry_count == 0
        else ProviderReliabilityResult.USABLE_WITH_LIMITATIONS
        if successful_history_requests >= len(spec.symbols)
        else ProviderReliabilityResult.UNRELIABLE
    )
    strict_count = sum(row["usability"] == str(SessionUsability.USABLE_STRICT) for row in session_rows)
    combinations = len(spec.symbols) * len(spec.dates)
    minimum_success = combinations >= 25 and strict_count / combinations >= Decimal("0.80")
    pilot_result = (
        RealPilotResult.FAIL_DATA_QUALITY
        if not minimum_success
        else RealPilotResult.FAIL_RECONCILIATION
        if reconciliation_result == RealReconciliationResult.MATERIAL_MISMATCH
        else RealPilotResult.PASS_WITH_LIMITATIONS
        if quality_result != RealDataQualityResult.CLEAN
        or reconciliation_result != RealReconciliationResult.CLEAN
        or budget.retry_count
        else RealPilotResult.PASS
    )
    mapping_rows = [row.snapshot() for row in mappings]
    raw_hash = canonical_hash(
        [
            {key: value for key, value in row.items() if key != "retrieval_timestamp"}
            for row in raw_payloads
        ]
    )
    dataset_paths = {
        "raw_directory": str(raw_dir),
        "normalized_5m": str(normalized_path),
        "derived_10m": str(derived_10m_path),
        "derived_15m": str(derived_15m_path),
    }
    state = {
        "mappings": mapping_rows,
        "instrument_mapping_result": str(instrument_mapping_result(mappings)),
        "instrument_mapping_hash": canonical_hash(mapping_rows),
        "raw_pilot_hash": raw_hash,
        "normalized_5m_pilot_hash": intraday_dataset_hash(bars),
        "derived_10m_pilot_hash": intraday_dataset_hash(derived_10m),
        "derived_15m_pilot_hash": intraday_dataset_hash(derived_15m),
        "provider_capability_manifest_hash": capability_hash,
        "raw_pilot_row_count": raw_candle_count,
        "normalized_5m_row_count": len(bars),
        "derived_10m_row_count": len(derived_10m),
        "derived_15m_row_count": len(derived_15m),
        "request_budget": _budget_snapshot(budget),
        "requests": budget.request_rows,
        "sessions": session_rows,
        "quality_rows": quality_rows,
        "daily_reconciliation": reconciliation_rows,
        "opening_range": opening_rows,
        "vwap": vwap_rows,
        "first_touch": first_touch_rows,
        "confirmation_availability": confirmation_rows,
        "dataset_paths": dataset_paths,
        "raw_paths": [str(path) for path in sorted(raw_dir.glob("*.json"))],
        "real_data_quality_result": str(quality_result),
        "real_daily_intraday_reconciliation_result": str(reconciliation_result),
        "real_vwap_quality_result": str(
            VwapQualityResult.NO_PROVIDER_COMPARISON
            if vwap_rows
            else VwapQualityResult.UNUSABLE_DUE_TO_VOLUME
        ),
        "provider_reliability_result": str(reliability),
        "real_pilot_result": str(pilot_result),
        "minimum_success_passed": minimum_success,
        "retrieval_timestamp": retrieval_time.isoformat(),
        "runtime_status": "REAL_PILOT_INGESTED",
    }
    manifest = _pilot_manifest(state, spec)
    manifest_path = root / "data/research/intraday/v1/real_intraday_pilot_manifest_v1.json"
    _write_json(manifest_path, manifest)
    state["pilot_manifest_path"] = str(manifest_path)
    return state


def _rebuild_from_accepted_outputs(
    *,
    root: Path,
    existing: dict[str, Any],
    capabilities: Sequence[ProviderCapability],
    capability_hash: str,
    baseline_before: dict[str, Any],
    tests_passed: bool,
    frontend_build_passed: bool,
    started: float,
) -> dict[str, Any]:
    raw_paths = [Path(value) for value in existing["raw_paths"]]
    raw_payloads = [json.loads(path.read_text(encoding="utf-8")) for path in raw_paths]
    mappings = [InstrumentMapping(**row) for row in existing["instrument_mappings"]]
    request_info = existing["request_budget"]
    budget = RequestBudget(
        request_info["max_provider_requests"],
        request_info["expected_requests"],
        request_info["actual_requests"],
        request_info["retry_count"],
        list(existing["requests"]),
    )
    state = _analyze_accepted_payloads(
        root=root,
        raw_payloads=raw_payloads,
        mappings=mappings,
        outcomes=_load_selected_outcomes(root / "data"),
        budget=budget,
        capability_hash=capability_hash,
        retrieval_time=datetime.fromisoformat(existing["created_at"]),
        raw_dir=Path(existing["dataset_paths"]["raw_directory"]),
    )
    state.update(
        {
            "provider": "Groww",
            "selection_result": str(ProviderSelectionResult.PROVIDER_SELECTED),
            "credentials_present": existing["credentials_present"],
            "capabilities": [row.snapshot() for row in capabilities],
            "runtime_status": "ACCEPTED_REAL_PILOT_REUSED_WITHOUT_PROVIDER_REQUESTS",
        }
    )
    return _finalize_reports(
        root=root,
        state=state,
        spec=PilotSpec(),
        baseline_before=baseline_before,
        tests_passed=tests_passed,
        frontend_build_passed=frontend_build_passed,
        started=started,
    )


def _finalize_reports(
    *,
    root: Path,
    state: dict[str, Any],
    spec: PilotSpec,
    baseline_before: dict[str, Any],
    tests_passed: bool,
    frontend_build_passed: bool,
    started: float,
) -> dict[str, Any]:
    baseline_after = _baseline_state(root / "data")
    baseline_unchanged = baseline_before == baseline_after
    safety = {
        "validation_state": DEFAULT_INTRADAY_CONFIG.validation_state,
        "validation_run_count": 0,
        "validation_performance_exposed": False,
        "strategy_v2_created": False,
        "strategy_v1_modified": False,
        "frozen_outcomes_rewritten": False,
        "full_history_ingestion_performed": False,
        "full_history_ingestion_authorized": False,
        "live_signals_generated": 0,
        "live_orders_placed": 0,
        "broker_order_calls": 0,
        "remote_migrations_applied": 0,
        "supabase_records_persisted": 0,
    }
    scalability = _scalability_row()
    summary = {
        "phase": "Step 02.14",
        "command": "Command 04",
        "pilot_version": PILOT_VERSION,
        "pilot_profile": PILOT_PROFILE,
        "capability_audit_version": CAPABILITY_AUDIT_VERSION,
        "provider_candidates": [row["provider_name"] for row in state["capabilities"]],
        "capabilities": state["capabilities"],
        "selected_provider": state.get("provider"),
        "pilot_provider_selection_result": state["selection_result"],
        "provider_research_rights_status": str(ResearchRightsStatus.USABLE_WITH_RESTRICTIONS),
        "credentials_present": bool(state["credentials_present"]),
        "secret_values_recorded": False,
        "pilot": {
            "symbols": list(spec.symbols),
            "dates": [value.isoformat() for value in spec.dates],
            "date_range": [min(spec.dates).isoformat(), max(spec.dates).isoformat()],
            "development_only": True,
            "selection_reason": "Five frozen development opportunities spanning price, liquidity, gaps, and daily stop/target/time classifications",
            "corporate_action_check": "NO_NEARBY_SELECTED_STRUCTURAL_EVENTS",
            "maximum_normalized_rows": spec.max_normalized_rows,
            "minimum_success": "at least 25 symbol-sessions and at least 80% strict usable",
        },
        "request_budget": state.get("request_budget", _empty_budget(spec)),
        "requests": state.get("requests", []),
        "instrument_mappings": state.get("mappings", []),
        "instrument_mapping_result": state.get("instrument_mapping_result", str(InstrumentMappingResult.INCONCLUSIVE)),
        "hashes": {
            "raw_pilot_hash": state.get("raw_pilot_hash"),
            "normalized_5m_pilot_hash": state.get("normalized_5m_pilot_hash"),
            "derived_10m_pilot_hash": state.get("derived_10m_pilot_hash"),
            "derived_15m_pilot_hash": state.get("derived_15m_pilot_hash"),
            "instrument_mapping_hash": state.get("instrument_mapping_hash"),
            "provider_capability_manifest_hash": state["provider_capability_manifest_hash"],
        },
        "row_counts": {
            "raw": state.get("raw_pilot_row_count", 0),
            "normalized_5m": state.get("normalized_5m_row_count", 0),
            "derived_10m": state.get("derived_10m_row_count", 0),
            "derived_15m": state.get("derived_15m_row_count", 0),
        },
        "sessions": state.get("sessions", []),
        "quality": _quality_summary(state.get("sessions", [])),
        "daily_reconciliation": state.get("daily_reconciliation", []),
        "opening_range": state.get("opening_range", []),
        "vwap": state.get("vwap", []),
        "first_touch": state.get("first_touch", []),
        "first_touch_summary": _first_touch_summary(state.get("first_touch", [])),
        "confirmation_availability": state.get("confirmation_availability", []),
        "classifications": {
            "REAL_INTRADAY_DATA_QUALITY_RESULT": state.get("real_data_quality_result", str(RealDataQualityResult.NO_REAL_DATA_INGESTED)),
            "REAL_DAILY_INTRADAY_RECONCILIATION_RESULT": state.get("real_daily_intraday_reconciliation_result", str(RealReconciliationResult.INCONCLUSIVE)),
            "REAL_VWAP_QUALITY_RESULT": state.get("real_vwap_quality_result", str(VwapQualityResult.INCONCLUSIVE)),
            "PROVIDER_PILOT_RELIABILITY_RESULT": state.get("provider_reliability_result", str(ProviderReliabilityResult.INCONCLUSIVE)),
            "FULL_INTRADAY_INGESTION_FEASIBILITY": str(FullIngestionFeasibility.FEASIBLE_WITH_BATCHING),
            "REAL_INTRADAY_PILOT_RESULT": state["real_pilot_result"],
            "INTRADAY_ARCHITECTURE_RESULT": (
                "READY_FOR_BOUNDED_REAL_RESEARCH"
                if state["real_pilot_result"] in {str(RealPilotResult.PASS), str(RealPilotResult.PASS_WITH_LIMITATIONS)}
                else "READY_FOR_PILOT_INGESTION"
            ),
        },
        "scalability": scalability,
        "licensing_retention": {
            "private_research": "USABLE_WITH_RESTRICTIONS",
            "local_storage": "UNKNOWN",
            "long_term_retention": "UNKNOWN",
            "transformation": "IMPLIED_FOR_BACKTESTING_NOT_EXPLICIT",
            "redistribution": "UNKNOWN_NOT_PERMITTED_BY_THIS_COMMAND",
        },
        "dataset_paths": state.get("dataset_paths", {}),
        "raw_paths": state.get("raw_paths", []),
        "pilot_manifest_path": state.get("pilot_manifest_path"),
        "regression": {
            "before": baseline_before,
            "after": baseline_after,
            "unchanged": baseline_unchanged,
            "baseline_mutation_violations": 0 if baseline_unchanged else 1,
        },
        "security": {
            "backend_env_ignored": _git_ignored(root, root / "backend/.env"),
            "raw_intraday_ignored": _git_ignored(root, root / "data/raw/intraday/probe.json"),
            "normalized_intraday_ignored": _git_ignored(root, root / "data/normalized/intraday/probe.csv.gz"),
            "derived_intraday_ignored": _git_ignored(root, root / "data/derived/intraday/probe.csv.gz"),
            "credentials_logged": False,
            "authorization_headers_logged": False,
            "adapter_order_methods": False,
        },
        "safety": safety,
        "runtime_status": state["runtime_status"],
        "runtime_seconds": time.perf_counter() - started,
        "tests_passed": tests_passed,
        "frontend_build_passed": frontend_build_passed,
        "known_limitations": [
            "Tiny quality/provenance pilot only; no performance inference",
            "Groww candle timestamp definition is not explicit in official prose",
            "Provider retention, redistribution, adjustments, endpoint rate, and price are not fully documented",
            "Provider VWAP is unavailable; only internal volume-weighted VWAP is calculated",
        ],
    }
    reports_dir = root / "data/reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    csv_payloads = {
        REPORT_NAMES[1]: state["capabilities"],
        REPORT_NAMES[2]: state.get("mappings", []),
        REPORT_NAMES[3]: state.get("requests", []),
        REPORT_NAMES[4]: state.get("sessions", []),
        REPORT_NAMES[5]: state.get("quality_rows", []),
        REPORT_NAMES[6]: state.get("daily_reconciliation", []),
        REPORT_NAMES[7]: state.get("opening_range", []),
        REPORT_NAMES[8]: state.get("vwap", []),
        REPORT_NAMES[9]: state.get("first_touch", []),
        REPORT_NAMES[10]: state.get("confirmation_availability", []),
        REPORT_NAMES[11]: [scalability],
        REPORT_NAMES[12]: [_pilot_report_row(summary)],
    }
    for filename, rows in csv_payloads.items():
        _write_csv(reports_dir / filename, rows)
    summary["report_paths"] = [str(reports_dir / name) for name in REPORT_NAMES]
    summary["artifact_count"] = len(REPORT_NAMES)
    security = summary["security"]
    security_ok = (
        security["backend_env_ignored"]
        and security["raw_intraday_ignored"]
        and security["normalized_intraday_ignored"]
        and security["derived_intraday_ignored"]
        and not security["credentials_logged"]
        and not security["authorization_headers_logged"]
        and not security["adapter_order_methods"]
    )
    ready = (
        state["real_pilot_result"] in {str(RealPilotResult.PASS), str(RealPilotResult.PASS_WITH_LIMITATIONS)}
        and baseline_unchanged
        and tests_passed
        and frontend_build_passed
        and security_ok
    )
    summary["step_status"] = "COMPLETE" if ready else "IMPLEMENTED_PENDING_OR_BLOCKED"
    summary["ready_for_review"] = ready
    _write_json(reports_dir / REPORT_NAMES[0], summary)
    return summary


def _baseline_state(data_dir: Path) -> dict[str, Any]:
    verify_current_portfolio_backtest_baseline(data_dir)
    hashes = portfolio_backtest_regression_hashes(data_dir)
    if not all(portfolio_backtest_regression_hash_checks(hashes).values()):
        raise ValueError("A frozen strategy baseline hash failed verification")
    intraday_report = json.loads(
        (data_dir / "reports/intraday_architecture_v1_summary.json").read_text(encoding="utf-8")
    )
    observed_intraday = intraday_report["dataset_hashes"]
    if observed_intraday != EXPECTED_SYNTHETIC_HASHES:
        raise ValueError("The frozen synthetic intraday hashes changed")
    return {
        "datasets": hashes,
        "diagnostic_registry": _diagnostic_registry_state(data_dir),
        "cost_registry": _cost_registry_state(data_dir),
        "temporal_registry": _temporal_registry_state(data_dir),
        "intraday_config_hash": DEFAULT_INTRADAY_CONFIG.config_hash(),
        "intraday_synthetic_hashes": observed_intraday,
    }


def _load_selected_outcomes(data_dir: Path) -> list[dict[str, str]]:
    path = resolve_current_strategy_outcome_dataset(data_dir)
    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row.get("symbol") in PILOT_SYMBOLS
            and row.get("decision_date") in {"2022-01-03", "2022-01-04"}
        ]
    selected = {row["symbol"]: row for row in rows}
    if set(selected) != set(PILOT_SYMBOLS):
        raise ValueError("Frozen outcome pilot selection could not be reproduced")
    return [selected[symbol] for symbol in PILOT_SYMBOLS]


def _load_daily_references(
    data_dir: Path, symbols: Sequence[str], dates: Sequence[date]
) -> dict[tuple[str, date], DailyBarReference]:
    result: dict[tuple[str, date], DailyBarReference] = {}
    for trading_date in dates:
        filename = f"sec_bhavdata_full_{trading_date.strftime('%d%m%Y')}.csv"
        path = data_dir / "reference/nse/daily/raw" / filename
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for source_row in csv.DictReader(handle):
                row = {str(key).strip(): str(value).strip() for key, value in source_row.items()}
                symbol = str(row.get("SYMBOL", "")).strip().upper()
                if symbol not in symbols or str(row.get("SERIES", "")).strip().upper() != "EQ":
                    continue
                result[(symbol, trading_date)] = DailyBarReference(
                    symbol,
                    trading_date,
                    Decimal(str(row["OPEN_PRICE"]).strip()),
                    Decimal(str(row["HIGH_PRICE"]).strip()),
                    Decimal(str(row["LOW_PRICE"]).strip()),
                    Decimal(str(row["CLOSE_PRICE"]).strip()),
                    int(Decimal(str(row["TTL_TRD_QNTY"]).replace(",", "").strip())),
                    f"NSE_SECURITY_BHAVDATA:{filename}",
                )
    return result


def _reconciliation_row(
    bars: Sequence[CanonicalIntradayBar], daily: DailyBarReference | None
) -> dict[str, Any]:
    if daily is None:
        return _unavailable_reconciliation_row(bars[0].symbol, bars[0].trading_date, "DAILY_REFERENCE_MISSING")
    price_tolerance = Decimal("0.05")
    price_tolerance_pct = Decimal("0.50")
    volume_tolerance = Decimal("2")
    result = reconcile_daily_bar(
        bars,
        daily,
        data_status=PilotDataStatus.REAL_SOURCE_DATA,
        price_tolerance=price_tolerance,
        volume_tolerance_pct=volume_tolerance,
    )
    intraday_values = {
        "open": bars[0].open,
        "high": max(row.high for row in bars),
        "low": min(row.low for row in bars),
        "close": bars[-1].close,
        "volume": sum(row.volume or 0 for row in bars),
    }
    diffs = {
        "open": result.open_diff,
        "high": result.high_diff,
        "low": result.low_diff,
        "close": result.close_diff,
    }
    pct = {
        name: abs(value) * Decimal("100") / getattr(daily, name)
        if value is not None and getattr(daily, name)
        else None
        for name, value in diffs.items()
    }
    volume_pct = (
        abs(Decimal(result.volume_diff) * Decimal("100") / Decimal(daily.volume))
        if result.volume_diff is not None and daily.volume
        else None
    )
    price_material = any(
        abs(value or 0) > price_tolerance
        and pct[name] is not None
        and pct[name] > price_tolerance_pct
        for name, value in diffs.items()
    )
    volume_material = volume_pct is not None and volume_pct > volume_tolerance
    classification = (
        ReconciliationClassification.MATERIAL_PRICE_MISMATCH
        if price_material
        else ReconciliationClassification.MATERIAL_VOLUME_MISMATCH
        if volume_material
        else ReconciliationClassification.MINOR_SOURCE_DIFFERENCE
        if any(value not in (None, Decimal("0")) for value in diffs.values())
        or result.volume_diff not in (None, 0)
        else ReconciliationClassification.MATCH
    )
    return {
        "symbol": daily.symbol,
        "trading_date": daily.trading_date,
        "classification": str(classification),
        "intraday_open": intraday_values["open"],
        "daily_open": daily.open,
        "open_abs_diff": abs(result.open_diff or 0),
        "open_pct_diff": pct["open"],
        "intraday_high": intraday_values["high"],
        "daily_high": daily.high,
        "high_abs_diff": abs(result.high_diff or 0),
        "high_pct_diff": pct["high"],
        "intraday_low": intraday_values["low"],
        "daily_low": daily.low,
        "low_abs_diff": abs(result.low_diff or 0),
        "low_pct_diff": pct["low"],
        "intraday_close": intraday_values["close"],
        "daily_close": daily.close,
        "close_abs_diff": abs(result.close_diff or 0),
        "close_pct_diff": pct["close"],
        "intraday_volume": intraday_values["volume"],
        "daily_volume": daily.volume,
        "volume_abs_diff": abs(result.volume_diff or 0),
        "volume_pct_diff": volume_pct,
        "price_tolerance_rupees": price_tolerance,
        "price_tolerance_pct": price_tolerance_pct,
        "volume_tolerance_pct": volume_tolerance,
        "daily_source": daily.source,
    }


def _first_touch_rows(
    outcomes: Sequence[dict[str, str]],
    grouped: Mapping[tuple[str, date], list[CanonicalIntradayBar]],
    calendar: NseCashSessionCalendar,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for outcome in outcomes:
        symbol = outcome["symbol"]
        entry_date = date.fromisoformat(outcome["next_session_date"])
        holding_dates = [
            date.fromisoformat(outcome[f"session_date_{index}"])
            for index in range(1, 5)
            if outcome.get(f"session_date_{index}")
            and date.fromisoformat(outcome[f"session_date_{index}"]) in PILOT_DATES
        ]
        available = [bar for value in holding_dates for bar in grouped.get((symbol, value), [])]
        if not available or entry_date not in PILOT_DATES:
            rows.append(
                {
                    "decision_date": outcome["decision_date"],
                    "entry_date": outcome["next_session_date"],
                    "symbol": symbol,
                    "daily_outcome": outcome["first_touch_outcome"],
                    "comparison": "INSUFFICIENT_INTRADAY_DATA",
                }
            )
            continue
        entry_timestamp = calendar.session_for(entry_date).opens_at
        result = evaluate_first_touch(
            entry_timestamp=entry_timestamp,
            stop_price=Decimal(outcome["stop_price"]),
            target_price=Decimal(outcome["target_price"]),
            bars=available,
            max_holding_date=max(holding_dates),
            ambiguity_policy=AmbiguityPolicy.CONSERVATIVE_STOP_FIRST,
        )
        daily = outcome["first_touch_outcome"]
        normalized_daily = "NEITHER" if daily == "NEITHER_WITHIN_HORIZON" else daily
        normalized_intraday = {
            str(FirstTouch.GAP_THROUGH_STOP): str(FirstTouch.STOP_FIRST),
            str(FirstTouch.GAP_THROUGH_TARGET): str(FirstTouch.TARGET_FIRST),
        }.get(str(result.first_touch), str(result.first_touch))
        comparable_complete = len(holding_dates) == 4
        if not comparable_complete and result.first_touch == FirstTouch.NEITHER:
            comparison = "INSUFFICIENT_INTRADAY_DATA"
        elif result.first_touch == FirstTouch.INTRABAR_SEQUENCE_AMBIGUOUS:
            comparison = "5M_STILL_AMBIGUOUS"
        elif outcome.get("same_bar_ambiguous") == "True":
            comparison = "DAILY_AMBIGUOUS_RESOLVED_BY_5M"
        elif normalized_intraday == normalized_daily:
            comparison = "AGREES"
        else:
            comparison = "DAILY_NONAMBIGUOUS_CHANGED"
        rows.append(
            {
                "decision_date": outcome["decision_date"],
                "entry_date": outcome["next_session_date"],
                "symbol": symbol,
                "entry_reference": outcome["hypothetical_entry_price"],
                "stop": outcome["stop_price"],
                "target": outcome["target_price"],
                "first_real_5m_eligible_bar": min(bar.bar_start for bar in available),
                "first_stop_touch": result.first_stop_touch_timestamp,
                "first_target_touch": result.first_target_touch_timestamp,
                "first_touch_result": str(result.first_touch),
                "same_bar_ambiguity": result.ambiguous_same_bar,
                "gap_through_stop": result.first_touch == FirstTouch.GAP_THROUGH_STOP,
                "gap_through_target": result.first_touch == FirstTouch.GAP_THROUGH_TARGET,
                "daily_outcome": daily,
                "comparison": comparison,
                "holding_sessions_available": len(holding_dates),
                "frozen_outcome_modified": False,
            }
        )
    return rows


def _confirmation_rows(
    outcomes: Sequence[dict[str, str]],
    strict_groups: Mapping[tuple[str, date], list[CanonicalIntradayBar]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for outcome in outcomes:
        symbol = outcome["symbol"]
        entry_date = date.fromisoformat(outcome["next_session_date"])
        bars = sorted(strict_groups.get((symbol, entry_date), []), key=lambda row: row.bar_start)
        vwap = calculate_session_vwap(bars) if bars else []
        result.append(
            {
                "symbol": symbol,
                "entry_date": entry_date,
                "first_5m_close_available": len(bars) >= 1,
                "first_10m_close_available": len(bars) >= 2,
                "first_15m_close_available": len(bars) >= 3,
                "opening_range_status_available": len(bars) >= 3,
                "vwap_at_5m_available": len(vwap) >= 1 and vwap[0].vwap is not None,
                "vwap_at_10m_available": len(vwap) >= 2 and vwap[1].vwap is not None,
                "vwap_at_15m_available": len(vwap) >= 3 and vwap[2].vwap is not None,
                "cumulative_volume_available": len(vwap) >= 3 and vwap[2].cumulative_volume >= 0,
                "causal_completed_bars_only": True,
                "strategy_rule_defined": False,
            }
        )
    return result


def _quality_result(rows: Sequence[dict[str, Any]]) -> RealDataQualityResult:
    if not rows or not any(row["actual_bars"] for row in rows):
        return RealDataQualityResult.NO_REAL_DATA_INGESTED
    unusable = sum(row["usability"] == str(SessionUsability.UNUSABLE) for row in rows)
    warnings = sum(row["usability"] == str(SessionUsability.USABLE_WITH_WARNING) for row in rows)
    missing = sum(int(row["missing_bars"]) for row in rows)
    if unusable > len(rows) * 0.2:
        return RealDataQualityResult.POOR
    if unusable or missing > len(rows):
        return RealDataQualityResult.USABLE_WITH_MATERIAL_GAPS
    if warnings or missing:
        return RealDataQualityResult.USABLE_WITH_MINOR_GAPS
    return RealDataQualityResult.CLEAN


def _overall_reconciliation(rows: Sequence[dict[str, Any]]) -> RealReconciliationResult:
    classes = {row["classification"] for row in rows}
    if not rows or classes == {str(ReconciliationClassification.UNAVAILABLE_DAILY_REFERENCE)}:
        return RealReconciliationResult.INCONCLUSIVE
    if any(value.startswith("MATERIAL_") for value in classes):
        return RealReconciliationResult.MATERIAL_MISMATCH
    if classes == {str(ReconciliationClassification.MATCH)}:
        return RealReconciliationResult.CLEAN
    return RealReconciliationResult.CLEAN_WITH_SOURCE_DIFFERENCES


def _quality_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "symbol_session_combinations": len(rows),
        "strict_usable_sessions": sum(row.get("usability") == str(SessionUsability.USABLE_STRICT) for row in rows),
        "usable_with_warning_sessions": sum(row.get("usability") == str(SessionUsability.USABLE_WITH_WARNING) for row in rows),
        "unusable_sessions": sum(row.get("usability") == str(SessionUsability.UNUSABLE) for row in rows),
        "missing_bar_sessions": sum(bool(row.get("missing_bars")) for row in rows),
        "duplicate_sessions": sum(bool(row.get("duplicate_bars")) for row in rows),
        "invalid_ohlc_sessions": sum(bool(row.get("invalid_ohlc")) for row in rows),
        "off_session_rows": sum(int(row.get("off_session_rows", 0)) for row in rows),
    }


def _first_touch_summary(rows: Sequence[dict[str, Any]]) -> dict[str, int]:
    return {
        "applicable_pilot_opportunities": len(rows),
        "daily_ambiguous_count": sum(row.get("daily_outcome") == "INTRABAR_SEQUENCE_AMBIGUOUS" for row in rows),
        "five_minute_resolved_count": sum(row.get("comparison") == "DAILY_AMBIGUOUS_RESOLVED_BY_5M" for row in rows),
        "five_minute_still_ambiguous_count": sum(row.get("comparison") == "5M_STILL_AMBIGUOUS" for row in rows),
        "classification_change_count": sum(row.get("comparison") == "DAILY_NONAMBIGUOUS_CHANGED" for row in rows),
        "gap_through_stop_count": sum(bool(row.get("gap_through_stop")) for row in rows),
        "gap_through_target_count": sum(bool(row.get("gap_through_target")) for row in rows),
    }


def _scalability_row() -> dict[str, Any]:
    windows_per_symbol = math.ceil((365.25 * 5) / 30)
    requests = 500 * windows_per_symbol
    return {
        "symbols": 500,
        "years": 5,
        "native_interval": "5m",
        "maximum_days_per_request": 30,
        "estimated_historical_requests": requests,
        "conservative_planning_throttle_requests_per_second": 1,
        "theoretical_minimum_retrieval_hours_at_planning_throttle": round(requests / 3600, 2),
        "practical_retrieval_time_range": "10-16 hours plus retry/reconciliation overhead",
        "estimated_rows": STORAGE_ESTIMATE["estimated_rows"],
        "estimated_storage": STORAGE_ESTIMATE["planning_range_gib_with_metadata"],
        "provider_cost": "UNKNOWN_NOT_DOCUMENTED_IN_REPOSITORY_OR_AUDITED_PAGES",
        "feasibility": str(FullIngestionFeasibility.FEASIBLE_WITH_BATCHING),
        "bulk_ingestion_executed": False,
    }


def _pilot_manifest(state: dict[str, Any], spec: PilotSpec) -> dict[str, Any]:
    return {
        "provider": "Groww",
        "symbols": list(spec.symbols),
        "instrument_mappings": state["mappings"],
        "dates": [value.isoformat() for value in spec.dates],
        "selection_reason": "Frozen development opportunities with price/liquidity/gap/outcome diversity",
        "development_only": True,
        "request_budget": state["request_budget"],
        "requests": state["requests"],
        "provider_capability_hash": state["provider_capability_manifest_hash"],
        "terms_status": str(ResearchRightsStatus.USABLE_WITH_RESTRICTIONS),
        "credentials_present": True,
        "raw_hash": state["raw_pilot_hash"],
        "normalized_hash": state["normalized_5m_pilot_hash"],
        "derived_10m_hash": state["derived_10m_pilot_hash"],
        "derived_15m_hash": state["derived_15m_pilot_hash"],
        "instrument_mapping_hash": state["instrument_mapping_hash"],
        "created_at": state["retrieval_timestamp"],
        "pilot_version": PILOT_VERSION,
        "dataset_paths": state["dataset_paths"],
        "raw_paths": state["raw_paths"],
        "row_counts": {
            "raw": state["raw_pilot_row_count"],
            "normalized_5m": state["normalized_5m_row_count"],
            "derived_10m": state["derived_10m_row_count"],
            "derived_15m": state["derived_15m_row_count"],
        },
    }


def _extract_candles(response: Mapping[str, Any]) -> list[Any]:
    value: Any = response
    if isinstance(value.get("payload"), dict):
        value = value["payload"]
    if isinstance(value.get("data"), dict):
        value = value["data"]
    candles = value.get("candles")
    if not isinstance(candles, list):
        raise ValueError("Provider response does not contain a candle list")
    return candles


def _provider_candle_row(candle: Any) -> dict[str, Any]:
    if isinstance(candle, Mapping):
        values = {
            "timestamp": candle.get("timestamp") or candle.get("time") or candle.get("date"),
            "open": candle.get("open"),
            "high": candle.get("high"),
            "low": candle.get("low"),
            "close": candle.get("close"),
            "volume": candle.get("volume"),
            "provider_vwap": candle.get("vwap"),
        }
    else:
        if not isinstance(candle, Sequence) or len(candle) < 6:
            raise ValueError("Provider candle is incomplete")
        values = dict(zip(("timestamp", "open", "high", "low", "close", "volume"), candle[:6]))
        values["provider_vwap"] = None
    if any(values[key] is None for key in ("timestamp", "open", "high", "low", "close", "volume")):
        raise ValueError("Provider candle is missing a required field")
    return values


def _validate_development_dates(values: Iterable[date]) -> None:
    if any(value < DEVELOPMENT_START or value > DEVELOPMENT_END for value in values):
        raise ValueError("Validation-window provider requests are prohibited")


def _request_metric(
    request_id: str,
    category: str,
    status: str,
    response_category: str,
    started: float,
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "provider": "Groww",
        "endpoint_category": category,
        "status": status,
        "response_category": response_category,
        "retry_number": 0,
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
    }


def _budget_snapshot(budget: RequestBudget) -> dict[str, int]:
    return {
        "max_provider_requests": budget.max_provider_requests,
        "expected_requests": budget.expected_requests,
        "actual_requests": budget.actual_requests,
        "retry_count": budget.retry_count,
    }


def _empty_budget(spec: PilotSpec) -> dict[str, int]:
    return {
        "max_provider_requests": spec.max_provider_requests,
        "expected_requests": spec.expected_requests,
        "actual_requests": 0,
        "retry_count": 0,
    }


def _empty_pilot_state() -> dict[str, Any]:
    return {
        "mappings": [],
        "requests": [],
        "sessions": [],
        "quality_rows": [],
        "daily_reconciliation": [],
        "opening_range": [],
        "vwap": [],
        "first_touch": [],
        "confirmation_availability": [],
        "dataset_paths": {},
        "raw_paths": [],
        "provider_reliability_result": str(ProviderReliabilityResult.INCONCLUSIVE),
    }


def _missing_session_row(symbol: str, trading_date: date, expected: int) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "trading_date": trading_date,
        "expected_bars": expected,
        "actual_bars": 0,
        "missing_bars": expected,
        "duplicate_bars": 0,
        "out_of_order": False,
        "invalid_ohlc": False,
        "negative_volume": False,
        "off_session_rows": 0,
        "coverage_pct": Decimal("0"),
        "quality_status": "NO_ROWS",
        "session_usability_version": SESSION_USABILITY_VERSION,
        "usability": str(SessionUsability.UNUSABLE),
        "timestamp_definition_warning": "OFFICIAL_PROSE_NOT_EXPLICIT",
    }


def _unavailable_reconciliation_row(symbol: str, trading_date: date, reason: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "trading_date": trading_date,
        "classification": str(ReconciliationClassification.UNAVAILABLE_DAILY_REFERENCE),
        "reason": reason,
    }


def _pilot_report_row(summary: dict[str, Any]) -> dict[str, Any]:
    quality = summary["quality"]
    return {
        "pilot_version": PILOT_VERSION,
        "provider": summary["selected_provider"],
        "selection_result": summary["pilot_provider_selection_result"],
        "real_pilot_result": summary["classifications"]["REAL_INTRADAY_PILOT_RESULT"],
        "symbol_count": len(summary["pilot"]["symbols"]),
        "session_count_per_symbol": len(summary["pilot"]["dates"]),
        "symbol_session_combinations": quality["symbol_session_combinations"],
        "strict_usable_sessions": quality["strict_usable_sessions"],
        "normalized_rows": summary["row_counts"]["normalized_5m"],
        "validation_state": summary["safety"]["validation_state"],
        "live_orders": summary["safety"]["live_orders_placed"],
    }


def _git_ignored(root: Path, path: Path) -> bool:
    import subprocess

    result = subprocess.run(
        ["git", "check-ignore", "-q", str(path)], cwd=root, check=False, capture_output=True
    )
    return result.returncode == 0


def _write_new_json(path: Path, value: Any) -> None:
    if path.exists():
        raise FileExistsError(f"Raw pilot payload is immutable: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_ready(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_ready(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    prepared = [json_ready(dict(row)) for row in rows]
    fields = sorted({key for row in prepared for key in row}) or ["status"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in prepared:
            writer.writerow({key: _csv_value(row.get(key)) for key in fields})


def _write_gzip_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    prepared = [json_ready(dict(row)) for row in rows]
    fields = sorted({key for row in prepared for key in row}) or ["status"]
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in prepared:
            writer.writerow({key: _csv_value(row.get(key)) for key in fields})


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return value


def _optional_text(value: Any) -> str | None:
    if value is None or not str(value).strip() or str(value).strip().lower() == "nan":
        return None
    return str(value).strip()


def _notify(progress: Callable[[str], None] | None, message: str) -> None:
    if progress:
        progress(message)
