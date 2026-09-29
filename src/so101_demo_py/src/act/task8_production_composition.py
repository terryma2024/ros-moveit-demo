"""The one trusted production composition for the Task 8 measurement driver.

Astra finding 1: the measurement CLI called ``production_driver()`` with no collaborators, so the production path
could only raise ``PRODUCTION_DRIVER_WIRING_PENDING``. This module is the composition that replaces that dead end.

The seam is at the **external I/O** level, deliberately: tests may supply the stack, detector, controller port,
phase-camera evaluator and clock (the ROS/MuJoCo/process boundary), but they may not supply the *driver*, because the
composition's own rules - one stack, CUDA with no CPU fallback, binding only at this entry, generation-scoped cleanup
- are what has to be under test.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path
import time

from so101_demo.act.task8_artifact_bundle import require_runtime_descriptor

__all__ = ["build_production_measurement_driver", "PROVIDER_SEAM_ENV"]

PROVIDER_SEAM_ENV = "SO101_TASK8_PROVIDER_SEAM"
#: P1-1: the seam a SUCCESS test may use. It names only the two BOTTOM boundaries - the MuJoCo/ROS client and the
#: detector model - so the stack, clock, controller and phase camera are still the real composition's own.
BOTTOM_IO_SEAM_ENV = "SO101_TASK8_BOTTOM_IO_SEAM"

#: the five collaborators the driver needs, and the order the composition builds them in
PROVIDER_NAMES = ("stack", "clock", "detector", "controller", "phase_camera")


class ProductionCompositionError(ValueError):
    """Raised when the composition cannot be built; the message is the machine-readable code."""


def _bottom_io_from_seam():
    """The TWO bottom boundaries the success test may stand in for, and nothing else.

    ``SO101_TASK8_BOTTOM_IO_SEAM="pkg.mod:client,pkg.mod:detector_factory"`` - an entry whose attribute name mentions
    the detector is the model factory, anything else is the lowest-level client. Anything not named here (the stack,
    the clock, the controller, the phase camera) is still built by this composition.
    """

    spec = os.environ.get(BOTTOM_IO_SEAM_ENV)
    if not spec:
        return {}
    resolved = {}
    for entry in (part.strip() for part in spec.split(",")):
        if not entry:
            continue
        module_name, _, attribute = entry.partition(":")
        if not module_name or not attribute:
            raise ProductionCompositionError(f"PRODUCTION_BOTTOM_IO_SEAM_INVALID: {entry}")
        module = importlib.import_module(module_name)
        value = getattr(module, attribute, None)
        if value is None:
            raise ProductionCompositionError(f"PRODUCTION_BOTTOM_IO_SEAM_INVALID: {entry}")
        for name, key in (("detector", "detector_factory"), ("frame", "frame_source"),
                          ("phase", "phase_path"), ("path", "phase_path"),
                          ("target", "target"), ("occluder", "occluder_geometry")):
            if name in attribute:
                resolved[key] = value
                break
        else:
            resolved["client"] = value
    return resolved


class MeasurementDetectorAdapter:
    """The driver calls its detector as a CALLABLE; the production detector's interface is ``detect(frame, query)``.

    P1-1 named the mismatch: ``task8_measurement_driver`` does ``self.detector({...})`` while ``YoloSegDetector``
    exposes ``detect(frame, query)`` and declares no ``__call__``. Protocol matching belongs here, where the
    composition already adapts the controller for the same reason - and a missing frame source fails closed by name
    rather than being papered over with an empty image.
    """

    def __init__(self, detector, *, frame_source=None, class_id=None):
        self.detector = detector
        self.frame_source = frame_source
        self.class_id = class_id

    def __call__(self, request):
        if self.frame_source is None:
            raise ProductionCompositionError("PRODUCTION_DETECTOR_FRAME_SOURCE_REQUIRED")
        frame = self.frame_source(request)
        if frame is None:
            raise ProductionCompositionError("PRODUCTION_DETECTOR_FRAME_SOURCE_REQUIRED")
        from so101_demo.core.detection import DetectionQuery

        # the same whitelisted class the production ACT detector queries with (`adapters/act/detector.py:141`):
        # DetectionQuery validates its class_id against {cup, plastic_cup}, so the model id is NOT a class id
        result = self.detector.detect(frame, DetectionQuery(class_id=self.class_id or "plastic_cup"))
        return _serializable_detection(result)


def _serializable_detection(result):
    """Translate the detector's REAL return type into a closed document the driver can canonicalize.

    P1-1 (rereview 5): the adapter used to return ``detect()`` unchanged. The production type is
    ``core/detection.DetectionBatch`` - a dataclass whose candidates carry ``mask: numpy.ndarray`` - while the driver
    embeds this value in a record it canonicalizes with ``json.dumps``. Tests passed dictionaries, so the mismatch was
    invisible. The translation is explicit and CLOSED: fixed keys, no numpy, and a mask reduced to the two things a
    reader can verify without the array (its shape and its digest). Anything this composition does not understand is
    refused by name rather than stored and choked on later.
    """

    import hashlib

    from so101_demo.core.detection import DetectionBatch

    if not isinstance(result, DetectionBatch):
        raise ProductionCompositionError(
            f"PRODUCTION_DETECTION_RESULT_UNSUPPORTED: {type(result).__name__}")

    def candidate_document(candidate):
        mask = getattr(candidate, "mask", None)
        mask_shape = [int(value) for value in getattr(mask, "shape", ())]
        payload = getattr(mask, "tobytes", None)
        mask_sha256 = hashlib.sha256(payload()).hexdigest() if callable(payload) else hashlib.sha256(
            str(mask_shape).encode()).hexdigest()
        document = {
            "instance_id": candidate.instance_id,
            "class_id": candidate.class_id,
            "confidence": float(candidate.confidence),
            "bbox_xyxy": [float(value) for value in candidate.bbox_xyxy],
            "source_stamp_ns": int(candidate.source_stamp_ns),
            "source_frame_id": candidate.source_frame_id,
            "image_width": int(candidate.image_width),
            "image_height": int(candidate.image_height),
            "segmentation_quality": (None if candidate.segmentation_quality is None
                                     else float(candidate.segmentation_quality)),
            "mask_shape": mask_shape,
            "mask_sha256": mask_sha256,
        }
        return document

    device = getattr(result.runtime_device, "value", result.runtime_device)
    return {
        "model_id": result.model_id,
        "weights_sha256": result.weights_sha256,
        "runtime_device": device,
        "inference_latency_ms": float(result.inference_latency_ms),
        "image_width": int(result.image_width),
        "image_height": int(result.image_height),
        "candidates": [candidate_document(candidate) for candidate in result.candidates],
    }


def _providers_from_seam():
    """Resolve the providers, preferring an explicit seam over the real launch wiring.

    The seam names ``module:factory`` and must return a mapping of provider names to instances. It exists so a test can
    stand in for the ROS/MuJoCo I/O without skipping the composition itself.
    """

    seam = os.environ.get(PROVIDER_SEAM_ENV)
    if not seam:
        raise ProductionCompositionError("PRODUCTION_PROVIDERS_UNAVAILABLE")
    module_name, _, attribute = seam.partition(":")
    if not module_name or not attribute:
        raise ProductionCompositionError("PRODUCTION_PROVIDER_SEAM_INVALID")
    module = importlib.import_module(module_name)
    factory = getattr(module, attribute)
    built = factory()
    if not isinstance(built, dict):
        raise ProductionCompositionError("PRODUCTION_PROVIDER_SEAM_INVALID")
    return built


class PhaseCameraMatrixEvaluator:
    """The production phase-camera evaluator: the admitted matrix, and the GEOMETRY it must be judged against.

    P1-3 (rereview4) named what this class used to be: *"configuration echo, not measurement."* It returned the matrix's
    own occluder names, camera block and hash, with `phase` and `index` as labels - so moving the cup, the camera or an
    occluder could not change the observation, and the driver's `period_s=0.002` was a claim about ONE sample per phase.

    It now measures: for each sample of the phase's joint path it poses the head camera from the admitted geometry and
    the sample's **neck joint** (this camera is head-mounted, so the neck pans it), projects the target through the
    pinhole, and decides visibility against the occluders' own geometry. **Every sample keeps the input it was projected
    from and the result it produced**, so a reader re-derives the projection instead of trusting a summary.

    When it is handed no geometry it says so (`geometry_state: "ABSENT"`) rather than returning something that looks
    like a measurement - the shape the driver's own fixtures rely on, made honest.
    """

    #: the joint that pans the head camera; the same index the search binding reads for its start angle
    NECK_JOINT_INDEX = 6
    #: the horizontal field of view the pixels are derived from when the document does not carry intrinsics
    DEFAULT_HFOV_RAD = 1.0
    #: the admitted phase-path cadence: 2 ms, the period the driver's private replay labels its rows with. One number,
    #: named in one place, so "sampled at the admitted period" is a property rather than a coincidence of two literals
    ADMITTED_PERIOD_S = 0.002

    def __init__(self, document: dict, *, trajectory=None, target=None, occluder_geometry=None,
                 period_s=None) -> None:
        self.document = document
        self.occluders = tuple(document.get("occluders", ()))
        self.trajectory = trajectory
        self.target = target
        self.occluder_geometry = dict(occluder_geometry or {})
        # P1-3 (rereview 5): an admitted occluder without geometry must be refused WHEN THE EVALUATOR IS BUILT, not
        # only when a particular target happens to project - otherwise a measurement can pass through this evaluator
        # with the visibility question silently unanswerable (`_occluded`'s own check still guards the call).
        for name in self.occluders:
            if not isinstance(self.occluder_geometry.get(name), dict):
                raise ProductionCompositionError(f"PHASE_CAMERA_OCCLUDER_GEOMETRY_REQUIRED: {name}")
        declared = period_s if period_s is not None else document.get("period_s")
        self.period_s = float(declared) if declared is not None else self.ADMITTED_PERIOD_S

    # -- geometry -------------------------------------------------------------------------------------------------
    @staticmethod
    def _rotation(rpy):
        import math

        roll, pitch, yaw = (float(value) for value in rpy)
        cr, sr, cp, sp, cy, sy = (math.cos(roll), math.sin(roll), math.cos(pitch), math.sin(pitch),
                                  math.cos(yaw), math.sin(yaw))
        return ((cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr),
                (sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr),
                (-sp, cp * sr, cp * cr))

    @staticmethod
    def _apply(matrix, vector):
        return tuple(sum(row[index] * vector[index] for index in range(3)) for row in matrix)

    def _camera_pose(self, neck_rad: float):
        """The camera's world pose at one sample: the admitted block, panned by the sample's own neck angle."""

        import math

        camera = self.document.get("camera", {})
        position = tuple(float(value) for value in camera.get("position_m", (0.0, 0.0, 0.0)))
        rpy = list(float(value) for value in camera.get("rpy_rad", (0.0, 0.0, 0.0)))
        rpy[2] += float(neck_rad)
        return position, tuple(rpy)

    def _image_size(self):
        """The admitted camera's image size - the bounds `in_frame` is decided against."""

        camera = self.document.get("camera", {})
        for name in ("width_px", "height_px"):
            if camera.get(name) is None:
                raise ProductionCompositionError(f"PHASE_CAMERA_INTRINSICS_REQUIRED: {name}")
        return float(camera["width_px"]), float(camera["height_px"])

    def _project(self, point_world, position, rpy):
        """Pinhole projection: world point -> pixel, or None when it is behind the camera."""

        camera = self.document.get("camera", {})
        # P1-3 (rereview 5): the projection is MADE of these three, so inventing them (640/480/1.0 rad) made
        # `in_frame` a statement about the defaults rather than about the admitted camera. Missing is refused by name.
        for name in ("width_px", "height_px", "horizontal_fov_rad"):
            if camera.get(name) is None:
                raise ProductionCompositionError(f"PHASE_CAMERA_INTRINSICS_REQUIRED: {name}")
        width = float(camera["width_px"])
        height = float(camera["height_px"])
        hfov = float(camera["horizontal_fov_rad"])
        focal = (width / 2.0) / max(1e-9, __import__("math").tan(hfov / 2.0))
        rotation = self._rotation(rpy)
        relative = tuple(point_world[index] - position[index] for index in range(3))
        # world -> camera is the transpose of camera -> world
        in_camera = tuple(sum(rotation[row][col] * relative[row] for row in range(3)) for col in range(3))
        if in_camera[2] <= 1e-6:
            return None
        u = width / 2.0 + focal * in_camera[0] / in_camera[2]
        v = height / 2.0 - focal * in_camera[1] / in_camera[2]
        return u, v, focal, in_camera

    def _occluded(self, position, target_point, target_radius):
        """Whether a named occluder's own geometry stands between the camera and the target."""

        import math

        blocked_by = []
        for name in self.occluders:
            geometry = self.occluder_geometry.get(name)
            if not isinstance(geometry, dict):
                # P1-3 (rereview 5): the matrix ADMITS this occluder, so the visibility decision cannot be made
                # without its geometry - skipping it silently published a measurement that ignored a named occluder
                raise ProductionCompositionError(f"PHASE_CAMERA_OCCLUDER_GEOMETRY_REQUIRED: {name}")
            centre = tuple(float(value) for value in geometry.get("position_m", ()))
            if len(centre) != 3:
                continue
            radius = float(geometry.get("radius_m", 0.0))
            direction = tuple(target_point[index] - position[index] for index in range(3))
            length = math.sqrt(sum(value * value for value in direction))
            if length <= 0:
                continue
            unit = tuple(value / length for value in direction)
            to_centre = tuple(centre[index] - position[index] for index in range(3))
            along = sum(to_centre[index] * unit[index] for index in range(3))
            if along <= 0 or along >= length:            # behind the camera or beyond the target
                continue
            perpendicular = math.sqrt(max(0.0, sum(value * value for value in to_centre) - along * along))
            if perpendicular <= radius + target_radius:
                blocked_by.append(name)
        return blocked_by

    def _sample(self, entry):
        """One retained sample: its INPUT (the joints it was taken at) and its RESULT (the projection)."""

        import math

        joints = [float(value) for value in entry.get("joints_rad", ())]
        neck = joints[self.NECK_JOINT_INDEX] if len(joints) > self.NECK_JOINT_INDEX else 0.0
        position, rpy = self._camera_pose(neck)
        target_point = tuple(float(value) for value in (self.target or {}).get("position_m", ()))
        target_radius = float((self.target or {}).get("radius_m", 0.0))
        projected = self._project(target_point, position, rpy) if len(target_point) == 3 else None
        blocked = self._occluded(position, target_point, target_radius) if projected else []
        sample = {"t_s": float(entry.get("t_s", 0.0)), "joints_rad": joints, "neck_rad": neck,
                  "camera": {"position_m": list(position), "rpy_rad": list(rpy)}}
        if projected is None:
            sample.update({"bbox_px": None, "in_frame": False, "occluded_by": blocked})
            return sample
        u, v, focal, _in_camera = projected
        radius_px = focal * target_radius / max(1e-9, abs(_in_camera[2]))
        # `in_frame`, NOT `visible`: the driver's raw layer refuses verdict-like tokens in a raw row
        # (`FORBIDDEN_OUTPUT_TOKENS` contains "visible"), and whether the projection landed inside the image is a
        # measurement result rather than a verdict - so the key is named for what it measures
        #
        # AND IT MEANS INSIDE THE IMAGE (P1-3, rereview 5): the old code marked every positive-depth projection
        # `in_frame=True`, so a cup a metre off-axis - `u` far beyond the width - was reported in frame. The bounds
        # are the admitted camera's own, and the check is on the bbox the sample carries.
        bbox = [u - radius_px, v - radius_px, u + radius_px, v + radius_px]
        camera_width, camera_height = self._image_size()
        in_frame = bbox[0] >= 0.0 and bbox[1] >= 0.0 and bbox[2] <= camera_width and bbox[3] <= camera_height
        sample.update({"bbox_px": bbox, "in_frame": bool(in_frame), "occluded_by": blocked})
        return sample

    def _path_for(self, phase):
        """The phase's joint path: a mapping, or a provider the run supplies per phase."""

        if callable(self.trajectory):
            return self.trajectory(phase) or {}
        return self.trajectory or {}

    def __call__(self, phase, index):
        camera = self.document.get("camera", {})
        observation = {"phase": phase, "frame_index": index, "row_count": len(self.occluders),
                       "occluders": list(self.occluders),
                       "camera": {"frame_id": camera.get("frame_id"), "width_px": camera.get("width_px"),
                                  "height_px": camera.get("height_px")},
                       "matrix_sha256": self.document.get("matrix_sha256")}
        samples = self._path_for(phase).get("samples") or []
        if not samples or not self.target:
            observation.update({"geometry_state": "ABSENT", "period_s": self.period_s, "samples": []})
            return observation
        observation.update({"geometry_state": "MEASURED", "period_s": self.period_s,
                            "target": dict(self.target),
                            "samples": [self._sample(entry) for entry in samples]})
        return observation


class _MonotonicClock:
    """The production clock the driver calls: one method, monotonic, no mapping dressed up as a clock.

    The previous `_monotonic_clock()` returned `{"now": time.monotonic}`, which the driver's `self.clock.monotonic()`
    cannot use - so the composition could not run a measurement at all (Astra re-review #3, finding 1).
    """

    def monotonic(self) -> float:
        return time.monotonic()


def _monotonic_clock() -> _MonotonicClock:
    return _MonotonicClock()


class Task8StackAdapter:
    """The driver's stack protocol over ONE low-level MuJoCo/ROS client.

    The review's finding was that the composition handed the driver a `PersistentTaskStack()` that implements none of
    `launch / close / cleanup / readback / run_search / camera_info / tf / probe`. This adapter is the missing layer: it
    owns no policy - the composition's rules stay in the composition - and it turns the driver's calls into the
    client's calls, returning the client's own values so a measurement carries real readback rather than constants.
    """

    def __init__(self, client) -> None:
        if client is None:
            raise ProductionCompositionError("PRODUCTION_IO_CLIENT_REQUIRED")
        self.client = client

    def launch(self, anchor):
        return self.client.launch(anchor)

    def close(self, anchor):
        return self.client.close(anchor)

    def cleanup(self, anchor, generation):
        return self.client.cleanup(anchor, generation)

    def readback(self, anchor):
        return self.client.readback(anchor)

    def run_search(self, anchor, request):
        return self.client.run_search(anchor, request)

    def camera_info(self, anchor):
        return self.client.camera_info(anchor)

    def tf(self, anchor):
        return self.client.tf(anchor)

    def probe(self, anchor, command):
        return self.client.probe(anchor, command)


class MeasurementControllerAdapter:
    """The callable controller the measurement driver uses, over the admitted head-search state machine.

    `HeadSearchController` is a state machine (`reset / tick / advance_deadline / fail`), and the driver calls
    `self.controller({"anchor": ..., "sample": ...})` once per recorded sample and stores the returned document. Astra
    re-review #3, finding 1: the composition handed the driver the bare state machine, which is not callable, so the
    success path sealed INVALID with "'HeadSearchController' object is not callable".

    This adapter is that missing layer. It asks the low-level client for the anchor's current frame and neck feedback,
    stamps them with this measurement's identity and receive time, ticks the REAL state machine once, issues the
    resulting command through the same client, and returns the controller's own document as the ack.
    """

    def __init__(self, controller, *, client, clock, session_id: str, attempt_id: str) -> None:
        for name, value in (("client", client), ("clock", clock)):
            if value is None:
                raise ProductionCompositionError(f"PRODUCTION_CONTROLLER_ADAPTER_REQUIRED: {name}")
        for name, value in (("session_id", session_id), ("attempt_id", attempt_id)):
            if not isinstance(value, str) or not value:
                raise ProductionCompositionError(f"PRODUCTION_CONTROLLER_ADAPTER_REQUIRED: {name}")
        self.controller = controller
        self.client = client
        self.clock = clock
        self.session_id = session_id
        self.attempt_id = attempt_id

    def _stamp(self, document: dict) -> dict:
        # the state machine refuses a frame or feedback that does not name this case, and treats an old receive
        # time as stale input, so the stamp is applied here rather than trusted to the client
        return {**document, "session_id": self.session_id, "attempt_id": self.attempt_id,
                "received_wall_s": self.clock.monotonic()}

    def __call__(self, sample: dict) -> dict:
        anchor = sample["anchor"]
        frame = self._stamp(self.client.frame(anchor))
        feedback = self._stamp(self.client.neck_feedback(anchor))
        command = self.controller.tick(frame, feedback, self.clock.monotonic())
        self.client.command(anchor, dict(command))
        return {"anchor": anchor, "sample": sample["sample"], "command": dict(command),
                "status": command.get("status")}


def _admitted_controller_config(*, context, descriptor, session_id=None, attempt_id=None,
                              search_start_rad=None):
    """The controller's 18-field config, from the admitted calibration and this measurement's identity.

    Astra re-review #3, finding 1: the composition used to leave `controller=None` unless a `controller_settings`
    argument was supplied - and nothing in the tree ever supplied it, so the production path had no controller at
    all. The config's one real source is `HeadSearchBinding.search_config`, which assembles it from the admitted
    calibration and validates it by constructing the controller; a missing calibration or identity fails closed by
    name rather than being papered over.
    """

    from .head_search_binding import validate_head_search_binding

    calibration = getattr(context, "calibration_report", None)
    if not isinstance(calibration, dict):
        raise ProductionCompositionError("PRODUCTION_CALIBRATION_REPORT_REQUIRED")
    admitted = validate_head_search_binding(descriptor, calibration)
    # CP-1635: the per-run values arrive as ARGUMENTS. They are produced by the run - the ids belong to the case being
    # measured and the search start is derived from its reset targets - so a context built at admission cannot carry
    # them, and reading them from one refused the formal path at its first check. The refusals are unchanged in
    # substance and in name: a missing value still fails closed rather than being defaulted.
    identity = {}
    for name, value in (("session_id", session_id), ("attempt_id", attempt_id)):
        if not isinstance(value, str) or not value:
            raise ProductionCompositionError(f"PRODUCTION_MEASUREMENT_IDENTITY_REQUIRED: {name}")
        identity[name] = value
    if type(search_start_rad) not in (int, float):
        raise ProductionCompositionError("PRODUCTION_MEASUREMENT_IDENTITY_REQUIRED: search_start_rad")
    return admitted.search_config(session_id=identity["session_id"], attempt_id=identity["attempt_id"],
                                  search_start_rad=float(search_start_rad))


def build_real_providers(*, context, descriptor, binding=None, io_client=None,
                         session_id=None, attempt_id=None, search_start_rad=None,
                         yolo_detector_factory=None, controller_factory=None, frame_source=None,
                         phase_path=None, target=None, occluder_geometry=None) -> dict:
    """Build the five production collaborators from the admitted context and the frozen descriptor.

    This is what the formal entry reaches with nothing set in the environment: the detector comes from the descriptor's
    admitted CUDA configuration through the production factory, the controller from the same descriptor's head-search
    block, the stack from its own class (constructed, never started here), the clock from the monotonic source, and the
    phase camera from the admitted phase-camera matrix.
    """

    # P1-1: the two BOTTOM boundaries may be stood in for - and only those two. Everything else (the stack when a
    # client is supplied, the clock, the controller adapter, the phase camera) is still this composition's own work,
    # which the whole-provider seam could never show because it replaced all five at once.
    if any(value is None for value in (io_client, yolo_detector_factory, frame_source,
                                       phase_path, target, occluder_geometry)):
        seam = _bottom_io_from_seam()
        seam_client = seam.get("client")
        # a named client may be an object or a factory/class: call it once when it is the latter, so the seam can name
        # either the repo's own canned client class or a ready-made instance
        if io_client is None and seam_client is not None:
            io_client = seam_client() if callable(seam_client) and not hasattr(seam_client, "launch") else seam_client
        yolo_detector_factory = yolo_detector_factory or seam.get("detector_factory")
        frame_source = frame_source or seam.get("frame_source")
        phase_path = phase_path or seam.get("phase_path")
        target = target or seam.get("target")
        occluder_geometry = occluder_geometry or seam.get("occluder_geometry")


    from so101_demo.act.search import HeadSearchController
    from so101_demo.act.task8_measurement_schema import load_phase_camera_matrix
    from so101_demo.adapters.perception.detector_factory import DetectorFactoryOptions, build_detector
    from so101_demo.runtime.task_stack import PersistentTaskStack

    head = descriptor["head_search"]
    detector = head["detector"]
    options = DetectorFactoryOptions(
        backend=detector["backend"],
        requested_device=detector["requested_device"],
        allow_cpu_fallback=detector["allow_cpu_fallback"],
        yolo_weights_path=Path(detector["weights_path"]),
        yolo_weights_sha256=detector["weights_sha256"],
        yolo_model_id=detector["model_id"],
        yolo_imgsz=detector["image_size_px"],
    )
    # torch is an opt-in dependency (the repository's own `explicit_ml` marker), so the detector's constructor is
    # the sanctioned external-I/O seam here - exactly the parameter `build_detector` itself exposes
    built = (build_detector(options) if yolo_detector_factory is None
             else build_detector(options, yolo_detector_factory=yolo_detector_factory))
    # never None, and never a second source: the config is built from the admitted calibration and this
    # measurement's identity, and any missing piece raises a named refusal (Astra re-review #3, finding 1)
    config = _admitted_controller_config(context=context, descriptor=descriptor, session_id=session_id,
                                           attempt_id=attempt_id, search_start_rad=search_start_rad)
    if controller_factory is not None:
        controller = controller_factory(config)
    else:
        # the driver needs a CALLABLE, and a bare state machine is not one: the adapter supplies that shape and
        # needs the same low-level client the stack uses
        if io_client is None:
            raise ProductionCompositionError("PRODUCTION_CONTROLLER_ADAPTER_REQUIRED: io_client")
        controller = MeasurementControllerAdapter(
            HeadSearchController(config), client=io_client, clock=_monotonic_clock(),
            session_id=session_id, attempt_id=attempt_id)          # P1-1: the parameters, not the context
    # P1-1: `task8_measurement_driver` calls `self.detector({...})`, while the production detector's interface is
    # `detect(frame, query)` and it declares no `__call__`. Match the protocols here, where the controller is adapted
    # for the same reason - and refuse by name when the frame source the real detector needs is not available.
    detector = built.detector
    if not callable(detector):
        if not hasattr(detector, "detect"):
            raise ProductionCompositionError("PRODUCTION_DETECTOR_PROTOCOL_UNSUPPORTED")
        detector = MeasurementDetectorAdapter(detector, frame_source=frame_source)
    return {
        "detector": detector,
        "controller": controller,
        # the stack is the adapter over the one low-level client when one is supplied; without a client the
        # persistent stack is still built, but the adapter is what implements the protocol the driver calls
        "stack": Task8StackAdapter(io_client) if io_client is not None else PersistentTaskStack(),
        "clock": _monotonic_clock(),
        # P1-3: the phase camera is built with the geometry a measurement actually has - the run's phase path, the
        # target it looks for, and the occluders' own geometry - so the replay measures instead of echoing the matrix.
        # Without them the evaluator says ABSENT, and the DRIVER refuses that by name rather than sealing it.
        "phase_camera": PhaseCameraMatrixEvaluator(
            load_phase_camera_matrix(), trajectory=phase_path,
            # a provider is called once for the run's own values: the target and the occluders' geometry are
            # per-measurement facts, while the phase path is per phase and stays callable
            target=target() if callable(target) else target,
            occluder_geometry=occluder_geometry() if callable(occluder_geometry) else occluder_geometry),
    }


def build_production_measurement_driver(*, context, identity, providers=None,
                                        session_id=None, attempt_id=None, search_start_rad=None,
                                        frame_source=None):
    """Build the single production measurement driver for one measurement context.

    Every rule below is the composition's own, and none of them can be satisfied by injecting a driver instead.
    """

    # section 4.2: the descriptor travels with the context and is the only authority for the device policy
    descriptor = getattr(context, "runtime_descriptor", None)
    if not isinstance(descriptor, dict):
        raise ProductionCompositionError("PRODUCTION_RUNTIME_DESCRIPTOR_REQUIRED")
    require_runtime_descriptor(descriptor)

    # resource binding happens here and only here, and the context has to say it was bound at the entry
    binding = getattr(context, "resource_binding", None)
    if not isinstance(binding, dict) or binding.get("bound_at_entry") is not True:
        raise ProductionCompositionError("PRODUCTION_RESOURCE_BINDING_REQUIRED")

    if providers is not None:                       # explicit test substitution
        supplied = dict(providers)
    elif os.environ.get(PROVIDER_SEAM_ENV):         # external-I/O substitution, tests only
        supplied = _providers_from_seam()
    else:                                           # the formal entry's path: real construction
        supplied = build_real_providers(context=context, descriptor=descriptor, session_id=session_id,
                                        attempt_id=attempt_id, search_start_rad=search_start_rad,
                                        frame_source=frame_source)
    missing = [name for name in PROVIDER_NAMES if name not in supplied]
    if missing:
        raise ProductionCompositionError(f"PRODUCTION_PROVIDER_MISSING: {missing[0]}")

    from so101_demo.act.task8_measurement_driver import Task8MujocoMeasurementDriver

    # one stack, built once, for the whole measurement - never a stack per anchor
    stack = supplied["stack"]
    cleanup_scope = getattr(context, "generation", None)
    if not cleanup_scope:
        raise ProductionCompositionError("PRODUCTION_GENERATION_REQUIRED")

    return Task8MujocoMeasurementDriver(
        identity=identity,
        stack=stack,
        clock=supplied["clock"],
        detector=supplied["detector"],
        controller=supplied["controller"],
        phase_camera=supplied["phase_camera"],
    )
