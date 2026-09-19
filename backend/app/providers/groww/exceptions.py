class GrowwProviderError(RuntimeError):
    code = "GROWW_PROVIDER_ERROR"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.code)


class GrowwProviderNotConfiguredError(GrowwProviderError):
    code = "GROWW_NOT_CONFIGURED"

    def __init__(self) -> None:
        super().__init__("GROWW_NOT_CONFIGURED")


class GrowwAuthenticationError(GrowwProviderError):
    code = "GROWW_AUTH_FAILED"

    def __init__(self) -> None:
        super().__init__("Groww authentication failed.")


class GrowwHistoricalDataError(GrowwProviderError):
    code = "GROWW_HISTORICAL_REQUEST_FAILED"

    def __init__(self) -> None:
        super().__init__("Groww historical data request failed.")


class GrowwMarketDataError(GrowwProviderError):
    code = "GROWW_MARKET_DATA_REQUEST_FAILED"

    def __init__(self) -> None:
        super().__init__("Groww market data request failed.")


class GrowwRateLimitError(GrowwProviderError):
    code = "GROWW_RATE_LIMITED"

    def __init__(self) -> None:
        super().__init__("Groww market data rate limit reached.")
