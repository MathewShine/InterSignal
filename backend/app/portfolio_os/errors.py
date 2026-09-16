"""Stable Portfolio OS domain errors."""


class PortfolioOSError(Exception):
    """Base class for Portfolio OS failures."""


class PortfolioNotFound(PortfolioOSError, LookupError):
    pass


class AccountNotFound(PortfolioOSError, LookupError):
    pass


class SecurityNotFound(PortfolioOSError, LookupError):
    pass


class InvalidTransaction(PortfolioOSError, ValueError):
    pass


class InsufficientPosition(InvalidTransaction):
    pass


class CurrencyMismatch(PortfolioOSError, ValueError):
    pass


class ReconciliationError(PortfolioOSError, RuntimeError):
    pass


class InvalidPortfolioState(PortfolioOSError, ValueError):
    pass


__all__ = (
    "AccountNotFound",
    "CurrencyMismatch",
    "InsufficientPosition",
    "InvalidPortfolioState",
    "InvalidTransaction",
    "PortfolioNotFound",
    "PortfolioOSError",
    "ReconciliationError",
    "SecurityNotFound",
)
