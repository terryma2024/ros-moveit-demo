"""Broker generation binding, the initial gate and the broker mask localisation."""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
from parallel_ros_runtime_support import _lease, _valid_worker_nodes
import pytest


def test_broker_generation_binding_is_monotonic_and_fail_closed():
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    runtime = ParallelRosRuntimePorts(
        SimpleNamespace(), catalog={}, broker_generation=1
    )

    assert runtime.bind_broker_generation(2) is True
    assert runtime.broker_generation == 2
    for invalid in (1, 0, -1, True, None, "3"):
        with pytest.raises(RuntimeError, match="BROKER_GENERATION"):
            runtime.bind_broker_generation(invalid)
        assert runtime.broker_generation == 2


def test_production_initial_gate_queries_goals_and_uses_action_status_qos(monkeypatch):
    import rclpy
    from rclpy.qos import qos_profile_action_status_default

    from so101_demo.backends.mujoco import teleop_runtime
    from so101_demo.runtime.parallel_ros_ports import observations as runtime_module_observations

    captured_qos = []

    class Future:
        def __init__(self, value):
            self.value = value

        def done(self):
            return True

        def result(self):
            return self.value

    class ServiceClient:
        def wait_for_service(self, *, timeout_sec):
            return timeout_sec > 0.0

        def call_async(self, _request):
            return Future(SimpleNamespace(
                scene=SimpleNamespace(
                    robot_state=SimpleNamespace(attached_collision_objects=[])
                )
            ))

    class CancelClient:
        def wait_for_service(self, *, timeout_sec):
            return timeout_sec > 0.0

        def call_async(self, _request):
            return Future(SimpleNamespace(goals_canceling=[]))

    class Node:
        def __init__(self, name):
            self.name = name
            self.callbacks = []
            self.graph_reads = 0

        def create_client(self, _service, name):
            return CancelClient() if name.endswith("/cancel_goal") else ServiceClient()

        def create_subscription(self, _message, _topic, callback, qos):
            captured_qos.append(qos)
            self.callbacks.append(callback)
            return object()

        def get_node_names_and_namespaces(self):
            valid = _valid_worker_nodes()
            incomplete = tuple(
                node for node in valid if node != "/so101_base_to_camera_link"
            )
            nodes = incomplete if self.graph_reads < 2 else valid
            self.graph_reads += 1
            return [
                (node.rsplit("/", 1)[1], node.rsplit("/", 1)[0] or "/")
                for node in nodes
            ]

        def destroy_node(self):
            return None

    def create_node(name):
        return Node(name)

    def spin_once(node, *, timeout_sec):
        assert timeout_sec == 0.01

    monkeypatch.setattr(rclpy, "ok", lambda: True)
    monkeypatch.setattr(rclpy, "create_node", create_node)
    monkeypatch.setattr(rclpy, "spin_once", spin_once)
    fingertip_contacts = {"left": (), "right": ()}
    monkeypatch.setattr(
        teleop_runtime,
        "current_evidence",
        lambda *_args, **_kwargs: SimpleNamespace(
            reset_epoch=2,
            has_contact=True,
            left_fingertip_contacts=fingertip_contacts["left"],
            right_fingertip_contacts=fingertip_contacts["right"],
            other_object_contacts=(SimpleNamespace(geom2="table"),),
        ),
    )

    table_supported = runtime_module_observations.observe_parallel_initial_gate(
        runtime_module_observations.ResetBoundaryReceipt(
            "reset-2", "session-1", 1.0, 2.0, 2, (0.0,) * 6
        ),
        timeout_s=0.25,
    )
    assert table_supported.has_contact is False
    assert table_supported.worker_node_fqns == _valid_worker_nodes()

    fingertip_contacts["left"] = (SimpleNamespace(geom1="left_fingertip"),)
    fingertip_contact = runtime_module_observations.observe_parallel_initial_gate(
        runtime_module_observations.ResetBoundaryReceipt(
            "reset-2", "session-1", 1.0, 2.0, 2, (0.0,) * 6
        ),
        timeout_s=0.25,
    )
    assert fingertip_contact.has_contact is True

    assert captured_qos == [qos_profile_action_status_default] * 6

    with pytest.raises(
        RuntimeError,
        match=r"^POINT_INITIAL_GATE_OBSERVATION_TIMEOUT:joint_state$",
    ):
        runtime_module_observations.observe_parallel_initial_gate(
            runtime_module_observations.ResetBoundaryReceipt("reset-2", "session-1", 1.0, 2.0),
            timeout_s=0.05,
        )


def test_initial_gate_requires_fresh_observed_joints_goals_attachment_contact_and_nodes():
    from so101_demo.runtime.parallel_ros_ports.observations import (
        InitialGateObservation,
        ResetBoundaryReceipt,
    )
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    reset = ResetBoundaryReceipt("reset-2", "session-1", 10.0, 12.0)
    observation = InitialGateObservation(
        reset_epoch="reset-2",
        simulation_session_id="session-1",
        source_frame_monotonic_s=11.0,
        joint_positions=(0.0,) * 6,
        active_controller_goal_ids=(),
        moveit_attached_object_ids=(),
        has_contact=False,
        worker_node_fqns=_valid_worker_nodes(),
    )
    ports = ParallelRosRuntimePorts.for_test(
        resources=SimpleNamespace(session_id="session-1"),
        catalog={"task_start": {"cup_position_world_m": [0.02, -0.28, 0.165]}},
        observe_initial=lambda _boundary: observation,
    )
    lease = _lease()
    gate = ports.initial_gate(lease, reset)
    for field in (
        "batch_id",
        "coordinator_epoch",
        "worker_id",
        "worker_generation",
        "point_id",
        "attempt_id",
        "lease_generation",
    ):
        assert getattr(gate, field) == getattr(lease, field)
    assert gate.canonical_joints is True
    assert gate.no_controller_goal is True
    assert gate.no_attachment is True
    assert gate.no_contact is True
    assert gate.no_stale_node is True
    assert gate.source_frame_monotonic_s == 11.0

    for changed in (
        {"joint_positions": (0.1,) + (0.0,) * 5},
        {"active_controller_goal_ids": ("goal-1",)},
        {"moveit_attached_object_ids": ("plastic_cup",)},
        {"has_contact": True},
        {"worker_node_fqns": ("/move_group", "/move_group")},
    ):
        invalid = InitialGateObservation(
            **{**observation.__dict__, **changed}
        )
        ports = ParallelRosRuntimePorts.for_test(
            resources=SimpleNamespace(session_id="session-1"),
            catalog={"task_start": {"cup_position_world_m": [0.02, -0.28, 0.165]}},
            observe_initial=lambda _boundary, value=invalid: value,
        )
        with pytest.raises(RuntimeError, match="POINT_INITIAL_GATE"):
            ports.initial_gate(_lease(), reset)


def test_initial_gate_reads_evidence_through_the_retained_reader_only_when_the_task_has_one(monkeypatch):
    from so101_demo.runtime.parallel_ros_ports import point_gate
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    seen = []

    def observe(boundary, **kwargs):
        seen.append(kwargs)
        raise RuntimeError("stop after the call")

    monkeypatch.setattr(point_gate, "observe_parallel_initial_gate", observe)
    reader = lambda session, timeout_s=5.0: None
    for dependencies, expected in (({"retained_evidence": reader}, {"read_evidence": reader}), ({}, {})):
        ports = ParallelRosRuntimePorts.for_test(
            resources=SimpleNamespace(session_id="session-1"),
            catalog={"task_start": {"cup_position_world_m": [0.02, -0.28, 0.165]}}, observe_initial=None)
        ports.dependencies.pop("observe_initial")   # the production path: `observe_parallel_initial_gate`
        ports.dependencies.update(dependencies)
        with pytest.raises(RuntimeError, match="stop after the call"):
            ports.initial_gate(_lease(), SimpleNamespace(reset_epoch="reset-2"))
        assert seen.pop() == {"teacher_profile": False, **expected}


def test_initial_gate_rejection_names_every_failed_predicate_in_fixed_order():
    from so101_demo.runtime.parallel_ros_ports.observations import (
        InitialGateObservation,
        ResetBoundaryReceipt,
    )
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    reset = ResetBoundaryReceipt("reset-2", "session-1", 10.0, 12.0)
    rejected = InitialGateObservation(
        reset_epoch="reset-3",
        simulation_session_id="session-2",
        source_frame_monotonic_s=9.0,
        joint_positions=(0.1,) + (0.0,) * 5,
        active_controller_goal_ids=("goal-1",),
        moveit_attached_object_ids=("plastic_cup",),
        has_contact=True,
        worker_node_fqns=("/move_group",),
        node_graph_stable=False,
    )
    ports = ParallelRosRuntimePorts.for_test(
        resources=SimpleNamespace(session_id="session-1"),
        catalog={"task_start": {"cup_position_world_m": [0.02, -0.28, 0.165]}},
        observe_initial=lambda _boundary: rejected,
    )
    expected = (
        "POINT_INITIAL_GATE_OBSERVATION_REJECTED:reset_epoch,simulation_session,"
        "freshness,joints,goals,attachment,contact,stable_graph,worker_nodes"
    )
    with pytest.raises(RuntimeError) as rejected_error:
        ports.initial_gate(_lease(), reset)
    rejection, node_payload = str(rejected_error.value).split(";worker_nodes=", 1)
    assert rejection == expected
    assert json.loads(node_payload) == {
        "duplicates": [],
        "missing": [
            node for node in ParallelRosRuntimePorts.expected_worker_nodes()
            if node != "/move_group"
        ],
        "truncated": False,
        "unexpected": [],
    }

    ports.dependencies["observe_initial"] = lambda _boundary: object()
    with pytest.raises(
        RuntimeError,
        match=r"^POINT_INITIAL_GATE_OBSERVATION_REJECTED:type$",
    ):
        ports.initial_gate(_lease(), reset)


def test_broker_mask_is_decoded_row_major_and_localized_against_exact_depth_and_tf():
    from so101_demo.parallel_batch.broker import BrokerResponse
    from so101_demo.parallel_batch.contracts.common import ExecutionKind, ModelOutcome
    from so101_demo.parallel_batch.contracts.identity import InferenceRequest
    from so101_demo.runtime.parallel_ros_ports.observations import CupCandidateLocalizer

    request = InferenceRequest(
        request_id="attempt-1-yolo",
        model_id="plastic-cup-yolo11n-seg-v1",
        execution_kind=ExecutionKind.ATTEMPT,
        batch_id="batch-1",
        coordinator_epoch=1,
        worker_id="worker-01",
        worker_generation=1,
        point_id="task_start",
        lease_generation=1,
        reset_epoch="reset-2",
        image_timestamp_s=12.0,
        input_relative_path=(
            "worker-01/attempts/task_start/attempt-1/working/"
            "perception/input/rgb.npy"
        ),
        input_sha256="ab" * 32,
        deadline_s=5.0,
        attempt_id="attempt-1",
    )
    candidate_document = {
        "model_id": "plastic-cup-yolo11n-seg-v1",
        "weights_sha256": "ab" * 32,
        "runtime_device": "cuda",
        "inference_latency_ms": 1.0,
        "shape": [2, 3, 3],
        "source_stamp_ns": 12_000_000_000,
        "source_frame_id": "task_camera_frame",
        "candidates": [
            {
                "instance_id": "cup-1",
                "class_id": "plastic_cup",
                "confidence": 0.9,
                "bbox_xyxy": [0.0, 0.0, 3.0, 2.0],
                "segmentation_quality": 0.95,
                "mask_rle": {"shape": [2, 3], "counts": [1, 2, 2, 1]},
            }
        ],
    }
    response = BrokerResponse(
        request,
        1,
        ModelOutcome.QUALIFIED,
        candidate_document,
        None,
        1.0,
        2.0,
        1.1,
        2.1,
        1.2,
    )
    camera = SimpleNamespace(
        width=3,
        height=2,
        header=SimpleNamespace(
            frame_id="task_camera_frame",
            stamp=SimpleNamespace(sec=12, nanosec=0),
        ),
    )
    depth = SimpleNamespace(
        width=3,
        height=2,
        header=camera.header,
        data=b"depth",
    )
    seen = {}

    class Localizer:
        def localize(self, candidate, actual_camera, actual_depth, lookup):
            seen.update(
                mask=np.array(candidate.mask, copy=True),
                camera=actual_camera,
                depth=actual_depth,
                transform=lookup("world", candidate.source_frame_id, candidate.source_stamp_ns),
            )
            return SimpleNamespace(tag="localized-from-mask", points_world=np.array([[0.0, 0.0, 0.12], [0.0, 0.0, 0.21]]))

    value = CupCandidateLocalizer(localizer=Localizer()).localize(
        response,
        camera_info=camera,
        depth_message=depth,
        lookup_exact=lambda target, source, stamp: (target, source, stamp),
    )
    assert value.tag == "localized-from-mask"
    assert seen["mask"].tolist() == [[False, True, True], [False, False, True]]
    assert seen["camera"] is camera
    assert seen["depth"] is depth
    assert seen["transform"] == ("world", "task_camera_frame", 12_000_000_000)


def _rejected_gate(tmp_path, *, observed, attempt_root=True):
    from so101_demo.runtime.parallel_ros_ports.observations import (
        InitialGateObservation,
        ResetBoundaryReceipt,
    )
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    reset = ResetBoundaryReceipt("reset-2", "session-1", 10.0, 12.0, 2)
    observation = InitialGateObservation(
        reset_epoch="reset-2", simulation_session_id="session-1",
        source_frame_monotonic_s=11.0, joint_positions=(0.0,) * 6,
        active_controller_goal_ids=(), moveit_attached_object_ids=(),
        has_contact=False, worker_node_fqns=tuple(sorted(observed)), node_graph_stable=True,
    )
    resources = SimpleNamespace(session_id="session-1", controller_namespace="/")
    if attempt_root:
        resources.worker_root = tmp_path
    ports = ParallelRosRuntimePorts(
        resources,
        catalog={"task_start": {"cup_position_world_m": [0.02, -0.28, 0.165]}},
        dependencies={"observe_initial": lambda _boundary: observation, "act_profile": True},
    )
    with pytest.raises(RuntimeError) as rejected:
        ports.initial_gate(_lease(), reset)
    return str(rejected.value)


def test_a_rejected_worker_inventory_keeps_the_full_observation_in_a_file(tmp_path):
    """The 300 character fault reason cut off the node list; the whole observation goes to the task directory."""
    required = (
        "/arm_controller", "/gripper_controller", "/neck_controller", "/joint_state_broadcaster", "/move_group",
        "/mujoco_ros2_control_node", "/robot_state_publisher", "/so101_base_to_camera_link",
        "/so101_camera_link_to_task_camera_frame", "/controller_manager",
        "/move_group_private_94319910618432", "/moveit_simple_controller_manager", "/robotsystem",
        "/transform_listener_impl_abcdef")
    stray = tuple(f"/stray_node_{index:02d}" for index in range(20))
    observed = (*required, *stray)

    message = _rejected_gate(tmp_path, observed=observed)

    assert message.startswith("POINT_INITIAL_GATE_OBSERVATION_REJECTED:worker_nodes;worker_nodes=")
    assert len(message) <= 300
    name = message.split(";observation=", 1)[1]
    assert name == "gate-observation-attempt-1.json"
    document = json.loads((tmp_path / name).read_text())
    assert document["failures"] == ["worker_nodes"]
    assert document["worker_nodes"]["observed"] == sorted(observed)
    assert document["worker_nodes"]["unknown"] == sorted(stray)
    assert "/move_group/moveit" in document["worker_nodes"]["missing_internal"]


def test_a_rejected_worker_inventory_without_a_task_directory_keeps_the_original_message(tmp_path):
    message = _rejected_gate(tmp_path, observed=("/move_group",), attempt_root=False)

    assert message.startswith("POINT_INITIAL_GATE_OBSERVATION_REJECTED:worker_nodes;worker_nodes=")
    assert ";observation=" not in message
    assert list(tmp_path.iterdir()) == []


def _gate_with_scene(monkeypatch, *, scene_results, service_ready, capsys=None):
    """The production gate over fake nodes; `scene_results` are the successive scene call outcomes (None: no result)."""
    import rclpy

    from so101_demo.backends.mujoco import teleop_runtime
    from so101_demo.runtime.parallel_ros_ports import observations

    class Future:
        def __init__(self, value):
            self.value = value

        def done(self):
            return True

        def result(self):
            return self.value

    scene_calls, waits = [], []
    scene = SimpleNamespace(scene=SimpleNamespace(robot_state=SimpleNamespace(attached_collision_objects=[])))

    class SceneClient:
        def wait_for_service(self, *, timeout_sec):
            waits.append(timeout_sec)
            return service_ready

        def service_is_ready(self):
            return service_ready

        def call_async(self, _request):
            scene_calls.append(1)
            value = scene_results[min(len(scene_calls) - 1, len(scene_results) - 1)]
            return Future(scene if value == "scene" else None)

    class CancelClient:
        def wait_for_service(self, *, timeout_sec):
            return True

        def call_async(self, _request):
            return Future(SimpleNamespace(goals_canceling=[]))

    class Node:
        def create_client(self, _service, name):
            return CancelClient() if name.endswith("/cancel_goal") else SceneClient()

        def create_subscription(self, *_args):
            return object()

        def get_node_names_and_namespaces(self):
            return [(node.rsplit("/", 1)[1], node.rsplit("/", 1)[0] or "/") for node in _valid_worker_nodes()]

        def destroy_node(self):
            return None

    monkeypatch.setattr(rclpy, "ok", lambda: True)
    monkeypatch.setattr(rclpy, "create_node", lambda name: Node())
    monkeypatch.setattr(rclpy, "spin_once", lambda node, *, timeout_sec: None)
    monkeypatch.setattr(teleop_runtime, "current_evidence", lambda *_a, **_k: SimpleNamespace(
        reset_epoch=2, left_fingertip_contacts=(), right_fingertip_contacts=()))
    call = lambda: observations.observe_parallel_initial_gate(
        observations.ResetBoundaryReceipt("reset-2", "session-1", 1.0, 2.0, 2, (0.0,) * 6), timeout_s=0.25)
    return call, scene_calls, waits


def test_gate_retries_one_scene_read_that_returned_no_result(monkeypatch):
    call, scene_calls, _waits = _gate_with_scene(monkeypatch, scene_results=[None, "scene"], service_ready=True)
    assert call().moveit_attached_object_ids == () and len(scene_calls) == 2


def test_gate_names_a_scene_read_that_returned_no_result_twice(monkeypatch, capsys):
    call, scene_calls, _waits = _gate_with_scene(monkeypatch, scene_results=[None], service_ready=True)
    with pytest.raises(RuntimeError, match=r"^POINT_INITIAL_GATE_SCENE_UNAVAILABLE: FUTURE_NO_RESULT$"):
        call()
    assert len(scene_calls) == 2
    err = capsys.readouterr().err
    assert "POINT_INITIAL_GATE_SCENE_UNAVAILABLE_DIAGNOSTIC reason=FUTURE_NO_RESULT" in err
    assert "service_is_ready=True rclpy_ok=True" in err and "elapsed_s=" in err


def test_gate_names_a_scene_service_that_never_appears_after_one_retry(monkeypatch, capsys):
    call, scene_calls, waits = _gate_with_scene(monkeypatch, scene_results=["scene"], service_ready=False)
    with pytest.raises(RuntimeError, match=r"^POINT_INITIAL_GATE_SCENE_UNAVAILABLE: WAIT_FOR_SERVICE_TIMEOUT$"):
        call()
    assert waits == [0.125, 0.125] and scene_calls == []   # the same total wait as one attempt
    assert "reason=WAIT_FOR_SERVICE_TIMEOUT" in capsys.readouterr().err
