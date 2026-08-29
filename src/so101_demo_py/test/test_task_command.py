import pytest

from so101_demo.core.task_command import (
    CommandValidationError,
    TaskCommand,
    validate_instruction,
    validate_task_command,
)


def test_valid_candidate_becomes_immutable_task_command() -> None:
    command = validate_task_command(
        {"target_object": "plastic_cup", "action": "pick", "constraints": {}}
    )
    assert command == TaskCommand("plastic_cup", "pick", ())
    assert command.to_dict() == {
        "target_object": "plastic_cup",
        "action": "pick",
        "constraints": {},
    }
    with pytest.raises(AttributeError):
        command.action = "place"


@pytest.mark.parametrize(
    "candidate",
    [
        {},
        {"target_object": "plastic_cup", "action": "pick"},
        {"target_object": "plastic_cup", "action": "pick", "constraints": {}, "x": 0.1},
        {"target_object": "metal_cup", "action": "pick", "constraints": {}},
        {"target_object": 1, "action": "pick", "constraints": {}},
        {"target_object": "plastic_cup", "action": 1, "constraints": {}},
        {"target_object": "plastic_cup", "action": "place", "constraints": {}},
        {"target_object": "plastic_cup", "action": "pick", "constraints": {"speed": 0.2}},
        {"target_object": "plastic_cup", "action": "pick", "constraints": {"x": "left"}},
        [{"target_object": "plastic_cup", "action": "pick", "constraints": {}}],
    ],
)
def test_invalid_candidates_fail_closed(candidate: object) -> None:
    with pytest.raises(CommandValidationError):
        validate_task_command(candidate)


def test_instruction_is_single_nonempty_bounded_string() -> None:
    assert validate_instruction("  帮我拿杯子  ") == "帮我拿杯子"
    assert validate_instruction("你" * 200) == "你" * 200
    for invalid in (None, "", "   ", "你" * 201):
        with pytest.raises(CommandValidationError):
            validate_instruction(invalid)
