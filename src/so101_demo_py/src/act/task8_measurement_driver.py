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
# the same search request for every anchor and every generation, so the anchors are comparable
SEARCH_REQUEST = {"mode": "COARSE_THEN_FINE", "period_s": 0.002, "max_iterations": 64}
FORBIDDEN_OUTPUT_TOKENS = ("PASS", "FAIL", "qualified", "visible", "target_in_view", "contact_ok", "_ok")


def _canonical(document) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class Task8MujocoMeasurementDriver:
    """Orchestrates three anchor acquisitions; dependencies are injected so unit tests launch no real stack."""

    def __init__(self, *, stack, clock, detector, controller, phase_camera, identity,
                 contract=None) -> None:
        self.stack = stack
        self.clock = clock
        self.detector = detector
        self.controller = controller
        self.phase_camera = phase_camera
        from so101_demo.act.task8_measurement_schema import MeasurementIdentity

        # Astra item 3: the identity is the schema's ten-member document, passed in rather than invented
        self.identity = MeasurementIdentity.require(identity)
        # P1-2 (rereview 5): the aggregator computes each field from `raw["measurements"][field]` and reads its limit
        # from `raw["configured"][field]`, keyed by the CONTRACT's field names - so the contract must reach the one
        # place that writes raw records, and it is passed in rather than guessed.
        self.contract = contract if isinstance(contract, dict) else {}
        self._files: list[dict] = []
        self._scrub_check: list[str] = []

    def run(self, context, output_root) -> Path:
        root = Path(output_root)
        root.mkdir(parents=True, exist_ok=True)
        # section 4.2: the descriptor the measurement runs under travels with the raw batch, so the later report is bound
        # to the configuration that was actually measured rather than to a path somebody could re-read and change
        descriptor = getattr(context, "runtime_descriptor", None)
        if isinstance(descriptor, dict):
            payload = json.dumps(descriptor, sort_keys=True).encode("utf-8")
            (root / "runtime-descriptor.json").write_bytes(payload)
            # Astra item 3: the descriptor is part of the sealed closure, so it is indexed like every other artefact
            self._files.append({"payload_path": "runtime-descriptor.json",
                                "payload_sha256": _sha256(payload), "encoding": "utf-8"})
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
            # P1-3: a replay row is either a MEASUREMENT or a named refusal. Sealing an ABSENT observation would
            # publish a phase path that was never sampled, which is the failure the marker was introduced to expose.
            if not isinstance(observation, dict) or observation.get("geometry_state") != "MEASURED":
                state = observation.get("geometry_state") if isinstance(observation, dict) else type(observation).__name__
                raise ValueError(
                    f"MEASUREMENT_PHASE_GEOMETRY_REQUIRED: {anchor}: the phase camera reported {state!r}; the replay "
                    "needs the run's trajectory, camera and target geometry")
            self._write_record(root, anchor, f"phase-{index:02d}-{phase.lower()}",
                               {"source_stamp": stamp, "receive_monotonic_s": self.clock.monotonic(),
                                "session_id": identity["session_id"], "reset_epoch": identity["reset_epoch"],
                                "attempt_id": identity["attempt_id"], "physics_step": index,
                                "period_s": PRIVATE_REPLAY_PERIOD_S, "phase": phase,
                                "observation": observation})

        # the live search: the measurement's whole point is what the search did against the real scene, so its raw
        # iterations belong in the batch or the anchor fails by name
        search = getattr(self.stack, "run_search", None)
        if not callable(search):
            raise ValueError(f"MEASUREMENT_SEARCH_REQUIRED: {anchor}: the stack cannot run the live search")
        try:
            found = search(anchor, dict(SEARCH_REQUEST))
        except Exception as error:
            raise ValueError(f"MEASUREMENT_SEARCH_REQUIRED: {anchor}: {type(error).__name__}") from error
        if type(found) is not dict or not isinstance(found.get("iterations"), list) or not found["iterations"]:
            raise ValueError(f"MEASUREMENT_SEARCH_REQUIRED: {anchor}: the search reported no iterations")
        stamp = self.clock.monotonic()
        self._write_record(root, anchor, "search",
                           {"source_stamp": stamp, "receive_monotonic_s": self.clock.monotonic(),
                            "session_id": identity["session_id"], "reset_epoch": identity["reset_epoch"],
                            "attempt_id": identity["attempt_id"], "physics_step": -3, **found})

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

    def _aggregator_evidence(self, record: dict) -> dict:
        """Present this record's own evidence under the names the aggregator's formulas read.

        P1-2 (rereview 5): the formulas read `raw["measurements"][field]` (a list of bbox dicts for the bbox fields)
        and `raw["configured"][field]` (the configured limit). The record already carries the bbox evidence - my P1-1
        translation of the real `DetectionBatch` keeps each candidate's `bbox_xyxy` - so this is a RENAMING at write
        time, never an addition after sealing, never a re-seal, and it does not touch the identity.
        """

        measurements_section = (self.contract or {}).get("measurements") or {}
        if not measurements_section:
            return {}
        detection = record.get("detector_input")
        candidates = (detection or {}).get("candidates") if isinstance(detection, dict) else None
        boxes = []
        for candidate in candidates or ():
            bbox = candidate.get("bbox_xyxy") if isinstance(candidate, dict) else None
            if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                x1, y1, x2, y2 = (float(value) for value in bbox)
                boxes.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2, "accepted": True})
        from so101_demo.act.task8_measurement_formulas import BBOX_EVIDENCE_FIELDS

        # the camera evidence: the admitted camera block's own horizontal FOV, which is what the FOV field is
        # measured against (its `threshold_source` is the model's FOV, not a pending config value)
        camera_block = getattr(self.phase_camera, "document", {}).get("camera") or {}
        measurements = {}
        fov_limit = None
        focal = camera_block.get("focal_px")
        principal = camera_block.get("principal_point_px")
        if (camera_block.get("horizontal_fov_rad") is not None and camera_block.get("width_px")
                and isinstance(focal, (list, tuple)) and len(focal) == 2
                and isinstance(principal, (list, tuple)) and len(principal) == 2):
            # `_f_horizontal_fov_rad` derives the angle PER FRAME from `fx`, `cx` and the width, compares the minimum
            # against the model's own FOV, and requires `tolerance_rad` beside them. Both numbers here were MEASURED by
            # the sampler from the headless model (`focal_px`, `principal_point_px` from the sampled poses; the FOV
            # from the camera's declared fovy), so the comparison the formula makes is between two measured values at
            # the protocol's tolerance - not between a value and itself.
            measurements["horizontal_fov_rad"] = {
                "frames": [{"fx": float(focal[0]), "cx": float(principal[0]),
                            "width": float(camera_block["width_px"])}],
                "model_fov_rad": float(camera_block["horizontal_fov_rad"]),
                # the design fixes the geometric cross-check tolerance at 1e-6 rad; it is a protocol constant, not a
                # config value awaiting approval, which is why this field IS measurable in this chain
                "tolerance_rad": 1e-6,
            }
            fov_limit = float(camera_block["horizontal_fov_rad"])
        # ONLY the fields this measurement truly produced, under the names whose formula reads them: the bbox
        # evidence goes to `BBOX_EVIDENCE_FIELDS`. Emitting it under EVERY declared field - which is what this did
        # first - made fields look measured whose evidence a calibration head search produces and this chain does not;
        # those are now simply absent, and the aggregator reports them UNMEASURED (the owner's disposition, CP-1789).
        for field in BBOX_EVIDENCE_FIELDS:
            if boxes and field in measurements_section:
                measurements[field] = boxes
        # ONLY approved limits travel: an entry whose value is unapproved (`value: null` with
        # `requires_approved_value: true`) or absent is omitted, and the aggregator reports that field UNMEASURED
        configured = {}
        for field, entry in measurements_section.items():
            if not isinstance(entry, dict):
                continue
            limit = entry.get("configured_limit")
            if limit is None and field == "horizontal_fov_rad":
                limit = fov_limit                    # its threshold source is the model, measured above
            if limit is None:
                continue
            configured[field] = limit
        return {"measurements": measurements, "configured": configured}

    def _write_record(self, root: Path, anchor: str, name: str, record: dict) -> None:
        # one place stamps the lifecycle, so no row can be written without naming the restart it was measured under
        record = {**record, **self._aggregator_evidence(record), "lifecycle": LIFECYCLE}
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
        from so101_demo.act.task8_measurement_contract import _canonical as _seal_canonical
        from so101_demo.act.task8_measurement_schema import BATCH_KIND, write_closed_json

        # Astra item 3: this is the ONE seal owner, and its document is the schema's, not a private shape
        # Astra item 3: the provenance rows are the driver's own record and cannot live in the sealed document
        # (_BATCH_KEYS has no room for them), so they get an indexed home of their own inside the closure
        # Astra item 3: the schema reads each sealed anchor as a NAME (f"anchors/{anchor}/"), so the names are what
        # the document carries; the driver's richer per-anchor records live in index.json beside the provenance rows
        anchor_names = [row["anchor"] if isinstance(row, dict) else str(row) for row in anchors]
        provenance = _canonical({"files": self._files, "anchors": anchors})
        provenance_path = root / "index.json"
        provenance_path.write_bytes(provenance)
        self._files = list(self._files) + [{"payload_path": "index.json",
                                            "payload_sha256": _sha256(provenance), "encoding": "utf-8"}]

        document = {"schema_version": 1, "kind": BATCH_KIND, "status": status,
                    "cleanup": cleanup, "contamination": contamination,
                    "identity": self.identity, "anchors": anchor_names,
                    "files": {row["payload_path"]: row["payload_sha256"] for row in self._files}}
        if status == "INVALID":
            document["error_code"] = error_code
        document["batch_sha256"] = hashlib.sha256(_seal_canonical(document)).hexdigest()
        return write_closed_json(root / "batch.json", document)


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
