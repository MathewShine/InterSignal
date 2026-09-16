from __future__ import annotations

from app.platform.models import StrategyLifecycle


class InvalidLifecycleTransition(ValueError):
    pass


_TERMINAL_OR_BLOCKING = frozenset(
    {
        StrategyLifecycle.REJECTED,
        StrategyLifecycle.DATA_BLOCKED,
        StrategyLifecycle.SOURCE_BLOCKED,
    }
)

ALLOWED_TRANSITIONS: dict[StrategyLifecycle, frozenset[StrategyLifecycle]] = {
    StrategyLifecycle.IDEA: frozenset(
        {StrategyLifecycle.PREREGISTERED, StrategyLifecycle.PAUSED}
    )
    | _TERMINAL_OR_BLOCKING,
    StrategyLifecycle.PREREGISTERED: frozenset(
        {StrategyLifecycle.DEVELOPMENT_EVALUATED, StrategyLifecycle.PAUSED}
    )
    | _TERMINAL_OR_BLOCKING,
    StrategyLifecycle.DEVELOPMENT_EVALUATED: frozenset(
        {StrategyLifecycle.VALIDATION_CANDIDATE, StrategyLifecycle.PAUSED}
    )
    | _TERMINAL_OR_BLOCKING,
    StrategyLifecycle.VALIDATION_CANDIDATE: frozenset(
        {StrategyLifecycle.VALIDATION_EVALUATED, StrategyLifecycle.PAUSED}
    )
    | _TERMINAL_OR_BLOCKING,
    StrategyLifecycle.VALIDATION_EVALUATED: frozenset(
        {StrategyLifecycle.PRODUCTION_CANDIDATE, StrategyLifecycle.PAUSED}
    )
    | _TERMINAL_OR_BLOCKING,
    StrategyLifecycle.PAUSED: frozenset(_TERMINAL_OR_BLOCKING),
    StrategyLifecycle.REJECTED: frozenset({StrategyLifecycle.PAUSED}),
    StrategyLifecycle.DATA_BLOCKED: frozenset(
        {StrategyLifecycle.PAUSED, StrategyLifecycle.REJECTED}
    ),
    StrategyLifecycle.SOURCE_BLOCKED: frozenset(
        {StrategyLifecycle.PAUSED, StrategyLifecycle.REJECTED}
    ),
    StrategyLifecycle.PRODUCTION_CANDIDATE: frozenset(
        {StrategyLifecycle.PAUSED, StrategyLifecycle.REJECTED}
    ),
}


def validate_transition(
    previous: StrategyLifecycle, new: StrategyLifecycle
) -> None:
    if new == previous:
        raise InvalidLifecycleTransition(
            f"Lifecycle state is already {previous.value}; no transition recorded"
        )
    if new not in ALLOWED_TRANSITIONS[previous]:
        raise InvalidLifecycleTransition(
            f"Invalid strategy lifecycle transition: {previous.value} -> {new.value}"
        )


__all__ = ("ALLOWED_TRANSITIONS", "InvalidLifecycleTransition", "validate_transition")
