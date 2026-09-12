from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.backtesting.costs.cost_models import (
    BOTH,
    BUY,
    COST_MODEL_VERSION,
    COST_PROFILE,
    DP_CHARGE,
    EXCHANGE_TRANSACTION_CHARGE,
    GST,
    HISTORICAL_RATE_PRECISION,
    NET_ESTIMATE_WARNING,
    OTHER_REGULATORY,
    SEBI_CHARGE,
    SELL,
    STAMP_DUTY,
    STT,
    BrokerageConfig,
    CostModelConfig,
    CostRateSchedule,
    SlippageConfig,
)

NSE_LEVIES_URL = (
    "https://www.nseindia.com/static/invest/first-time-investor-sebi-turnover-fees-stt-other-levies"
)
NSE_EXCHANGE_2023_URL = "https://nsearchives.nseindia.com/content/circulars/FA56129.pdf"
NSE_EXCHANGE_2024_URL = "https://nsearchives.nseindia.com/content/circulars/FA64232.pdf"
CBIC_GST_URL = "https://cbic-gst.gov.in/pdf/circular-cgst-119.pdf"
CDSL_TARIFF_URL = "https://www.cdslindia.com/DP/CurrentDPs.html"


def default_cost_model_config() -> CostModelConfig:
    schedules = (
        CostRateSchedule(
            STT,
            BOTH,
            Decimal("0.001"),
            "EXECUTED_TURNOVER",
            date(2022, 1, 1),
            None,
            "HISTORICAL_APPROXIMATION",
            True,
            "NSE publishes 0.100% on both delivery purchase and sale through 2026; applied uniformly to the frozen sample because a complete historical contract-note schedule was not reconstructed.",
            NSE_LEVIES_URL,
        ),
        CostRateSchedule(
            EXCHANGE_TRANSACTION_CHARGE,
            BOTH,
            Decimal("0.0000345"),
            "EXECUTED_TURNOVER",
            date(2022, 1, 1),
            date(2023, 3, 31),
            "HISTORICAL_APPROXIMATION",
            True,
            "Uses the NSE pre-April-2023 first turnover slab of Rs 3.45 per lakh; actual member slab is unavailable.",
            NSE_EXCHANGE_2023_URL,
        ),
        CostRateSchedule(
            EXCHANGE_TRANSACTION_CHARGE,
            BOTH,
            Decimal("0.0000325"),
            "EXECUTED_TURNOVER",
            date(2023, 4, 1),
            date(2024, 9, 30),
            "HISTORICAL_APPROXIMATION",
            True,
            "Uses the NSE first turnover slab of Rs 3.25 per lakh; actual member slab is unavailable.",
            NSE_EXCHANGE_2023_URL,
        ),
        CostRateSchedule(
            EXCHANGE_TRANSACTION_CHARGE,
            BOTH,
            Decimal("0.0000297"),
            "EXECUTED_TURNOVER",
            date(2024, 10, 1),
            None,
            "AUTHORITATIVE",
            False,
            "Uniform NSE cash-market transaction charge of Rs 2.97 each side per lakh from 2024-10-01.",
            NSE_EXCHANGE_2024_URL,
        ),
        CostRateSchedule(
            SEBI_CHARGE,
            BOTH,
            Decimal("0.000001"),
            "EXECUTED_TURNOVER",
            date(2022, 1, 1),
            None,
            "REGULATORY_PUBLISHED",
            False,
            "Rs 10 per crore on purchases and sales of non-debt securities.",
            NSE_LEVIES_URL,
        ),
        CostRateSchedule(
            GST,
            BOTH,
            Decimal("0.18"),
            "EXPLICIT_TAXABLE_FEE_BASE",
            date(2022, 1, 1),
            None,
            "REGULATORY_PUBLISHED",
            False,
            "18% on stock-broking services; the model excludes security notional, STT, and stamp duty from the taxable base.",
            CBIC_GST_URL,
        ),
        CostRateSchedule(
            STAMP_DUTY,
            BUY,
            Decimal("0.00015"),
            "EXECUTED_TURNOVER",
            date(2022, 1, 1),
            None,
            "REGULATORY_PUBLISHED",
            False,
            "0.015% on the buyer for delivery transfer; centralized collection applies from 2020-07-01.",
            NSE_LEVIES_URL,
        ),
        CostRateSchedule(
            DP_CHARGE,
            SELL,
            Decimal("13.50"),
            "FLAT_PER_SELL_TRADE_RESEARCH_PROXY",
            date(2022, 1, 1),
            None,
            "RESEARCH_ASSUMPTION",
            True,
            "Provider-neutral Rs 13.50 per sell-trade proxy. DP client tariffs vary; CDSL's own DP debit tariff is not a universal retail charge.",
            CDSL_TARIFF_URL,
        ),
        CostRateSchedule(
            OTHER_REGULATORY,
            BOTH,
            Decimal("0"),
            "EXECUTED_TURNOVER",
            date(2022, 1, 1),
            None,
            "RESEARCH_ASSUMPTION",
            True,
            "No separate other-regulatory amount is assumed in V1; the component remains visible and configurable.",
            "",
        ),
    )
    return CostModelConfig(
        version=COST_MODEL_VERSION,
        profile=COST_PROFILE,
        venue="NSE",
        product_scope="LONG_CASH_EQUITY_DELIVERY_ONLY",
        currency="INR",
        brokerage=BrokerageConfig(),
        slippage=SlippageConfig(),
        rate_schedules=schedules,
        gst_taxable_components=(
            "BROKERAGE",
            EXCHANGE_TRANSACTION_CHARGE,
            SEBI_CHARGE,
            DP_CHARGE,
            OTHER_REGULATORY,
        ),
        rounding_quantum=Decimal("0.01"),
        rounding_mode="ROUND_HALF_UP",
        component_rounding_policy="ROUND_EACH_SIDE_COMPONENT_TO_PAISE_THEN_SUM",
        historical_rate_precision=HISTORICAL_RATE_PRECISION,
        net_estimate_warning=NET_ESTIMATE_WARNING,
    )


DEFAULT_COST_CONFIG = default_cost_model_config()
DEFAULT_COST_CONFIG_HASH = DEFAULT_COST_CONFIG.config_hash()
EXPECTED_COST_CONFIG_HASH = "9f20882e8fc4c6333c53637e516704ea73cc1db0cecb1ac2d9a5155996789c48"
