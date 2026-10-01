"""Phase 1 of the formal head search calibration: sealed inputs, one admission, one resource binding.

The phase validates the six controlled dependencies the plan names - dataset manifest, model manifest,
geometry seal, scenario partitions, production config and camera config - by the digest the seal declares
for each, so an absent or rewritten input is refused before any later phase reads it. It then takes the
single `role=calibration` measurement flight through the repository's existing
`CalibrationMeasurementAdmission`, with release and recorder refused unconditionally, and binds the run's
resources exactly once at the entry, because design section 8.2 allows no phase to rebind them.

Nothing here starts ROS, MuJoCo or a detector and nothing is written unless the caller passes an explicit
`output_path`; the phase document is the only file this module ever creates.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from collections.abc import Mapping
from pathlib import Path

from so101_demo.act.task8_calibration_admission import (
    ADMISSIBLE_OPERATIONS,
    REFUSED_OPERATIONS,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256

SCHEMA_VERSION = 1
KIND = "head_search_calibration_inputs"
PHASE = "input_validation"

#: the three refusals phase 1 owns, exactly as the plan fixes their spelling
CAL_INPUT_UNSEALED = "CAL_INPUT_UNSEALED"
CAL_ADMISSION_REFUSED = "CAL_ADMISSION_REFUSED"
CAL_BINDING_REBOUND = "CAL_BINDING_REBOUND"
REFUSAL_CODES = (CAL_INPUT_UNSEALED, CAL_ADMISSION_REFUSED, CAL_BINDING_REBOUND)

#: the controlled dependencies of plan section 2b, and nothing else: an input phase 1 cannot name is not
#: a sealed input it can validate, so a seal declaring one is refused rather than silently digested
SEALED_INPUT_NAMES = (
    "dataset_manifest",
    "model_manifest",
    "geometry_seal",
    "scenario_partitions",
    "production_config",
    "camera_config",
)
SEALED_INPUT_KEYS = ("path", "sha256")

#: the only role a calibration measurement flight may carry
CALIBRATION_ROLE = "calibration"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class CalibrationInputsRefused(ValueError):
    """A phase-1 refusal, carrying the exact code the run records and stops on."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _finite(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _valid_interval(value) -> bool:
    return (
        type(value) in (list, tuple)
        and len(value) == 2
        and all(_finite(item) for item in value)
        and value[0] < value[1]
    )


def _sealed_bytes(name: str, declared_path) -> bytes:
    """Read one declared input as the regular file the seal names, never through a symlink."""

    if type(declared_path) is not str or not declared_path:
        raise CalibrationInputsRefused(CAL_INPUT_UNSEALED, f"{name}: the seal names no path")
    path = Path(declared_path)
    if not path.is_absolute() or ".." in path.parts or path.is_symlink():
        raise CalibrationInputsRefused(
            CAL_INPUT_UNSEALED, f"{name}: {declared_path} is not a plain sealed path"
        )
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise CalibrationInputsRefused(
                    CAL_INPUT_UNSEALED, f"{name}: {declared_path} is not a regular file"
                )
            return stream.read()
    except OSError as error:
        raise CalibrationInputsRefused(
            CAL_INPUT_UNSEALED,
            f"{name}: {declared_path} is absent or unreadable ({error.strerror or error})",
        ) from error


def validate_sealed_inputs(sealed_inputs) -> dict:
    """Digest every sealed input and return the validated manifest, or refuse the whole seal.

    The caller supplies the seal: one `{"path", "sha256"}` declaration per controlled dependency. A seal
    that omits a dependency, names something else, or whose bytes no longer match the declared digest is
    refused as `CAL_INPUT_UNSEALED` before any phase consumes it. Reading is the only filesystem access.
    """

    if not isinstance(sealed_inputs, Mapping):
        raise CalibrationInputsRefused(
            CAL_INPUT_UNSEALED, "the seal is not a document of declared sealed inputs"
        )
    declared_names = set(sealed_inputs)
    required = set(SEALED_INPUT_NAMES)
    if declared_names != required:
        missing = sorted(required - declared_names)
        unknown = sorted(declared_names - required)
        detail = []
        if missing:
            detail.append(f"the seal omits {missing}")
        if unknown:
            detail.append(f"the seal declares unvalidatable inputs {unknown}")
        raise CalibrationInputsRefused(CAL_INPUT_UNSEALED, "; ".join(detail))

    inputs: dict[str, dict] = {}
    for name in SEALED_INPUT_NAMES:
        declaration = sealed_inputs[name]
        if not isinstance(declaration, Mapping) or set(declaration) != set(SEALED_INPUT_KEYS):
            raise CalibrationInputsRefused(
                CAL_INPUT_UNSEALED,
                f"{name}: a sealed input is declared as exactly {SEALED_INPUT_KEYS}",
            )
        declared_sha256 = declaration["sha256"]
        payload = _sealed_bytes(name, declaration["path"])
        measured = hashlib.sha256(payload).hexdigest()
        if measured != declared_sha256:
            raise CalibrationInputsRefused(
                CAL_INPUT_UNSEALED,
                f"{name}: {declaration['path']} digests to {measured} but the seal declares "
                f"{declared_sha256!r}",
            )
        inputs[name] = {
            "path": declaration["path"],
            "sha256": measured,
            "size_bytes": len(payload),
        }

    body = {"schema_version": SCHEMA_VERSION, "kind": KIND, "sealed": True, "inputs": inputs}
    manifest = dict(body)
    # the manifest's own digest covers every recorded input, so later phases cite one identity
    manifest["manifest_sha256"] = canonical_sha256(body)
    return manifest


def decide_calibration_admission(
    *, admission, generation: str, operation: str, role: str = CALIBRATION_ROLE
) -> dict:
    """Take the single `role=calibration` measurement flight, or refuse with `CAL_ADMISSION_REFUSED`.

    Release and recorder are refused here, before the admission is consulted, so no admission document -
    however permissive - can make them admissible. Any role but calibration and any operation outside the
    four the measurement protocol admits are refused the same way. The granted decision must bind one
    measurement plan and one safe interval; an admission that grants a bare flight is refused too.
    """

    if operation in REFUSED_OPERATIONS:
        raise CalibrationInputsRefused(
            CAL_ADMISSION_REFUSED,
            f"{operation!r} is refused unconditionally: a calibration run never releases or records",
        )
    if role != CALIBRATION_ROLE:
        raise CalibrationInputsRefused(
            CAL_ADMISSION_REFUSED, f"role {role!r} is not {CALIBRATION_ROLE!r}"
        )
    if operation not in ADMISSIBLE_OPERATIONS:
        raise CalibrationInputsRefused(
            CAL_ADMISSION_REFUSED,
            f"operation {operation!r} is not one of {ADMISSIBLE_OPERATIONS}",
        )
    granted = admission.admit(role=role, generation=generation, operation=operation)
    if not isinstance(granted, Mapping) or granted.get("admitted") is not True:
        reason = granted.get("reason") if isinstance(granted, Mapping) else granted
        raise CalibrationInputsRefused(
            CAL_ADMISSION_REFUSED, f"{role!r} {operation!r} on {generation!r}: {reason}"
        )
    plan_sha256 = granted.get("measurement_plan_sha256")
    interval = granted.get("safe_interval_rad")
    if type(plan_sha256) is not str or _SHA256.fullmatch(plan_sha256) is None:
        raise CalibrationInputsRefused(
            CAL_ADMISSION_REFUSED, "the admission granted a flight with no measurement plan"
        )
    if not _valid_interval(interval):
        raise CalibrationInputsRefused(
            CAL_ADMISSION_REFUSED, "the admission granted a flight with no safe interval"
        )
    return {
        "admitted": True,
        "reason": None,
        "role": role,
        "generation": generation,
        "operation": operation,
        "measurement_plan_sha256": plan_sha256,
        "safe_interval_rad": [float(interval[0]), float(interval[1])],
    }


class CalibrationResourceBinder:
    """The run's resources, bound exactly once at the CLI entry and never rebound inside a phase."""

    #: the keys the production measurement context requires of an entry-origin binding
    REQUIRED_KEYS = ("bound_at_entry", "cpu_cores", "gpu_device")

    def __init__(self) -> None:
        self._binding: dict | None = None

    @property
    def binding(self) -> dict | None:
        return None if self._binding is None else dict(self._binding)

    def bind(
        self,
        *,
        generation: str,
        measurement_plan_sha256: str,
        safe_interval_rad,
        cpu_cores: int,
        gpu_device,
    ) -> dict:
        """Bind once and return the record; a second attempt in the same run raises `CAL_BINDING_REBOUND`.

        A malformed resource argument is a caller bug and raises a plain `ValueError` without a refusal
        code, so it can never be mistaken for one of the three calibration decisions.
        """

        if self._binding is not None:
            raise CalibrationInputsRefused(
                CAL_BINDING_REBOUND,
                f"the run's resources are already bound for generation "
                f"{self._binding['generation']!r}; the entry binds once and no phase rebinds",
            )
        if type(generation) is not str or not generation:
            raise ValueError("a resource binding needs the generation it is bound to")
        if type(measurement_plan_sha256) is not str or not measurement_plan_sha256:
            raise ValueError("a resource binding needs the measurement plan it is bound to")
        if not _valid_interval(safe_interval_rad):
            raise ValueError("a resource binding needs one ordered safe interval")
        if type(cpu_cores) is not int or cpu_cores <= 0:
            raise ValueError("cpu_cores must be a positive int")
        if not (type(gpu_device) is int or (type(gpu_device) is str and gpu_device)):
            raise ValueError("gpu_device must be an int or a non-empty name")
        self._binding = {
            "bound_at_entry": True,
            "cpu_cores": cpu_cores,
            "gpu_device": gpu_device,
            "generation": generation,
            "measurement_plan_sha256": measurement_plan_sha256,
            "safe_interval_rad": [float(safe_interval_rad[0]), float(safe_interval_rad[1])],
        }
        return dict(self._binding)


def validate_head_search_calibration_inputs(
    *,
    sealed_inputs,
    admission,
    generation: str,
    operation: str,
    cpu_cores: int,
    gpu_device,
    role: str = CALIBRATION_ROLE,
    binder: CalibrationResourceBinder | None = None,
    output_path=None,
) -> dict:
    """Produce phase 1's three artefacts in order: manifest, admission decision, resource binding.

    The CLI holds one `binder` for the whole run and passes it here at the entry, so a later phase that
    tried to bind again would be refused with `CAL_BINDING_REBOUND`. When `output_path` is given the phase
    document is written there and nowhere else; without it the phase writes nothing at all.
    """

    manifest = validate_sealed_inputs(sealed_inputs)
    decision = decide_calibration_admission(
        admission=admission, generation=generation, operation=operation, role=role
    )
    run = CalibrationResourceBinder() if binder is None else binder
    binding = run.bind(
        generation=decision["generation"],
        measurement_plan_sha256=decision["measurement_plan_sha256"],
        safe_interval_rad=decision["safe_interval_rad"],
        cpu_cores=cpu_cores,
        gpu_device=gpu_device,
    )
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "phase": PHASE,
        "manifest": manifest,
        "admission": decision,
        "resource_binding": binding,
    }
    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return document
