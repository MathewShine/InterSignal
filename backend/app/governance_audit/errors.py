"""Stable Governance / Audit domain errors."""


class GovernanceError(Exception):
    """Base class for Governance / Audit failures."""


class GovernanceSubjectNotFound(GovernanceError, LookupError):
    pass


class AuthorizationNotFound(GovernanceError, LookupError):
    pass


class InvalidAuthorizationTransition(GovernanceError, ValueError):
    pass


class AuthorizationExpired(GovernanceError, ValueError):
    pass


class PolicyNotFound(GovernanceError, LookupError):
    pass


class ViolationNotFound(GovernanceError, LookupError):
    pass


class InvalidOverride(GovernanceError, ValueError):
    pass


class GovernanceIntegrityError(GovernanceError, RuntimeError):
    pass


__all__ = (
    "AuthorizationExpired",
    "AuthorizationNotFound",
    "GovernanceError",
    "GovernanceIntegrityError",
    "GovernanceSubjectNotFound",
    "InvalidAuthorizationTransition",
    "InvalidOverride",
    "PolicyNotFound",
    "ViolationNotFound",
)
