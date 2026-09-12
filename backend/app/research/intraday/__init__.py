"""Provider-neutral intraday data and execution-ordering research architecture."""

from app.research.intraday.architecture import build_intraday_architecture_research
from app.research.intraday.config import (
    CANONICAL_INTRADAY_PROFILE,
    EXECUTION_ORDERING_VERSION,
    INTRADAY_RESEARCH_ARCHITECTURE_VERSION,
)
from app.research.intraday.development_ingestion import (
    COMMAND_VERSION as DEVELOPMENT_INTRADAY_INGESTION_VERSION,
    PROFILE as DEVELOPMENT_INTRADAY_INGESTION_PROFILE,
    RunMode as DevelopmentIntradayRunMode,
    run_development_intraday_ingestion,
)
from app.research.intraday.confirmation_diagnostic import (
    DIAGNOSTIC_VERSION as INTRADAY_CONFIRMATION_DIAGNOSTIC_VERSION,
    PROFILE as INTRADAY_CONFIRMATION_DIAGNOSTIC_PROFILE,
    run_intraday_confirmation_diagnostic,
)
from app.research.intraday.confirmation_rule_experiment import (
    EXPERIMENT_VERSION as INTRADAY_CONFIRMATION_RULE_EXPERIMENT_VERSION,
    PROFILE as INTRADAY_CONFIRMATION_RULE_EXPERIMENT_PROFILE,
    run_intraday_confirmation_rule_experiment,
)
from app.research.intraday.early_path_recovery_diagnostic import (
    DIAGNOSTIC_VERSION as EARLY_PATH_RECOVERY_DIAGNOSTIC_VERSION,
    PROFILE as EARLY_PATH_RECOVERY_DIAGNOSTIC_PROFILE,
    run_early_path_recovery_diagnostic,
)
from app.research.intraday.provider_pilot import build_real_intraday_provider_pilot
from app.research.intraday.root_cause_audit import (
    AUDIT_PROFILE as GROWW_INTRADAY_ROOT_CAUSE_AUDIT_PROFILE,
    AUDIT_VERSION as GROWW_INTRADAY_ROOT_CAUSE_AUDIT_VERSION,
    build_groww_intraday_root_cause_audit,
)
from app.research.intraday.resume_ingestion import (
    COMMAND_VERSION as DEVELOPMENT_INTRADAY_INGESTION_RESUME_VERSION,
    PROFILE as DEVELOPMENT_INTRADAY_INGESTION_RESUME_PROFILE,
    ResumeMode as DevelopmentIntradayResumeMode,
    run_development_intraday_resume,
)

__all__ = [
    "CANONICAL_INTRADAY_PROFILE",
    "EXECUTION_ORDERING_VERSION",
    "INTRADAY_RESEARCH_ARCHITECTURE_VERSION",
    "DEVELOPMENT_INTRADAY_INGESTION_PROFILE",
    "DEVELOPMENT_INTRADAY_INGESTION_VERSION",
    "DevelopmentIntradayRunMode",
    "EARLY_PATH_RECOVERY_DIAGNOSTIC_PROFILE",
    "EARLY_PATH_RECOVERY_DIAGNOSTIC_VERSION",
    "INTRADAY_CONFIRMATION_DIAGNOSTIC_PROFILE",
    "INTRADAY_CONFIRMATION_DIAGNOSTIC_VERSION",
    "INTRADAY_CONFIRMATION_RULE_EXPERIMENT_PROFILE",
    "INTRADAY_CONFIRMATION_RULE_EXPERIMENT_VERSION",
    "GROWW_INTRADAY_ROOT_CAUSE_AUDIT_PROFILE",
    "GROWW_INTRADAY_ROOT_CAUSE_AUDIT_VERSION",
    "DEVELOPMENT_INTRADAY_INGESTION_RESUME_PROFILE",
    "DEVELOPMENT_INTRADAY_INGESTION_RESUME_VERSION",
    "DevelopmentIntradayResumeMode",
    "build_intraday_architecture_research",
    "build_real_intraday_provider_pilot",
    "build_groww_intraday_root_cause_audit",
    "run_development_intraday_ingestion",
    "run_development_intraday_resume",
    "run_early_path_recovery_diagnostic",
    "run_intraday_confirmation_diagnostic",
    "run_intraday_confirmation_rule_experiment",
]
