"""Controlled, non-promotable historical strategy diagnostics."""

from app.diagnostics.strategy_diagnostic import (
    STRATEGY_DIAGNOSTIC_FRAMEWORK_PROFILE,
    STRATEGY_DIAGNOSTIC_FRAMEWORK_VERSION,
    ExperimentDefinition,
    ExperimentRegistry,
    build_experiment_definitions,
    run_strategy_diagnostic_framework,
)
from app.diagnostics.exit_stop_path_diagnostic import (
    EXIT_COMMAND_VERSION,
    EXIT_EXPERIMENT_IDS,
    ExitExperimentRegistry,
    build_exit_experiment_definitions,
    run_exit_stop_path_diagnostics,
)
from app.diagnostics.entry_quality_diagnostic import (
    ENTRY_QUALITY_COMMAND_VERSION,
    ENTRY_QUALITY_EXPERIMENT_IDS,
    EntryQualityRegistry,
    build_entry_quality_definitions,
    run_entry_quality_diagnostics,
)
from app.diagnostics.score_calibration_diagnostic import (
    SCORE_CALIBRATION_COMMAND_VERSION,
    SCORE_CALIBRATION_EXPERIMENT_IDS,
    ScoreCalibrationRegistry,
    build_score_calibration_definitions,
    run_score_calibration_diagnostics,
)
from app.diagnostics.regime_context_diagnostic import (
    REGIME_CONTEXT_COMMAND_VERSION,
    REGIME_CONTEXT_EXPERIMENT_IDS,
    RegimeContextRegistry,
    build_regime_context_definitions,
    run_regime_context_diagnostics,
)
from app.diagnostics.strategy_diagnostic_synthesis import (
    SYNTHESIS_PROFILE,
    SYNTHESIS_VERSION,
    build_hypothesis_catalog,
    run_strategy_diagnostic_synthesis,
)

__all__ = [
    "STRATEGY_DIAGNOSTIC_FRAMEWORK_VERSION",
    "STRATEGY_DIAGNOSTIC_FRAMEWORK_PROFILE",
    "ExperimentDefinition",
    "ExperimentRegistry",
    "build_experiment_definitions",
    "run_strategy_diagnostic_framework",
    "EXIT_COMMAND_VERSION",
    "EXIT_EXPERIMENT_IDS",
    "ExitExperimentRegistry",
    "build_exit_experiment_definitions",
    "run_exit_stop_path_diagnostics",
    "ENTRY_QUALITY_COMMAND_VERSION",
    "ENTRY_QUALITY_EXPERIMENT_IDS",
    "EntryQualityRegistry",
    "build_entry_quality_definitions",
    "run_entry_quality_diagnostics",
    "SCORE_CALIBRATION_COMMAND_VERSION",
    "SCORE_CALIBRATION_EXPERIMENT_IDS",
    "ScoreCalibrationRegistry",
    "build_score_calibration_definitions",
    "run_score_calibration_diagnostics",
    "REGIME_CONTEXT_COMMAND_VERSION",
    "REGIME_CONTEXT_EXPERIMENT_IDS",
    "RegimeContextRegistry",
    "build_regime_context_definitions",
    "run_regime_context_diagnostics",
    "SYNTHESIS_VERSION",
    "SYNTHESIS_PROFILE",
    "build_hypothesis_catalog",
    "run_strategy_diagnostic_synthesis",
]
