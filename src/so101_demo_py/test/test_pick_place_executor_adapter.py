from __future__ import annotations

import builtins
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from so101_demo.adapters.pick_place_executor import (
    DynamicCupPickPlaceExecutor,
    DynamicRuntimeContext,
)
from so101_demo.ports.pick_place_executor import (
    DynamicCupPickPlaceRequest,
    ExecutorDispatchError,
)


def _context(tmp_path: Path) -> DynamicRuntimeContext:
    return DynamicRuntimeContext(
        session_id="text-agent-session",
        expected_reset_epoch=3,
        evidence_root=tmp_path,
        source_commit="e58eee1",
        installed_prefix="/data/work/ws_moveit/install/so101_demo_py",
    )


def _request(**changes: object) -> DynamicCupPickPlaceRequest:
    values: dict[str, object] = {
        "request_id": "req-001",
        "capability": "dynamic_cup_pick_place",
        "backend": "mujoco",
        "scene_source": "observe_only",
        "target_object": "plastic_cup",
        "action": "pick",
    }
    values.update(changes)
    return DynamicCupPickPlaceRequest(**values)  # type: ignore[arg-type]


def test_context_is_frozen_and_adapter_calls_runner_once_with_only_whitelisted_options(
    tmp_path: Path,
) -> None:
    calls: list[object] = []
    context = _context(tmp_path)
    executor = DynamicCupPickPlaceExecutor(
        context,
        runner=lambda options: calls.append(options) or 0,
    )

    with pytest.raises(FrozenInstanceError):
        context.session_id = "replacement"  # type: ignore[misc]

    result = executor.dispatch(_request())

    assert result.exit_code == 0
    assert result.runtime_session_id == "text-agent-session"
    assert len(calls) == 1
    options = calls[0]
    assert vars(options) == {
        "backend": "mujoco",
        "mode": "execute",
        "execute": True,
        "scene_source": "observe_only",
        "dynamic_policy": None,
        "cup_pose_timeout_s": 5.0,
        "source_commit": "e58eee1",
        "installed_prefix": "/data/work/ws_moveit/install/so101_demo_py",
        "session_id": "text-agent-session",
        "expected_reset_epoch": 3,
        "evidence_root": tmp_path,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"capability": "arbitrary_provider_capability"},
        {"backend": "gazebo"},
        {"scene_source": "provider_scene"},
        {"target_object": "metal_cup"},
        {"action": "place"},
    ],
)
def test_invalid_typed_request_is_rejected_without_runner_or_ros_import(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    changes: dict[str, str],
) -> None:
    calls: list[object] = []
    real_import = builtins.__import__

    def reject_rclpy(name: str, *args: object, **kwargs: object):
        if name == "rclpy" or name.startswith("rclpy."):
            raise AssertionError("rclpy must not be imported for rejected dispatch")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_rclpy)
    executor = DynamicCupPickPlaceExecutor(
        _context(tmp_path),
        runner=lambda options: calls.append(options) or 0,
    )

    result = executor.dispatch(_request(**changes))

    assert result.exit_code == 1
    assert result.runtime_session_id == "text-agent-session"
    assert calls == []


def test_preview_path_never_imports_ros_or_dispatches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from so101_demo.application.text_agent import AgentRequest, TextAgent
    from so101_demo.ports.task_planner import PlannerCandidate, PlannerMetadata

    real_import = builtins.__import__

    def reject_rclpy(name: str, *args: object, **kwargs: object):
        if name == "rclpy" or name.startswith("rclpy."):
            raise AssertionError("rclpy must not be imported for preview")
        return real_import(name, *args, **kwargs)

    class Planner:
        def plan(self, instruction: str) -> PlannerCandidate:
            return PlannerCandidate(
                {"target_object": "plastic_cup", "action": "pick", "constraints": {}},
                PlannerMetadata("test", "test", 0, None, None, None, False),
            )

    monkeypatch.setattr(builtins, "__import__", reject_rclpy)
    agent = TextAgent(Planner(), DynamicCupPickPlaceExecutor(_context(tmp_path)))

    result = agent.handle(
        AgentRequest("req-preview", "帮我拿杯子", "preview", False, "mujoco")
    )

    assert result.dispatch is False
    assert result.runtime_session_id is None


def test_runner_exception_becomes_stable_redacted_executor_error(tmp_path: Path) -> None:
    def runner(_options: object) -> int:
        raise RuntimeError("secret endpoint https://token.example/internal")

    executor = DynamicCupPickPlaceExecutor(_context(tmp_path), runner=runner)

    with pytest.raises(ExecutorDispatchError) as captured:
        executor.dispatch(_request())

    assert captured.value.code == "DYNAMIC_RUNTIME_EXCEPTION"
    assert str(captured.value) == "DYNAMIC_RUNTIME_EXCEPTION"
    assert "secret" not in str(captured.value)
    assert "token.example" not in str(captured.value)
    assert captured.value.__cause__ is None
    assert captured.value.__suppress_context__ is True


@pytest.mark.parametrize("runner_result", [True, False, "0", 0.0, None])
def test_runner_result_must_be_an_exact_integer(
    tmp_path: Path,
    runner_result: object,
) -> None:
    executor = DynamicCupPickPlaceExecutor(
        _context(tmp_path),
        runner=lambda _options: runner_result,
    )

    with pytest.raises(ExecutorDispatchError) as captured:
        executor.dispatch(_request())

    assert captured.value.code == "DYNAMIC_RUNTIME_RESULT_INVALID"
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
