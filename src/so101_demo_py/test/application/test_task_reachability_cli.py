import json

from so101_demo.application.task_reachability import (
    ReachabilityReport,
    ReachabilityStatus,
)
from so101_demo.cli.task_reachability import (
    build_parser,
    result_document,
    result_exit_code,
)


def _report(status: ReachabilityStatus) -> ReachabilityReport:
    return ReachabilityReport(
        point_id="task_start",
        status=status,
        segments=(),
        first_failure_code=None if status is ReachabilityStatus.REACHABLE else "FAILED",
        scene_revision=7,
    )


def test_parser_requires_points_policy_session_and_evidence() -> None:
    options = build_parser().parse_args(
        [
            "--points",
            "points.yaml",
            "--policy",
            "policy.yaml",
            "--session-id",
            "sim-a",
            "--evidence-file",
            "reachability.json",
            "--point-id",
            "task_start",
        ]
    )

    assert options.point_id == "task_start"
    assert options.session_id == "sim-a"


def test_result_envelope_and_exit_codes_are_stable() -> None:
    reachable = _report(ReachabilityStatus.REACHABLE)
    unreachable = _report(ReachabilityStatus.UNREACHABLE)
    unknown = _report(ReachabilityStatus.UNKNOWN)

    assert json.loads(json.dumps(result_document((reachable,)))) == {
        "status": "SUCCEEDED",
        "reports": [
            {
                "point_id": "task_start",
                "status": "REACHABLE",
                "segments": [],
                "first_failure_code": None,
                "scene_revision": 7,
            }
        ],
    }
    assert result_exit_code((reachable,)) == 0
    assert result_exit_code((reachable, unreachable)) == 2
    assert result_exit_code((reachable, unknown)) == 1


# ---- R3-a: the filter runs against the per-episode targets of a schema 6 policy ---------------------------------------------------

def test_parser_takes_an_optional_teacher_execution_policy() -> None:
    base = ["--points", "p.json", "--policy", "q.yaml", "--session-id", "s", "--evidence-file", "e.json"]
    assert build_parser().parse_args(base).teacher_execution_policy is None
    assert build_parser().parse_args([*base, "--teacher-execution-policy", "t.yaml"]).teacher_execution_policy.name == "t.yaml"


def test_per_point_inputs_are_the_template_of_the_episode_and_its_via_offset() -> None:
    from pathlib import Path

    from so101_demo.act.teacher_endpoint import load_teacher_execution_policy
    from so101_demo.cli.task_reachability import episode_check_inputs
    from test_dynamic_pick import _template
    from paths import PACKAGE_ROOT

    policy = load_teacher_execution_policy(PACKAGE_ROOT / "config/act/teacher_execution_policy_side_wrist_diversity.yaml")
    template = _template()
    plain_template, plain_offset, plain_values = episode_check_inputs(template, None, "act-0001")
    assert plain_template is template and plain_offset is None and plain_values is None        # no schema 6 policy: nothing changes
    schema5 = load_teacher_execution_policy(PACKAGE_ROOT / "config/act/teacher_execution_policy_side_wrist_fast_two_leg_open_1s.yaml")
    assert episode_check_inputs(template, schema5, "act-0001")[0] is template
    episode_template, offset, values = episode_check_inputs(template, policy, "act-0001")
    assert values["scene_id"] == "act-0001" and offset == tuple(values["carry_via_offset_m"])
    assert episode_template.pregrasp_world_z_clearance_m == template.pregrasp_world_z_clearance_m + values["pregrasp_height_offset_m"]
    again = episode_check_inputs(template, policy, "act-0001")
    assert again[1] == offset and again[2] == values                                           # deterministic
    assert episode_check_inputs(template, policy, "act-0002")[2] != values
