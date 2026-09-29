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

#: the five collaborators the driver needs, and the order the composition builds them in
PROVIDER_NAMES = ("stack", "clock", "detector", "controller", "phase_camera")


class ProductionCompositionError(ValueError):
    """Raised when the composition cannot be built; the message is the machine-readable code."""


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
    """The production phase-camera evaluator: the admitted matrix, read per (phase, index).

    No such component existed before this batch - the repository had the matrix (``load_phase_camera_matrix``) and the
    aggregator's derivation, but nothing the driver could call. It returns the observation shape the driver and the
    chain fixture both document, with the matrix's own occluder set as its content.
    """

    def __init__(self, document: dict) -> None:
        self.document = document
        self.occluders = tuple(document.get("occluders", ()))

    def __call__(self, phase, index):
        # the observation names the geometry the matrix was evaluated against, so the row proves WHICH camera and
        # which admitted matrix produced it rather than echoing a configured occluder set (Astra re-review #3, finding 1)
        camera = self.document.get("camera", {})
        return {"phase": phase, "frame_index": index, "row_count": len(self.occluders),
                "occluders": list(self.occluders),
                "camera": {"frame_id": camera.get("frame_id"), "width_px": camera.get("width_px"),
                           "height_px": camera.get("height_px")},
                "matrix_sha256": self.document.get("matrix_sha256")}


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
                         yolo_detector_factory=None, controller_factory=None) -> dict:
    """Build the five production collaborators from the admitted context and the frozen descriptor.

    This is what the formal entry reaches with nothing set in the environment: the detector comes from the descriptor's
    admitted CUDA configuration through the production factory, the controller from the same descriptor's head-search
    block, the stack from its own class (constructed, never started here), the clock from the monotonic source, and the
    phase camera from the admitted phase-camera matrix.
    """

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
            session_id=getattr(context, "session_id"), attempt_id=getattr(context, "attempt_id"))
    return {
        "detector": built.detector,
        "controller": controller,
        # the stack is the adapter over the one low-level client when one is supplied; without a client the
        # persistent stack is still built, but the adapter is what implements the protocol the driver calls
        "stack": Task8StackAdapter(io_client) if io_client is not None else PersistentTaskStack(),
        "clock": _monotonic_clock(),
        "phase_camera": PhaseCameraMatrixEvaluator(load_phase_camera_matrix()),
    }


def build_production_measurement_driver(*, context, identity, providers=None,
                                        session_id=None, attempt_id=None, search_start_rad=None):
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
                                        attempt_id=attempt_id, search_start_rad=search_start_rad)
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
