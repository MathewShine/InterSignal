from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

BENCHMARK_CONTEXT_VERSION = "BENCHMARK_CONTEXT_V1"
SECTOR_CONTEXT_VERSION = "SECTOR_CONTEXT_V1"

PRIMARY_BENCHMARK_ID = "NIFTY_500"
SECONDARY_BENCHMARK_ID = "NIFTY_50"

BENCHMARK_INDEXES = {
    PRIMARY_BENCHMARK_ID: "NIFTY 500",
    SECONDARY_BENCHMARK_ID: "NIFTY 50",
}

BENCHMARK_RETURN_WINDOWS = (1, 2, 3, 5, 10, 20)
RELATIVE_BENCHMARK_WINDOWS = (1, 3, 5, 10, 20)
SECONDARY_BENCHMARK_WINDOWS = (5, 20)
SECTOR_RETURN_WINDOWS = (1, 3, 5, 10, 20)

MAPPING_STATUS_POINT_IN_TIME_VERIFIED = "POINT_IN_TIME_VERIFIED"
MAPPING_STATUS_CURRENT_ONLY = "CURRENT_ONLY"
MAPPING_STATUS_INFERRED_WITH_EVIDENCE = "INFERRED_WITH_EVIDENCE"
MAPPING_STATUS_UNAVAILABLE = "UNAVAILABLE"

ALLOWED_SECTOR_MAPPING_STATUSES = (
    MAPPING_STATUS_POINT_IN_TIME_VERIFIED,
    MAPPING_STATUS_INFERRED_WITH_EVIDENCE,
)

SUPPORTED_SECTOR_INDEX_NAMES = (
    "NIFTY AUTO",
    "NIFTY BANK",
    "NIFTY CAPITAL GOODS",
    "NIFTY CEMENT",
    "NIFTY CHEMICALS",
    "NIFTY COMMERCIAL & TRANSPORT SERVICES",
    "NIFTY CONSTRUCTION",
    "NIFTY CONSUMER DURABLES",
    "NIFTY CONSUMER SERVICES",
    "NIFTY FINANCIAL SERVICES",
    "NIFTY FINANCIAL SERVICES 25/50",
    "NIFTY FMCG",
    "NIFTY HEALTHCARE INDEX",
    "NIFTY HOSPITALS",
    "NIFTY HOUSING FINANCE",
    "NIFTY INSURANCE",
    "NIFTY IT",
    "NIFTY MEDIA",
    "NIFTY METAL",
    "NIFTY NBFC",
    "NIFTY OIL & GAS",
    "NIFTY PHARMA",
    "NIFTY POWER",
    "NIFTY PRIVATE BANK",
    "NIFTY PSU BANK",
    "NIFTY REALTY",
    "NIFTY REITS & REALTY",
    "NIFTY RETAIL",
    "NIFTY TELECOMMUNICATIONS",
    "NIFTY500 HEALTHCARE",
)

INDUSTRY_TO_SECTOR_INDEX_ID = {
    "Automobile and Auto Components": "NIFTY_AUTO",
    "Capital Goods": "NIFTY_CAPITAL_GOODS",
    "Chemicals": "NIFTY_CHEMICALS",
    "Construction": "NIFTY_CONSTRUCTION",
    "Consumer Durables": "NIFTY_CONSUMER_DURABLES",
    "Consumer Services": "NIFTY_CONSUMER_SERVICES",
    "Fast Moving Consumer Goods": "NIFTY_FMCG",
    "Financial Services": "NIFTY_FINANCIAL_SERVICES",
    "Healthcare": "NIFTY_HEALTHCARE_INDEX",
    "Information Technology": "NIFTY_IT",
    "Media Entertainment & Publication": "NIFTY_MEDIA",
    "Metals & Mining": "NIFTY_METAL",
    "Oil Gas & Consumable Fuels": "NIFTY_OIL_AND_GAS",
    "Power": "NIFTY_POWER",
    "Realty": "NIFTY_REALTY",
    "Telecommunication": "NIFTY_TELECOMMUNICATIONS",
}


@dataclass(frozen=True, slots=True)
class IndexDefinition:
    index_id: str
    index_name: str
    category: str
    role: str = ""
    source_reference: str = ""


@dataclass(frozen=True, slots=True)
class IndexDailyRecord:
    trading_date: date
    index_id: str
    index_name: str
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal
    source: str
    source_reference: str
    source_date: date | None
    raw_source_file: str = ""


def canonical_index_id(index_name: str) -> str:
    text = index_name.strip().upper()
    text = text.replace("&", " AND ")
    text = re.sub(r"[^A-Z0-9]+", "_", text)
    return text.strip("_")
