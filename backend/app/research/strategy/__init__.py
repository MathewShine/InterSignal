"""Controlled strategy-research experiments."""

from app.research.strategy.rr_score_mapping_experiment import (
    EXPERIMENT_ID,
    EXPERIMENT_VERSION,
    PROFILE,
    run_rr_cap4_experiment,
)
from app.research.strategy.rr_cap4_holdout_validation import (
    VALIDATION_RECORD_ID,
    VALIDATION_VERSION,
    finalize_validation_review,
    run_one_shot_validation,
)
from app.research.strategy.family_a_momentum import (
    FAMILY_CODE,
    FAMILY_VERSION,
    RESEARCH_PROFILE as FAMILY_A_RESEARCH_PROFILE,
    RESEARCH_PROTOCOL as FAMILY_A_RESEARCH_PROTOCOL,
    build_family_a_architecture,
    finalize_family_a_review,
)
from app.research.strategy.family_a_development_backtest import (
    COMMAND_VERSION as FAMILY_A_DEVELOPMENT_VERSION,
    build_family_a_development_backtests,
    finalize_development_review,
)
from app.research.strategy.family_a_phase2_research import (
    PHASE2_VERSION as FAMILY_A_PHASE2_VERSION,
    build_family_a_phase2_research,
    finalize_phase2_review,
)
from app.research.strategy.family_a_phase2_development_evaluation import (
    COMMAND_VERSION as FAMILY_A_PHASE2_DEVELOPMENT_VERSION,
    build_family_a_phase2_development_evaluation,
    finalize_phase2_development_review,
)
from app.research.strategy.family_a_phase2_closure import (
    COMMAND_VERSION as FAMILY_A_PHASE2_CLOSURE_VERSION,
    build_family_a_phase2_closure,
    finalize_family_a_closure,
)

__all__ = (
    "EXPERIMENT_ID",
    "EXPERIMENT_VERSION",
    "PROFILE",
    "VALIDATION_RECORD_ID",
    "VALIDATION_VERSION",
    "finalize_validation_review",
    "run_one_shot_validation",
    "run_rr_cap4_experiment",
    "FAMILY_CODE",
    "FAMILY_VERSION",
    "FAMILY_A_RESEARCH_PROFILE",
    "FAMILY_A_RESEARCH_PROTOCOL",
    "build_family_a_architecture",
    "finalize_family_a_review",
    "FAMILY_A_DEVELOPMENT_VERSION",
    "build_family_a_development_backtests",
    "finalize_development_review",
    "FAMILY_A_PHASE2_VERSION",
    "build_family_a_phase2_research",
    "finalize_phase2_review",
    "FAMILY_A_PHASE2_DEVELOPMENT_VERSION",
    "build_family_a_phase2_development_evaluation",
    "finalize_phase2_development_review",
    "FAMILY_A_PHASE2_CLOSURE_VERSION",
    "build_family_a_phase2_closure",
    "finalize_family_a_closure",
)
