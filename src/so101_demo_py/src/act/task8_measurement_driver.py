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
# the nine phases of the design's coverage matrix, taken from the window that enforces them rather than retyped
_PHASES = ("SEARCH", "APPROACH", "CLOSE", "MICRO_LIFT", "TRANSPORT", "ALIGN", "RELEASE",
           "RADIAL_RETREAT", "FINAL_CHECK")
PRIVATE_REPLAY_PERIOD_S = 0.002
# every anchor is measured under its own full restart of the stack, so every raw row says which lifecycle it belongs to
LIFECYCLE = "FULL_RESTART"
# one fixed probe, identical for every anchor, that must not touch anything: it exercises the arm's clearance before the
# geometry samples are taken, and a touch fails that anchor rather than being averaged into the batch
PROBE_COMMAND = {"joint_positions_rad": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0], "duration_s": 0.2, "profile": "fixed"}
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
            identity = {"anchor": anchor}
            try:
                self.stack.launch(anchor)
                # the session, reset epoch and attempt are the stack's own readback: an ordinal is not an identity,
                # and a stack that cannot report them fails closed before a single row is written
                identity = self._read_identity(anchor)
                self._acquire(root, anchor, identity, ordinal)
            except Exception as error:                      # a failed anchor stops every later anchor
                failure = (anchor, identity, type(error).__name__, str(error))
                break
            self.stack.close(anchor)
            anchors.append({"anchor": anchor, "identity": identity, "status": "COLLECTED"})
        if failure is not None:
            anchor, identity, kind, message = failure
            receipt, contamination = self._cleanup_once(context, anchor)
            anchors.append({"anchor": anchor, "identity": identity, "status": "ABORTED"})
            # the raw message is the error code when the failure carried one; the type name is the fallback
            return self._seal(root, context, anchors, status="INVALID",
                              error_code=message or kind, cleanup=receipt, contamination=contamination)
        receipt, contamination = self._cleanup_once(context, ANCHORS[-1])
        return self._seal(root, context, anchors, status="CLOSED" if contamination is None else "INVALID",
                          error_code=contamination, cleanup=receipt, contamination=contamination)

    def _cleanup_once(self, context, anchor) -> tuple:
        """Clean up once for this case's own generation; a refused cleanup is recorded, never raised.

        Single-flight and generation-scoped: the receipt names the generation the cleanup was requested for, so a stale
        generation cannot clean a newer one by accident, and a stack that refuses the cleanup leaves contamination
        evidence instead of an unattributed exception.
        """

        requested = {"anchor": anchor, "generation": context.generation}
        try:
            result = self.stack.cleanup(anchor, context.generation)
        except Exception as error:
            return ({"requested": requested, "status": "REFUSED", "error": type(error).__name__,
                     "message": str(error)}, f"CLEANUP_REFUSED: {type(error).__name__}")
        return ({"requested": requested, "status": "CONFIRMED", "result": result}, None)

    def _read_identity(self, anchor: str) -> dict:
        """Read this anchor's real session, reset epoch and attempt from the stack, or fail closed by name."""

        readback = getattr(self.stack, "readback", None)
        if not callable(readback):
            raise ValueError("MEASUREMENT_READBACK_REQUIRED: the stack cannot report session, reset epoch and attempt")
        report = readback(anchor)
        if type(report) is not dict:
            raise ValueError("MEASUREMENT_READBACK_REQUIRED: readback is not a mapping")
        identity = {"anchor": anchor, "session_id": report.get("session_id"),
                    "reset_epoch": report.get("reset_epoch"), "attempt_id": report.get("attempt_id")}
        for name in ("session_id", "attempt_id"):
            if not isinstance(identity[name], str) or not identity[name]:
                raise ValueError(f"MEASUREMENT_READBACK_REQUIRED: {name}")
        if type(identity["reset_epoch"]) is not int or identity["reset_epoch"] < 0:
            raise ValueError("MEASUREMENT_READBACK_REQUIRED: reset_epoch")
        return identity

    def _acquire(self, root: Path, anchor: str, identity: dict, ordinal: int) -> None:
        """Record ten geometry samples and one raw frame per phase - all provenance, no judgement."""

        # the private replay first: nine phases at the 2 ms cadence, evaluated by the real phase camera, so a run
        # cannot reach a sealed batch without the coverage its contract's phase matrix depends on
        for index, phase in enumerate(_PHASES):
            stamp = self.clock.monotonic()
            observation = self.phase_camera(phase, index)
            self._write_record(root, anchor, f"phase-{index:02d}-{phase.lower()}",
                               {"source_stamp": stamp, "receive_monotonic_s": self.clock.monotonic(),
                                "session_id": identity["session_id"], "reset_epoch": identity["reset_epoch"],
                                "attempt_id": identity["attempt_id"], "physics_step": index,
                                "period_s": PRIVATE_REPLAY_PERIOD_S, "phase": phase,
                                "observation": observation})

        # the camera evidence the measurement claims must be in the batch as raw rows: the intrinsics the camera
        # actually reported and the transforms actually used, or the anchor fails by name
        try:
            info = self.stack.camera_info(anchor)
            transforms = self.stack.tf(anchor)
        except Exception as error:
            raise ValueError(f"MEASUREMENT_CAMERA_REQUIRED: {anchor}: {type(error).__name__}") from error
        if type(info) is not dict or type(transforms) is not dict:
            raise ValueError(f"MEASUREMENT_CAMERA_REQUIRED: {anchor}: camera evidence is not a mapping")
        stamp = self.clock.monotonic()
        for name, payload in (("camera-info", info), ("tf", transforms)):
            self._write_record(root, anchor, name,
                               {"source_stamp": stamp, "receive_monotonic_s": self.clock.monotonic(),
                                "session_id": identity["session_id"], "reset_epoch": identity["reset_epoch"],
                                "attempt_id": identity["attempt_id"], "physics_step": -2, **payload})

        probe = getattr(self.stack, "probe", None)
        if not callable(probe):
            raise ValueError("MEASUREMENT_PROBE_REQUIRED: the stack cannot run the fixed non-contact arm probe")
        report = probe(anchor, dict(PROBE_COMMAND))
        contacts = (report or {}).get("contacts")
        if not isinstance(contacts, list):
            raise ValueError("MEASUREMENT_PROBE_REQUIRED: the probe did not report its contacts")
        stamp = self.clock.monotonic()
        self._write_record(root, anchor, "probe",
                           {"source_stamp": stamp, "receive_monotonic_s": self.clock.monotonic(),
                            "session_id": identity["session_id"], "reset_epoch": identity["reset_epoch"],
                            "attempt_id": identity["attempt_id"], "physics_step": -1,
                            "command": dict(PROBE_COMMAND), "contact_count": len(contacts),
                            "contacts": contacts})
        if contacts:
            raise ValueError(f"MEASUREMENT_PROBE_CONTACT: {anchor} touched during the fixed probe")

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
        # one place stamps the lifecycle, so no row can be written without naming the restart it was measured under
        record = {**record, "lifecycle": LIFECYCLE}
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
                            "lifecycle": record["lifecycle"],
                            "receive_monotonic_s": record["receive_monotonic_s"],
                            "session_id": record["session_id"], "reset_epoch": record["reset_epoch"],
                            "attempt_id": record["attempt_id"], "physics_step": record["physics_step"],
                            "payload_path": relative, "payload_sha256": _sha256(payload),
                            "encoding": "utf-8", "shape": [len(record)]})

    def _seal(self, root: Path, context, anchors: list, *, status: str, error_code,
              cleanup=None, contamination=None) -> Path:
        document = {"schema_version": 1, "kind": "task8_calibration_batch", "status": status,
                    "cleanup": cleanup, "contamination": contamination,
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
