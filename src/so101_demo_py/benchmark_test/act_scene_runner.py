"""Container side of the ACT-scene perception gate (`test_act_scene_perception_gate.py`).

Runs inside the production perception image with the package under test mounted over its `so101_demo`: the production YOLO detector
(frozen options, confidence 0.25, NMS 0.7, the BGR hand-over), the production wire conversion of the Broker (`normalize_batch`) and the
Worker's `BrokerMaskLocalizer` with rule R6, on rendered frames of the ACT scene. It reads `/cases/spec.json` and the `*.npz` frames
beside it and writes `/out/results.json`; the verdicts are the test's job.
"""

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np

from so101_demo.adapters.perception import detector_factory
from so101_demo.application.object_pose import LocalizationError
from so101_demo.core.detection import DetectionFrame, DetectionQuery
from so101_demo.parallel_batch.broker import BrokerResponse
from so101_demo.parallel_batch.contracts import ExecutionKind, InferenceRequest, ModelOutcome
from so101_demo.runtime import parallel_perception_runtime as runtime
from so101_demo.runtime.parallel_perception_runtime import normalize_batch
from so101_demo.runtime.parallel_ros_runtime import BrokerMaskLocalizer

STAMP_NS = 1_000_000_000
FRAME_ID = "task_camera_frame"


def request():
    return InferenceRequest(
        request_id="attempt-1-yolo", model_id=runtime.YOLO_ID, execution_kind=ExecutionKind.ATTEMPT, batch_id="batch-1",
        coordinator_epoch=1, worker_id="worker-01", worker_generation=1, point_id="task_start", lease_generation=1,
        reset_epoch="reset-2", image_timestamp_s=1.0,
        input_relative_path="worker-01/attempts/task_start/attempt-1/working/perception/input/rgb.npy",
        input_sha256="ab" * 32, deadline_s=5.0, attempt_id="attempt-1")


def main() -> int:
    spec = json.loads(Path("/cases/spec.json").read_text())
    width, height, k = spec["width"], spec["height"], spec["k"]
    stamp = NS(sec=1, nanosec=0)
    camera = NS(width=width, height=height, header=NS(stamp=stamp, frame_id=FRAME_ID), k=k)
    tf = NS(transform=NS(rotation=NS(**spec["tf"]["rotation"]), translation=NS(**spec["tf"]["translation"])))
    options = runtime.frozen_options(Path("/models/yolo/best.pt"), Path("/models/grounded"))
    detector = detector_factory.build_detector(options[runtime.YOLO_ID]).detector
    localizer = BrokerMaskLocalizer()
    results, started, weights_sha256 = [], time.time(), None
    for case in spec["cases"]:
        data = np.load(f"/cases/{case['name']}.npz")
        rgb, depth = data["rgb"], data["depth"]
        depth_message = NS(width=width, height=height, header=NS(stamp=stamp, frame_id=FRAME_ID), encoding="32FC1", step=width * 4,
                           is_bigendian=False, data=np.ascontiguousarray(depth, dtype="<f4").tobytes())
        frame = DetectionFrame(rgb, STAMP_NS, FRAME_ID)
        batch = detector.detect(frame, DetectionQuery("plastic_cup"))
        weights_sha256 = batch.weights_sha256
        document = normalize_batch(batch, frame)
        record = {"name": case["name"], "stratum": case["stratum"], "gt": case["gt"],
                  "candidates": [[c["instance_id"], round(c["confidence"], 4)] for c in document["candidates"]]}
        response = BrokerResponse(request(), 1, ModelOutcome.QUALIFIED if document["candidates"] else ModelOutcome.NORMAL_REJECTION,
                                  document, None, 1.0, 2.0, 1.1, 2.1, 1.2)
        if not document["candidates"]:
            record.update(outcome="NO_CANDIDATE")
        else:
            try:
                localized = localizer.localize(response, camera_info=camera, depth_message=depth_message,
                                               lookup_exact=lambda target, frame_id, stamp_ns: tf)
                center = np.asarray(localized.center_world_xyz, dtype=float)
                record.update(outcome="ONE", center=center.tolist(),
                              xy_error_m=float(np.linalg.norm(center[:2] - np.asarray(case["gt"][:2], dtype=float))))
            except RuntimeError as error:
                record.update(outcome="AMBIGUOUS", detail=str(error)[:200])
            except LocalizationError as error:
                record.update(outcome="REJECTED", detail=str(error)[:200])
        results.append(record)
    Path("/out/results.json").write_text(json.dumps({"results": results, "seconds": time.time() - started,
                                                      "weights_sha256": weights_sha256}, indent=1))
    print("done", len(results), f"{time.time() - started:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
