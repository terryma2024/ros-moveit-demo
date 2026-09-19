"""One macOS W2 campaign Worker: register with the supervisor, then drive three round trips.

The registered ACK is written first and atomically. The supervisor refuses to promote a Worker that
has not acknowledged, so a Worker that reaches the task loop without one cannot exist.
"""

import json
import os
import sys
import time

ack_path, endpoint, worker_id, out_path = sys.argv[1:5]

#: Optional station arguments. Absent means the IPC-only Worker every earlier campaign used;
#: present means this Worker also owns a visible station, started from the validated chain.
station_arguments = sys.argv[5:8]

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
    from pathlib import Path as _Path

    from so101_demo.runtime.parallel_worker_runtime import station_environment
    from so101_demo.runtime.task_stack import PersistentTaskStack, default_task_station_config

    station_session, station_root, station_domain = station_arguments
    config = default_task_station_config(station_session, _Path(station_root))
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

        candidate = _Path(get_package_prefix("so101_demo_py")) / "lib/so101_demo_py/motion_stack_ready"
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

try:
    client = V4PermissionOnlyClient(endpoint_path=endpoint)
    results = []
    for index in range(3):
        response = client.call("worker.progress", {"worker_id": worker_id, "index": index},
                               request_id=f"{worker_id}-req-{index:02d}")
        body = response.output_descriptor or {}
        results.append({"request_id": response.request_id, "status": response.status,
                        "device": body.get("device"), "candidates": body.get("candidates")})

    with open(out_path + ".part", "w", encoding="utf-8") as handle:
        json.dump({"worker_id": worker_id, "pid": os.getpid(), "results": results,
                   "station_record": station_record}, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(out_path + ".part", out_path)
finally:
    # The station outlives its Worker unless someone stops it (CP-UQ268): the supervisor owns
    # this process group, but the launch the stack spawned can land in its own group, so the
    # Worker that started the station is the one that must shut it down - on every exit path.
    if station is not None:
        station.shutdown()
