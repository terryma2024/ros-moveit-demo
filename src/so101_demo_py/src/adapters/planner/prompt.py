import json

from ...core.planner_outcome import PLANNER_OUTCOME_JSON_SCHEMA
from ...ports.task_planner import PlannerProviderError

PLANNER_SYSTEM_PROMPT = (
    "Classify the instruction, then return one JSON object matching this schema. "
    "Use outcome=unsupported for negated or unsupported requests. "
    "Use outcome=ambiguous for conflicting, conditional, uncertain, or underspecified requests. "
    "Only outcome=supported may carry command, and it must be an affirmative unambiguous pick "
    "of the plastic cup. Normalize 杯子 or 水杯 to plastic_cup. "
    "Never emit coordinates, poses, joints, trajectories, shell commands, ROS names, or execution authorization. "
    f"JSON schema: {json.dumps(PLANNER_OUTCOME_JSON_SCHEMA, ensure_ascii=False, sort_keys=True)}"
)


def decode_candidate(content: object) -> object:
    if not isinstance(content, str) or not content.strip():
        raise PlannerProviderError("PROVIDER_CONTENT_EMPTY")
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        raise PlannerProviderError("PROVIDER_JSON_INVALID") from None
