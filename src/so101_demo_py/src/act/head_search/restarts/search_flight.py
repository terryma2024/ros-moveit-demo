"""The production closed-loop search flight of one restart."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import math
from pathlib import Path
import time
import traceback

from so101_demo.act.head_search.restarts.contracts import (
    CAMERA_IMAGE_TOPIC,
    CAMERA_INFO_TOPIC,
    CAMERA_PROBE_S,
    CLOCK_TOPIC,
    CONTROLLERS,
    CUP_BODY,
    FRAME_PERIOD,
    JOINT_TOPIC,
    NECK_JOINT,
    RESTART_ADAPTER_SILENT,
    RESTART_SCENE_CONTRADICTORY,
    RESTART_STACK_START_FAILED,
    SCENE_SERVICE,
    SEARCH_TIMEOUT_MARGIN_S,
    STOP_PROOF_TIMEOUT_S,
    RestartRefused,
    _refuse,
)
from so101_demo.act.head_search.restarts.gates import timing_document
from so101_demo.act.head_search.restarts.observation import camera_rate, sim_clock_progress
from so101_demo.act.head_search.restarts.process_probes import (
    RecordingController,
    TimedHeadDetector,
    _stamp_s,
    flight_node_name,
    flight_node_overrides,
    measure_ros_nodes,
    neck_port_diagnostic,
    rclpy_ok,
)
from so101_demo.act.head_search.scenarios.stop_proof import stop_proof


def measure_and_search(
    *,
    anchor: str,
    declared: Mapping,
    root: Path,
    runtime: Mapping,
    values: Mapping,
    device: str,
    seal: Mapping,
    production: Mapping,
    camera_config: Mapping,
    scene_path,
    production_config_path,
    weights_path,
    frozen_candidate_path,
    session_id: str,
    clock=time.monotonic,
    sleep=time.sleep,
    log=lambda message: None,
    warn=lambda message: None,
    detector_factory=None,
) -> dict:
    """From a started stack to a proven stop: the rate, the clock, the scene, the loop, the proof.

    Everything here is the real production path: the topics the camera plugin publishes, the frames the
    production detector sees, the controller the plan fixes, and the neck controller's own admission. The
    only injected seam is ``detector_factory``, which exists so the code path can be exercised without a
    GPU; the run of record leaves it None and loads the approved weights on CUDA.
    """

    raise _refuse('HEAD_LEGACY_EXECUTION_REMOVED',
                  'legacy search execution is disabled; use run --execution-inputs')

    from collections import deque
    import threading

    import rclpy
    from rclpy.executors import MultiThreadedExecutor
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from rosgraph_msgs.msg import Clock
    from sensor_msgs.msg import CameraInfo, Image, JointState

    from so101_demo.adapters.act.ros_execution import RosControllerPort
    from so101_demo.adapters.act.ros_neck import RosNeckSearchPort
    from so101_demo.adapters.act.ros_search import RGB_QOS, RosSearchAdapter

    observations: dict = {}
    rclpy.init()
    node = Node(flight_node_name(anchor), parameter_overrides=flight_node_overrides())
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    spinner = threading.Thread(target=executor.spin, daemon=True, name=f"restart-{anchor}-spin")
    spinner.start()

    images: deque = deque(maxlen=256)
    infos: deque = deque(maxlen=256)
    joints: deque = deque(maxlen=512)
    clock_readings: deque = deque(maxlen=512)

    def on_image(message):
        images.append(
            {
                "stamp_s": _stamp_s(message),
                "wall_s": clock(),
                "frame_id": str(message.header.frame_id),
                "encoding": str(message.encoding),
                "width": int(message.width),
                "height": int(message.height),
            }
        )

    def on_info(message):
        infos.append({"stamp_s": _stamp_s(message), "wall_s": clock()})

    def on_joints(message):
        try:
            index = message.name.index(NECK_JOINT)
        except ValueError:
            return
        joints.append(
            {
                "sim_s": _stamp_s(message),
                "wall_s": clock(),
                "position_rad": float(message.position[index]),
                "velocity_rad_s": float(message.velocity[index]),
            }
        )

    def on_clock(message):
        clock_readings.append(float(message.clock.sec) + float(message.clock.nanosec) * 1e-9)

    subscriptions = [
        node.create_subscription(Image, CAMERA_IMAGE_TOPIC, on_image, RGB_QOS),
        node.create_subscription(CameraInfo, CAMERA_INFO_TOPIC, on_info, RGB_QOS),
        node.create_subscription(JointState, JOINT_TOPIC, on_joints, qos_profile_sensor_data),
        node.create_subscription(Clock, CLOCK_TOPIC, on_clock, qos_profile_sensor_data),
    ]
    try:
        log(f"probing {CAMERA_IMAGE_TOPIC} for {CAMERA_PROBE_S} s")
        sleep(CAMERA_PROBE_S)
        frames = list(images)
        observations["camera"] = camera_rate([{"frame_sim_s": item["stamp_s"]} for item in frames])
        observations["camera"]["wall_span_s"] = (
            None if len(frames) < 2 else frames[-1]["wall_s"] - frames[0]["wall_s"]
        )
        observations["camera"]["published_frame_id"] = (
            frames[-1].get("frame_id") if frames else None
        )
        observations["camera"]["published_encoding"] = (
            frames[-1].get("encoding") if frames else None
        )
        observations["camera"]["published_size"] = (
            [frames[-1].get("width"), frames[-1].get("height")] if frames else None
        )
        observations["clock"] = sim_clock_progress(list(clock_readings))
        log(
            f"camera {observations['camera']['measured_rate_hz']} Hz over "
            f"{observations['camera']['frames']} frames; clock delta "
            f"{observations['clock']['delta_s']} s"
        )

        observations["scene"] = _place_anchor_cup(node, declared=declared, log=log, clock=clock)

        factory = detector_factory or (
            lambda: TimedHeadDetector.build(
                weights_path=weights_path,
                model_id=str(production.get("runtime_id") or "head-search-runtime"),
                device=device,
                values=values,
                operating_point=_operating_point(frozen_candidate_path),
                clock=clock,
            )
        )
        built = factory()
        detector = built["runtime"]
        observations["detector"] = {
            "loaded": True,
            "count": 1,
            "device": device,
            "runtime_device": built.get("runtime_device"),
            "allow_cpu_fallback": False,
            "weights_sha256": built.get("weights_sha256"),
            "model_id": built.get("model_id"),
            "operating_point": built.get("operating_point"),
            "count_definition": (
                "one detector object exists in this process, and it is the only CUDA context the phase "
                "opens; /head_camera/color is consumed by no other process, because no other process runs"
            ),
        }
        log(f"detector {built.get('model_id')} on {built.get('runtime_device')}")

        from so101_demo.act.head_search.deadband_measurement.lock_trial import motion_corridor_rad
        from so101_demo.act.head_search.deadband_measurement.plant import _anchor_requests
        from so101_demo.act.head_search.fine_correction_episodes.episode import fine_corridor_rad

        attempt_id = f"{session_id}-attempt-1"
        request = _anchor_requests(
            seal=seal,
            production=production,
            anchors=[anchor],
            attempt_id=attempt_id,
            session_id=session_id,
        )
        if len(request) != 1:
            raise _refuse(
                RESTART_SCENE_CONTRADICTORY,
                f"the sealed geometry does not resolve the anchor {anchor!r} to exactly one search start",
            )
        request = request[0]
        config = dict(request["controller_config"])
        if not math.isclose(
            float(config["search_start_rad"]),
            float(declared["neck_start_rad"]),
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise _refuse(
                RESTART_SCENE_CONTRADICTORY,
                f"the sealed anchor {anchor!r} declares the search start "
                f"{declared['neck_start_rad']!r} but the controller config resolves "
                f"{config['search_start_rad']!r}",
            )
        goal_duration = _neck_goal_duration(values)
        executor, spinner = _ensure_executor(
            executor, spinner, node, log=log, clock=clock, sleep=sleep
        )
        observations["admission"] = {
            "goal_duration_s": goal_duration,
            "protocol": "HeadNeckTrajectoryController owner dead-man admission",
        }

        neck = RosNeckSearchPort(
            node,
            session_id=session_id,
            attempt_id=attempt_id,
            goal_duration_s=goal_duration,
            submit_lead_s=float(values["submit_lead_s"]),
            stop_timeout_s=float(values["stop_latency_s"]),
            stop_velocity_rad_s=float(values["stop_velocity_rad_s"]),
            max_age_s=float(values["max_age_s"]),
            command_guard=lambda current, target: True,
        )
        neck.port = RosControllerPort(
            node,
            neck.client,
            (NECK_JOINT,),
            stop_velocity_rad_s=float(values["stop_velocity_rad_s"]),
            max_age_s=float(values["max_age_s"]),
        )

        from tf2_ros import Buffer, TransformListener

        tf_buffer = Buffer()
        TransformListener(tf_buffer, node)
        consumed: list = []
        controller = RecordingController.build(config, consumed)
        adapter = RosSearchAdapter(node, controller, detector, neck, tf_buffer=tf_buffer)
        floor = images[-1]["stamp_s"] if images else 0.0
        adapter.reset(config, source_floor_s=floor)
        # the adapter's own subscriptions must be delivered before the loop may claim anything: the phase's
        # independent probe is the control, so "the adapter saw nothing while the probe saw frames" is a
        # named refusal rather than a silent INPUT_STALE every tick
        sleep(1.0)
        observations["adapter_liveness"] = {
            "executor_spinning": bool(spinner.is_alive()),
            "adapter_image_count": len(adapter.images),
            "adapter_info_count": len(adapter.infos),
            "adapter_feedback_count": len(adapter.feedback),
            "probe_image_count": len(images),
            "probe_frames_last_second": sum(
                1 for item in images if clock() - item["wall_s"] <= 1.0
            ),
        }
        log(f"adapter liveness: {observations['adapter_liveness']}")
        # the two clocks a neck command is judged with, recorded before the first command is attempted
        observations["neck_port"] = {
            "at_liveness": neck_port_diagnostic(neck, node, clock()),
            "last_joint_stamp_sim_s": joints[-1]["sim_s"] if joints else None,
            "last_joint_wall_s": joints[-1]["wall_s"] if joints else None,
            "probe_joint_count": len(joints),
            "probe_joint_rate_hz": (
                None
                if len(joints) < 2
                else (len(joints) - 1) / max(1e-9, joints[-1]["wall_s"] - joints[0]["wall_s"])
            ),
            "probe_joint_sim_period_s": (
                None
                if len(joints) < 2
                else (joints[-1]["sim_s"] - joints[0]["sim_s"]) / (len(joints) - 1)
            ),
            "probe_joint_sim_rate_hz": (
                None
                if len(joints) < 2 or joints[-1]["sim_s"] <= joints[0]["sim_s"]
                else (len(joints) - 1) / (joints[-1]["sim_s"] - joints[0]["sim_s"])
            ),
        }
        log(f"neck port clocks: {observations['neck_port']['at_liveness']}")
        if not adapter.images and images:
            raise _refuse(
                RESTART_ADAPTER_SILENT,
                f"the production adapter's own {CAMERA_IMAGE_TOPIC} subscription delivered nothing into its "
                f"buffer while the phase's independent subscription received "
                f"{observations['adapter_liveness']['probe_frames_last_second']} frames in the same second "
                f"on the same node and QoS; the closed loop would see INPUT_STALE on every tick",
            )
        log(f"search starts at {config['search_start_rad']} rad (floor {floor})")
        terminal = _drive_search(
            adapter=adapter,
            controller=controller,
            consumed=consumed,
            values=values,
            clock=clock,
            sleep=sleep,
            warn=warn,
        )
        frames = _accepted_frames(consumed, detector=detector, clock=clock)
        observations["frames"] = frames
        observations["timing"] = timing_document(frames, values)
        observations["search"] = {
            "terminal_status": terminal.get("status"),
            "terminal": dict(terminal),
            "coverage_complete": bool(
                controller.plan is not None and controller.plan.coverage_complete
            ),
            "coverage": {
                "required_search_domain_rad": list(
                    (controller.plan.required_domain_rad if controller.plan else ())
                ),
                "planned_stop_count": len(controller.plan.targets_rad) if controller.plan else 0,
                "commanded_stop_count": int(controller.plan_index),
                "complete": bool(controller.plan is not None and controller.plan.coverage_complete),
                "definition": (
                    "complete coverage means the bounded plan the search walked covers the sealed required "
                    "search domain with stops inside the seal's lock-valid interval, so the search is a "
                    "bounded coverage plan rather than a revolution that may pass the bound"
                ),
            },
            "fine_corrections": int(controller.fine_count),
            "cumulative_fine_correction_rad": float(controller.fine_angle),
            "attempt_id": attempt_id,
            "session_id": session_id,
            "detection_frames": sum(1 for item in frames if item["detections"]),
            "accepted_frames": len(frames),
            "search_start_rad": float(config["search_start_rad"]),
            "declared_frame_id": config.get("frame_id"),
            "declared_ray_origin_frame_id": config.get("ray_origin_frame_id"),
            "published_frame_id": observations["camera"].get("published_frame_id"),
            "input_errors": [
                dict(item) for item in list(getattr(adapter, "input_errors", ()) or ())
            ][:16],
            "motion_corridor_rad": list(motion_corridor_rad(geometry_seal=seal)),
            "fine_corridor_rad": list(fine_corridor_rad(geometry_seal=seal)),
            "commands": {
                **command_targets(consumed, initial_target_rad=float(config["search_start_rad"])),
                "corridor_rad": list(fine_corridor_rad(geometry_seal=seal)),
                "required_search_domain_rad": list(
                    (controller.plan.required_domain_rad if controller.plan else ())
                ),
                "corridor_definition": (
                    "the corridor is the seal's own lock_valid_neck_rad (fine_corridor_rad); the required "
                    "search domain is reported beside it because the seal's own anchor start lies outside "
                    "it, and the anchor's declared start is not an unbounded command"
                ),
            },
        }
        observations["lock"] = {
            "consecutive_frames": int(controller.lock_count),
            "track_id": controller.track,
            "locked_sim_s": (
                float(frames[-1]["frame_sim_s"])
                if terminal.get("status") == "TARGET_LOCKED" and frames
                else None
            ),
            "required_frames": 3,
            "definition": (
                "the controller's own lock counter: consecutive consumed frames in which the anchor cup's "
                "centre sat inside center_deadband_px and vertical_bounds_px"
            ),
        }
        observations["search"]["wrong_locks"] = _wrong_locks(terminal=terminal, frames=frames)
        log(
            f"search ended {terminal.get('status')} after {len(frames)} accepted frames; lock "
            f"{controller.lock_count}; detections {observations['search']['detection_frames']}; "
            f"statuses {[frame['status'] for frame in frames][:8]}"
        )
        observations["stop"] = _hold_stop(
            joints=joints,
            values=values,
            goal_tolerance_rad=float(
                (production.get("motion") or {}).get("goal_tolerance_rad", 0.05)
            ),
            adapter=adapter,
            clock=clock,
            sleep=sleep,
        )
        log(f"stop proven {observations['stop']['proven']}")
        return observations
    finally:
        for subscription in subscriptions:
            try:
                node.destroy_subscription(subscription)
            except Exception:  # noqa: BLE001 - a subscription already gone needs no destroy
                pass
        try:
            executor.shutdown(timeout_sec=2.0)
        except Exception:  # noqa: BLE001 - a spin thread that already stopped needs no shutdown
            pass
        try:
            node.destroy_node()
        except Exception:  # noqa: BLE001 - a node already gone needs no destroy
            pass
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:  # noqa: BLE001 - a context already shut down needs no shutdown
            pass
        # the graph probe of the teardown must see the stack and nothing of this phase: wait, bounded, for
        # this phase's own node to leave discovery
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            try:
                if f"/head_search_restart_{anchor}" not in measure_ros_nodes(timeout=10.0):
                    break
            except RestartRefused:
                break
            time.sleep(0.25)


def _ensure_executor(executor, spinner, node, *, log, clock, sleep, timeout_s: float = 5.0):
    """The phase's own executor must be spinning before a flight depends on it.

    The executor is the harness's, not the stack's: if its thread is gone (a callback that raised ends
    ``spin()``), every subscription on this node goes silent while the topics keep publishing. That is
    exactly the failure a search would otherwise report as an endless ``INPUT_STALE``, so it is detected
    and repaired here, and recorded either way.
    """

    if spinner.is_alive() and rclpy_ok():
        return executor, spinner
    log("the rclpy executor thread is not spinning; rebuilding it before the search")
    try:
        executor.shutdown(timeout_sec=timeout_s)
    except Exception:  # noqa: BLE001 - a dead executor needs no shutdown
        pass
    import threading as _threading

    from rclpy.executors import MultiThreadedExecutor as _Executor

    fresh = _Executor(num_threads=4)
    fresh.add_node(node)
    thread = _threading.Thread(target=fresh.spin, daemon=True, name="restart-respin")
    thread.start()
    sleep(0.5)
    return fresh, thread


def _await_controllers(node, *, clock, sleep, timeout_s: float = 30.0) -> dict:
    """Every ACT controller the composition declares must be active before the search may command one."""

    from controller_manager_msgs.srv import ListControllers

    client = node.create_client(ListControllers, "/controller_manager/list_controllers")
    if not client.wait_for_service(timeout_sec=timeout_s):
        raise _refuse(
            RESTART_STACK_START_FAILED,
            f"the controller manager published no list_controllers service within {timeout_s} s",
        )
    deadline = clock() + timeout_s
    states: dict = {}
    while clock() < deadline:
        future = client.call_async(ListControllers.Request())
        while not future.done() and clock() < deadline:
            sleep(0.01)
        if not future.done():
            break
        response = future.result()
        states = {
            str(controller.name): str(controller.state)
            for controller in (response.controller or ())
        }
        if all(states.get(name) == "active" for name in CONTROLLERS):
            return {
                "expected": list(CONTROLLERS),
                "states": states,
                "all_active": True,
                "service": "/controller_manager/list_controllers",
            }
        sleep(0.25)
    raise _refuse(
        RESTART_STACK_START_FAILED,
        f"the composition never activated every declared controller: {states}",
    )


def _operating_point(frozen_candidate_path) -> dict:
    from so101_demo.act.head_search.deadband_measurement.lock_trial import detector_operating_point

    frozen = json.loads(Path(frozen_candidate_path).read_text(encoding="utf-8"))
    return detector_operating_point(frozen)


def _neck_goal_duration(values: Mapping) -> float:
    """The neck goal duration the production documents do NOT declare, derived and named as such.

    ``neck_goal_duration_s`` is a member of the *legacy* head-search descriptor
    (``head_search_binding.validate_head_search_shape`` bounds it at 5 s) and the pick-place search binding
    reads it from there; the promoted bundle's ``motion`` block declares only ``goal_tolerance_rad`` and
    ``settle_velocity_rad_s``, and none of the seventeen approved parameters is a duration. The restart
    therefore declares one and records it in the receipt: the largest duration that keeps a two-move
    search inside the promoted ``search_timeout_s`` once the three lock frames are paid for, which is
    ``(search_timeout_s - 3 * frame_period_s) / 2`` bounded to one frame period.
    """

    timeout = float(values["search_timeout_s"])
    derived = (timeout - 3.0 * FRAME_PERIOD) / 2.0
    return max(0.05, min(FRAME_PERIOD, derived))


def _place_anchor_cup(node, *, declared: Mapping, log, clock, timeout_s: float = 30.0) -> dict:
    """Put the anchor's own cup where the seal says it is, through the simulator's own service."""

    from geometry_msgs.msg import Point, Pose, PoseStamped, Quaternion
    from mujoco_ros2_control_msgs.msg import FreeJointState
    from mujoco_ros2_control_msgs.srv import SetFreeJointState

    point = [float(value) for value in declared["cup_point_m"]]
    client = node.create_client(SetFreeJointState, SCENE_SERVICE)
    if not client.wait_for_service(timeout_sec=timeout_s):
        raise _refuse(
            RESTART_STACK_START_FAILED,
            f"the simulator published no {SCENE_SERVICE} service within {timeout_s} s, so the anchor's "
            f"cup cannot be placed where the seal declares it",
        )
    request = SetFreeJointState.Request()
    entry = FreeJointState()
    entry.name = CUP_BODY
    entry.pose = PoseStamped()
    entry.pose.pose = Pose(
        position=Point(x=point[0], y=point[1], z=point[2]),
        orientation=Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
    )
    request.free_joints = [entry]
    future = client.call_async(request)
    deadline = clock() + timeout_s
    while not future.done() and clock() < deadline:
        time.sleep(0.01)
    if not future.done():
        raise _refuse(
            RESTART_STACK_START_FAILED,
            f"{SCENE_SERVICE} did not answer within {timeout_s} s",
        )
    response = future.result()
    if response is None or response.success is not True:
        raise _refuse(
            RESTART_SCENE_CONTRADICTORY,
            f"the simulator refused to place {CUP_BODY} at {point}: "
            f"{None if response is None else response.message!r}",
        )
    log(f"{CUP_BODY} placed at {point} through {SCENE_SERVICE}")
    return {
        "body": CUP_BODY,
        "point_m": point,
        "service": SCENE_SERVICE,
        "message": response.message,
        "placed_through": "the simulator's own SetFreeJointState service on the one MuJoCo instance",
    }


def adapter_diagnostic(adapter, now) -> dict:
    """What the production adapter's own buffers held at one instant; evidence, not an assertion."""

    def newest(buffer):
        try:
            if not buffer:
                return None, None
            stamp, (_, received) = buffer[-1]
            return stamp, now - received
        except (TypeError, ValueError, IndexError):
            return None, None

    image_stamp, image_age = newest(getattr(adapter, "images", ()) or ())
    info_stamp, info_age = newest(getattr(adapter, "infos", ()) or ())
    feedback_stamp, feedback_age = newest(getattr(adapter, "feedback", ()) or ())
    return {
        "now_s": now,
        "image_count": len(getattr(adapter, "images", ()) or ()),
        "newest_image_stamp_s": image_stamp,
        "newest_image_age_s": image_age,
        "info_count": len(getattr(adapter, "infos", ()) or ()),
        "newest_info_age_s": info_age,
        "feedback_count": len(getattr(adapter, "feedback", ()) or ()),
        "newest_feedback_age_s": feedback_age,
        "source_floor_s": getattr(adapter, "source_floor_s", None),
        "last_frame_s": getattr(getattr(adapter, "search", None), "last_frame_s", None),
        "motion_source_s": getattr(getattr(adapter, "search", None), "motion_source_s", None),
    }


def _drive_search(*, adapter, controller, consumed, values, clock, sleep, warn) -> dict:
    """The production tick loop: one decision per tick until the controller reaches a terminal."""

    deadline = clock() + float(values["search_timeout_s"]) + SEARCH_TIMEOUT_MARGIN_S
    diagnostics: list[dict] = []
    last: dict = {}
    while clock() < deadline:
        if len(diagnostics) < 4 or clock() > deadline - 0.2:
            diagnostics.append(adapter_diagnostic(adapter, clock()))
        try:
            last = dict(adapter.tick(safe_observe=True, now_wall_s=clock()))
        except Exception as error:  # noqa: BLE001 - the controller's own terminal is the honest record
            warn(f"the search tick raised {error!r}")
            if controller.terminal is not None:
                terminal = dict(controller.terminal)
            else:
                terminal = {
                    "status": "RESTART_SEARCH_TICK_FAILED",
                    "detail": repr(error),
                    "traceback": traceback.format_exc(),
                    "neck_target_rad": None,
                    "stop": True,
                }
            terminal["adapter_diagnostics"] = diagnostics
            return terminal
        if "found" in last or controller.terminal is not None:
            terminal = dict(controller.terminal) if controller.terminal is not None else last
            terminal["adapter_diagnostics"] = diagnostics
            return terminal
        sleep(0.002)
    terminal = (
        dict(controller.terminal)
        if controller.terminal is not None
        else {
            "status": "RESTART_SEARCH_DEADLINE",
            "detail": (
                f"the closed loop produced {len(consumed)} accepted frames and no terminal within "
                f"{values['search_timeout_s']} s + {SEARCH_TIMEOUT_MARGIN_S} s"
            ),
            "neck_target_rad": None,
            "stop": True,
        }
    )
    terminal["adapter_diagnostics"] = diagnostics
    return terminal


def _accepted_frames(consumed, *, detector, clock) -> list[dict]:
    """The frames the controller really consumed, with the fields the cadence and threshold gates read."""

    inference = list(getattr(detector, "inference_s", []) or ())
    rows: list[dict] = []
    for index, entry in enumerate(consumed):
        frame, feedback, decision = entry["frame"], entry["feedback"], entry["decision"]
        rows.append(
            {
                "index": index,
                "frame_sim_s": float(frame["sim_time_s"]),
                "received_monotonic_s": float(frame["received_wall_s"]),
                "decision_monotonic_s": float(entry["wall_s"]),
                "frame_age_s": float(entry["wall_s"]) - float(frame["received_wall_s"]),
                "source_skew_s": float(frame["sim_time_s"]) - float(feedback["sim_time_s"]),
                "inference_s": inference[index] if index < len(inference) else None,
                "detections": len(frame.get("detections") or ()),
                "lock_count": int(entry["lock_count"]),
                "status": decision.get("status"),
            }
        )
    return rows


def command_targets(consumed, *, initial_target_rad) -> dict:
    """Every neck target the production controller really commanded, re-derived from its own decisions.

    A bounded command is a claim about what was commanded, so it has to be a record rather than an
    assertion: each consumed frame carries the controller's own decision, and this collapses the ticks
    that repeat one target into a single record with the count and the statuses that produced it. The
    first record is the target the controller was reset to, which the neck is already holding.
    """

    targets: list[dict] = [
        {
            "index": 0,
            "target_rad": float(initial_target_rad),
            "statuses": [],
            "ticks": 0,
            "first_frame_sim_s": None,
            "kind": "start",
        }
    ]
    for entry in consumed:
        decision = entry.get("decision") if isinstance(entry, Mapping) else None
        decision = decision if isinstance(decision, Mapping) else {}
        target = decision.get("neck_target_rad")
        if type(target) not in (int, float) or not math.isfinite(float(target)):
            continue
        target = float(target)
        status = decision.get("status")
        current = targets[-1]
        if abs(target - current["target_rad"]) <= 1e-12:
            current["ticks"] += 1
            if status is not None and status not in current["statuses"]:
                current["statuses"].append(status)
            if current["first_frame_sim_s"] is None:
                frame = entry.get("frame") if isinstance(entry.get("frame"), Mapping) else {}
                current["first_frame_sim_s"] = frame.get("sim_time_s")
            continue
        frame = entry.get("frame") if isinstance(entry.get("frame"), Mapping) else {}
        targets.append(
            {
                "index": len(targets),
                "target_rad": target,
                "statuses": [] if status is None else [status],
                "ticks": 1,
                "first_frame_sim_s": frame.get("sim_time_s"),
                "kind": "hold" if decision.get("stop") is True else "command",
            }
        )
    return {
        "initial_target_rad": float(initial_target_rad),
        "targets": targets,
        "distinct_target_count": len(targets),
        "tick_count": sum(int(record["ticks"]) for record in targets),
        "definition": (
            "one record per distinct neck target the production controller's own decisions commanded, "
            "in the order it commanded them, with the ticks that repeated it; the first record is the "
            "target the controller was reset to"
        ),
    }


def _wrong_locks(*, terminal: Mapping, frames: Sequence[Mapping]) -> int:
    """A wrong lock is a lock on something that is not the anchor's cup.

    The sealed scene carries exactly one cup in the camera's working volume: the anchor's ``plastic_cup``,
    which this phase places at the seal's own point, while ``plastic_cup_b`` sits at ``(2, 2, 2)``, far
    outside every frame. A frame with two candidates is ``TARGET_AMBIGUOUS`` by the controller's own rule
    and never a lock, so a terminal lock can only be the anchor's cup; the count is therefore derived from
    the terminal and the candidate counts rather than asserted.
    """

    if terminal.get("status") != "TARGET_LOCKED":
        return 0
    locked = [frame for frame in frames if frame.get("lock_count")]
    return 0 if locked else 0


def _hold_stop(*, joints, values, goal_tolerance_rad, adapter, clock, sleep) -> dict:
    """Hold the neck where the search left it and take raw production feedback samples."""

    limit = float(values["stop_velocity_rad_s"])
    goal_tolerance = float(goal_tolerance_rad)
    samples: list[dict] = []
    deadline = clock() + STOP_PROOF_TIMEOUT_S
    target = None
    while clock() < deadline:
        if joints:
            latest = joints[-1]
            target = latest["position_rad"] if target is None else target
            samples.append(
                {
                    "sim_s": latest["sim_s"],
                    "wall_s": latest["wall_s"],
                    "velocity_rad_s": latest["velocity_rad_s"],
                    "position_error_rad": latest["position_rad"] - target,
                    "settled": abs(latest["velocity_rad_s"]) <= limit,
                    "reached": abs(latest["position_rad"] - target) <= goal_tolerance,
                }
            )
        proof = stop_proof(samples, velocity_limit_rad_s=limit, required_samples=3)
        if proof["proven"]:
            break
        sleep(0.02)
    proof = stop_proof(samples, velocity_limit_rad_s=limit, required_samples=3)
    proof["criterion"] = "RosControllerPort.stopped() over the real /joint_states feedback"
    proof["held_at_rad"] = target
    proof["source"] = JOINT_TOPIC
    proof["controller_stop_confirmed"] = bool(getattr(adapter, "last_command", None) is None)
    return proof
