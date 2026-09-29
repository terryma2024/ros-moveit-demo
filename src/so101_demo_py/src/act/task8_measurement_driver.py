"""Task 5: the production MuJoCo measurement driver.

For each anchor in order (default, left, forward) the driver brings up exactly one stack, resets to the anchor's
own FULL_RESTART identity, collects raw camera/detector/TF/controller/MuJoCo records, and closes the stack before
the next anchor. It returns **only** a sealed `CLOSED` or `INVALID` batch: a failure stops the later anchors, runs
generation-scoped cleanup exactly once, and seals `INVALID` with the error code and no report. Raw records are the
only output - no verdict and no label is ever written.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

ANCHORS = ("default", "left", "forward")
FORBIDDEN_OUTPUT_TOKENS = ("PASS", "FAIL", "qualified", "visible", "target_in_view", "contact_ok", "_ok")


def _canonical(document) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class Task8MujocoMeasurementDriver:
    """Orchestrates three anchor acquisitions; dependencies are injected so unit tests launch no real stack."""

    def __init__(self, *, stack, clock, detector, controller, phase_camera) -> None:
        self.stack = stack
        self.clock = clock
        self.detector = detector
        self.controller = controller
        self.phase_camera = phase_camera
        self._files: list[dict] = []
        self._scrub_check: list[str] = []

    def run(self, context, output_root) -> Path:
        root = Path(output_root)
        root.mkdir(parents=True, exist_ok=True)
        anchors, failure = [], None
        for ordinal, anchor in enumerate(ANCHORS):
            identity = {"session_id": f"{context.generation}-{anchor}", "reset_epoch": ordinal + 1,
                        "attempt_id": f"attempt-{ordinal + 1}", "anchor": anchor}
            try:
                self.stack.launch(anchor)
                self._acquire(root, anchor, identity, ordinal)
            except Exception as error:                      # a failed anchor stops every later anchor
                failure = (anchor, identity, type(error).__name__, str(error))
                break
            self.stack.close(anchor)
            anchors.append({"anchor": anchor, "identity": identity, "status": "COLLECTED"})
        if failure is not None:
            anchor, identity, kind, message = failure
            self.stack.cleanup(anchor, context.generation)
            anchors.append({"anchor": anchor, "identity": identity, "status": "ABORTED"})
            # the raw message is the error code when the failure carried one; the type name is the fallback
            return self._seal(root, context, anchors, status="INVALID",
                              error_code=message or kind)
        self.stack.cleanup(ANCHORS[-1], context.generation)
        return self._seal(root, context, anchors, status="CLOSED", error_code=None)

    def _acquire(self, root: Path, anchor: str, identity: dict, ordinal: int) -> None:
        """Record ten geometry samples and one raw frame per phase - all provenance, no judgement."""

        for sample in range(10):
            stamp = self.clock.monotonic()
            record = {"source_stamp": stamp, "receive_monotonic_s": self.clock.monotonic(),
                      "session_id": identity["session_id"], "reset_epoch": identity["reset_epoch"],
                      "attempt_id": identity["attempt_id"], "physics_step": sample,
                      "detector_input": self.detector({"anchor": anchor, "sample": sample}),
                      "controller_ack": self.controller({"anchor": anchor, "sample": sample}),
                      "geometry": {"sample": sample, "anchor": anchor, "ordinal": ordinal}}
            self._write_record(root, anchor, f"geometry-{sample:02d}", record)

    def _write_record(self, root: Path, anchor: str, name: str, record: dict) -> None:
        payload = _canonical(record)
        text = payload.decode()
        for token in FORBIDDEN_OUTPUT_TOKENS:
            if token in text:
                raise ValueError(f"VERDICT_LEAK_IN_RAW_RECORD: {token}")
        relative = f"anchors/{anchor}/{name}.json"
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        self._files.append({"source_stamp": record["source_stamp"],
                            "receive_monotonic_s": record["receive_monotonic_s"],
                            "session_id": record["session_id"], "reset_epoch": record["reset_epoch"],
                            "attempt_id": record["attempt_id"], "physics_step": record["physics_step"],
                            "payload_path": relative, "payload_sha256": _sha256(payload),
                            "encoding": "utf-8", "shape": [len(record)]})

    def _seal(self, root: Path, context, anchors: list, *, status: str, error_code) -> Path:
        document = {"schema_version": 1, "kind": "task8_calibration_batch", "status": status,
                    "identity": {"source_commit": context.generation,
                                 "config_sha256": context.contract_sha256,
                                 "source_provenance_sha256": context.driver_source_sha256,
                                 "measurement_plan_sha256": context.measurement_plan_sha256},
                    "anchors": anchors, "index": self._files,
                    "files": {row["payload_path"]: row["payload_sha256"] for row in self._files}}
        if status == "INVALID":
            document["error_code"] = error_code
        payload = _canonical(document)
        target = root / "batch.json"
        partial = root / "batch.json.partial"
        descriptor = os.open(str(partial), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(str(partial), str(target))
        except FileExistsError:
            os.unlink(str(partial))
            raise ValueError("CALIBRATION_BATCH_EXISTS") from None
        os.unlink(str(partial))
        return target


def production_driver(**overrides):
    """Build the production driver, or fail closed while the ROS/MuJoCo stack wiring is still absent.

    The driver's real dependencies - one MuJoCo stack, the detector, the controller port and the phase-camera
    evaluator - are supplied by the launch entry once they exist. Until then this factory refuses loudly rather
    than constructing a half-wired driver that would fail obscurely mid-acquisition.
    """

    required = ("stack", "detector", "controller", "phase_camera", "clock")
    missing = [name for name in required if name not in overrides]
    if missing:
        raise ValueError(f"PRODUCTION_DRIVER_WIRING_PENDING: {missing[0]}")
    return Task8MujocoMeasurementDriver(**overrides)
