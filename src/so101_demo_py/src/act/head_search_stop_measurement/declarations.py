"""The declared controller stop, feedback and quantisation inputs."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
from pathlib import Path
import sys

from so101_demo.act.head_search_stop_measurement.contracts import (
    _CONSTANT,
    CAL_CONTROLLER_STOP_TOLERANCE_CONTRADICTORY,
    CAL_CONTROLLER_STOP_TOLERANCE_UNDECLARED,
    CAL_FEEDBACK_PERIOD_UNDECLARED,
    DECLARED_CONSTANTS,
    FEEDBACK_PERIOD_RULE,
    QUANTISATION_BASIS_KEY,
    QUANTISATION_RULE,
    QUANTISATION_SEARCH,
    STOP_TOLERANCE_CONSTANT,
    WINDOW_MAX_AGE_CONSTANT,
    WINDOW_SAMPLES_CONSTANT,
    WINDOW_STEP_CONSTANT,
    ZERO_BASIS_REQUIRED,
    _nonnegative_number,
    _positive_number,
    _refuse,
)
from so101_demo.act.head_search_timing_measurement.contracts import (
    _digest,
    _finite,
)
from so101_demo.act.head_search_timing_measurement.control import (
    read_control_period,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256


def read_controller_stop_declaration(path) -> dict:
    """The constants the Head neck's stop window declares, read out of the installed limits module.

    The module is parsed rather than imported: every declared constant of the stop window has to be present
    with a literal value. A module that declares none of them, or only some of them,
    is refused as undeclared - a missing tolerance is not a zero tolerance.
    """

    header = Path(path)
    if not header.is_file():
        raise _refuse(
            CAL_CONTROLLER_STOP_TOLERANCE_UNDECLARED,
            f"the controller's stop declaration {header} does not exist, so no stopped tolerance is declared",
        )
    text = header.read_text(encoding="utf-8")
    constants: dict[str, float] = {}
    source_lines: dict[str, str] = {}
    for line in text.splitlines():
        match = _CONSTANT.match(line.strip())
        if match is None:
            continue
        constants[match.group("name")] = float(match.group("value").replace("_", ""))
        source_lines[match.group("name")] = line.strip()
    missing = [name for name in DECLARED_CONSTANTS if name not in constants]
    if missing:
        raise _refuse(
            CAL_CONTROLLER_STOP_TOLERANCE_UNDECLARED,
            f"the controller's stop declaration {header} declares no {missing}: a controller whose stop "
            f"window declares no stopped tolerance has no tolerance to cite, and a default would be an "
            f"invented number",
        )
    tolerance = constants[STOP_TOLERANCE_CONSTANT]
    if not math.isfinite(tolerance) or tolerance <= 0.0:
        raise _refuse(
            CAL_CONTROLLER_STOP_TOLERANCE_UNDECLARED,
            f"the controller's stop declaration {header} declares a non-positive "
            f"{STOP_TOLERANCE_CONSTANT} of {tolerance!r}",
        )
    samples = constants[WINDOW_SAMPLES_CONSTANT]
    if samples < 3:
        raise _refuse(
            CAL_CONTROLLER_STOP_TOLERANCE_UNDECLARED,
            f"the controller's stop declaration {header} requires only {samples} samples, which cannot even "
            f"carry the three consecutive samples the stop protocol fixes",
        )
    return {
        "path": str(header),
        "sha256": _digest(header),
        "constants": dict(sorted(constants.items())),
        "source_lines": source_lines,
        "stopped_tolerance_rad_s": tolerance,
        "window_samples": int(samples),
        "window_step_s": constants[WINDOW_STEP_CONSTANT] / 1e9,
        "window_max_age_s": constants[WINDOW_MAX_AGE_CONSTANT] / 1e9,
    }


def declared_controller_stop_tolerance(
    *, installed_declaration, source_declaration, controller_config_path
) -> dict:
    """The tolerance the running controller was built with, or a refusal that says why it cannot be cited.

    The installed header is the artefact that declares it; the source declaration has to be the same bytes,
    because otherwise the running controller and the tree it was built from disagree about when a sample is
    stopped. The window's own step has to be the sealed controller's period, because a window that steps at
    another rate is a declaration of another controller.
    """

    installed = read_controller_stop_declaration(installed_declaration)
    source = read_controller_stop_declaration(source_declaration)
    if installed["sha256"] != source["sha256"]:
        raise _refuse(
            CAL_CONTROLLER_STOP_TOLERANCE_CONTRADICTORY,
            f"the installed controller declaration {installed['path']} digests to {installed['sha256']} but "
            f"the source declaration {source['path']} digests to {source['sha256']}: the running controller "
            f"and its source disagree, so neither tolerance can be cited as the running one",
        )
    period = read_control_period(controller_config_path)
    step = installed["window_step_s"]
    if not math.isclose(step, period, rel_tol=0.0, abs_tol=1e-12):
        raise _refuse(
            CAL_CONTROLLER_STOP_TOLERANCE_CONTRADICTORY,
            f"the controller's stop window steps every {step} s but the sealed controller configuration "
            f"declares a period of {period} s: the declaration describes another controller",
        )
    return {
        "stopped_tolerance_rad_s": installed["stopped_tolerance_rad_s"],
        "unit": "rad/s",
        "measured_here": False,
        "declared_by": {
            "path": installed["path"],
            "sha256": installed["sha256"],
            "constant": STOP_TOLERANCE_CONSTANT,
            "source_line": installed["source_lines"][STOP_TOLERANCE_CONSTANT],
            "constant_path": f"head_neck_limits.{STOP_TOLERANCE_CONSTANT}",
        },
        "window_samples": installed["window_samples"],
        "window_step_s": step,
        "window_max_age_s": installed["window_max_age_s"],
        "controller_cycle_period_s": period,
        "source_declaration": {"path": source["path"], "sha256": source["sha256"]},
        "cross_checks": {
            "installed_equals_source": True,
            "window_step_matches_controller_period": True,
            "window_span_s": installed["window_samples"] * step,
        },
    }


def read_feedback_declarations(controller_config_path) -> dict:
    """The two declared rates: the feedback period the stop path consumes, and the controller's own cycle."""

    import yaml

    path = Path(controller_config_path)
    if not path.is_file():
        raise _refuse(
            CAL_FEEDBACK_PERIOD_UNDECLARED, f"the controller configuration {path} does not exist"
        )
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        manager = document["controller_manager"]["ros__parameters"]["update_rate"]
        broadcaster = document["joint_state_broadcaster"]["ros__parameters"]["update_rate"]
    except (KeyError, TypeError, ValueError, yaml.YAMLError) as error:
        raise _refuse(
            CAL_FEEDBACK_PERIOD_UNDECLARED,
            f"the controller configuration {path} declares no controller_manager and "
            f"joint_state_broadcaster update_rate pair: {error}",
        ) from error
    for name, rate in (("controller_manager", manager), ("joint_state_broadcaster", broadcaster)):
        if not _finite(rate) or float(rate) <= 0.0:
            raise _refuse(
                CAL_FEEDBACK_PERIOD_UNDECLARED,
                f"the controller configuration {path} declares the non-positive {name} update_rate {rate!r}",
            )
    return {
        "path": str(path),
        "sha256": _digest(path),
        "period_s": 1.0 / float(broadcaster),
        "feedback_rate_hz": float(broadcaster),
        "controller_cycle_period_s": 1.0 / float(manager),
        "controller_cycle_rate_hz": float(manager),
        "declared_by": {
            "period_s": {
                "keys": {"joint_state_broadcaster": "ros__parameters.update_rate"},
                "rule": FEEDBACK_PERIOD_RULE,
            },
            "controller_cycle_period_s": {
                "keys": {"controller_manager": "ros__parameters.update_rate"},
                "rule": (
                    "the controller manager's own update rate: the rate the controller's stop window steps "
                    "at, recorded beside the feedback period because both are declared"
                ),
            },
        },
    }


def undeclared_quantisation(detail: str | None = None) -> dict:
    """The quantisation block when no artefact declares one: `null`, with the refusal that says so."""

    return {
        "declared": False,
        "measured_here": False,
        "quantisation_rad": None,
        "path": None,
        "sha256": None,
        "declared_by": None,
        "rule": QUANTISATION_RULE,
        "declaration_search": dict(QUANTISATION_SEARCH),
        "detail": detail
        or (
            "no retained artefact declares a joint or encoder resolution: the field is written `null` with "
            "the refusal CAL_FEEDBACK_QUANTISATION_UNDECLARED instead of being defaulted, and phase 7 refuses "
            "any document whose quantisation_rad is missing or not a finite non-negative number"
        ),
    }


def declared_quantisation(path) -> dict:
    """The quantisation a caller's declaration states, or the refusal block when there is no declaration.

    A declaration carries either `quantisation_rad` itself, or the two declarations the resolution is derived
    from: `counts_per_revolution` and `joint_travel_rad`. Anything else is a caller error (a plain
    `ValueError`), because a document that names neither is not a declaration of a resolution.

    An explicitly **zero** `quantisation_rad` is a valid declaration on this platform - the MuJoCo feedback
    path exposes joint velocities with no encoder quantisation, so the second term of the stop envelope is
    identically zero - but only when the document also states the basis of the zero. A bare zero, and a
    document that declares no resolution at all, are refused: the zero is declared here, never defaulted for
    a missing value.
    """

    if path is None:
        return undeclared_quantisation()
    declaration_path = Path(path)
    if not declaration_path.is_file():
        return undeclared_quantisation(
            f"the declared quantisation artefact {declaration_path} does not exist, so no resolution is "
            f"declared and none is invented"
        )
    document = json.loads(declaration_path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError(f"the quantisation declaration {declaration_path} is not a document")
    digest = _digest(declaration_path)
    basis = None
    if "quantisation_rad" in document:
        value = _nonnegative_number("the declared quantisation_rad", document["quantisation_rad"])
        keys = {"quantisation_rad": "quantisation_rad"}
        derivation = "declared directly"
        if value == 0.0:
            basis = document.get(QUANTISATION_BASIS_KEY)
            if type(basis) is not str or not basis.strip():
                raise ValueError(
                    f"the quantisation declaration {declaration_path} declares quantisation_rad = 0.0 "
                    f"without a {QUANTISATION_BASIS_KEY}: {ZERO_BASIS_REQUIRED}"
                )
            basis = basis.strip()
            derivation = "declared directly as an explicit zero, with its basis"
    elif "counts_per_revolution" in document and "joint_travel_rad" in document:
        counts = _positive_number(
            "the declared counts_per_revolution", document["counts_per_revolution"]
        )
        travel = _positive_number("the declared joint_travel_rad", document["joint_travel_rad"])
        value = travel / counts
        keys = {
            "counts_per_revolution": "counts_per_revolution",
            "joint_travel_rad": "joint_travel_rad",
        }
        derivation = "joint_travel_rad / counts_per_revolution"
    else:
        raise ValueError(
            f"the quantisation declaration {declaration_path} declares neither quantisation_rad nor the "
            f"counts_per_revolution and joint_travel_rad pair the resolution is derived from"
        )
    declared_by = {
        "path": str(declaration_path),
        "sha256": digest,
        "keys": keys,
        "rule": QUANTISATION_RULE,
        "derivation": derivation,
    }
    block = {
        "declared": True,
        "measured_here": False,
        "quantisation_rad": value,
        "path": str(declaration_path),
        "sha256": digest,
        "declared_by": declared_by,
        "rule": QUANTISATION_RULE,
        "declaration_search": dict(QUANTISATION_SEARCH),
        "detail": (
            "the resolution is a declaration of the plant or the encoder, read from the artefact named here "
            "and not measured by this producer"
        ),
    }
    if basis is not None:
        declared_by[QUANTISATION_BASIS_KEY] = basis
        block[QUANTISATION_BASIS_KEY] = basis
        block["detail"] = (
            "the resolution is declared as an explicit zero, with the basis of the zero recorded here: the "
            "feedback path of this platform exposes velocities without an encoder quantisation"
        )
    return block


def _document(path, body: Mapping) -> dict:
    """One document, with its own path and the canonical digest of everything but that digest."""

    document = {**body, "path": str(path)}
    document["sha256"] = canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    return document


def _declaration_runtime() -> dict:
    """What a declaration-only producer ran as: an interpreter and nothing else started."""

    import so101_demo

    return {
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "so101_demo_module_path": str(Path(so101_demo.__file__).resolve()),
        "muJoCo_imported": False,
        "cuda_used": False,
        "ros_nodes_started": False,
        "mujoco_neck_commanded": False,
        "hardware_motion_commanded": False,
    }
