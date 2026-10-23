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
