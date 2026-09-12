from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping, Sequence

from app.research.temporal_validation.config import (
    DEVELOPMENT_WINDOW_VERSION,
    canonical_hash,
    json_ready,
)


@dataclass(frozen=True, slots=True)
class ExperimentFreezeArtifact:
    """Immutable definition frozen on development data before holdout authorization."""

    experiment_id: str
    experiment_version: str
    hypothesis: str
    development_window: str
    parameters: Mapping[str, Any]
    primary_metric: str
    secondary_metrics: Sequence[str]
    falsification_criteria: Sequence[str]
    promotion_criteria: Sequence[str]
    minimum_sample: int
    baseline_dependencies: Mapping[str, str]
    development_result_hash: str
    cost_model: str
    frozen_at: str
    validation_authorized: bool = False

    def parameter_hash(self) -> str:
        return canonical_hash(self.parameters)

    def freeze_payload(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "experiment_version": self.experiment_version,
            "hypothesis": self.hypothesis,
            "development_window": self.development_window,
            "parameters": self.parameters,
            "parameter_hash": self.parameter_hash(),
            "primary_metric": self.primary_metric,
            "secondary_metrics": list(self.secondary_metrics),
            "falsification_criteria": list(self.falsification_criteria),
            "promotion_criteria": list(self.promotion_criteria),
            "minimum_sample": self.minimum_sample,
            "baseline_dependencies": self.baseline_dependencies,
            "development_result_hash": self.development_result_hash,
            "cost_model": self.cost_model,
            "frozen_at": self.frozen_at,
            "validation_authorized": self.validation_authorized,
        }

    def development_freeze_hash(self) -> str:
        return canonical_hash(self.freeze_payload())

    def snapshot(self) -> dict[str, Any]:
        return json_ready(
            self.freeze_payload()
            | {"development_freeze_hash": self.development_freeze_hash()}
        )

    def validate(self) -> None:
        required_text = (
            self.experiment_id,
            self.experiment_version,
            self.hypothesis,
            self.development_window,
            self.primary_metric,
            self.development_result_hash,
            self.cost_model,
            self.frozen_at,
        )
        if any(not str(value).strip() for value in required_text):
            raise ValueError("Experiment freeze artifact has an empty required field")
        if self.development_window != DEVELOPMENT_WINDOW_VERSION:
            raise ValueError("Experiments must freeze against DEVELOPMENT_WINDOW_V1")
        if self.minimum_sample < 1:
            raise ValueError("minimum_sample must be positive")
        if self.validation_authorized:
            raise ValueError("Freeze artifacts cannot self-authorize validation")

    def with_parameters(self, parameters: Mapping[str, Any]) -> ExperimentFreezeArtifact:
        return replace(self, parameters=parameters)


def experiment_freeze_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "INTERSIGNAL_STRATEGY_EXPERIMENT_FREEZE_V1",
        "title": "Strategy experiment development freeze",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "experiment_id",
            "experiment_version",
            "hypothesis",
            "development_window",
            "parameters",
            "parameter_hash",
            "primary_metric",
            "secondary_metrics",
            "falsification_criteria",
            "promotion_criteria",
            "minimum_sample",
            "baseline_dependencies",
            "development_result_hash",
            "development_freeze_hash",
            "frozen_at",
            "cost_model",
            "validation_authorized",
        ],
        "properties": {
            "experiment_id": {"type": "string", "minLength": 1},
            "experiment_version": {"type": "string", "minLength": 1},
            "hypothesis": {"type": "string", "minLength": 1},
            "development_window": {"const": DEVELOPMENT_WINDOW_VERSION},
            "parameters": {"type": "object"},
            "parameter_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "primary_metric": {"type": "string", "minLength": 1},
            "secondary_metrics": {"type": "array", "items": {"type": "string"}},
            "falsification_criteria": {"type": "array", "minItems": 1},
            "promotion_criteria": {"type": "array", "minItems": 1},
            "minimum_sample": {"type": "integer", "minimum": 1},
            "baseline_dependencies": {"type": "object"},
            "development_result_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "development_freeze_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "frozen_at": {"type": "string", "minLength": 1},
            "cost_model": {"const": "INDIA_EQUITY_COST_MODEL_V1"},
            "validation_authorized": {"const": False},
        },
        "governance": {
            "one_changed_dimension_required": True,
            "validation_authorization_external_to_freeze": True,
            "parameter_change_requires_new_version": True,
            "old_validation_result_remains_immutable": True,
        },
    }

