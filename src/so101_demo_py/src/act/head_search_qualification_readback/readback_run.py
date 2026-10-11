"""The live readback observation and the readback writer."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import json
import math
import os
from pathlib import Path
import time

from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search_measured_readback import (
    NOT_OBSERVABLE,
)
from so101_demo.act.head_search_qualification_readback.observations import (
    ARTIFACT,
    BASE_FRAME,
    CAMERA_FRAME,
    CAMERA_SOURCES,
    IMAGE_TOPIC,
    KIND,
    PHASE,
    READBACK_COMPONENT_UNBUILDABLE,
    READBACK_DETECTOR_FAILED,
    READBACK_FOREIGN_OWNER_ACTIVE,
    READBACK_GPU_NOT_RELEASED,
    READBACK_OWNERSHIP_MISMATCH,
    READBACK_OWNERSHIP_REFUSED,
    READBACK_PROBE_FAILED,
    READBACK_RUN_ROOT_EXISTS,
    READBACK_RUNTIME_UNVERIFIED,
    READBACK_STACK_START_FAILED,
    READBACK_TEARDOWN_UNPROVEN,
    RUNNER_GRAPH_NODE,
    RUNNER_NODE,
    RUNNING_STACK_OBSERVATION,
    SCHEMA_VERSION,
    SESSION_ID,
    STDERR_LOG,
    STDOUT_LOG,
    TEARDOWN_ARTIFACT,
    TEARDOWN_FACTS,
    _digest,
    _refuse,
    _utc_now,
    _write,
    approved_values,
    camera_measurement_records,
    observe_qualification_values,
    readback_document,
)
from so101_demo.act.head_search_restarts.contracts import (
    CAMERA_INFO_TOPIC,
    CAMERA_PROBE_S,
    JOINT_TOPIC,
    RESTART_OWNERSHIP_MISMATCH,
    RESTART_OWNERSHIP_REFUSED,
    RESTART_RUNTIME_UNVERIFIED,
)
from so101_demo.act.head_search_restarts.gates import stack_environment
from so101_demo.act.head_search_restarts.observation import (
    read_ownership_receipt,
    require_runtime_of_record,
    teardown_proof,
)
from so101_demo.act.head_search_restarts.process_probes import probe_owners
from so101_demo.perception_benchmark.contracts import canonical_sha256


def _stamp_s(message) -> float:
    return float(message.header.stamp.sec) + float(message.header.stamp.nanosec) * 1e-9


def _zyx_from_quaternion(quaternion) -> list[float]:
    """The pick-place calibration contract's fixed decomposition: ZYX, in (-pi, pi]."""

    x, y, z, w = (float(value) for value in quaternion)
    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr_cosp, cosr_cosp)
    sinp = 2.0 * (w * y - z * x)
    pitch = math.copysign(math.pi / 2.0, sinp) if abs(sinp) >= 1.0 else math.asin(sinp)
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(siny_cosp, cosy_cosp)
    return [roll, pitch, yaw]


def _wrap_pi(angle: float) -> float:
    wrapped = math.fmod(angle + math.pi, 2.0 * math.pi)
    if wrapped <= 0.0:
        wrapped += 2.0 * math.pi
    return wrapped - math.pi


def _camera_measurements_from_live(*, infos, frames, transform, joints) -> dict:
    """The four camera measurements, derived from what the running stack published.

    ``transform`` is the ``base -> head_camera_frame`` sample the running description's TF served, or the
    reason it could not be looked up. Nothing is defaulted: a source that published nothing yields
    ``not_observable`` with that reason and a null value.
    """

    from statistics import median

    live: dict[str, dict] = {}
    if infos:
        rows = [
            [float(row["k"][0]), float(row["k"][4]), float(row["k"][2]), float(row["k"][5])]
            for row in infos
            if isinstance(row.get("k"), (list, tuple)) and len(row["k"]) >= 6
        ]
        if rows:
            value = [float(median([row[index] for row in rows])) for index in range(4)]
            live["head_intrinsics_px"] = {
                "value": value,
                "observation": RUNNING_STACK_OBSERVATION,
                "component": f"the running camera plugin, {CAMERA_INFO_TOPIC}",
                "source": CAMERA_SOURCES["head_intrinsics_px"],
                "derivation": "per-component median of [K00, K11, K02, K12] over the valid frames",
                "raw": {
                    "frames": len(rows),
                    "width": rows and infos[-1].get("width"),
                    "height": rows and infos[-1].get("height"),
                    "samples": rows[:8],
                    "frame_id": infos[-1].get("frame_id"),
                },
            }
        else:
            live["head_intrinsics_px"] = {
                "value": None,
                "observation": NOT_OBSERVABLE,
                "reason": f"{CAMERA_INFO_TOPIC} published no distortion-free K this readback could read",
            }
    else:
        live["head_intrinsics_px"] = {
            "value": None,
            "observation": NOT_OBSERVABLE,
            "reason": f"the running stack published no {CAMERA_INFO_TOPIC} within {CAMERA_PROBE_S} s",
        }

    if frames and not infos:
        live["head_intrinsics_px"]["reason"] = (
            f"the running stack published {len(frames)} {IMAGE_TOPIC} frames but no "
            f"{CAMERA_INFO_TOPIC}, so the intrinsics were not observed"
        )
    neck = [row["position_rad"] for row in joints if row.get("name") == "neck_yaw_joint"]
    context = {
        "camera_frames": len(frames),
        "camera_info_frames": len(infos),
        "neck_yaw_rad": neck[-1] if neck else None,
        "tf_sample": transform,
    }
    if not isinstance(transform, Mapping) or transform.get("error"):
        reason = (
            transform.get("error")
            if isinstance(transform, Mapping)
            else f"no {BASE_FRAME} -> {CAMERA_FRAME} transform was looked up"
        )
        for name in ("head_translation_m", "head_rpy_rad", "yaw_zero_bearing_rad"):
            live[name] = {
                "value": None,
                "observation": NOT_OBSERVABLE,
                "source": CAMERA_SOURCES[name],
                "reason": f"the running description served no {BASE_FRAME} -> {CAMERA_FRAME} transform: "
                f"{reason}",
                "raw": context,
            }
        return live
    translation = [float(value) for value in transform["translation_m"]]
    quaternion = [float(value) for value in transform["quaternion_xyzw"]]
    rpy = _zyx_from_quaternion(quaternion)
    x, y, z, w = quaternion
    forward = [
        2.0 * (x * z + w * y),
        2.0 * (y * z - w * x),
        1.0 - 2.0 * (x * x + y * y),
    ]
    bearing = _wrap_pi(math.atan2(forward[1], forward[0]))
    live["head_translation_m"] = {
        "value": translation,
        "observation": RUNNING_STACK_OBSERVATION,
        "component": f"the running robot description's TF, {BASE_FRAME} -> {CAMERA_FRAME}",
        "source": CAMERA_SOURCES["head_translation_m"],
        "derivation": "the transform's translation, in metres",
        "raw": {**context, "quaternion_xyzw": quaternion},
    }
    live["head_rpy_rad"] = {
        "value": rpy,
        "observation": RUNNING_STACK_OBSERVATION,
        "component": f"the running robot description's TF, {BASE_FRAME} -> {CAMERA_FRAME}",
        "source": CAMERA_SOURCES["head_rpy_rad"],
        "derivation": "ZYX decomposition of the transform's normalised quaternion, wrapped to (-pi, pi]",
        "raw": {**context, "quaternion_xyzw": quaternion},
    }
    live["yaw_zero_bearing_rad"] = {
        "value": bearing,
        "observation": RUNNING_STACK_OBSERVATION,
        "component": f"the running robot description's TF, {BASE_FRAME} -> {CAMERA_FRAME}",
        "source": CAMERA_SOURCES["yaw_zero_bearing_rad"],
        "derivation": "wrap_pi(atan2(a_y, a_x)) with a = R * [0, 0, 1] the optical forward axis",
        "raw": {**context, "forward_axis": forward},
    }
    return live


def prepare_deadman_directory(controller_config_path) -> str:
    """The private dead-man directory the sealed controllers file declares for the neck, created.

    The neck controller refuses to activate without it (design section 1.4), so the readback creates it
    (mode 0700, owned by this process) before the stack starts. An undeclared directory, or one whose
    socket path would exceed the AF_UNIX bound, is a refusal, never a default.
    """

    from so101_demo.adapters.act.head_neck_owner import HeadNeckOwner
    from so101_demo.adapters.act.head_neck_owner_build import deadman_directory_from_controllers

    try:
        directory = HeadNeckOwner.ensure_directory(deadman_directory_from_controllers(controller_config_path))
    except Exception as error:  # noqa: BLE001 - an undeclared directory is a refusal, not a default
        raise _refuse(
            READBACK_PROBE_FAILED,
            f"the controller configuration declares no usable dead-man directory: "
            f"{type(error).__name__}: {error}",
        ) from error
    if len(os.fsencode(os.path.join(directory, "neck-18446744073709551615.sock"))) > 107:
        raise _refuse(
            READBACK_PROBE_FAILED,
            f"the AF_UNIX dead-man sockets under {directory} exceed the 107-byte bound",
        )
    return str(directory)


def run_readback_observation(
    *,
    run_root=None,
    evidence_root,
    workdir,
    production: Mapping,
    seal: Mapping,
    anchor: str,
    production_config_path,
    urdf_path,
    scene_path,
    plugin_config_path,
    controller_config_path,
    weights_path,
    device: str = "cuda",
    runtime: Mapping | None = None,
    values: Mapping | None = None,
    stdout=None,
    stderr=None,
    clock=time.monotonic,
    sleep=time.sleep,
    excluded_pids: Sequence[int] = (),
    stack_factory=None,
    detector_factory=None,
    probe=None,
    camera_probe_s: float = CAMERA_PROBE_S,
) -> dict:
    """Bring up the one production composition, observe everything, tear it down and prove it gone.

    The order is the restarts phase's own and it is not negotiable: the pre-start probe must be empty, the
    dead-man directory exists before the stack starts, one ``RestartStack`` is started and waited for as a
    steady state, the observations are taken while it runs, and the post-teardown probe must be empty
    before this function returns. The observation is returned raw; deciding what it means is the caller's.
    """

    from collections import deque
    import threading

    import rclpy
    from rclpy.executors import MultiThreadedExecutor
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from rclpy.time import Time
    from sensor_msgs.msg import CameraInfo, Image, JointState

    from so101_demo.act.head_search_deadband_measurement.plant import _anchor_requests
    from so101_demo.act.head_search_restarts.restart_run import (
        _await_graph,
        _kill_stragglers,
        _require_empty,
        _stack_factory,
    )
    from so101_demo.adapters.act.ros_search import RGB_QOS

    def log(message: str) -> None:
        line = f"[{_utc_now()}] readback: {message}\n"
        if stdout is not None:
            stdout.write(line)
            stdout.flush()

    def warn(message: str) -> None:
        line = f"[{_utc_now()}] readback: {message}\n"
        if stderr is not None:
            stderr.write(line)
            stderr.flush()

    observer = probe or (lambda **kwargs: probe_owners(**kwargs))
    root = Path(evidence_root)
    root.mkdir(parents=True, exist_ok=True)
    started = clock()
    started_at = _utc_now()
    log("pre-start ownership probe")
    before = observer(excluded_pids=excluded_pids, excluded_nodes=(RUNNER_GRAPH_NODE,))
    try:
        _require_empty(before, anchor=PHASE, stage="pre-start")
    except CalibrationInputsRefused as error:
        raise _refuse(READBACK_FOREIGN_OWNER_ACTIVE, f"{error.code}: {error.detail}") from error
    log(f"pre-start probe clean: {before['owner_processes']}")

    deadman_directory = prepare_deadman_directory(controller_config_path)
    environment = stack_environment(SESSION_ID)

    stack = None
    rclpy_state: dict = {}
    observations: dict = {"deadman_directory": str(deadman_directory)}
    try:
        factory = stack_factory or _stack_factory
        stack = factory(
            urdf_path=urdf_path,
            scene_path=scene_path,
            plugin_config_path=plugin_config_path,
            controller_config_path=controller_config_path,
            workspace=root / "stack",
            session_id=SESSION_ID,
            environment=environment,
            logger=lambda message: log(f"stack: {message}"),
        )
        log("starting the production composition")
        try:
            stack.start()
        except Exception as error:  # noqa: BLE001 - a stack that will not start is a refusal
            raise _refuse(
                READBACK_STACK_START_FAILED,
                f"the production composition did not start: {type(error).__name__}: {error}",
            ) from error
        observations["stack"] = _await_graph(
            observer,
            anchor=PHASE,
            clock=clock,
            sleep=sleep,
            excluded_pids=excluded_pids,
            log=log,
        )
        if not observations["stack"].get("nodes"):
            raise _refuse(
                READBACK_STACK_START_FAILED,
                "the production composition published no node within the graph timeout",
            )
        log(f"stack up: {sorted(observations['stack'].get('nodes') or [])}")

        rclpy.init()
        # the context is recorded before the node exists: a node the runtime refuses still leaves an
        # initialised context behind, and the teardown below must shut it down either way
        rclpy_state["initialized"] = True
        node = Node(RUNNER_NODE)
        executor = MultiThreadedExecutor(num_threads=4)
        executor.add_node(node)
        spinner = threading.Thread(target=executor.spin, daemon=True, name="readback-spin")
        spinner.start()
        images: deque = deque(maxlen=256)
        infos: deque = deque(maxlen=256)
        joints: deque = deque(maxlen=512)

        def on_image(message):
            images.append({"stamp_s": _stamp_s(message), "frame_id": str(message.header.frame_id)})

        def on_info(message):
            infos.append(
                {
                    "stamp_s": _stamp_s(message),
                    "frame_id": str(message.header.frame_id),
                    "width": int(message.width),
                    "height": int(message.height),
                    "k": [float(value) for value in message.k],
                }
            )

        def on_joints(message):
            names = list(message.name)
            for index, name in enumerate(names):
                if name == "neck_yaw_joint":
                    joints.append({"name": name, "position_rad": float(message.position[index])})

        node.create_subscription(Image, IMAGE_TOPIC, on_image, RGB_QOS)
        node.create_subscription(CameraInfo, CAMERA_INFO_TOPIC, on_info, RGB_QOS)
        node.create_subscription(JointState, JOINT_TOPIC, on_joints, qos_profile_sensor_data)
        transform: dict = {}
        try:
            import tf2_ros

            buffer = tf2_ros.Buffer()
            listener = tf2_ros.TransformListener(buffer, node, spin_thread=False)
            log(f"probing the camera and the TF for {camera_probe_s} s")
            sleep(camera_probe_s)
            try:
                stamped = buffer.lookup_transform(BASE_FRAME, CAMERA_FRAME, Time())
                transform = {
                    "translation_m": [
                        float(stamped.transform.translation.x),
                        float(stamped.transform.translation.y),
                        float(stamped.transform.translation.z),
                    ],
                    "quaternion_xyzw": [
                        float(stamped.transform.rotation.x),
                        float(stamped.transform.rotation.y),
                        float(stamped.transform.rotation.z),
                        float(stamped.transform.rotation.w),
                    ],
                    "stamp_s": float(stamped.header.stamp.sec)
                    + float(stamped.header.stamp.nanosec) * 1e-9,
                    "child_frame_id": str(stamped.child_frame_id),
                }
            except Exception as error:  # noqa: BLE001 - an unavailable TF is recorded, never invented
                transform = {"error": f"{type(error).__name__}: {error}"}
            del listener
        except Exception as error:  # noqa: BLE001 - a missing tf2 is recorded with its reason
            transform = {"error": f"tf2_ros unavailable: {type(error).__name__}: {error}"}
            sleep(camera_probe_s)
        camera_live = _camera_measurements_from_live(
            infos=list(infos), frames=list(images), transform=transform, joints=list(joints)
        )
        observations["camera_measurements"] = camera_live
        observations["clock_probe"] = {
            "camera_frames": len(images),
            "camera_info_frames": len(infos),
        }
        log(
            f"camera: {len(images)} frames, {len(infos)} camera_info; observed "
            f"{sorted(name for name, row in camera_live.items() if row.get('value') is not None)}"
        )

        requests = _anchor_requests(
            seal=seal,
            production=production,
            anchors=[anchor],
            attempt_id=f"{SESSION_ID}-attempt-1",
            session_id=SESSION_ID,
        )
        if len(requests) != 1:
            raise _refuse(
                READBACK_COMPONENT_UNBUILDABLE,
                f"the sealed geometry resolves the anchor {anchor!r} to {len(requests)} declarations",
            )
        configuration = requests[0]["controller_config"]
        observations["configuration_sha256"] = canonical_sha256(configuration)
        observations["search_start_rad"] = configuration["search_start_rad"]

        built = (detector_factory or _default_detector_factory)(
            weights_path=weights_path,
            production=production,
            values=values or {},
            device=device,
            runtime=runtime or {},
            clock=clock,
            log=log,
        )
        detector = built["runtime"]
        observations["detector"] = {
            "loaded": True,
            "count": 1,
            "device": device,
            "runtime_device": built.get("runtime_device"),
            "cuda_device": built.get("cuda_device"),
            "allow_cpu_fallback": False,
            "weights_sha256": built.get("weights_sha256"),
            "model_id": built.get("model_id"),
            "count_definition": (
                "one detector object exists in this process, and it is the only CUDA context this phase "
                "opens; no other process consumes the head camera, because no other process runs"
            ),
        }
        observations["values"] = observe_qualification_values(
            values=values or {},
            configuration=configuration,
            detector=detector,
            controller_factory=None,
            neck_port_factory=None,
            stop_criterion_factory=None,
        )
        rclpy_state.update({"node": node, "executor": executor, "spinner": spinner})
    finally:
        # the runner's own node leaves the graph before the post-teardown probe, whatever happened above:
        # the teardown proof excludes that node by name, and a node left spinning would keep a CUDA-free
        # but real participant in the graph the proof reads
        if rclpy_state:
            if "node" in rclpy_state:
                try:
                    rclpy_state["executor"].remove_node(rclpy_state["node"])
                    rclpy_state["executor"].shutdown()
                    rclpy_state["node"].destroy_node()
                except Exception as error:  # noqa: BLE001 - a derelict runner node is excluded by name
                    warn(f"the runner node teardown raised {error!r}")
            try:
                import rclpy as _rclpy

                _rclpy.shutdown()
            except Exception as error:  # noqa: BLE001 - an already-shut-down context is not a failure
                warn(f"the rclpy shutdown raised {error!r}")
            if "spinner" in rclpy_state:
                rclpy_state["spinner"].join(timeout=10.0)
        if stack is not None:
            log("stopping the stack")
            try:
                stack.stop()
            except Exception as error:  # noqa: BLE001 - a stop failure is verified, not asserted
                warn(f"the stack stop raised {error!r}")
            _kill_stragglers(excluded_pids=excluded_pids, log=log)

    log("post-teardown ownership probe")
    after = observer(excluded_pids=excluded_pids, excluded_nodes=(RUNNER_GRAPH_NODE,))
    proof = teardown_proof(
        processes=after.get("processes") or (),
        nodes=after.get("nodes") or (),
        gpu_compute_apps=after.get("gpu_compute_apps") or (),
        sim_clock_s=after.get("sim_clock_s") or (),
        own_pid=os.getpid(),
        runner_node=RUNNER_GRAPH_NODE,
    )
    proof["before"] = {
        "processes": before.get("processes"),
        "nodes": before.get("nodes"),
        "gpu_compute_apps": before.get("gpu_compute_apps"),
    }
    if not all(proof.get(field) is True for field in TEARDOWN_FACTS):
        raise _refuse(
            READBACK_TEARDOWN_UNPROVEN,
            f"the readback's stack could not be proven gone: {json.dumps(proof, sort_keys=True)}",
        )
    if proof.get("gpu_released") is not True:
        raise _refuse(
            READBACK_GPU_NOT_RELEASED,
            "a compute process still held the GPU after the readback's stack stopped",
        )
    observations["teardown"] = proof
    observations["elapsed_s"] = clock() - started
    observations["started_at_utc"] = started_at
    observations["finished_at_utc"] = _utc_now()
    log(f"readback observation complete in {observations['elapsed_s']:.1f} s; stack proven gone")
    return observations


def _default_detector_factory(
    *, weights_path, production, values, device, runtime, clock, log
) -> dict:
    """The one CUDA detector: the production weights loaded with the promoted operating point.

    It is the same construction the restart phase flies (``TimedHeadDetector.build``): the production
    ``HeadRgbDetector`` over the installed ``YoloSegDetector``, ``allow_cpu_fallback=False``, the weight
    digest checked against the frozen config's own declaration. A detector that will not load is
    ``READBACK_DETECTOR_FAILED`` - the readback never falls back to a CPU model.
    """

    from so101_demo.adapters.act.detector import HeadRgbDetector
    from so101_demo.adapters.perception.yolo_seg import YoloSegDetector

    declared = str(runtime.get("weight_sha256_declared") or "")
    observed = _digest(weights_path)
    if declared and observed != declared:
        raise _refuse(
            READBACK_DETECTOR_FAILED,
            f"the weights at {weights_path} digest to {observed}, the frozen config declares {declared}",
        )
    model_id = str(production.get("runtime_id") or "head-search-runtime")
    try:
        yolo = YoloSegDetector(
            weights_path=Path(weights_path),
            expected_sha256=observed,
            requested_device=device,
            allow_cpu_fallback=False,
            model_id=model_id,
            imgsz=640,
        )
        detector = HeadRgbDetector(
            yolo,
            model_id=model_id,
            weights_sha256=observed,
            tracking_iou=float(values["tracking_iou"]),
            min_bbox_aspect=float(values["min_bbox_aspect"]),
        )
    except Exception as error:  # noqa: BLE001 - a detector that will not load is a refusal
        raise _refuse(
            READBACK_DETECTOR_FAILED,
            f"the production detector could not be loaded on {device}: {type(error).__name__}: {error}",
        ) from error
    log(f"detector {model_id} loaded on {getattr(yolo, 'runtime_device', device)}")
    return {
        "runtime": detector,
        "runtime_device": str(getattr(yolo, "runtime_device", device)),
        "cuda_device": str(runtime.get("cuda_device") or device),
        "weights_sha256": observed,
        "model_id": model_id,
    }


def write_head_search_qualification_readback(
    *,
    run_root,
    evidence_root,
    ownership_receipt,
    runtime: Mapping,
    approved_bundle: Mapping,
    production_config: Mapping,
    observe: Callable[..., Mapping],
    approved_bundle_path,
    production_config_path,
    camera_reference: Mapping | None = None,
    command: str = "",
    now=time.gmtime,
    clock=time.monotonic,
) -> dict:
    """Take the Step 1 receipt, observe the running composition, and publish the readback it proves.

    The order is fixed: the qualification run root this readback is taken for must not exist yet (the
    aggregate claims it afterwards and never resumes one), the runtime must be the CUDA-only runtime of
    record, the Step 1 receipt must guard exactly that run root, and the promoted values must be the
    approved ones - only then is the stack started through ``observe``. A refused observation is written
    out as evidence before it is raised: a readback that could not be taken is still readable.
    """

    root = Path(run_root)
    if root.exists():
        raise _refuse(
            READBACK_RUN_ROOT_EXISTS,
            f"the qualification run root {root} already exists; this readback is taken for a run root the "
            f"aggregate has not claimed yet, and no qualification phase is ever resumed",
        )
    evidence = Path(evidence_root)
    if evidence.exists() and any(evidence.iterdir()):
        raise _refuse(
            READBACK_RUN_ROOT_EXISTS,
            f"the evidence root {evidence} already exists and is not empty; a readback is never resumed "
            f"or overwritten",
        )
    try:
        runtime = require_runtime_of_record(runtime)
    except CalibrationInputsRefused as error:
        raise _refuse(READBACK_RUNTIME_UNVERIFIED, f"{error.code}: {error.detail}") from error
    try:
        ownership = read_ownership_receipt(ownership_receipt, run_root=root)
    except CalibrationInputsRefused as error:
        code = {
            RESTART_OWNERSHIP_REFUSED: READBACK_OWNERSHIP_REFUSED,
            RESTART_OWNERSHIP_MISMATCH: READBACK_OWNERSHIP_MISMATCH,
            RESTART_RUNTIME_UNVERIFIED: READBACK_RUNTIME_UNVERIFIED,
        }.get(error.code, READBACK_OWNERSHIP_MISMATCH)
        raise _refuse(code, f"{error.code}: {error.detail}") from error
    approved = approved_values(production_config=production_config, approved_bundle=approved_bundle)
    evidence.mkdir(parents=True, exist_ok=True)
    values = approved["values"]
    started = clock()
    taken_at = _utc_now(now)
    stdout = (evidence / STDOUT_LOG).open("a", encoding="utf-8")
    stderr = (evidence / STDERR_LOG).open("a", encoding="utf-8")
    observation: dict = {}
    try:
        observation = dict(
            observe(
                run_root=root,
                evidence_root=evidence,
                runtime=runtime,
                values=values,
                stdout=stdout,
                stderr=stderr,
            )
            or {}
        )
    except CalibrationInputsRefused as error:
        elapsed = clock() - started
        print(f"the readback refused: {error}", file=stderr)
        stderr.flush()
        _write(
            evidence,
            "readback-refusal.json",
            {
                "schema_version": SCHEMA_VERSION,
                "kind": f"{KIND}_refusal",
                "phase": PHASE,
                "run_root": str(root),
                "evidence_root": str(evidence),
                "code": error.code,
                "detail": error.detail,
                "elapsed_s": elapsed,
                "refused_at_utc": _utc_now(now),
                "provenance": {
                    "run_root": str(root),
                    "evidence_root": str(evidence),
                    "source_commit": runtime.get("source_commit"),
                    "production_config_sha256": runtime.get("production_config_sha256"),
                    "values_sha256": approved["values_sha256"],
                    "weight_sha256": runtime.get("weight_sha256_declared"),
                    "elapsed_s": elapsed,
                },
            },
        )
        stdout.close()
        stderr.close()
        raise
    elapsed = clock() - started
    stdout.close()
    stderr.close()

    detector = observation.get("detector") or {}
    live_camera = observation.get("camera_measurements") or {}
    camera_records = camera_measurement_records(live=live_camera, reference=camera_reference)
    document = readback_document(
        run_root=root,
        evidence_root=evidence,
        runtime=runtime,
        approved=approved,
        observations=observation.get("values") or {},
        camera_measurements=camera_records,
        detector=detector,
        ownership=ownership,
        approved_bundle_path=approved_bundle_path,
        production_config_path=production_config_path,
        elapsed_s=elapsed,
        taken_at_utc=taken_at,
        command=command,
    )
    teardown_path = _write(evidence, TEARDOWN_ARTIFACT, observation.get("teardown") or {})
    _write(evidence, ARTIFACT, document)
    document_path = evidence / ARTIFACT
    return {
        "run_root": str(root),
        "evidence_root": str(evidence),
        "document": document,
        "document_path": str(document_path),
        "document_sha256": _digest(document_path),
        "teardown_proof": str(teardown_path),
        "teardown": observation.get("teardown") or {},
        "values": document["values"],
        "camera_measurements": document["camera_measurements"],
        "elapsed_s": elapsed,
        "status": document["status"],
    }
