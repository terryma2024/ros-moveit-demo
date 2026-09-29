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
        return {"phase": phase, "frame_index": index, "row_count": len(self.occluders),
                "occluders": list(self.occluders)}


def _monotonic_clock():
    return {"now": time.monotonic}


def build_real_providers(*, context, descriptor, controller_settings=None, binding=None,
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
    if controller_settings is not None:
        # the controller is settings-driven: the admission entry derives them from the admitted calibration report
        # (the child's own helper) and hands them in, so the library reads no environment of its own
        controller = (HeadSearchController(controller_settings) if controller_factory is None
                      else controller_factory(controller_settings))
    else:
        controller = None
    return {
        "detector": built.detector,
        "controller": controller,
        "stack": PersistentTaskStack(),          # constructed only; the composition never starts it here
        "clock": _monotonic_clock(),
        "phase_camera": PhaseCameraMatrixEvaluator(load_phase_camera_matrix()),
    }


def build_production_measurement_driver(*, context, identity, providers=None):
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
        supplied = build_real_providers(context=context, descriptor=descriptor)
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
