"""HS-318: the three ``FULL_RESTART`` anchor phases, their teardown proofs and the aggregate contract.

Every case here runs against injected observations: a synthetic process table, a synthetic ROS node list,
synthetic camera frames, a synthetic detector and a fake reservation socket that speaks the frozen C++
``SOGR``/``SOIA``/``SOGB`` protocol. No MuJoCo, no ROS node, no GPU and no detector is started.
"""

from __future__ import annotations

import hashlib
import json
import socket
import struct
import tempfile
import threading
import uuid
from pathlib import Path

import pytest
from so101_demo.act import head_search_restarts as module
from so101_demo.act.head_search_aggregate import (
    RESTART_KIND,
    _gate_restarts,
    _Reasons,
)
from so101_demo.act.head_search_restarts import (
    AGGREGATE_ARTIFACT,
    ANCHORS,
    DECLARED_FRAME_RATE_HZ,
    LIFECYCLE,
    OPERATION,
    PHASE_BY_ANCHOR,
    RESTART_ANCHOR_UNDECLARED,
    RESTART_CADENCE_BROKEN,
    RESTART_DEVICE_UNAVAILABLE,
    RESTART_FOREIGN_OWNER_ACTIVE,
    RESTART_FRAME_RATE_MISMATCH,
    RESTART_GPU_NOT_RELEASED,
    RESTART_NODE_MISSING,
    RESTART_OWNERSHIP_MISMATCH,
    RESTART_OWNERSHIP_REFUSED,
    RESTART_RESERVATION_REFUSED,
    RESTART_RUN_ROOT_EXISTS,
    RESTART_RUNTIME_UNVERIFIED,
    RESTART_SCENE_CONTRADICTORY,
    RESTART_SEARCH_UNPROVEN,
    RESTART_SIM_CLOCK_STALLED,
    RESTART_STOP_UNPROVEN,
    RESTART_TEARDOWN_UNPROVEN,
    ReservationAuthority,
    ReservedControllerPort,
    RestartRefused,
    anchor_declarations,
    camera_rate,
    classify_nodes,
    encode_bound_reservation_frame,
    frame_thresholds,
    goal_digest,
    read_ownership_receipt,
    receipt_document,
    restart_gates,
    restart_refusals,
    sim_clock_progress,
    stack_observation,
    teardown_proof,
    timing_document,
    validate_restart_receipt,
    write_head_search_restarts,
)

SHA = "a" * 64
OTHER_SHA = "b" * 64

#: the promoted values the timing gate reads; the fixtures use the real promoted numbers
VALUES = {
    "max_age_s": 0.014736005008453503,
    "max_skew_s": 0.010000000000001563,
    "stop_velocity_rad_s": 0.04136050464213824,
    "submit_lead_s": 0.004,
    "stop_latency_s": 0.07012353999540209,
    "goal_tolerance_rad": 0.05,
    "search_timeout_s": 0.7089213519976479,
    "min_bbox_aspect": 0.5,
}


# --- fixtures -------------------------------------------------------------------------------------


def runtime_identity(**overrides) -> dict:
    document = {
        "final_run": "/evidence/head-toolchain-20261001T130437Z",
        "source_commit": "956b5b74bfc2581a6222970c924ac0fd4e5e93e0",
        "setup_bash_present": True,
        "production_config": "/evidence/frozen/head_search_v2.json",
        "production_config_sha256": "dfa0af9b" + "0" * 56,
        "values_count": 17,
        "values_sha256": "3c787fd7" + "0" * 56,
        "allow_cpu_fallback": False,
        "cuda_device": "cuda:0",
        "weight_path": "/evidence/weights/best.pt",
        "weight_sha256_declared": "2afd5506" + "0" * 56,
        "weight_sha256_observed": "2afd5506" + "0" * 56,
    }
    document.update(overrides)
    return document


def stack_rows(*commands) -> list[dict]:
    return [{"pid": 1000 + index, "argv": command} for index, command in enumerate(commands)]


OWNED_STACK = stack_rows(
    "/opt/ros/jazzy/lib/mujoco_ros2_control/ros2_control_node",
    "/opt/ros/jazzy/lib/robot_state_publisher/robot_state_publisher",
)


#: every node the composition declares, exactly as the real stack publishes them: the
#: ``ros2_control_node`` process hosts ``controller_manager``, the simulator's two internal nodes and one
#: node per controller
OWNED_NODES = [
    "/controller_manager",
    "/mujoco_ros2_control_node",
    "/robot_state_publisher",
    "/robotsystem",
    "/joint_state_broadcaster",
    "/arm_controller",
    "/gripper_controller",
    "/neck_controller",
]


def observed_stack(**overrides) -> dict:
    document = stack_observation(
        processes=OWNED_STACK,
        nodes=OWNED_NODES,
        gpu_compute_apps=[{"pid": 4321, "process_name": "python3", "used_memory": "1200 MiB"}],
        sim_clock_s=[10.0, 10.5],
    )
    document.update(overrides)
    return document


def frames(
    count: int = 12, *, period: float = 0.1, start: float = 100.0, **overrides
) -> list[dict]:
    rows = [
        {
            "index": index,
            "frame_sim_s": round(start + index * period, 9),
            "received_monotonic_s": 1.0 + index * period,
            "frame_age_s": 0.002,
            "source_skew_s": 0.004,
            "inference_s": 0.02,
            "detections": 1 if index >= 6 else 0,
            "lock_count": max(0, index - 8),
        }
        for index in range(count)
    ]
    for index, row in enumerate(rows):
        row.update(overrides.get(index, {}))
    return rows


def anchor_run(**overrides) -> dict:
    document = {
        "anchor": "default",
        "declared_anchor": {
            "anchor": "default",
            "neck_start_rad": 0.1,
            "centre_angle_rad": 0.23109066719589708,
            "cup_point_m": [0.02, -0.28, 0.165],
        },
        "stack": observed_stack(),
        "camera": camera_rate(frames(30), declared_hz=DECLARED_FRAME_RATE_HZ),
        "clock": sim_clock_progress([10.0, 13.0]),
        "detector": {
            "loaded": True,
            "count": 1,
            "device": "cuda",
            "runtime_device": "cuda:0",
            "allow_cpu_fallback": False,
            "weights_sha256": runtime_identity()["weight_sha256_declared"],
            "model_id": "head-search-v2",
        },
        "search": {
            "terminal_status": "TARGET_LOCKED",
            "coverage_complete": True,
            "wrong_locks": 0,
            "attempt_id": "restart-default-attempt-1",
            "session_id": "head-search-restarts",
            "fine_corrections": 1,
            "cumulative_fine_correction_rad": 0.1311,
            "detection_frames": 6,
            "coverage": {"complete": True, "commanded_stop_count": 1, "planned_stop_count": 2},
        },
        "lock": {"consecutive_frames": 3, "track_id": "head-cup-0", "locked_sim_s": 100.9},
        "frames": frames(),
        "timing": timing_document(frames(), VALUES),
        "stop": {
            "proven": True,
            "qualifying_samples": 3,
            "required_samples": 3,
            "longest_consecutive_run": 3,
        },
        "teardown": {
            "previous_stack_stopped": True,
            "controller_owner_stopped": True,
            "children_exited": True,
            "graph_clear": True,
            "before": {"processes": [], "nodes": [], "gpu_compute_apps": []},
            "after": {"processes": [], "nodes": [], "gpu_compute_apps": []},
            "gpu_released": True,
        },
        "refusals": [],
    }
    document.update(overrides)
    return document


def receipt(runtime: dict | None = None, **overrides) -> dict:
    runtime = runtime or runtime_identity()
    document = receipt_document(
        anchor_run=anchor_run(**overrides.pop("anchor_run", {})),
        runtime=runtime,
        approved_bundle_sha256=overrides.pop("approved_bundle_sha256", "c" * 64),
        run_root="/evidence/qualification-restarts-20261001T150000Z",
        anchor_root="/evidence/qualification-restarts-20261001T150000Z/default",
        ownership={
            "path": "/evidence/gate/exclusive-ownership.json",
            "sha256": SHA,
            "status": "EXCLUSIVE_OWNERSHIP_OK",
            "checked_at_utc": "2026-10-01T15:00:00Z",
            "planned_run_root": "/evidence/qualification-restarts-20261001T150000Z",
        },
        producer={"entry": "so101_head_search_calibration measure-restarts", "argv_sha256": SHA},
        values=VALUES,
        elapsed_s=42.0,
        **overrides,
    )
    return document


# --- the receipt and the aggregate contract ---------------------------------------------------------


def test_receipt_carries_the_kind_the_aggregate_declares():
    document = receipt()
    assert document["kind"] == RESTART_KIND
    assert document["lifecycle"] == LIFECYCLE
    assert document["operation"] == OPERATION
    assert document["anchor"] == "default"
    assert document["phase"] == PHASE_BY_ANCHOR["default"]


def test_every_anchor_maps_to_its_own_phase_and_artifact():
    assert tuple(PHASE_BY_ANCHOR) == ANCHORS
    assert PHASE_BY_ANCHOR == {
        "default": "restart_default",
        "left": "restart_left",
        "forward": "restart_forward",
    }
    assert len({module.ARTIFACT_BY_ANCHOR[anchor] for anchor in ANCHORS}) == 3


def test_the_receipt_satisfies_the_aggregates_own_restart_gate(tmp_path):
    """The strongest available check: the real gate, fed the real receipt, records no refusal."""

    runtime = runtime_identity()
    document = receipt(runtime)
    path = tmp_path / "restart-default.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    reasons = _Reasons()
    readings = _gate_restarts(
        {"restart_receipts": [str(path)]},
        {"runtime": runtime},
        {"bundle_sha256": document["approved_bundle_sha256"]},
        reasons,
    )
    # the anchor presented is accepted field by field; the two the gate still wants are named apart
    assert [item["item"] for item in reasons.both()] == ["restart_left", "restart_forward"]
    assert readings["receipts"]["default"]["path"] == str(path)
    assert (
        readings["receipts"]["default"]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    )


def test_all_three_anchors_satisfy_the_gate_together(tmp_path):
    runtime = runtime_identity()
    paths = []
    for anchor in ANCHORS:
        document = receipt(runtime, anchor_run={"anchor": anchor})
        assert document["anchor"] == anchor
        path = tmp_path / f"restart-{anchor}.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        paths.append(str(path))
    reasons = _Reasons()
    _gate_restarts(
        {"restart_receipts": paths},
        {"runtime": runtime},
        {"bundle_sha256": receipt(runtime)["approved_bundle_sha256"]},
        reasons,
    )
    assert reasons.both() == []


def test_a_receipt_that_claims_a_lock_with_two_frames_is_refused_by_the_gate(tmp_path):
    document = receipt()
    document["lock"]["consecutive_frames"] = 2
    path = tmp_path / "restart-default.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    reasons = _Reasons()
    _gate_restarts(
        {"restart_receipts": [str(path)]},
        {"runtime": runtime_identity()},
        {"bundle_sha256": document["approved_bundle_sha256"]},
        reasons,
    )
    assert [item["item"] for item in reasons.violations] == ["restart_default"]


def test_receipt_is_self_consistent_and_carries_its_own_digest():
    document = receipt()
    assert validate_restart_receipt(document) == []
    body = {key: value for key, value in document.items() if key != "sha256"}
    assert document["sha256"] == module.canonical_sha256(body)


def test_validate_restart_receipt_names_what_is_missing():
    document = receipt()
    body = {key: value for key, value in document.items() if key != "sha256"}
    del body["detector"]
    body["sha256"] = module.canonical_sha256(body)
    problems = validate_restart_receipt(body)
    assert problems and any("detector" in problem for problem in problems)


def test_restart_gates_are_derived_from_the_evidence_not_asserted():
    gates = restart_gates(anchor_run())
    assert gates == {
        "graph": "PASS",
        "detector": "PASS",
        "search": "PASS",
        "lock": "PASS",
        "timing": "PASS",
        "stop": "PASS",
    }
    broken = restart_gates(anchor_run(search={"terminal_status": "TARGET_NOT_FOUND"}))
    assert broken["search"] == "FAIL"


# --- the teardown proof -----------------------------------------------------------------------------


def test_teardown_proof_needs_every_observation_to_be_empty():
    proof = teardown_proof(processes=[], nodes=[], gpu_compute_apps=[], sim_clock_s=[10.0, 12.0])
    assert proof["previous_stack_stopped"] is True
    assert proof["controller_owner_stopped"] is True
    assert proof["children_exited"] is True
    assert proof["graph_clear"] is True
    assert proof["gpu_released"] is True


def test_teardown_proof_fails_on_a_leaked_mujoco_process():
    proof = teardown_proof(
        processes=stack_rows("/opt/ros/jazzy/lib/mujoco_ros2_control/ros2_control_node"),
        nodes=[],
        gpu_compute_apps=[],
    )
    assert proof["previous_stack_stopped"] is False
    assert proof["controller_owner_stopped"] is False
    assert proof["children_exited"] is False


def test_teardown_proof_excludes_the_phases_own_node_and_pid_by_name():
    """The runner's own node and pid are excluded explicitly, and the raw rows stay beside the verdict."""

    proof = teardown_proof(
        processes=[],
        nodes=["/head_search_restart_default"],
        gpu_compute_apps=[{"pid": "4242", "process_name": "python3", "used_memory": "10 MiB"}],
        own_pid=4242,
        runner_node="/head_search_restart_default",
    )
    assert proof["graph_clear"] is True
    assert proof["gpu_released"] is True
    assert proof["excluded_runner_node"] == "/head_search_restart_default"
    assert proof["excluded_own_pid"] == 4242
    assert proof["residual_nodes"] == []
    assert proof["residual_gpu_compute_apps"] == []
    assert proof["node_count"] == 1 and proof["gpu_compute_app_count"] == 1


def test_teardown_proof_still_fails_on_another_process_holding_the_gpu():
    proof = teardown_proof(
        processes=[],
        nodes=[],
        gpu_compute_apps=[{"pid": "99", "process_name": "python3", "used_memory": "10 MiB"}],
        own_pid=4242,
    )
    assert proof["gpu_released"] is False
    assert proof["residual_gpu_compute_apps"][0]["pid"] == "99"


def test_teardown_proof_fails_on_a_node_left_in_the_graph():
    proof = teardown_proof(processes=[], nodes=["/controller_manager"], gpu_compute_apps=[])
    assert proof["graph_clear"] is False


def test_teardown_proof_fails_when_the_gpu_is_still_held():
    proof = teardown_proof(
        processes=[],
        nodes=[],
        gpu_compute_apps=[{"pid": 999, "process_name": "python3", "used_memory": "900 MiB"}],
    )
    assert proof["gpu_released"] is False


# --- the stack health gates -------------------------------------------------------------------------


def test_classify_nodes_matches_the_declared_owners_and_names_foreign_ones():
    reading = classify_nodes([*OWNED_NODES, "/some_other_node"])
    assert reading["matched"]["controller_manager"] == "/controller_manager"
    assert reading["matched"]["robot_state_publisher"] == "/robot_state_publisher"
    assert reading["matched"]["mujoco_ros2_control_node"] == "/mujoco_ros2_control_node"
    assert reading["matched"]["robotsystem"] == "/robotsystem"
    assert reading["foreign"] == ["/some_other_node"]
    assert reading["missing"] == []


def test_classify_nodes_reports_a_missing_owner():
    reading = classify_nodes(["/controller_manager"])
    assert "robot_state_publisher" in reading["missing"]
    assert "robotsystem" in reading["missing"]


def test_classify_nodes_reads_a_controller_spawner_as_transient_not_foreign():
    reading = classify_nodes([*OWNED_NODES, "/spawner_neck_controller"])
    assert reading["transient"] == ["/spawner_neck_controller"]
    assert reading["foreign"] == []


def test_camera_rate_accepts_the_declared_rate():
    reading = camera_rate(frames(30), declared_hz=DECLARED_FRAME_RATE_HZ)
    assert reading["frame_rate_hz"] == DECLARED_FRAME_RATE_HZ
    assert reading["frames"] == 30
    assert reading["matches_declared"] is True
    assert reading["measured_rate_hz"] == pytest.approx(DECLARED_FRAME_RATE_HZ, rel=1e-6)
    assert reading["duplicate_count"] == 0
    assert reading["backward_count"] == 0


def test_camera_rate_refuses_a_rate_that_is_not_the_declared_one():
    slow = frames(30, period=0.12)
    reading = camera_rate(slow, declared_hz=DECLARED_FRAME_RATE_HZ)
    assert reading["matches_declared"] is False
    assert reading["measured_rate_hz"] < DECLARED_FRAME_RATE_HZ
    assert reading["rate_error_hz"] > module.RATE_TOLERANCE_HZ


def test_camera_rate_refuses_duplicate_and_backward_stamps():
    duplicated = frames(6)
    duplicated[3]["frame_sim_s"] = duplicated[2]["frame_sim_s"]
    assert camera_rate(duplicated, declared_hz=DECLARED_FRAME_RATE_HZ)["duplicate_count"] == 1
    backward = frames(6)
    backward[3]["frame_sim_s"] = backward[2]["frame_sim_s"] - 0.05
    assert camera_rate(backward, declared_hz=DECLARED_FRAME_RATE_HZ)["backward_count"] == 1


def test_sim_clock_progress_needs_the_clock_to_advance():
    assert sim_clock_progress([10.0, 12.5])["advancing"] is True
    assert sim_clock_progress([10.0, 12.5])["delta_s"] == pytest.approx(2.5)
    assert sim_clock_progress([10.0, 10.0])["advancing"] is False
    assert sim_clock_progress([])["advancing"] is False


def test_frame_thresholds_are_read_off_the_accepted_frames():
    values = {"max_age_s": 0.0147, "max_skew_s": 0.010000000000001563}
    reading = frame_thresholds(frames(12), values, frame_period_s=0.1)
    assert reading["within_thresholds"] is True
    assert reading["max_frame_age_s"] == pytest.approx(0.002)
    assert reading["max_inference_s"] == pytest.approx(0.02)
    stale = frames(12)
    stale[2]["frame_age_s"] = 0.5
    exceeded = frame_thresholds(stale, values, frame_period_s=0.1)
    assert exceeded["within_thresholds"] is False
    assert exceeded["exceeded_thresholds"] == ["max_age_s"]


# --- refusals ---------------------------------------------------------------------------------------


def test_read_ownership_receipt_refuses_a_refused_gate(tmp_path):
    path = tmp_path / "exclusive-ownership.json"
    path.write_text(
        json.dumps(
            {
                "operation": "QUALIFICATION_OWNERSHIP_CHECK",
                "status": "EXCLUSIVE_OWNERSHIP_REFUSED",
                "refusals": [{"code": "STACK_OWNER_ACTIVE"}],
                "planned_run_root": "/evidence/run",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RestartRefused) as refusal:
        read_ownership_receipt(path, run_root="/evidence/run")
    assert refusal.value.code == RESTART_OWNERSHIP_REFUSED


def test_read_ownership_receipt_refuses_a_receipt_that_guards_another_root(tmp_path):
    path = tmp_path / "exclusive-ownership.json"
    path.write_text(
        json.dumps(
            {
                "operation": "QUALIFICATION_OWNERSHIP_CHECK",
                "status": "EXCLUSIVE_OWNERSHIP_OK",
                "refusals": [],
                "planned_run_root": "/evidence/somewhere-else",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RestartRefused) as refusal:
        read_ownership_receipt(path, run_root="/evidence/run")
    assert refusal.value.code == RESTART_OWNERSHIP_MISMATCH


def test_restart_refusals_reports_every_failed_gate():
    document = receipt()
    document["search"]["terminal_status"] = "TARGET_NOT_FOUND"
    document["timing"]["cadence_continuous"] = False
    document["stop"]["proven"] = False
    codes = {item["code"] for item in restart_refusals(document)}
    assert RESTART_SEARCH_UNPROVEN in codes
    assert RESTART_CADENCE_BROKEN in codes
    assert RESTART_STOP_UNPROVEN in codes


def test_restart_refusals_names_a_foreign_node_and_a_missing_owner():
    document = receipt()
    document["stack"]["nodes"] = ["/controller_manager", "/intruder"]
    codes = {item["code"]: item["detail"] for item in restart_refusals(document)}
    assert RESTART_FOREIGN_OWNER_ACTIVE in codes
    assert "intruder" in codes[RESTART_FOREIGN_OWNER_ACTIVE]
    assert RESTART_NODE_MISSING in codes


def test_restart_refusals_names_a_frame_rate_that_is_not_the_declared_one():
    document = receipt()
    document["camera"] = camera_rate(frames(30, period=0.13), declared_hz=DECLARED_FRAME_RATE_HZ)
    codes = {item["code"] for item in restart_refusals(document)}
    assert RESTART_FRAME_RATE_MISMATCH in codes


def test_restart_refusals_names_a_stalled_simulation_clock():
    document = receipt()
    document["clock"] = sim_clock_progress([10.0, 10.0])
    codes = {item["code"] for item in restart_refusals(document)}
    assert RESTART_SIM_CLOCK_STALLED in codes


def test_restart_refusals_names_an_unproven_teardown():
    document = receipt()
    document["teardown"]["graph_clear"] = False
    codes = {item["code"] for item in restart_refusals(document)}
    assert RESTART_TEARDOWN_UNPROVEN in codes
    document = receipt()
    document["teardown"]["gpu_released"] = False
    codes = {item["code"] for item in restart_refusals(document)}
    assert RESTART_GPU_NOT_RELEASED in codes


def test_restart_refusals_names_a_detector_that_is_not_one_cuda_detector():
    document = receipt()
    document["detector"]["device"] = "cpu"
    codes = {item["code"] for item in restart_refusals(document)}
    assert RESTART_DEVICE_UNAVAILABLE in codes


# --- the anchor declaration -------------------------------------------------------------------------


SEAL = {
    "in_frame_matrix": {
        "default": {"neck_start_rad": 0.1, "centre_angle_rad": 0.23109066719589708},
        "left": {"neck_start_rad": 0.0, "centre_angle_rad": -0.0587558227157227},
        "forward": {"neck_start_rad": 0.0, "centre_angle_rad": 0.18822150530477078},
    },
    "workspace_matrix": {
        "key_samples": [
            {"kind": "anchor", "anchor": "default", "point_m": [0.02, -0.28, 0.165]},
            {"kind": "anchor", "anchor": "left", "point_m": [-0.08, -0.28, 0.165]},
            {"kind": "anchor", "anchor": "forward", "point_m": [0.02, -0.36, 0.165]},
        ]
    },
}


def test_anchor_declarations_read_the_seal():
    declared = anchor_declarations(SEAL)
    assert [item["anchor"] for item in declared] == list(ANCHORS)
    assert declared[0]["neck_start_rad"] == 0.1
    assert declared[2]["cup_point_m"] == [0.02, -0.36, 0.165]


def test_anchor_declarations_refuse_an_undeclared_anchor():
    with pytest.raises(RestartRefused) as refusal:
        anchor_declarations(SEAL, ["nowhere"])
    assert refusal.value.code == RESTART_ANCHOR_UNDECLARED


def test_anchor_declarations_refuse_a_seal_without_the_anchor_point():
    seal = json.loads(json.dumps(SEAL))
    seal["workspace_matrix"]["key_samples"] = [
        sample for sample in seal["workspace_matrix"]["key_samples"] if sample["anchor"] != "left"
    ]
    with pytest.raises(RestartRefused) as refusal:
        anchor_declarations(seal)
    assert refusal.value.code == RESTART_SCENE_CONTRADICTORY


# --- the reservation protocol -----------------------------------------------------------------------


def test_bound_reservation_frame_is_the_frozen_codec_byte_for_byte():
    from so101_demo.adapters.act.controller_reservation_client import _encode_bound_frame

    arguments = dict(
        generation=7,
        goal_uuid=bytes(range(16)),
        role=3,
        permit_uuid=uuid.UUID("12345678-1234-4234-9234-123456789abc").bytes,
        target_digest=bytes(range(32)),
        claim_monotonic_ns=1000,
        deadline_ns=2000,
        session_id="head-search-restarts",
        broker_incarnation="restart-owner",
        controller_incarnation="inc",
        controller_boot_incarnation="boot",
        goal_cdr=b"\x00\x01\x02\x03",
        capability=bytes([9] * 32),
    )
    frozen = _encode_bound_frame(**arguments)
    mine = encode_bound_reservation_frame(**arguments)
    assert mine == frozen


def test_goal_digest_is_the_sha256_of_the_serialised_goal():
    assert goal_digest(b"abc") == hashlib.sha256(b"abc").digest()
    assert len(goal_digest(b"abc")) == 32


class FakeReservationSocket:
    """The frozen C++ socket protocol, minimal: SOIA identity, SOGR arm, SOGB bound reserve."""

    def __init__(self, *, role: int, capability: bytes, generation: int = 0):
        self.role = role
        self.capability = capability
        self.generation = generation
        self.armed: list[int] = []
        self.reject_bound = False
        self.reserved: list[bytes] = []
        self.closed: list[int] = []
        self.frames: list[bytes] = []
        self.path = None

    def serve(self, connection) -> None:
        header = connection.recv(4)
        if len(header) != 4:
            return
        size = struct.unpack(">I", header)[0]
        body = b""
        while len(body) < size:
            chunk = connection.recv(size - len(body))
            if not chunk:
                return
            body += chunk
        frame = header + body
        self.frames.append(frame)
        if body[:4] == b"SOIA":
            if (
                body[4] != 1
                or body[5] != 1
                or body[6:38] != self.capability
                or body[38] != self.role
            ):
                connection.sendall(b"\x00\x00\x00\x06SOID\x01\x00")
                return
            if self.generation == 0:
                connection.sendall(b"\x00\x00\x00\x06SOID\x01\x00")
                return
            identity = b"inc-1\x05boot1"
            payload = (
                b"SOID\x01\x01"
                + bytes([self.role])
                + struct.pack(">Q", self.generation)
                + bytes([5])
                + b"inc-1"
                + bytes([5])
                + b"boot1"
            )
            assert identity
            connection.sendall(struct.pack(">I", len(payload)) + payload)
            return
        if body[:4] == b"SOGB":
            self.reserved.append(frame)
            generation = struct.unpack(">Q", body[38:46])[0]
            accepted = (
                not self.reject_bound and self.generation != 0 and generation == self.generation
            )
            connection.sendall(
                b"SOGA\x01"
                + (b"\x00" if accepted else b"\x01")
                + b"\x00\x00"
                + struct.pack(">Q", generation)
            )
            return
        if body[5] == 3:
            generation = struct.unpack(">Q", body[38:46])[0]
            self.generation = generation
            self.armed.append(generation)
            connection.sendall(b"SOGA\x01\x00\x00\x00" + struct.pack(">Q", generation))
            return
        if body[5] == 2:
            generation = struct.unpack(">Q", body[38:46])[0]
            self.closed.append(generation)
            self.generation = 0
            connection.sendall(b"SOGA\x01\x00\x00\x00" + struct.pack(">Q", generation))
            return
        connection.sendall(b"SOGA\x01\x01\x00\x00" + struct.pack(">Q", 0))


class FakeReservationServer:
    def __init__(self, role: int, capability: bytes):
        self.socket_state = FakeReservationSocket(role=role, capability=capability)
        self.directory = None
        self._listener = None
        self._thread = None

    def start(self, directory, name):
        self.directory = directory
        self.path = directory / name
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(self.path))
        listener.listen(4)
        self._listener = listener

        def loop():
            while True:
                try:
                    connection, _ = listener.accept()
                except OSError:
                    return
                with connection:
                    try:
                        self.socket_state.serve(connection)
                    except OSError:
                        pass

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        if self._listener is not None:
            self._listener.close()


@pytest.fixture
def socket_root():
    """A short private directory: AF_UNIX paths are bounded at 107 bytes by the kernel itself."""

    directory = Path(tempfile.mkdtemp(prefix="hsr-", dir="/tmp"))
    try:
        yield directory
    finally:
        for child in sorted(directory.iterdir(), reverse=True):
            child.unlink()
        directory.rmdir()


def reservation_authority(socket_root, *, roles=("neck",)):
    tmp_path = socket_root
    capabilities = {role: bytes([7 + index] * 32) for index, role in enumerate(roles)}
    servers = {
        role: FakeReservationServer(
            role={"arm": 1, "gripper": 2, "neck": 3}[role], capability=capabilities[role]
        ).start(tmp_path, f"{role}.sock")
        for role in roles
    }
    for role in roles:
        (tmp_path / f"{role}.provision").write_bytes(b"provision")
    authority = ReservationAuthority(
        directory=tmp_path,
        capabilities=capabilities,
        session_id="head-search-restarts",
        generation=11,
    )
    return authority, servers


def test_reservation_authority_arms_then_reserves_the_goal(socket_root):
    authority, servers = reservation_authority(socket_root)
    try:
        identity = authority.identity("neck")
        assert identity == {"generation": 11, "incarnation": "inc-1", "boot": "boot1"}
        goal_cdr = b"goal-bytes"
        assert authority.reserve("neck", goal=goal_cdr, goal_uuid=bytes(range(16))) is True
        assert servers["neck"].socket_state.armed == [11]
        assert len(servers["neck"].socket_state.reserved) == 1
        assert authority.reserved == [
            {"role": "neck", "generation": 11, "goal_uuid": bytes(range(16))}
        ]
    finally:
        for server in servers.values():
            server.stop()


def test_reservation_authority_refuses_when_the_capability_is_wrong(socket_root):
    authority, servers = reservation_authority(socket_root)
    authority._capabilities["neck"] = bytes([1] * 32)
    try:
        with pytest.raises(RestartRefused) as refusal:
            authority.identity("neck")
        assert refusal.value.code == RESTART_RESERVATION_REFUSED
    finally:
        for server in servers.values():
            server.stop()


def test_reservation_authority_refuses_a_rejected_reservation(socket_root):
    authority, servers = reservation_authority(socket_root)
    servers["neck"].socket_state.reject_bound = True
    try:
        with pytest.raises(RestartRefused) as refusal:
            authority.reserve("neck", goal=b"goal", goal_uuid=bytes(range(16)))
        assert refusal.value.code == RESTART_RESERVATION_REFUSED
    finally:
        for server in servers.values():
            server.stop()


class FakeControllerPort:
    """The installed ``RosControllerPort`` surface, without ROS."""

    def __init__(self):
        self.sent: list[tuple] = []
        self.cancelled: list[str] = []
        self.stopped_calls = 0

    def send(self, goal, *, goal_uuid=None):
        self.sent.append((goal, goal_uuid))
        return f"goal-{len(self.sent)}"

    def cancel(self, gid):
        self.cancelled.append(gid)

    def stopped(self):
        self.stopped_calls += 1
        return True

    def _feedback(self, message):
        return None


def test_reserved_controller_port_reserves_the_uuid_it_then_sends(socket_root):
    authority, servers = reservation_authority(socket_root)
    port = FakeControllerPort()
    reserved = ReservedControllerPort(
        port, authority=authority, role="neck", serialize=lambda goal: goal
    )
    try:
        gid = reserved.send(b"goal-cdr")
        assert gid == "goal-1"
        goal, goal_uuid = port.sent[0]
        assert goal == b"goal-cdr"
        assert bytes(goal_uuid.uuid) == authority.reserved[0]["goal_uuid"]
        assert bytes(reserved.reservations[0]["goal_uuid"].uuid) == bytes(goal_uuid.uuid)
        assert reserved.reservations[0]["goal_sha256"] == hashlib.sha256(b"goal-cdr").hexdigest()
        assert reserved.stopped() is True
        reserved.cancel(gid)
        assert port.cancelled == [gid]
    finally:
        for server in servers.values():
            server.stop()


def test_reserved_controller_port_never_sends_when_the_reservation_is_refused(socket_root):
    authority, servers = reservation_authority(socket_root)
    servers["neck"].socket_state.reject_bound = True
    port = FakeControllerPort()
    reserved = ReservedControllerPort(
        port, authority=authority, role="neck", serialize=lambda goal: goal
    )
    try:
        with pytest.raises(RestartRefused):
            reserved.send(b"goal-cdr")
        assert port.sent == []
    finally:
        for server in servers.values():
            server.stop()


# --- the producer -----------------------------------------------------------------------------------


class FakeStack:
    def __init__(self, name, log):
        self.name = name
        self.log = log

    def start(self):
        self.log.append(f"start:{self.name}")

    def stop(self):
        self.log.append(f"stop:{self.name}")


def producer_fixture(tmp_path, *, fail_teardown_on=None, ownership_ok=True):
    log: list[str] = []
    events: list[dict] = []
    gate = tmp_path / "exclusive-ownership.json"
    run_root = tmp_path / "qualification-restarts-20261001T150000Z"
    gate.write_text(
        json.dumps(
            {
                "operation": "QUALIFICATION_OWNERSHIP_CHECK",
                "status": "EXCLUSIVE_OWNERSHIP_OK"
                if ownership_ok
                else "EXCLUSIVE_OWNERSHIP_REFUSED",
                "refusals": [] if ownership_ok else [{"code": "STACK_OWNER_ACTIVE"}],
                "planned_run_root": str(run_root),
                "checked_at_utc": "2026-10-01T14:59:00Z",
            }
        ),
        encoding="utf-8",
    )

    def run_anchor(*, anchor, anchor_root, declared, **kwargs):
        log.append(f"anchor:{anchor}")
        if fail_teardown_on == anchor:
            raise RestartRefused(
                RESTART_TEARDOWN_UNPROVEN,
                f"the {anchor} stack did not stop",
            )
        events.append({"anchor": anchor, "root": str(anchor_root)})
        return anchor_run(anchor=anchor, declared_anchor=declared)

    return {
        "gate": gate,
        "run_root": run_root,
        "log": log,
        "events": events,
        "run_anchor": run_anchor,
    }


def test_producer_runs_the_three_anchors_in_order_and_writes_one_receipt_each(tmp_path):
    fixture = producer_fixture(tmp_path)
    result = write_head_search_restarts(
        run_root=fixture["run_root"],
        ownership_receipt=fixture["gate"],
        runtime=runtime_identity(),
        approved_bundle_sha256="c" * 64,
        seal=SEAL,
        workdir=tmp_path / "work",
        run_anchor=fixture["run_anchor"],
        producer={"entry": "so101_head_search_calibration measure-restarts", "argv_sha256": SHA},
    )
    assert fixture["log"] == ["anchor:default", "anchor:left", "anchor:forward"]
    assert result["receipts"] == {
        anchor: str(fixture["run_root"] / anchor / module.ARTIFACT_BY_ANCHOR[anchor])
        for anchor in ANCHORS
    }
    for anchor in ANCHORS:
        path = fixture["run_root"] / anchor / module.ARTIFACT_BY_ANCHOR[anchor]
        document = json.loads(path.read_text(encoding="utf-8"))
        assert document["anchor"] == anchor
        assert document["lifecycle"] == LIFECYCLE
        assert validate_restart_receipt(document) == []
    aggregate = json.loads((fixture["run_root"] / AGGREGATE_ARTIFACT).read_text(encoding="utf-8"))
    assert aggregate["anchors"] == list(ANCHORS)
    assert aggregate["receipts"] == result["receipts"]


def test_producer_refuses_the_whole_run_when_the_ownership_receipt_refused(tmp_path):
    fixture = producer_fixture(tmp_path, ownership_ok=False)
    with pytest.raises(RestartRefused) as refusal:
        write_head_search_restarts(
            run_root=fixture["run_root"],
            ownership_receipt=fixture["gate"],
            runtime=runtime_identity(),
            approved_bundle_sha256="c" * 64,
            seal=SEAL,
            workdir=tmp_path / "work",
            run_anchor=fixture["run_anchor"],
            producer={"entry": "x", "argv_sha256": SHA},
        )
    assert refusal.value.code == RESTART_OWNERSHIP_REFUSED
    assert fixture["log"] == []


def test_producer_refuses_to_resume_an_existing_run_root(tmp_path):
    fixture = producer_fixture(tmp_path)
    fixture["run_root"].mkdir(parents=True)
    with pytest.raises(RestartRefused) as refusal:
        write_head_search_restarts(
            run_root=fixture["run_root"],
            ownership_receipt=fixture["gate"],
            runtime=runtime_identity(),
            approved_bundle_sha256="c" * 64,
            seal=SEAL,
            workdir=tmp_path / "work",
            run_anchor=fixture["run_anchor"],
            producer={"entry": "x", "argv_sha256": SHA},
        )
    assert refusal.value.code == RESTART_RUN_ROOT_EXISTS


def test_producer_records_a_refused_anchor_and_still_runs_the_next_one(tmp_path):
    """Each restart is independent: a search that refuses is evidence, not a reason to skip an anchor."""

    fixture = producer_fixture(tmp_path)

    def run_anchor(*, anchor, anchor_root, declared, **kwargs):
        fixture["log"].append(f"anchor:{anchor}")
        if anchor == "left":
            return anchor_run(
                anchor=anchor,
                declared_anchor=declared,
                search={
                    "terminal_status": "SEARCH_TIMEOUT",
                    "coverage_complete": True,
                    "wrong_locks": 0,
                },
            )
        return anchor_run(anchor=anchor, declared_anchor=declared)

    with pytest.raises(RestartRefused) as refusal:
        write_head_search_restarts(
            run_root=fixture["run_root"],
            ownership_receipt=fixture["gate"],
            runtime=runtime_identity(),
            approved_bundle_sha256="c" * 64,
            seal=SEAL,
            workdir=tmp_path / "work",
            run_anchor=run_anchor,
            producer={"entry": "x", "argv_sha256": SHA},
        )
    assert refusal.value.code == RESTART_SEARCH_UNPROVEN
    assert fixture["log"] == ["anchor:default", "anchor:left", "anchor:forward"]
    for anchor in ANCHORS:
        assert (fixture["run_root"] / anchor / module.ARTIFACT_BY_ANCHOR[anchor]).is_file()
    aggregate = json.loads((fixture["run_root"] / AGGREGATE_ARTIFACT).read_text(encoding="utf-8"))
    assert aggregate["receipt_status"] == {"default": "PASS", "left": "REFUSED", "forward": "PASS"}


def test_producer_stops_at_the_anchor_whose_teardown_cannot_be_proven(tmp_path):
    fixture = producer_fixture(tmp_path, fail_teardown_on="left")
    with pytest.raises(RestartRefused) as refusal:
        write_head_search_restarts(
            run_root=fixture["run_root"],
            ownership_receipt=fixture["gate"],
            runtime=runtime_identity(),
            approved_bundle_sha256="c" * 64,
            seal=SEAL,
            workdir=tmp_path / "work",
            run_anchor=fixture["run_anchor"],
            producer={"entry": "x", "argv_sha256": SHA},
        )
    assert refusal.value.code == RESTART_TEARDOWN_UNPROVEN
    assert fixture["log"] == ["anchor:default", "anchor:left"]
    assert (fixture["run_root"] / "default" / module.ARTIFACT_BY_ANCHOR["default"]).is_file()
    assert not (fixture["run_root"] / "forward").exists()


def test_producer_refuses_a_runtime_that_never_falls_back_to_the_cpu():
    with pytest.raises(RestartRefused) as refusal:
        module.require_runtime_of_record(runtime_identity(allow_cpu_fallback=True))
    assert refusal.value.code == RESTART_RUNTIME_UNVERIFIED
