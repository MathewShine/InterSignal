"""Stable domain errors for Research Workbench queries."""


class ResearchWorkbenchError(Exception):
    """Base class for Workbench domain failures."""


class ResearchFamilyNotFound(ResearchWorkbenchError, LookupError):
    pass


class StrategyNotFound(ResearchWorkbenchError, LookupError):
    pass


class EvidenceNotFound(ResearchWorkbenchError, LookupError):
    pass


class ArtifactNotFound(ResearchWorkbenchError, LookupError):
    pass


class LineageNodeNotFound(ResearchWorkbenchError, LookupError):
    pass


class InvalidWorkbenchQuery(ResearchWorkbenchError, ValueError):
    pass


class WorkbenchIntegrityError(ResearchWorkbenchError, RuntimeError):
    pass


__all__ = (
    "ArtifactNotFound",
    "EvidenceNotFound",
    "InvalidWorkbenchQuery",
    "LineageNodeNotFound",
    "ResearchFamilyNotFound",
    "ResearchWorkbenchError",
    "StrategyNotFound",
    "WorkbenchIntegrityError",
)
