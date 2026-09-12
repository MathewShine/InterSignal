from __future__ import annotations

from dataclasses import dataclass

from app.research.temporal_validation.config import (
    AUTHORIZED_TO_EVALUATE,
    DEVELOPMENT_RUN,
    EVALUATED,
    REPRODUCTION_RUN,
    SEALED,
    VALIDATION_RUN,
    canonical_hash,
)
from app.research.temporal_validation.models import ExperimentFreezeArtifact


class ValidationAccessError(PermissionError):
    """Raised when sealed or one-shot validation governance rejects access."""


@dataclass(frozen=True, slots=True)
class ValidationAuthorization:
    experiment_id: str
    experiment_version: str
    development_freeze_hash: str
    authorization_reference: str
    authorization_token: str


@dataclass(slots=True)
class ValidationAccessGuard:
    state: str = SEALED
    validation_run_count: int = 0
    maximum_validation_run_count: int = 1
    authorized_freeze_hash: str | None = None
    authorization_token: str | None = None
    immutable_result_hash: str | None = None
    active_run_mode: str | None = None

    def authorize_validation(
        self,
        artifact: ExperimentFreezeArtifact,
        *,
        supplied_freeze_hash: str,
        explicit_user_authorized: bool,
        authorization_reference: str,
    ) -> ValidationAuthorization:
        artifact.validate()
        expected = artifact.development_freeze_hash()
        if not explicit_user_authorized:
            raise ValidationAccessError("Explicit user authorization is required")
        if supplied_freeze_hash != expected:
            raise ValidationAccessError("Development freeze hash mismatch")
        if self.state != SEALED or self.validation_run_count:
            raise ValidationAccessError("Validation cannot be authorized from the current state")
        if not authorization_reference.strip():
            raise ValidationAccessError("An auditable authorization reference is required")
        token = canonical_hash(
            {
                "experiment_id": artifact.experiment_id,
                "experiment_version": artifact.experiment_version,
                "development_freeze_hash": expected,
                "authorization_reference": authorization_reference,
            }
        )
        self.state = AUTHORIZED_TO_EVALUATE
        self.authorized_freeze_hash = expected
        self.authorization_token = token
        return ValidationAuthorization(
            experiment_id=artifact.experiment_id,
            experiment_version=artifact.experiment_version,
            development_freeze_hash=expected,
            authorization_reference=authorization_reference,
            authorization_token=token,
        )

    def require_validation_access(
        self,
        artifact: ExperimentFreezeArtifact,
        authorization: ValidationAuthorization | None,
    ) -> None:
        artifact.validate()
        if self.state == SEALED:
            raise ValidationAccessError("VALIDATION_WINDOW_V1 is SEALED")
        if artifact.development_freeze_hash() != self.authorized_freeze_hash:
            raise ValidationAccessError("Frozen experiment definition changed after authorization")
        if self.active_run_mode == VALIDATION_RUN and self.state == AUTHORIZED_TO_EVALUATE:
            if authorization is None or authorization.authorization_token != self.authorization_token:
                raise ValidationAccessError("Valid authorization token required")
            return
        if self.active_run_mode == REPRODUCTION_RUN and self.state == EVALUATED:
            return
        raise ValidationAccessError("Validation access requires an active authorized run")

    def _verify_authorization(
        self,
        artifact: ExperimentFreezeArtifact,
        authorization: ValidationAuthorization | None,
    ) -> None:
        artifact.validate()
        if self.state == SEALED:
            raise ValidationAccessError("VALIDATION_WINDOW_V1 is SEALED")
        if self.state != AUTHORIZED_TO_EVALUATE:
            raise ValidationAccessError("Validation performance is not available in the current state")
        if authorization is None or authorization.authorization_token != self.authorization_token:
            raise ValidationAccessError("Valid authorization token required")
        if artifact.development_freeze_hash() != self.authorized_freeze_hash:
            raise ValidationAccessError("Frozen experiment definition changed after authorization")

    def begin_run(
        self,
        mode: str,
        *,
        artifact: ExperimentFreezeArtifact | None = None,
        authorization: ValidationAuthorization | None = None,
        expected_result_hash: str | None = None,
    ) -> None:
        if mode == DEVELOPMENT_RUN:
            return
        if artifact is None:
            raise ValidationAccessError("A frozen experiment artifact is required")
        if mode == VALIDATION_RUN:
            self._verify_authorization(artifact, authorization)
            if self.validation_run_count >= self.maximum_validation_run_count:
                raise ValidationAccessError("One-shot validation limit reached")
            self.validation_run_count += 1
            self.active_run_mode = VALIDATION_RUN
            return
        if mode == REPRODUCTION_RUN:
            if self.state != EVALUATED or self.validation_run_count != 1:
                raise ValidationAccessError("Reproduction requires one completed validation")
            if artifact.development_freeze_hash() != self.authorized_freeze_hash:
                raise ValidationAccessError("Reproduction parameters differ from the frozen definition")
            if expected_result_hash != self.immutable_result_hash:
                raise ValidationAccessError("Reproduction must target the immutable validation result")
            self.active_run_mode = REPRODUCTION_RUN
            return
        raise ValueError(f"Unsupported experiment run mode: {mode}")

    def record_validation_result(self, result_hash: str) -> None:
        if (
            self.state != AUTHORIZED_TO_EVALUATE
            or self.validation_run_count != 1
            or self.active_run_mode != VALIDATION_RUN
        ):
            raise ValidationAccessError("No authorized validation run is awaiting a result")
        if not result_hash:
            raise ValueError("Validation result hash is required")
        if self.immutable_result_hash not in (None, result_hash):
            raise ValidationAccessError("Validation result is immutable")
        self.immutable_result_hash = result_hash
        self.state = EVALUATED
        self.active_run_mode = None
