import json

from ...core.task_command import TASK_COMMAND_JSON_SCHEMA
from ...ports.task_planner import PlannerProviderError

PLANNER_SYSTEM_PROMPT = (
    "Return one JSON object matching this schema. Normalize 杯子 or 水杯 to plastic_cup. "
    "Never emit coordinates, poses, joints, trajectories, shell commands, ROS names, or execution authorization. "
    f"JSON schema: {json.dumps(TASK_COMMAND_JSON_SCHEMA, ensure_ascii=False, sort_keys=True)}"
)


def decode_candidate(content: object) -> object:
    if not isinstance(content, str) or not content.strip():
        raise PlannerProviderError("PROVIDER_CONTENT_EMPTY")
    try:
        return json.loads(content)
    except json.JSONDecodeError as error:
        raise PlannerProviderError("PROVIDER_JSON_INVALID") from None
