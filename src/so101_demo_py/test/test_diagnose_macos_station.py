"""Contract tests for the macOS station diagnostic (design section 4.2).

The diagnostic exists to locate the first bad boundary of a station that never reaches
readiness, without pretending to know the root cause. Its modes are closed, its phases are
the six structured states of the design, and direct controller traffic never waits behind
the aggregate MoveIt graph. A missing implementation is reported as a failed assertion so
the RED is a real assertion failure rather than a collection error.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def _diagnostic_module():
    spec = importlib.util.find_spec("so101_demo.cli.diagnose_macos_station")
    assert spec is not None, (
        "so101_demo.cli.diagnose_macos_station is not implemented yet"
    )
    return importlib.import_module("so101_demo.cli.diagnose_macos_station")


_ACTIVE = {
    "joint_state_broadcaster": "active",
    "arm_controller": "active",
    "gripper_controller": "active",
}
_SERVICES = {
    "/apply_planning_scene": True,
    "/get_planning_scene": True,
    "/plan_kinematic_path": True,
}
_ACTIONS = {
    "/execute_trajectory": True,
    "/arm_controller/follow_joint_trajectory": True,
    "/gripper_controller/follow_joint_trajectory": True,
}


def _observation(module, *, visible: bool, completed: bool, controllers=None):
    return module.DirectControllerObservation(
        service_visible=visible,
        call_completed=completed,
        controllers=controllers if controllers is not None else {},
        ros_domain_id=41,
        observed_monotonic_ns=1_000_000,
    )


# --------------------------------------------------------------------------------------
# Closed modes and phases
# --------------------------------------------------------------------------------------


def test_station_phases_are_the_closed_design_set() -> None:
    module = _diagnostic_module()
    assert [phase.value for phase in module.StationPhase] == [
        "PLUGIN_RESOLVED",
        "SIMULATION_ENDPOINT_READY",
        "HARDWARE_INITIALIZING",
        "HARDWARE_READY",
        "CONTROLLER_MANAGER_SERVICES_READY",
        "CONTROLLERS_ACTIVE",
    ]


def test_the_legacy_three_closed_modes_resolve() -> None:
    module = _diagnostic_module()
    assert (
        module.resolve_mode("MINIMAL_CONTROLLER_MANAGER")
        is module.StationMode.MINIMAL_CONTROLLER_MANAGER
    )
    assert (
        module.resolve_mode("ROBOT_SYSTEM_CONTROLLER_MANAGER")
        is module.StationMode.ROBOT_SYSTEM_CONTROLLER_MANAGER
    )
    assert (
        module.resolve_mode("FULL_TASK_STATION")
        is module.StationMode.FULL_TASK_STATION
    )
    with pytest.raises(module.StationDiagnosticError) as error:
        module.resolve_mode("ARBITRARY_CONTROLLER_MANAGER")
    assert error.value.code == "STATION_LAUNCH_MODE_UNSUPPORTED"


def test_full_station_readiness_uses_manifest_python_and_installed_entrypoint(
    tmp_path: Path,
) -> None:
    module = _diagnostic_module()
    install = tmp_path / "closure"
    relative = "lib/so101_demo_py/motion_stack_ready"
    executable = install / relative
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    executable.chmod(0o755)
    manifest = SimpleNamespace(
        install_root=install,
        closure=SimpleNamespace(inventory={relative: object()}),
        semantic=SimpleNamespace(python_executable=Path("/venv/bin/python")),
    )

    assert module._readiness_argv(manifest) == (
        "/venv/bin/python",
        str(executable),
        "--timeout-s",
        "90.0",
    )

    manifest.closure.inventory.clear()
    with pytest.raises(module.StationDiagnosticError, match="READINESS_EXECUTABLE"):
        module._readiness_argv(manifest)


def test_minimal_mode_never_loads_the_robot_system(tmp_path: Path) -> None:
    module = _diagnostic_module()
    minimal = module.station_argv(
        module.StationMode.MINIMAL_CONTROLLER_MANAGER,
        share_root=tmp_path,
        session_id="session-a",
    )
    robot_system = module.station_argv(
        module.StationMode.ROBOT_SYSTEM_CONTROLLER_MANAGER,
        share_root=tmp_path,
        session_id="session-a",
    )

    assert minimal != robot_system
    assert "controller_manager" in minimal
    assert "mujoco_ros2_control" not in minimal
    assert not any("mujoco_plugins" in argument for argument in minimal)
    assert "mujoco_ros2_control" in robot_system
    assert any("mujoco_plugins.yaml" in argument for argument in robot_system)
    assert any("ros2_controllers.yaml" in argument for argument in robot_system)
    assert any(argument == "simulation_session_id:=session-a" for argument in robot_system)


def test_full_task_station_argv_is_fixed_and_uses_validated_binding_values(
    tmp_path: Path,
) -> None:
    module = _diagnostic_module()
    scene = tmp_path / "closure/share/so101_demo_py/assets/mujoco/scene.xml"
    scene.parent.mkdir(parents=True)
    scene.write_text("<mujoco/>", encoding="utf-8")
    evidence = tmp_path / "run/evidence"

    argv = module.full_task_station_argv(
        session_id="gate-a-session-1",
        task_evidence_root=evidence,
        scene=scene,
        readiness_timeout_s=90.0,
        python_executable=Path("/venv/bin/python"),
        ros2_script=Path("/ros/bin/ros2"),
    )

    assert argv == (
        "/venv/bin/python",
        "/ros/bin/ros2",
        "launch",
        "so101_demo_py",
        "so101_mujoco_task_station.launch.py",
        "headless:=false",
        "sensor_rendering:=true",
        "include_teleop:=false",
        "session_id:=gate-a-session-1",
        f"task_evidence_root:={evidence}",
        "readiness_timeout_s:=90.0",
        f"mujoco_scene:={scene}",
        "mujoco_initial_keyframe:=task_start",
    )


# --------------------------------------------------------------------------------------
# Direct controller observation is independent of the MoveIt graph
# --------------------------------------------------------------------------------------


def test_direct_observation_starts_as_soon_as_the_service_is_visible() -> None:
    module = _diagnostic_module()

    class Future:
        def done(self) -> bool:
            return False

    class Client:
        def __init__(self, ready: bool) -> None:
            self.ready = ready
            self.calls = 0

        def service_is_ready(self) -> bool:
            return self.ready

        def call_async(self, _request):
            self.calls += 1
            return Future()

    invisible = Client(False)
    observation = module.observe_direct_controllers(
        invisible,
        request_factory=object,
        spin_until_future_complete=lambda *args, **kwargs: None,
        node=object(),
        timeout_s=0.25,
        ros_domain_id=41,
        clock=lambda: 1_000,
    )
    assert observation.service_visible is False
    assert observation.call_completed is False
    assert invisible.calls == 0
    assert observation.ros_domain_id == 41
    assert observation.observed_monotonic_ns == 1_000

    visible = Client(True)
    observation = module.observe_direct_controllers(
        visible,
        request_factory=object,
        spin_until_future_complete=lambda *args, **kwargs: None,
        node=object(),
        timeout_s=0.25,
        ros_domain_id=41,
        clock=lambda: 2_000,
    )
    assert observation.service_visible is True
    assert observation.call_completed is False
    assert visible.calls == 1


def test_direct_observation_completes_with_the_controller_states() -> None:
    module = _diagnostic_module()

    class Controller:
        def __init__(self, name: str, state: str) -> None:
            self.name = name
            self.state = state

    class Future:
        def __init__(self) -> None:
            self.complete = False

        def done(self) -> bool:
            return self.complete

        def result(self):
            return type(
                "Response",
                (),
                {"controller": [Controller("arm_controller", "active")]},
            )()

    class Client:
        def __init__(self) -> None:
            self.calls = 0
            self.future = Future()

        def service_is_ready(self) -> bool:
            return True

        def call_async(self, _request):
            self.calls += 1
            return self.future

    client = Client()
    spin_calls: list = []

    def spin(*args, **kwargs):
        spin_calls.append((args, kwargs))

    pending = module.observe_direct_controllers(
        client,
        request_factory=object,
        spin_until_future_complete=spin,
        node=object(),
        timeout_s=0.25,
        ros_domain_id=77,
        clock=lambda: 10,
    )
    assert pending.controllers == {}

    client.future.complete = True
    completed = module.observe_direct_controllers(
        client,
        request_factory=object,
        spin_until_future_complete=spin,
        node=object(),
        timeout_s=0.25,
        ros_domain_id=77,
        clock=lambda: 20,
        pending=client.future,
    )
    assert completed.call_completed is True
    assert completed.service_visible is True
    assert completed.controllers == {"arm_controller": "active"}
    assert completed.ros_domain_id == 77
    assert client.calls == 1
    assert len(spin_calls) == 2


# --------------------------------------------------------------------------------------
# Distinct failure codes for distinct boundaries
# --------------------------------------------------------------------------------------


def test_classification_separates_invisibility_timeout_and_moveit_gaps() -> None:
    module = _diagnostic_module()

    invisible_phase, invisible_code = module.classify_observation(
        _observation(module, visible=False, completed=False),
        moveit_services=_SERVICES,
        moveit_actions=_ACTIONS,
    )
    timeout_phase, timeout_code = module.classify_observation(
        _observation(module, visible=True, completed=False),
        moveit_services=_SERVICES,
        moveit_actions=_ACTIONS,
    )
    inactive_phase, inactive_code = module.classify_observation(
        _observation(module, visible=True, completed=True, controllers={}),
        moveit_services=_SERVICES,
        moveit_actions=_ACTIONS,
    )
    service_phase, service_code = module.classify_observation(
        _observation(module, visible=True, completed=True, controllers=_ACTIVE),
        moveit_services={"/apply_planning_scene": True, "/get_planning_scene": False},
        moveit_actions=_ACTIONS,
    )
    action_phase, action_code = module.classify_observation(
        _observation(module, visible=True, completed=True, controllers=_ACTIVE),
        moveit_services=_SERVICES,
        moveit_actions={"/execute_trajectory": False},
    )
    ready_phase, ready_code = module.classify_observation(
        _observation(module, visible=True, completed=True, controllers=_ACTIVE),
        moveit_services=_SERVICES,
        moveit_actions=_ACTIONS,
    )

    assert invisible_code == "STATION_CONTROLLER_SERVICE_INVISIBLE"
    assert timeout_code == "STATION_CONTROLLER_CALL_TIMEOUT"
    assert inactive_code == "STATION_CONTROLLERS_NOT_ACTIVE"
    assert service_code == "STATION_MOVEIT_SERVICES_UNAVAILABLE"
    assert action_code == "STATION_MOVEIT_ACTIONS_UNAVAILABLE"
    assert ready_code is None
    assert len(
        {
            invisible_code,
            timeout_code,
            inactive_code,
            service_code,
            action_code,
        }
    ) == 5
    assert invisible_phase is module.StationPhase.HARDWARE_INITIALIZING
    assert timeout_phase is module.StationPhase.CONTROLLER_MANAGER_SERVICES_READY
    assert inactive_phase is module.StationPhase.CONTROLLER_MANAGER_SERVICES_READY
    assert service_phase is module.StationPhase.CONTROLLERS_ACTIVE
    assert action_phase is module.StationPhase.CONTROLLERS_ACTIVE
    assert ready_phase is module.StationPhase.CONTROLLERS_ACTIVE


def test_phase_deadlines_are_independent_and_expire_separately() -> None:
    module = _diagnostic_module()
    marks = {
        module.StationPhase.PLUGIN_RESOLVED: 1_000,
        module.StationPhase.SIMULATION_ENDPOINT_READY: 2_000,
        module.StationPhase.HARDWARE_INITIALIZING: 3_000,
    }
    deadlines = module.phase_deadlines(
        marks=marks,
        started_monotonic_ns=0,
        now_monotonic_ns=module.HARDWARE_INITIALIZING_BUDGET_NS + 4_000,
    )
    by_phase = {record.phase: record for record in deadlines}
    assert [record.phase for record in deadlines] == list(module.StationPhase)
    assert by_phase[module.StationPhase.PLUGIN_RESOLVED].observed_monotonic_ns == 1_000
    assert by_phase[module.StationPhase.PLUGIN_RESOLVED].expired is False
    assert by_phase[module.StationPhase.HARDWARE_INITIALIZING].observed_monotonic_ns == 3_000
    assert by_phase[module.StationPhase.HARDWARE_INITIALIZING].expired is False
    assert by_phase[module.StationPhase.HARDWARE_READY].observed_monotonic_ns is None
    assert by_phase[module.StationPhase.HARDWARE_READY].expired is True
    assert by_phase[module.StationPhase.HARDWARE_READY].deadline_monotonic_ns == (
        3_000 + module.HARDWARE_READY_BUDGET_NS
    )


def test_report_is_json_safe_and_carries_the_observation_identity() -> None:
    module = _diagnostic_module()
    observation = module.DirectControllerObservation(
        service_visible=True,
        call_completed=True,
        controllers=_ACTIVE,
        ros_domain_id=41,
        observed_monotonic_ns=5_000,
    )
    report = module.build_station_report(
        mode=module.StationMode.ROBOT_SYSTEM_CONTROLLER_MANAGER,
        ros_domain_id=41,
        observation=observation,
        phases=module.phase_deadlines(
            marks={module.StationPhase.PLUGIN_RESOLVED: 1_000},
            started_monotonic_ns=900,
            now_monotonic_ns=5_000,
        ),
        server_pid=4242,
        server_birth_identity=7_777,
        loaded_images=("/prefix/lib/libmujoco_ros2_control.dylib",),
        node_names=("/controller_manager",),
        service_names=("/controller_manager/list_controllers",),
        failure_code=None,
    )
    document = report.as_document()

    assert json.loads(json.dumps(document, sort_keys=True)) == document
    assert document["mode"] == "ROBOT_SYSTEM_CONTROLLER_MANAGER"
    assert document["ros_domain_id"] == 41
    assert document["observation"]["call_completed"] is True
    assert document["observation"]["controllers"] == _ACTIVE
    assert document["server_pid"] == 4242
    assert document["server_birth_identity"] == 7_777
    assert document["loaded_images"] == ["/prefix/lib/libmujoco_ros2_control.dylib"]
    assert document["failure_code"] is None
    assert [entry["phase"] for entry in document["phases"]] == [
        phase.value for phase in module.StationPhase
    ]


# --------------------------------------------------------------------------------------
# Closed CLI surface
# --------------------------------------------------------------------------------------


def test_cli_requires_a_closed_mode_and_rejects_arbitrary_launch_argv() -> None:
    module = _diagnostic_module()

    with pytest.raises(SystemExit):
        module.parse_arguments([])

    with pytest.raises(SystemExit):
        module.parse_arguments(
            ["--mode", "MINIMAL_CONTROLLER_MANAGER", "--launch-argv", "rm -rf /"]
        )

    options = module.parse_arguments(
        ["--mode", "MINIMAL_CONTROLLER_MANAGER", "--timeout-s", "12.5"]
    )
    assert options.mode is module.StationMode.MINIMAL_CONTROLLER_MANAGER
    assert options.timeout_s == 12.5


def test_full_task_station_cli_requires_manifest_binding_and_control() -> None:
    module = _diagnostic_module()

    with pytest.raises(SystemExit):
        module.parse_arguments(["--mode", "FULL_TASK_STATION"])

    options = module.parse_arguments(
        [
            "--mode",
            "FULL_TASK_STATION",
            "--control-set-manifest",
            "/tmp/manifest.json",
            "--run-binding",
            "/tmp/binding.json",
            "--control",
            "N",
        ]
    )
    assert options.control == "N"


def test_cli_rejects_a_negative_timeout() -> None:
    module = _diagnostic_module()
    with pytest.raises(SystemExit):
        module.parse_arguments(["--mode", "MINIMAL_CONTROLLER_MANAGER", "--timeout-s", "0"])


def test_station_robot_description_renders_the_shared_urdf(tmp_path: Path) -> None:
    """The diagnostic must use the station's own renderer, with the scene as a string.

    Regression: the wrapper handed a ``Path`` to the shared renderer, which expects the scene
    substitution value as ``str``; the first live diagnostic run failed with
    ``TypeError: replace() argument 2 must be str, not PosixPath`` instead of starting.
    """

    module = _diagnostic_module()
    share = tmp_path / "share"
    assets = share / "assets" / "mujoco"
    assets.mkdir(parents=True)
    (assets / "so101.urdf").write_text(
        "<robot name='so101'><hardware>"
        "<plugin>mujoco_ros2_control/MujocoSystemInterface</plugin>"
        "<param name='mujoco_model'>@SO101_MUJOCO_SCENE@</param>"
        "<param name='initial_keyframe'>@SO101_MUJOCO_INITIAL_KEYFRAME@</param>"
        "<param name='headless'>@SO101_MUJOCO_HEADLESS@</param>"
        "<param name='disable_rendering'>@SO101_MUJOCO_DISABLE_RENDERING@</param>"
        "<param name='sim_speed_factor'>@SO101_MUJOCO_SIM_SPEED_FACTOR@</param>"
        "</hardware></robot>",
        encoding="utf-8",
    )
    scene = assets / "scene.xml"
    scene.write_text("<mujoco/>", encoding="utf-8")

    rendered = module.station_robot_description(share)

    assert "@SO101_" not in rendered
    assert str(scene) in rendered
    assert "task_start" in rendered
    assert "mujoco_ros2_control/MujocoSystemInterface" in rendered


# --------------------------------------------------------------------------------------
# The fixed-dylib-farm round owner (remediation Task 3)
#
# One invocation owns exactly one station tree: it freezes the intent before spawning, reads
# readiness and the controller attestation back, writes its report atomically and cleans up
# on both the PASS and the FAIL path. A drifted receipt is refused with no signal at all.
# --------------------------------------------------------------------------------------


def _farm_fixture(tmp_path: Path, *, project_install: Path | None = None):
    """A synthetic fixed runtime: farm, install prefix, readiness entry and the two images."""

    module = _diagnostic_module()
    filesystem_root = tmp_path / "fs"
    farm_run = filesystem_root / "opt/ros/jazzy/dylib_farm/runs/fixture-01"
    farm_run.mkdir(parents=True)
    (farm_run / "libmujoco.3.4.0.dylib").write_bytes(b"farm-lib")
    (filesystem_root / "opt/ros/jazzy/dylib_farm/current").symlink_to(farm_run)
    install = project_install or (filesystem_root / "opt/data/so101/workspace/install")
    (install / "lib/so101_demo_py").mkdir(parents=True)
    readiness = install / "lib/so101_demo_py/motion_stack_ready"
    readiness.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' \'{"ready": true}\'\n', encoding="utf-8")
    readiness.chmod(0o755)
    (install / "lib/mujoco_ros2_control").mkdir(parents=True)
    node = install / "lib/mujoco_ros2_control/ros2_control_node"
    node.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    node.chmod(0o755)
    (install / "lib/libmujoco_ros2_control.dylib").write_bytes(b"plugin-bytes")
    (install / "opt/mujoco_vendor/lib").mkdir(parents=True)
    (install / "opt/mujoco_vendor/lib/libmujoco.3.4.0.dylib").write_bytes(b"vendor-bytes")

    paths = module.FixedFarmRuntimePaths(
        ros_root=filesystem_root / "opt/ros/jazzy",
        ros_install=filesystem_root / "opt/ros/jazzy/install",
        ros_dependency_overlay=filesystem_root / "opt/ros/jazzy/extra_ws/install",
        ros_fork_overlay=filesystem_root / "opt/data/so101/runtime/fork/current",
        python=filesystem_root / "opt/ros/jazzy/.venv/bin/python",
        ros2_script=filesystem_root / "opt/ros/jazzy/install/ros2cli/bin/ros2",
        data_root=filesystem_root / "opt/data",
        temp_root=filesystem_root / "opt/data/tmp",
        dylib_farm=filesystem_root / "opt/ros/jazzy/dylib_farm/current",
        project_install=install,
        runtime_home=filesystem_root / "opt/data/so101/home",
        ros_home=filesystem_root / "opt/data/so101/ros-home",
        ros_log_dir=filesystem_root / "opt/data/so101/ros-logs",
    )
    entries, manifest_sha256 = module._farm_library_inventory(paths.dylib_farm)
    assert entries
    receipt = {
        "status": "PASS",
        "level": "complete",
        "closure_prefixes": [
            str(filesystem_root / "opt/ros/jazzy"),
            str(filesystem_root / "opt/data/so101/workspace/install"),
            str(paths.dylib_farm),
        ],
        "dylib_farm": {
            "logical": str(paths.dylib_farm),
            "resolved": str(paths.dylib_farm.resolve()),
            "manifest_sha256": manifest_sha256,
            "library_count": len(entries),
        },
        "project_install": {"logical": str(install), "resolved": str(install.resolve())},
    }
    receipt_path = tmp_path / "doctor.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    return module, paths, receipt_path


def _farm_binding(tmp_path: Path, module, receipt_path: Path, contract) -> Path:
    binding = {
        "schema_version": 1,
        "round_id": "gate-a2-round-0001",
        "session_id": "gate-a2-round-0001",
        "ros_domain_id": 173,
        "task_evidence_root": str(tmp_path / "round/station"),
        "scene_path": str(tmp_path / "fs/opt/data/so101/workspace/install/scene.xml"),
        "farm_contract_sha256": contract.receipt_sha256,
        "farm_logical": str(contract.dylib_farm_logical),
        "farm_resolved": str(contract.dylib_farm_resolved),
        "farm_manifest_sha256": contract.dylib_farm_manifest_sha256,
        "owner_root_pid": os.getpid(),
        "owner_root_birth_identity": 41,
    }
    path = tmp_path / "run-binding.json"
    path.write_text(json.dumps(binding, indent=2, sort_keys=True), encoding="utf-8")
    return path


class _FakeStation:
    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.alive = False

    def poll(self):
        return 0


def _farm_round_hooks(module, install: Path, *, ready: bool = True):
    node = install / "lib/mujoco_ros2_control/ros2_control_node"
    plugin = install / "lib/libmujoco_ros2_control.dylib"
    vendor = install / "opt/mujoco_vendor/lib/libmujoco.3.4.0.dylib"
    calls = {"spawn": 0, "cleanup": 0}

    def spawn(argv, **kwargs):
        calls["spawn"] += 1
        calls["argv"] = argv
        calls["env"] = dict(kwargs["env"])
        return _FakeStation(9100)

    def rows():
        return ((9100, 1, "/usr/bin/python3 -m launch"), (9123, 9100, f"{node} --ros-args"))

    def cleanup(launch, identities):
        calls["cleanup"] += 1
        calls["identities"] = dict(identities)
        return {"escalation": [], "residue_pids": [], "complete": True}

    return {
        "_calls": calls,
        "spawn": spawn,
        "process_rows": rows,
        "loaded_image_probe": lambda pid: (plugin, vendor),
        "birth_identity": lambda pid: 77 if pid == 9123 else 41,
        "cleanup_owner_tree": cleanup,
        "sleep": lambda seconds: None,
        "clock": lambda: 0.0,
    }


def _farm_kwargs(hooks):
    return {key: value for key, value in hooks.items() if not key.startswith("_")}


def test_each_closed_mode_resolves_and_arbitrary_modes_do_not() -> None:
    module = _diagnostic_module()
    assert (
        module.resolve_mode("FIXED_DYLIB_FARM_FULL_TASK_STATION")
        is module.StationMode.FIXED_DYLIB_FARM_FULL_TASK_STATION
    )
    with pytest.raises(module.StationDiagnosticError) as error:
        module.resolve_mode("ARBITRARY_CONTROLLER_MANAGER")
    assert error.value.code == "STATION_LAUNCH_MODE_UNSUPPORTED"


def test_farm_mode_requires_receipt_binding_and_output_and_refuses_legacy_arguments() -> None:
    module = _diagnostic_module()

    with pytest.raises(SystemExit):
        module.parse_arguments(["--mode", "FIXED_DYLIB_FARM_FULL_TASK_STATION"])
    with pytest.raises(SystemExit):
        module.parse_arguments(
            [
                "--mode", "FIXED_DYLIB_FARM_FULL_TASK_STATION",
                "--farm-contract-receipt", "/tmp/doctor.json",
                "--run-binding", "/tmp/run-binding.json",
            ]
        )
    with pytest.raises(SystemExit):
        module.parse_arguments(
            [
                "--mode", "FIXED_DYLIB_FARM_FULL_TASK_STATION",
                "--farm-contract-receipt", "/tmp/doctor.json",
                "--run-binding", "/tmp/run-binding.json",
                "--output", "/tmp/report.json",
                "--control", "N",
            ]
        )
    options = module.parse_arguments(
        [
            "--mode", "FIXED_DYLIB_FARM_FULL_TASK_STATION",
            "--farm-contract-receipt", "/tmp/doctor.json",
            "--run-binding", "/tmp/run-binding.json",
            "--output", "/tmp/report.json",
            "--timeout-s", "180",
        ]
    )
    assert options.mode is module.StationMode.FIXED_DYLIB_FARM_FULL_TASK_STATION
    assert options.output == "/tmp/report.json"


def test_farm_round_owns_one_station_tree_and_writes_its_report_before_returning(
    tmp_path: Path,
) -> None:
    module, paths, receipt_path = _farm_fixture(tmp_path)
    contract = module.load_fixed_dylib_farm_contract(receipt_path)
    binding_path = _farm_binding(tmp_path, module, receipt_path, contract)
    hooks = _farm_round_hooks(module, paths.project_install)
    output = tmp_path / "station-report.json"

    rc = module.run_fixed_dylib_farm_full_task_station(
        farm_contract_receipt=receipt_path,
        run_binding_path=binding_path,
        output_path=output,
        timeout_s=30.0,
        paths=paths,
        **_farm_kwargs(hooks),
    )

    assert rc == 0
    assert hooks["_calls"]["spawn"] == 1
    assert hooks["_calls"]["cleanup"] == 1
    assert hooks["_calls"]["env"]["DYLD_LIBRARY_PATH"] == str(paths.dylib_farm)
    assert hooks["_calls"]["env"]["ROS_DOMAIN_ID"] == "173"
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["observation_class"] == "PASS"
    assert report["invalid_reasons"] == []
    assert report["spawned"] is True
    assert report["spawn_intent"]["spawned"] is True
    assert report["attestation"]["owner_binding"]["spawn_role"] == "controller_runtime"
    assert report["attestation"]["plugin_path"].endswith("libmujoco_ros2_control.dylib")
    assert report["attestation"]["vendor_path"].endswith("libmujoco.3.4.0.dylib")
    assert report["owner_tree"]["root_pid"] == os.getpid()
    assert report["cleanup"]["complete"] is True
    assert report["report_sha256"]
    intent = json.loads((tmp_path / "farm-station-spawn-intent.json").read_text("utf-8"))
    assert intent["role"] == "controller_runtime"
    assert intent["owner_root_pid"] == os.getpid()


def test_farm_round_refuses_a_drifted_receipt_before_spawning(tmp_path: Path) -> None:
    module, paths, receipt_path = _farm_fixture(tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["dylib_farm"]["manifest_sha256"] = "0" * 64
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    output = tmp_path / "station-report.json"
    hooks = _farm_round_hooks(module, paths.project_install)

    with pytest.raises(module.StationDiagnosticError) as error:
        module.load_fixed_dylib_farm_contract(receipt_path)
    assert error.value.code == "FARM_MANIFEST_DRIFT"

    # The runner itself reports the refusal instead of raising, with no spawn at all.
    contract = module.load_fixed_dylib_farm_contract(
        _farm_fixture(tmp_path / "second")[2])
    rc = module.run_fixed_dylib_farm_full_task_station(
        farm_contract_receipt=receipt_path,
        run_binding_path=_farm_binding(tmp_path, module, receipt_path, contract),
        output_path=output,
        timeout_s=30.0,
        paths=paths,
        **_farm_kwargs(hooks),
    )
    assert rc == 1
    assert hooks["_calls"]["spawn"] == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["spawned"] is False
    assert report["observation_class"] == "INVALID"
    assert "FARM_MANIFEST_DRIFT" in report["invalid_reasons"]


def test_farm_round_still_writes_a_report_and_cleans_up_when_it_is_not_ready(
    tmp_path: Path,
) -> None:
    module, paths, receipt_path = _farm_fixture(tmp_path)
    contract = module.load_fixed_dylib_farm_contract(receipt_path)
    binding_path = _farm_binding(tmp_path, module, receipt_path, contract)
    hooks = _farm_round_hooks(module, paths.project_install)
    readiness = paths.project_install / "lib/so101_demo_py/motion_stack_ready"
    readiness.write_text('#!/bin/sh\nprintf \'%s\\n\' \'{"ready": false}\'\n', encoding="utf-8")
    readiness.chmod(0o755)
    output = tmp_path / "station-report.json"

    rc = module.run_fixed_dylib_farm_full_task_station(
        farm_contract_receipt=receipt_path,
        run_binding_path=binding_path,
        output_path=output,
        timeout_s=30.0,
        paths=paths,
        **_farm_kwargs(hooks),
    )

    assert rc == 1
    assert hooks["_calls"]["spawn"] == 1
    assert hooks["_calls"]["cleanup"] == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["observation_class"] == "INVALID"
    assert "STATION_NOT_READY" in report["invalid_reasons"]
    assert report["cleanup"]["complete"] is True


def test_farm_environment_is_the_same_builder_as_the_runtime_contract_tool() -> None:
    """The diagnostic must not grow a second, drifting runtime environment."""

    module = _diagnostic_module()
    repository_root = Path(__file__).resolve().parents[3]
    tool = repository_root / "scripts" / "so101_macos_runtime_contract.py"
    spec = importlib.util.spec_from_file_location("so101_macos_runtime_contract", tool)
    assert spec is not None and spec.loader is not None
    contract_tool = importlib.util.module_from_spec(spec)
    sys.modules["so101_macos_runtime_contract"] = contract_tool
    spec.loader.exec_module(contract_tool)

    ours = module.FixedFarmRuntimePaths.production().environment(7)
    theirs = contract_tool.build_runtime_environment(
        contract_tool.RuntimePaths.production(repository_root), ros_domain_id=7)

    assert ours == theirs
    assert module.FARM_CLOSURE_PREFIXES == contract_tool.FIXED_CLOSURE_PREFIXES
    assert set(ours) == {
        "HOME", "PATH", "VIRTUAL_ENV", "PYTHONNOUSERSITE", "TMPDIR", "TMP", "TEMP",
        "ROS_HOME", "ROS_LOG_DIR", "ROS_DOMAIN_ID", "DYLD_LIBRARY_PATH",
        "GZ_CONFIG_PATH", "GZ_SIM_SYSTEM_PLUGIN_PATH",
    }
