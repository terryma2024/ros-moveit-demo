from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

TargetObject = Literal["plastic_cup"]
TaskAction = Literal["pick"]

TASK_COMMAND_JSON_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["target_object", "action", "constraints"],
    "properties": {
        "target_object": {"type": "string", "enum": ["plastic_cup"]},
        "action": {"type": "string", "enum": ["pick"]},
        "constraints": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "spatial_relation": {
                    "type": "string",
                    "enum": ["left", "right", "center", "nearest"],
                },
                "speed": {"type": "string", "enum": ["slow", "normal"]},
            },
        },
    },
}


class CommandValidationError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.code = "COMMAND_INVALID"
        self.reason = reason


@dataclass(frozen=True, slots=True)
class TaskCommand:
    target_object: TargetObject
    action: TaskAction
    constraints: tuple[tuple[str, str], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "target_object": self.target_object,
            "action": self.action,
            "constraints": dict(self.constraints),
        }


def validate_instruction(value: object, max_chars: int = 200) -> str:
    if not isinstance(value, str):
        raise CommandValidationError("instruction must be a string")
    instruction = value.strip()
    if not instruction or len(instruction) > max_chars:
        raise CommandValidationError("instruction length is invalid")
    return instruction


def validate_task_command(candidate: object) -> TaskCommand:
    if not isinstance(candidate, dict) or set(candidate) != {
        "target_object",
        "action",
        "constraints",
    }:
        raise CommandValidationError("top-level fields are invalid")
    if (
        not isinstance(candidate["target_object"], str)
        or not isinstance(candidate["action"], str)
        or candidate["target_object"] != "plastic_cup"
        or candidate["action"] != "pick"
    ):
        raise CommandValidationError("object or action is unsupported")
    constraints = candidate["constraints"]
    if not isinstance(constraints, dict):
        raise CommandValidationError("constraints must be an object")
    allowed = {
        "spatial_relation": {"left", "right", "center", "nearest"},
        "speed": {"slow", "normal"},
    }
    for key, value in constraints.items():
        if key not in allowed or not isinstance(value, str) or value not in allowed[key]:
            raise CommandValidationError("constraint is unsupported")
    return TaskCommand("plastic_cup", "pick", tuple(sorted(constraints.items())))
