"""One macOS W2 campaign Worker: register with the supervisor, then drive three round trips.

The registered ACK is written first and atomically. The supervisor refuses to promote a Worker that
has not acknowledged, so a Worker that reaches the task loop without one cannot exist.
"""

import json
import os
from pathlib import Path
import sys
import time

ack_path, endpoint, worker_id, out_path = sys.argv[1:5]

#: Optional station arguments. Absent means the IPC-only Worker every earlier campaign used;
#: present means this Worker also owns a visible station, started from the validated chain.
station_arguments = sys.argv[5:8]
lease_argument = sys.argv[8:9]

from so101_demo.runtime.parallel_ipc_v4 import V4PermissionOnlyClient

payload = {"pid": os.getpid(), "pgid": os.getpgid(0), "argv": ["worker", worker_id],
           "station": bool(station_arguments)}
with open(ack_path + ".part", "w", encoding="utf-8") as handle:
    json.dump(payload, handle)
    handle.flush()
    os.fsync(handle.fileno())
os.replace(ack_path + ".part", ack_path)

station = None
station_ready = None
if len(station_arguments) == 3:
    # Station ownership belongs to the Worker that will use it, and the environment comes from the
    # product guard: a canonical checkout prefix refuses the launch instead of shadowing this branch.
    # The domain is the one the plan allocated to this slot, so two Workers never share a ROS graph.
    import subprocess

    from so101_demo.runtime.parallel_worker_runtime import station_environment
    from so101_demo.runtime.task_stack import PersistentTaskStack, default_task_station_config

    station_session, station_root, station_domain = station_arguments
    config = default_task_station_config(station_session, Path(station_root))
    environment = station_environment(base=dict(os.environ))
    environment["ROS_DOMAIN_ID"] = station_domain
    station = PersistentTaskStack()
    station.start(config, environment=environment)

    # Wait for the same contract the rest of the branch uses, on this Worker's own domain: a Worker
    # must not drive a station that is not ready, and a missing readiness binary is a failure rather
    # than a reason to continue.
    import shutil

    # PATH is not guaranteed inside a spawned Worker, so the binary is resolved from the package
    # prefix the branch actually installed; a Worker that cannot find it refuses to continue rather
    # than drive a station it cannot prove ready.
    ready_binary = shutil.which("motion_stack_ready")
    if ready_binary is None:
        from ament_index_python.packages import get_package_prefix

        candidate = Path(get_package_prefix("so101_demo_py")) / "lib/so101_demo_py/motion_stack_ready"
        ready_binary = str(candidate) if candidate.is_file() else None
    if ready_binary is None:
        raise SystemExit("STATION_READY_BINARY_MISSING")
    completed = subprocess.run(
        [ready_binary, "--timeout-s", "150"], capture_output=True, text=True, env=environment,
    )
    try:
        station_ready = json.loads(completed.stdout or "{}")
    except ValueError:
        station_ready = {"raw": (completed.stdout or completed.stderr)[-200:]}
    station_ready["exit_code"] = completed.returncode
    station_ready["ros_domain_id"] = station_domain

station_record = {"requested": bool(station_arguments), "ready": station_ready}
if station_arguments and (station_ready or {}).get("exit_code") != 0:
    # Fail closed: a Worker must not serve a station whose ready contract did not pass, and the
    # refusal is written down rather than only exiting, so the evidence says why.
    payload = {"worker_id": worker_id, "pid": os.getpid(), "station_record": station_record,
               "failure_code": "STATION_NOT_READY", "results": []}
    with open(out_path + ".part", "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(out_path + ".part", out_path)
    raise SystemExit("STATION_NOT_READY")

infer_results = []
if lease_argument:
    # The Worker now speaks the production path: it reads the identity the entry point bound for it
    # and asks the shared Broker through `W2BrokerPort`, so its inference is a real model call gated
    # by the one-time table instead of an IPC-shape probe.
    from types import SimpleNamespace

    from so101_demo.parallel_batch.contracts import ExecutionKind
    from so101_demo.runtime.macos_w2_broker_port import BrokerAuthority, W2BrokerPort
    from so101_demo.runtime.parallel_ipc_v4 import V4PermissionOnlyClient as _V4Client

    lease_document = json.loads(Path(lease_argument[0]).read_text())
    authority = BrokerAuthority(healthy=True, generation=1, endpoint_path=endpoint)
    port_config = SimpleNamespace(
        broker_max_frame_bytes=8 * 1024 * 1024,
        executing_hard_timeout_s=float(lease_document.get("deadline_s", 240.0)),
        broker_recovery_timeout_s=90.0)
    port = W2BrokerPort(
        coordinator=lambda: authority, authority=authority, config=port_config,
        resources=SimpleNamespace(worker_root=Path(lease_document["worker_root"])),
        connection=_V4Client(endpoint_path=endpoint))
    snapshot = SimpleNamespace(
        path=Path(lease_document["snapshot_path"]), shape=tuple(lease_document["shape"]),
        input_sha256=lease_document["input_sha256"],
        source_stamp_ns=lease_document["source_stamp_ns"],
        source_frame_id=lease_document["source_frame_id"])
    for attempt_id in lease_document["attempt_ids"]:
        lease = SimpleNamespace(
            attempt_id=attempt_id, batch_id=lease_document["batch_id"],
            coordinator_epoch=lease_document["coordinator_epoch"], worker_id=worker_id,
            worker_generation=lease_document["worker_generation"],
            point_id=lease_document["point_id"],
            lease_generation=lease_document["lease_generation"])
        try:
            response = port.request_one(
                lease, ExecutionKind.ATTEMPT, model_id=lease_document["model_id"],
                snapshot=snapshot, start_event_id=f"{attempt_id}-start",
                start_event_type=lease_document["start_event_type"],
                reset_epoch=lease_document["reset_epoch"])
            descriptor = getattr(response, "output_descriptor", None) or {}
            infer_results.append({"request_id": f"{attempt_id}-{lease_document['model_id']}",
                                  "status": getattr(response, "status", None),
                                  "device": descriptor.get("device")})
        except Exception as error:  # noqa: BLE001 - the failure mode is the evidence
            infer_results.append({"request_id": f"{attempt_id}-{lease_document['model_id']}",
                                  "status": "ERROR", "error": f"{type(error).__name__}: {error}"})

    # A duplicate of the first request: the one-time table must refuse it, so a late or repeated
    # result cannot be admitted a second time.
    duplicate_id = lease_document["attempt_ids"][0]
    duplicate_lease = SimpleNamespace(
        attempt_id=duplicate_id, batch_id=lease_document["batch_id"],
        coordinator_epoch=lease_document["coordinator_epoch"], worker_id=worker_id,
        worker_generation=lease_document["worker_generation"],
        point_id=lease_document["point_id"],
        lease_generation=lease_document["lease_generation"])
    try:
        port.request_one(
            duplicate_lease, ExecutionKind.ATTEMPT, model_id=lease_document["model_id"],
            snapshot=snapshot, start_event_id=f"{duplicate_id}-start",
            start_event_type=lease_document["start_event_type"],
            reset_epoch=lease_document["reset_epoch"])
        duplicate_result = {"request_id": f"{duplicate_id}-{lease_document['model_id']}",
                            "status": "ADMITTED_TWICE"}
    except Exception as error:  # noqa: BLE001
        duplicate_result = {"request_id": f"{duplicate_id}-{lease_document['model_id']}",
                            "status": "REFUSED", "error": f"{type(error).__name__}: {error}"}


try:
    client = V4PermissionOnlyClient(endpoint_path=endpoint)
    results = []
    for index in range(3):
        response = client.call("worker.progress", {"worker_id": worker_id, "index": index},
                               request_id=f"{worker_id}-req-{index:02d}")
        body = response.output_descriptor or {}
        results.append({"request_id": response.request_id, "status": response.status,
                        "device": body.get("device"), "candidates": body.get("candidates")})

    # The pick-place half of the Worker: once its station is ready and its round trips are served,
    # one real point list runs on that station and on the Worker's own ROS domain through the
    # production batch runner in attach mode, with its own evidence root - so the two slots never
    # share a batch, a reset epoch or a directory.
    pick_place = {"requested": False}
    if station is not None and lease_argument:
        import subprocess as _subprocess

        from ament_index_python.packages import get_package_prefix as _prefix

        share = Path(_prefix("so101_demo_py")) / "share/so101_demo_py"
        batch_binary = Path(_prefix("so101_demo_py")) / "lib/so101_demo_py/so101_mujoco_rgbd_batch"
        pick_root = Path(station_arguments[1]) / "pick"
        pick_root.mkdir(parents=True, exist_ok=True)
        pick_place = {"requested": True, "binary": str(batch_binary),
                      "evidence_root": str(pick_root),
                      "points": str(share / "config/mujoco/rgbd_task_points.yaml")}
        if not batch_binary.is_file():
            pick_place["error"] = "BATCH_BINARY_MISSING"
        else:
            mujoco_pid = station.wait_for_descendant("ros2_control_node", 120.0)
            pick_place["mujoco_pid"] = mujoco_pid
            completed = _subprocess.run(
                [str(batch_binary),
                 "--points", pick_place["points"],
                 "--batch-id", f"{station_arguments[0]}-pick",
                 "--session-id", station_arguments[0],
                 "--evidence-root", str(pick_root),
                 "--attach-existing-stack", "--mujoco-pid", str(mujoco_pid)],
                capture_output=True, text=True, env=environment)
            pick_place["exit_code"] = completed.returncode
            pick_place["stdout_tail"] = (completed.stdout or "")[-400:]
            pick_place["stderr_tail"] = (completed.stderr or "")[-400:]

    with open(out_path + ".part", "w", encoding="utf-8") as handle:
        json.dump({"worker_id": worker_id, "pid": os.getpid(), "results": results,
                   "station_record": station_record, "infer_results": infer_results,
               "duplicate_result": duplicate_result, "pick_place": pick_place}, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(out_path + ".part", out_path)
finally:
    # The station outlives its Worker unless someone stops it (CP-UQ268): the supervisor owns
    # this process group, but the launch the stack spawned can land in its own group, so the
    # Worker that started the station is the one that must shut it down - on every exit path.
    if station is not None:
        station.shutdown()
