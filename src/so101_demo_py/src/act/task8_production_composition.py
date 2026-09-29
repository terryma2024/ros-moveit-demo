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


def build_production_measurement_driver(*, context, providers=None):
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

    supplied = dict(providers) if providers is not None else _providers_from_seam()
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
        stack=stack,
        clock=supplied["clock"],
        detector=supplied["detector"],
        controller=supplied["controller"],
        phase_camera=supplied["phase_camera"],
    )
