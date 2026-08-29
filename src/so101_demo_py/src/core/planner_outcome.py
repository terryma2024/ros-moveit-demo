from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from .task_command import (
    TASK_COMMAND_JSON_SCHEMA,
    CommandValidationError,
    TaskCommand,
    validate_task_command,
)


class PlannerOutcomeKind(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    AMBIGUOUS = "ambiguous"


PLANNER_OUTCOME_JSON_SCHEMA: Final[dict[str, object]] = {
    "oneOf": [
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["outcome", "command"],
            "properties": {
                "outcome": {"type": "string", "const": "supported"},
                "command": TASK_COMMAND_JSON_SCHEMA,
            },
        },
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["outcome"],
            "properties": {
                "outcome": {"type": "string", "const": "unsupported"},
            },
        },
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["outcome"],
            "properties": {
                "outcome": {"type": "string", "const": "ambiguous"},
            },
        },
    ]
}


@dataclass(frozen=True, slots=True)
class PlannerOutcome:
    kind: PlannerOutcomeKind
    command: TaskCommand | None


def validate_planner_outcome(value: object) -> PlannerOutcome:
    if not isinstance(value, dict):
        raise CommandValidationError("planner outcome must be an object")
    if value.get("outcome") == PlannerOutcomeKind.SUPPORTED.value:
        if set(value) != {"outcome", "command"}:
            raise CommandValidationError("supported outcome fields are invalid")
        return PlannerOutcome(
            PlannerOutcomeKind.SUPPORTED,
            validate_task_command(value["command"]),
        )
    if value.get("outcome") == PlannerOutcomeKind.UNSUPPORTED.value:
        if set(value) != {"outcome"}:
            raise CommandValidationError("unsupported outcome fields are invalid")
        return PlannerOutcome(PlannerOutcomeKind.UNSUPPORTED, None)
    if value.get("outcome") == PlannerOutcomeKind.AMBIGUOUS.value:
        if set(value) != {"outcome"}:
            raise CommandValidationError("ambiguous outcome fields are invalid")
        return PlannerOutcome(PlannerOutcomeKind.AMBIGUOUS, None)
    raise CommandValidationError("planner outcome is invalid")
