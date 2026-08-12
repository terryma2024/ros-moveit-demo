"""Hash- and AST-bound verifier for the approved five-win behavior baseline."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


class FrozenBehaviorViolation(RuntimeError):
    """Raised when a frozen execution input or call semantic changes."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_equal(name: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        raise FrozenBehaviorViolation(f"{name} changed: expected {expected!r}, got {actual!r}")


def _literal_assignments(tree: ast.AST) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for statement in getattr(tree, "body", ()):  # Only module constants are behavior inputs.
        if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
            continue
        target = statement.targets[0] if isinstance(statement, ast.Assign) else statement.target
        value = statement.value
        if not isinstance(target, ast.Name) or value is None:
            continue
        try:
            values[target.id] = ast.literal_eval(value)
        except (ValueError, TypeError):
            continue
    return values


def _calls(tree: ast.AST, name: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == name)
            or (isinstance(node.func, ast.Attribute) and node.func.attr == name)
        )
    ]


def _keyword_literal(call: ast.Call, name: str) -> Any:
    for keyword in call.keywords:
        if keyword.arg == name:
            try:
                return ast.literal_eval(keyword.value)
            except (ValueError, TypeError) as error:
                raise FrozenBehaviorViolation(f"{name} is no longer a literal") from error
    raise FrozenBehaviorViolation(f"{name} is missing")


def verify_transport_semantics(source: str, manifest: dict[str, Any]) -> dict[str, str]:
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        raise FrozenBehaviorViolation(f"transport source is not valid Python: {error}") from error
    contract = manifest["transport_ast_semantics"]
    constants = _literal_assignments(tree)
    expected_constants = {
        "EXPECTED_START_ARM": tuple(contract["expected_start_arm_rad"]),
        "EXPECTED_Q6": contract["expected_q6_rad"],
        "TARGETS": tuple(tuple(item) for item in contract["targets_arm_rad"]),
        "CONTACT_LOSS_GRACE_S": contract["physical_contract"]["contact_loss_grace_s"],
        "MAX_SEGMENT_CUP_DISPLACEMENT_M": contract["physical_contract"][
            "maximum_segment_cup_displacement_m"
        ],
        "MIN_TOTAL_LATERAL_M": contract["physical_contract"]["minimum_total_lateral_m"],
        "MAX_TOTAL_LATERAL_M": contract["physical_contract"]["maximum_total_lateral_m"],
        "MAX_TOTAL_VERTICAL_CHANGE_M": contract["physical_contract"][
            "maximum_total_vertical_change_m"
        ],
    }
    for name, expected in expected_constants.items():
        _require_equal(name, constants.get(name), expected)

    requests = _calls(tree, "JointPlanRequest")
    if len(requests) != 1:
        raise FrozenBehaviorViolation("JointPlanRequest call count changed")
    request = requests[0]
    planner = contract["planner_request"]
    for name in ("velocity_scaling", "acceleration_scaling", "planning_time_s"):
        _require_equal(name, _keyword_literal(request, name), planner[name])
    _require_equal(
        "JointPlanRequest joint names",
        ast.unparse(next(item.value for item in request.keywords if item.arg == "joint_names")),
        "ARM_JOINTS",
    )
    _require_equal(
        "JointPlanRequest start_state_joint_names",
        ast.unparse(
            next(item.value for item in request.keywords if item.arg == "start_state_joint_names")
        ),
        "ALL_JOINTS",
    )

    source_compact = "".join(source.split())
    required_fragments = {
        "plan_timeout_s": f"timeout_s={planner['plan_timeout_s']}",
        "execute_timeout_s": f"planned.trajectory,{planner['execute_timeout_s']}",
        "endpoint_timeout_s": f'),{planner["endpoint_timeout_s"]},f"transportwaypoint',
        "plan_to_execute_tolerance_rad": f"ifdrift>{planner['plan_to_execute_tolerance_rad']}",
        "start_arm_tolerance_rad": f")>{planner['start_arm_tolerance_rad']}",
        "start_q6_tolerance_rad": f")>{planner['start_q6_tolerance_rad']}",
    }
    for name, fragment in required_fragments.items():
        if fragment not in source_compact:
            raise FrozenBehaviorViolation(f"{name} call semantic changed")

    stable_calls = [
        call
        for call in _calls(tree, "stable_bilateral")
        if not isinstance(getattr(call, "parent", None), ast.FunctionDef)
    ]
    modes = [ast.unparse(call.args[1]) for call in stable_calls if len(call.args) >= 2]
    _require_equal(
        "phase force modes",
        modes,
        [
            "ContactForceMode.PRE_TRANSPORT_STATIC_HOLD",
            "ContactForceMode.DYNAMIC_TRANSPORT_SHADOW",
        ],
    )
    loops = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.For)
        and isinstance(node.iter, ast.Call)
        and ast.unparse(node.iter.func) == "enumerate"
    ]
    if not any(ast.unparse(item.iter) == "enumerate(TARGETS, start=1)" for item in loops):
        raise FrozenBehaviorViolation("waypoint loop order changed")
    return {
        "targets": "MATCH",
        "planner_request": "MATCH",
        "physical_contract": "MATCH",
        "phase_force_modes": "MATCH",
    }


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=repo_root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.strip()


def _verify_hash(repo_root: Path, relative: str, expected: str) -> None:
    _require_equal(relative, _sha256(repo_root / relative), expected)


def verify_frozen_behavior(repo_root: Path, manifest_path: Path) -> dict[str, str]:
    repo_root = repo_root.resolve()
    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    digest = _sha256(manifest_path)
    sha_path = manifest_path.with_suffix(".sha256")
    registered_digest = sha_path.read_text(encoding="utf-8").split()[0]
    _require_equal("manifest SHA-256", digest, registered_digest)

    _verify_hash(repo_root, manifest["grasp"]["source_path"], manifest["grasp"]["source_sha256"])
    _verify_hash(
        repo_root,
        manifest["motion_policy"]["path"],
        manifest["motion_policy"]["sha256"],
    )
    _verify_hash(
        repo_root,
        "src/so101_mujoco_demo_py/config/contact_calibration.yaml",
        manifest["approved_policy"]["contact_policy_sha256"],
    )

    phase_root = repo_root / "src/so101_mujoco_demo_py/so101_mujoco_demo_py"
    for filename, expected in manifest["phase_source_hashes"].items():
        if filename == "transport.py":
            continue
        relative = (
            Path(filename)
            if filename in {"live_runtime.py", "staged_approach.py"}
            else Path("live_phases") / filename
        )
        _require_equal(f"phase source {filename}", _sha256(phase_root / relative), expected)

    model = manifest["model_scene_geometry"]
    fixed_files = {
        "src/so101_mujoco_demo_py/mjcf/scene.xml": model["scene_xml_sha256"],
        "src/so101_mujoco_demo_py/mjcf/so101.xml": model["robot_mjcf_sha256"],
        "src/so101_mujoco_demo_py/config/task_scene.yaml": model["task_scene_yaml_sha256"],
        "src/so101_mujoco_demo_py/urdf/so101.urdf": model["urdf_sha256"],
    }
    control = manifest["planning_and_control"]
    fixed_files.update(
        {
            "src/so101_mujoco_demo_py/config/dependency-lock.yaml": control[
                "dependency_lock_sha256"
            ],
            "src/so101_mujoco_demo_py/config/ompl_planning.yaml": control["ompl_planning_sha256"],
            "src/so101_mujoco_demo_py/config/joint_limits.yaml": control["joint_limits_sha256"],
            "src/so101_mujoco_demo_py/config/moveit_controllers.yaml": control[
                "moveit_controllers_sha256"
            ],
            "src/so101_mujoco_demo_py/config/ros2_controllers.yaml": control[
                "ros2_controllers_sha256"
            ],
            "src/so101_mujoco_demo_py/config/mujoco_plugins.yaml": control["mujoco_plugins_sha256"],
        }
    )
    for relative, expected in fixed_files.items():
        _verify_hash(repo_root, relative, expected)

    transport_path = repo_root / manifest["transport_ast_semantics"]["path"]
    verify_transport_semantics(transport_path.read_text(encoding="utf-8"), manifest)

    backend_contract = manifest.get("backend_integration_contract")
    if not isinstance(backend_contract, dict):
        raise FrozenBehaviorViolation("backend integration contract is missing")
    if backend_contract.get("gazebo_source_frozen") is not False:
        raise FrozenBehaviorViolation("Gazebo source must not be frozen by this manifest")
    if backend_contract.get("checker") != "scripts/check_backend_integration.py":
        raise FrozenBehaviorViolation("backend integration checker changed")
    if _git(repo_root, "status", "--porcelain", "--", "src/so101_mujoco_demo_py/mjcf"):
        raise FrozenBehaviorViolation("protected MJCF working tree changed")

    gate = manifest["instrumentation_diff_gate"]
    changed = set(
        filter(
            None,
            _git(
                repo_root,
                "diff",
                "--name-only",
                manifest["behavior_baseline_commit"],
                "--",
            ).splitlines(),
        )
    )
    changed.update(
        filter(None, _git(repo_root, "ls-files", "--others", "--exclude-standard").splitlines())
    )
    allowed = tuple(item.rstrip("/") for item in gate["allowed_paths"])
    disallowed = sorted(
        path
        for path in changed
        if not any(path == item or path.startswith(f"{item}/") for item in allowed)
    )
    if disallowed:
        raise FrozenBehaviorViolation(f"instrumentation diff escaped allowlist: {disallowed}")

    return {
        "manifest_sha256": digest,
        "transport_semantics": "MATCH",
        "backend_integration_contract": "ACTIVE_GAZEBO_NOT_FROZEN",
        "instrumentation_diff_gate": "MATCH",
    }
