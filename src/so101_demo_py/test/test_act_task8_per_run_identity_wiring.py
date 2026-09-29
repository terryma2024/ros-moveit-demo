"""The per-run values must reach the composition as ARGUMENTS, not through the context.

`session_id`, `attempt_id` and `search_start_rad` are produced by the run: the ids belong to the case being measured
and the search start is derived from the reset targets. The adapter already supplies them that way -

    config = binding.search_config(session_id=request["session_id"], attempt_id=request["attempt_id"],
                                   search_start_rad=targets.joints_rad[6])          # pick_place_search_binding.py:57

- while the production composition reads them through `getattr(context, ...)`, and a context the CLI builds cannot
carry them because they do not exist yet at admission. The owner's decision (CP-1635) was to let the DRIVER pass them
into the composition, which is this file's subject.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from so101_demo.act.task8_calibration_admission import CalibrationMeasurementContext  # noqa: E402


def _formal_context(tmp_path, **extra):
    from test_act_task8_formal_context_fields import _formal_context as build

    return build(evidence_root=str(tmp_path), **extra)


def test_the_composition_takes_the_per_run_values_as_arguments(tmp_path):
    """`build_real_providers` must accept the three, because it is the layer that builds the controller config."""

    import inspect

    from so101_demo.act.task8_production_composition import build_real_providers

    parameters = inspect.signature(build_real_providers).parameters
    missing = [name for name in ("session_id", "attempt_id", "search_start_rad") if name not in parameters]
    assert not missing, (
        f"the composition must take {missing} as arguments: they are produced by the run, and a context built at "
        "admission cannot carry them")


def test_the_controller_config_comes_from_the_arguments_and_the_admitted_calibration(tmp_path):
    """And the config is built FROM those arguments - reading them from the context cannot work in production."""

    from test_act_head_search_binding import _inputs

    from so101_demo.act.task8_production_composition import _admitted_controller_config

    runtime, calibration, _weights, _sample = _inputs(tmp_path)
    context = _formal_context(tmp_path, calibration_report=calibration, runtime_descriptor=runtime)
    config = _admitted_controller_config(context=context, descriptor=runtime,
                                        session_id="session-1", attempt_id="attempt-1",
                                        search_start_rad=0.25)
    # the config is a mapping, not an object: read it the way its consumers do
    assert config["session_id"] == "session-1" and config["attempt_id"] == "attempt-1"
    assert config["search_start_rad"] == pytest.approx(0.25), config["search_start_rad"]
