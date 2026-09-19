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
station_arguments = sys.argv[5:7]

from so101_demo.runtime.parallel_ipc_v4 import V4PermissionOnlyClient

payload = {"pid": os.getpid(), "pgid": os.getpgid(0), "argv": ["worker", worker_id],
           "station": bool(station_arguments)}
with open(ack_path + ".part", "w", encoding="utf-8") as handle:
    json.dump(payload, handle)
    handle.flush()
    os.fsync(handle.fileno())
os.replace(ack_path + ".part", ack_path)

station = None
if len(station_arguments) == 2:
    # Station ownership belongs to the Worker that will use it, and the environment comes from the
    # product guard: a canonical checkout prefix refuses the launch instead of shadowing this branch.
    from so101_demo.runtime.parallel_worker_runtime import station_environment
    from so101_demo.runtime.task_stack import PersistentTaskStack, default_task_station_config

    station_session, station_root = station_arguments
    config = default_task_station_config(station_session, __import__("pathlib").Path(station_root))
    station = PersistentTaskStack()
    station.start(config, environment=station_environment(base=dict(os.environ)))

client = V4PermissionOnlyClient(endpoint_path=endpoint)
results = []
for index in range(3):
    response = client.call("worker.progress", {"worker_id": worker_id, "index": index},
                           request_id=f"{worker_id}-req-{index:02d}")
    body = response.output_descriptor or {}
    results.append({"request_id": response.request_id, "status": response.status,
                    "device": body.get("device"), "candidates": body.get("candidates")})

with open(out_path + ".part", "w", encoding="utf-8") as handle:
    json.dump({"worker_id": worker_id, "pid": os.getpid(), "results": results}, handle)
    handle.flush()
    os.fsync(handle.fileno())
os.replace(out_path + ".part", out_path)
