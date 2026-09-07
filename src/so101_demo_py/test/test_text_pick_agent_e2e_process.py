from __future__ import annotations

import json
from pathlib import Path
import sys

from launch import LaunchDescription, LaunchService
from launch.actions import ExecuteProcess
import pytest
from so101_demo.runtime.launch_composition import (
    E2ESupervisor,
    _e2e_process_handlers,
)


def _event(
    workflow_id: str,
    sequence: int,
    component: str,
    event: str,
    *,
    status: str = "OK",
    failure_code: str | None = None,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "workflow_id": workflow_id,
        "sequence": sequence,
        "component": component,
        "event": event,
        "status": status,
        "timestamp_ns": "CLOCK",
        "failure_code": failure_code,
        "payload": payload or {},
    }


def _event_process(
    records: list[tuple[float, dict[str, object]]],
    *,
    returncode: int,
    split: bool = False,
) -> ExecuteProcess:
    encoded_records = json.dumps(records, separators=(",", ":"))
    code = (
        "import json,sys,time; "
        f"records=json.loads({encoded_records!r}); "
        "[(time.sleep(delay), record.__setitem__('timestamp_ns',time.time_ns()), "
        "(lambda raw: (sys.stdout.buffer.write(raw[:len(raw)//2]), "
        "sys.stdout.buffer.flush(), time.sleep(0.002), "
        "sys.stdout.buffer.write(raw[len(raw)//2:]), sys.stdout.buffer.flush()))"
        "(('SO101_EVENT '+json.dumps(record,separators=(',',':'))+'\\n').encode())) "
        "for delay,record in records]; "
        f"raise SystemExit({returncode})"
    )
    if not split:
        code = code.replace("time.sleep(0.002)", "time.sleep(0.0)")
    return ExecuteProcess(cmd=[sys.executable, "-c", code], output="both")


def _sleep_process(*, ignore_term: bool = False) -> ExecuteProcess:
    setup = ""
    if ignore_term:
        setup = (
            "signal.signal(signal.SIGINT,signal.SIG_IGN);"
            "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
        )
    code = f"import signal,time;{setup}time.sleep(30)"
    return ExecuteProcess(cmd=[sys.executable, "-c", code], output="both")


def _run_graph(
    tmp_path: Path,
    *,
    text: ExecuteProcess,
    perception: ExecuteProcess,
    validator: ExecuteProcess,
    required: ExecuteProcess,
    patch_supervisor=None,
    acceptance_document: dict[str, object] | None = None,
) -> tuple[int, E2ESupervisor]:
    workflow_id = "process-workflow"
    run_root = tmp_path / "run"
    run_root.mkdir()
    for name in ("perception", "dynamic", "acceptance"):
        (run_root / name).mkdir()
    if acceptance_document is not None:
        (run_root / "acceptance" / "result.json").write_text(
            json.dumps(acceptance_document),
            encoding="utf-8",
        )
    scene = ExecuteProcess(
        cmd=[sys.executable, "-c", "import time;time.sleep(0.03)"],
        output="both",
    )
    supervisor = E2ESupervisor(
        workflow_id=workflow_id,
        request_id="request-1",
        session_id="session-1",
        backend="yolo_seg",
        source_commit="a" * 40,
        installed_prefix="/tmp/install",
        run_root=run_root,
        result_file=run_root / "e2e-result.json",
        text_agent_action=text,
        perception_action=perception,
        validator_action=validator,
    )
    supervisor._RECOVERY_TIMEOUT_S = 0.05
    supervisor._SIGINT_TIMEOUT_S = 0.05
    supervisor._SIGTERM_TIMEOUT_S = 0.05
    supervisor._SIGKILL_TIMEOUT_S = 0.05
    supervisor.register_owned(
        required,
        label="required runtime",
        required_long_lived=True,
        started=True,
    )
    if patch_supervisor is not None:
        patch_supervisor(supervisor)
    handlers = _e2e_process_handlers(
        supervisor,
        scene_setup=scene,
        event_children=(text, perception, validator),
        exit_children=(text, perception, validator, required),
    )
    service = LaunchService(argv=[])
    service.include_launch_description(
        LaunchDescription([*handlers, scene, required])
    )
    return service.run(), supervisor


def _success_processes(workflow_id: str = "process-workflow"):
    text = _event_process(
        [
            (
                0.01,
                _event(
                    workflow_id,
                    1,
                    "text_agent",
                    "DISPATCH_PREVIEW",
                    payload={"request_id": "request-1"},
                ),
            ),
            (
                0.01,
                _event(
                    workflow_id,
                    1,
                    "dynamic_runtime",
                    "RUNTIME_STARTED",
                    payload={
                        "request_id": "request-1",
                        "session_id": "session-1",
                        "reset_epoch": 0,
                    },
                ),
            ),
            (
                0.01,
                _event(
                    workflow_id,
                    2,
                    "dynamic_runtime",
                    "RUNTIME_READY",
                    payload={
                        "request_id": "request-1",
                        "session_id": "session-1",
                        "reset_epoch": 0,
                    },
                ),
            ),
            (
                0.80,
                _event(
                    workflow_id,
                    3,
                    "dynamic_runtime",
                    "RUNTIME_COMPLETED",
                    payload={
                        "manifest_path": "/tmp/manifest.json",
                        "runtime_exit_code": 0,
                    },
                ),
            ),
        ],
        returncode=0,
        split=True,
    )
    perception = _event_process(
        [
            (0.01, _event(workflow_id, 1, "perception", "PERCEPTION_READY")),
            (
                0.01,
                _event(
                    workflow_id,
                    2,
                    "perception",
                    "TARGET_SELECTED",
                    payload={"target_id": "cup", "class_name": "plastic_cup"},
                ),
            ),
            (
                0.01,
                _event(
                    workflow_id,
                    3,
                    "perception",
                    "CUP_POSE_PUBLISHED",
                    payload={"source_stamp_ns": 1, "frame_id": "world"},
                ),
            ),
        ],
        returncode=0,
        split=True,
    )
    validator = _event_process(
        [
            (
                0.01,
                _event(
                    workflow_id,
                    1,
                    "e2e_validator",
                    "E2E_ACCEPTED",
                    payload={"result_path": "/tmp/acceptance.json"},
                ),
            )
        ],
        returncode=0,
        split=True,
    )
    return text, perception, validator


def test_real_launch_service_accepts_only_after_owned_cleanup(tmp_path: Path) -> None:
    text, perception, validator = _success_processes()
    returncode, supervisor = _run_graph(
        tmp_path,
        text=text,
        perception=perception,
        validator=validator,
        required=_sleep_process(),
    )
    assert returncode == 0
    result = json.loads(supervisor.result_file.read_text(encoding="utf-8"))
    assert result["machine_accepted"] is True
    assert result["owned_process_cleanup"]["complete"] is True
    assert result["primary_failure"] is None


def test_real_launch_service_preserves_failure_before_child_exit(tmp_path: Path) -> None:
    text = _event_process(
        [
            (
                0.0,
                _event(
                    "process-workflow",
                    1,
                    "text_agent",
                    "PLANNER_FAILED",
                    status="ERROR",
                    failure_code="PLANNER_CHAIN_FAILED",
                ),
            )
        ],
        returncode=7,
        split=True,
    )
    inert = _event_process([], returncode=0)
    returncode, supervisor = _run_graph(
        tmp_path,
        text=text,
        perception=inert,
        validator=_event_process([], returncode=0),
        required=_sleep_process(),
    )
    assert returncode != 0
    assert supervisor.primary_failure["code"] == "PLANNER_CHAIN_FAILED"


def test_real_launch_service_rejects_truncated_event_at_eof(tmp_path: Path) -> None:
    text = ExecuteProcess(
        cmd=[
            sys.executable,
            "-c",
            "import sys;sys.stdout.write('SO101_EVENT {');sys.stdout.flush();raise SystemExit(4)",
        ],
        output="both",
    )
    returncode, supervisor = _run_graph(
        tmp_path,
        text=text,
        perception=_event_process([], returncode=0),
        validator=_event_process([], returncode=0),
        required=_sleep_process(),
    )
    assert returncode != 0
    assert supervisor.primary_failure["code"] == "EVENT_PROTOCOL_INVALID"


def test_real_launch_service_fails_when_required_child_exits_zero(tmp_path: Path) -> None:
    text, perception, validator = _success_processes()
    required = ExecuteProcess(cmd=[sys.executable, "-c", "pass"], output="both")
    returncode, supervisor = _run_graph(
        tmp_path,
        text=text,
        perception=perception,
        validator=validator,
        required=required,
    )
    assert returncode != 0
    assert supervisor.primary_failure["code"] == "REQUIRED_PROCESS_EXITED"


def test_real_launch_service_signal_escalation_makes_acceptance_nonzero(
    tmp_path: Path,
) -> None:
    text, perception, validator = _success_processes()
    returncode, supervisor = _run_graph(
        tmp_path,
        text=text,
        perception=perception,
        validator=validator,
        required=_sleep_process(ignore_term=True),
    )
    assert returncode != 0
    assert supervisor.accepted is True
    assert supervisor.primary_failure["code"] == "OWNED_PROCESS_CLEANUP_TIMEOUT"


def test_real_launch_service_evidence_write_error_is_nonzero(tmp_path: Path) -> None:
    text, perception, validator = _success_processes()

    def reject_writes(supervisor):
        def fail(_path, _data):
            raise OSError("injected write failure")

        supervisor._atomic_write = fail

    returncode, supervisor = _run_graph(
        tmp_path,
        text=text,
        perception=perception,
        validator=validator,
        required=_sleep_process(),
        patch_supervisor=reject_writes,
    )
    assert returncode != 0
    assert supervisor.primary_failure["code"] == "EVIDENCE_WRITE_FAILED"


@pytest.mark.parametrize(
    ("failure_code", "acceptance_document"),
    (
        (
            "E2E_MUJOCO_FINAL_INVALID",
            {
                "accepted": False,
                "failures": ["E2E_MUJOCO_FINAL_INVALID"],
                "physical_outcome": {"stable": False},
                "planning_scene_outcome": {},
            },
        ),
        (
            "E2E_PLANNING_SCENE_INVALID",
            {
                "accepted": False,
                "failures": ["E2E_PLANNING_SCENE_INVALID"],
                "physical_outcome": {"stable": True},
                "planning_scene_outcome": {
                    "attached_object_ids": ["cup"],
                    "pose_matches_mujoco": True,
                },
            },
        ),
    ),
)
def test_real_launch_service_rejects_invalid_physical_or_scene_evidence(
    tmp_path: Path,
    failure_code: str,
    acceptance_document: dict[str, object],
) -> None:
    text, perception, _validator = _success_processes()
    validator = _event_process(
        [
            (
                0.01,
                _event(
                    "process-workflow",
                    1,
                    "e2e_validator",
                    "E2E_REJECTED",
                    status="ERROR",
                    failure_code=failure_code,
                    payload={"result_path": "/tmp/acceptance.json"},
                ),
            )
        ],
        returncode=1,
        split=True,
    )
    returncode, supervisor = _run_graph(
        tmp_path,
        text=text,
        perception=perception,
        validator=validator,
        required=_sleep_process(),
        acceptance_document=acceptance_document,
    )
    assert returncode != 0
    assert supervisor.primary_failure["code"] == failure_code
    result = json.loads(supervisor.result_file.read_text(encoding="utf-8"))
    assert result["runtime_exit_code"] == 0
    assert result["machine_accepted"] is False
    assert result["physical_outcome"] == acceptance_document["physical_outcome"]
    assert result["planning_scene_outcome"] == acceptance_document[
        "planning_scene_outcome"
    ]


def test_out_of_order_cross_child_event_fails_without_reordering(tmp_path: Path) -> None:
    text, _perception, validator = _success_processes()
    perception = _event_process(
        [
            (0.01, _event("process-workflow", 1, "perception", "PERCEPTION_READY")),
            (
                1.20,
                _event(
                    "process-workflow",
                    2,
                    "perception",
                    "TARGET_SELECTED",
                    payload={"target_id": "cup", "class_name": "plastic_cup"},
                ),
            ),
        ],
        returncode=0,
    )
    returncode, supervisor = _run_graph(
        tmp_path,
        text=text,
        perception=perception,
        validator=validator,
        required=_sleep_process(),
    )
    assert returncode != 0
    assert supervisor.primary_failure["code"] == "EVENT_PROTOCOL_INVALID"
