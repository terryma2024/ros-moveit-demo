from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pytest
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.utilities import perform_substitutions
from so101_demo.runtime import launch_composition
from so101_demo.runtime.provenance import InstalledExecutionIdentity

from launch import LaunchContext


PACKAGE_ROOT = Path(__file__).parents[1]
LAUNCH_PATH = PACKAGE_ROOT / "launch/so101_mujoco_text_pick_agent.launch.py"
INSTRUCTION = "Pick the plastic cup. Apply no constraints."


def _builder():
    assert hasattr(launch_composition, "build_text_pick_agent_launch_description"), (
        "dedicated text-agent launch builder is missing"
    )
    return launch_composition.build_text_pick_agent_launch_description


def _declared(description) -> dict[str, DeclareLaunchArgument]:
    return {
        action.name: action
        for action in description.entities
        if isinstance(action, DeclareLaunchArgument)
    }


def _default(argument: DeclareLaunchArgument) -> str:
    return perform_substitutions(LaunchContext(), argument.default_value)


def _materialize(monkeypatch, tmp_path: Path, **overrides):
    monkeypatch.setattr(
        launch_composition,
        "resolve_installed_execution_identity",
        lambda: InstalledExecutionIdentity(
            source_commit="a" * 40,
            package_prefix="/tmp/so101-text-agent-install",
        ),
    )
    exit_status = launch_composition.PerceptionLaunchExitStatus()
    description = _builder()(exit_status)
    declared = _declared(description)
    context = LaunchContext()
    for name, argument in declared.items():
        if argument.default_value is not None:
            context.launch_configurations[name] = perform_substitutions(
                context, argument.default_value
            )
    context.launch_configurations.update(
        {
            "instruction": INSTRUCTION,
            "run_mode": "execute",
            "execute": "true",
            "skip_confirmation": "true",
            "session_id": "text-e2e-session-001",
            "evidence_file": str(tmp_path / "run.json"),
            **{key: str(value) for key, value in overrides.items()},
        }
    )
    opaque = next(entity for entity in description.entities if isinstance(entity, OpaqueFunction))
    return context, opaque.execute(context), exit_status


def test_public_text_agent_launch_is_thin_and_declares_contract() -> None:
    description = _builder()()
    declared = _declared(description)

    assert set(declared) == {
        "instruction",
        "run_mode",
        "execute",
        "skip_confirmation",
        "headless",
        "sensor_rendering",
        "session_id",
        "evidence_file",
        "readiness_timeout_s",
        "mujoco_scene",
        "mujoco_initial_keyframe",
        "perception_startup_timeout_s",
        "cup_pose_timeout_s",
    }
    assert declared["instruction"].default_value is None
    assert _default(declared["run_mode"]) == "dry_run"
    assert _default(declared["execute"]) == "false"
    assert _default(declared["skip_confirmation"]) == "false"
    assert _default(declared["headless"]) == "false"
    assert _default(declared["sensor_rendering"]) == "true"
    assert _default(declared["mujoco_initial_keyframe"]) == "task_start"
    assert _default(declared["perception_startup_timeout_s"]) == "30.0"
    assert _default(declared["cup_pose_timeout_s"]) == "45.0"

    assert LAUNCH_PATH.is_file()
    source = LAUNCH_PATH.read_text(encoding="utf-8")
    assert "DeclareLaunchArgument" not in source
    assert "build_text_pick_agent_launch_description" in source
    spec = importlib.util.spec_from_file_location("text_agent_launch", LAUNCH_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.generate_launch_description() is not None


@pytest.mark.parametrize(
    ("overrides", "message"),
    (
        ({"instruction": ""}, "instruction"),
        ({"run_mode": "dry_run"}, "run_mode=execute"),
        ({"execute": "false"}, "execute:=true"),
        ({"skip_confirmation": "false"}, "skip_confirmation:=true"),
        ({"sensor_rendering": "false"}, "sensor_rendering=true"),
        ({"headless": "sometimes"}, "headless"),
        ({"mujoco_initial_keyframe": "unknown"}, "initial keyframe"),
        ({"readiness_timeout_s": "0"}, "readiness_timeout_s"),
        ({"perception_startup_timeout_s": math.inf}, "perception_startup_timeout_s"),
        ({"cup_pose_timeout_s": "nan"}, "cup_pose_timeout_s"),
        ({"session_id": "../escape"}, "session_id"),
        ({"evidence_file": "relative.json"}, "evidence_file"),
        ({"mujoco_scene": "relative.xml"}, "mujoco_scene"),
    ),
)
def test_invalid_text_agent_inputs_fail_before_nodes_or_evidence(
    tmp_path: Path,
    monkeypatch,
    overrides: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(RuntimeError, match=message):
        _materialize(monkeypatch, tmp_path, **overrides)
    assert not (tmp_path / "run.d").exists()


def test_valid_preflight_creates_exclusive_session_evidence_directories(
    tmp_path: Path, monkeypatch
) -> None:
    _context, actions, _exit_status = _materialize(monkeypatch, tmp_path)

    run_root = tmp_path / "run.d/text-e2e-session-001"
    assert run_root.is_dir()
    assert run_root.stat().st_mode & 0o777 == 0o700
    assert (run_root / "perception").is_dir()
    assert (run_root / "dynamic").is_dir()
    assert isinstance(actions, list)
