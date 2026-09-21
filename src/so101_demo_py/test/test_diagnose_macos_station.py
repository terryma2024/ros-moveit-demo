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
from pathlib import Path

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


def test_only_the_two_closed_modes_resolve() -> None:
    module = _diagnostic_module()
    assert (
        module.resolve_mode("MINIMAL_CONTROLLER_MANAGER")
        is module.StationMode.MINIMAL_CONTROLLER_MANAGER
    )
    assert (
        module.resolve_mode("ROBOT_SYSTEM_CONTROLLER_MANAGER")
        is module.StationMode.ROBOT_SYSTEM_CONTROLLER_MANAGER
    )
    with pytest.raises(module.StationDiagnosticError) as error:
        module.resolve_mode("ARBITRARY_CONTROLLER_MANAGER")
    assert error.value.code == "STATION_LAUNCH_MODE_UNSUPPORTED"


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


def test_cli_rejects_a_negative_timeout() -> None:
    module = _diagnostic_module()
    with pytest.raises(SystemExit):
        module.parse_arguments(["--mode", "MINIMAL_CONTROLLER_MANAGER", "--timeout-s", "0"])
