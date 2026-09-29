"""Task 4: bounded calibration admission.

A `CALIBRATION_REQUIRED` status may admit exactly **one** calibration measurement flight. The production `act`
child stays rejected throughout, release and Recorder operations are never admissible, and a foreign or stale
generation cannot slip in. Every decision is recorded with its generation so a later audit can see which
admission authorized a command.
"""

from __future__ import annotations

import json

ADMISSIBLE_OPERATIONS = ("arm_probe", "neck_target", "stop", "retire")
REFUSED_OPERATIONS = ("release", "recorder")
ADMISSIBLE_STATUS = "CALIBRATION_REQUIRED"


class CalibrationMeasurementAdmission:
    """One-flight admission for a calibration generation."""

    def __init__(self, *, generation: str, status: str, measurement_plan_sha256: str,
                 safe_interval_rad, controller_generation: str, broker_generation: str) -> None:
        if not generation or not measurement_plan_sha256 or len(str(measurement_plan_sha256)) != 64:
            raise ValueError("CALIBRATION_ADMISSION_INVALID")
        lower, upper = safe_interval_rad
        if not lower < upper:
            raise ValueError("CALIBRATION_ADMISSION_INVALID")
        self.generation = generation
        self.status = status
        self.measurement_plan_sha256 = measurement_plan_sha256
        self.safe_interval_rad = (float(lower), float(upper))
        self.controller_generation = controller_generation
        self.broker_generation = broker_generation
        self._admitted = False
        self.events: list[dict] = []

    def admit(self, *, role: str, generation: str, operation: str) -> dict:
        """Admit the single calibration flight; every other request is refused with its reason."""

        def refuse(reason: str) -> dict:
            decision = {"admitted": False, "reason": reason, "generation": self.generation,
                        "operation": operation, "role": role}
            self.events.append(decision)
            return decision

        if self.status != ADMISSIBLE_STATUS:
            return refuse(f"STATUS_NOT_ADMISSIBLE: {self.status}")
        if role != "calibration":
            return refuse(f"ROLE_NOT_CALIBRATION: {role}")
        if generation != self.generation:
            return refuse(f"GENERATION_MISMATCH: {generation}")
        if operation in REFUSED_OPERATIONS:
            return refuse(f"OPERATION_REFUSED: {operation}")
        if operation not in ADMISSIBLE_OPERATIONS:
            return refuse(f"OPERATION_UNKNOWN: {operation}")
        if self._admitted:
            return refuse("SECOND_FLIGHT_REFUSED")
        self._admitted = True
        decision = {"admitted": True, "reason": None, "generation": self.generation,
                    "operation": operation, "role": role,
                    "measurement_plan_sha256": self.measurement_plan_sha256,
                    "safe_interval_rad": list(self.safe_interval_rad)}
        self.events.append(decision)
        return decision


class CalibrationMeasurementContext:
    """The entry-bound calibration context.

    Resource binding happens **once**, at the calibration CLI entry, and travels in this context; internal
    components never rebind. The context carries the contract and controlled-input digests so every event and
    receipt can name the exact inputs its generation was measured against.
    """

    REQUIRED_BINDING_KEYS = ("bound_at_entry", "cpu_cores", "gpu_device")

    def __init__(self, *, generation: str, contract_sha256: str, measurement_plan_sha256: str,
                 safe_interval_rad, candidate_sha256: str, policy_sha256: str,
                 driver_source_sha256: str, controller_generation: str, broker_generation: str,
                 evidence_root: str, resource_binding, runtime_descriptor,
                 # The production controller path reads these four through the context, and until they existed here the
                 # formal composition failed at its first check while a duck-typed test namespace satisfied it
                 # (CP-1632/1633). They default to None so existing callers keep working: what ENFORCES them is the
                 # composition, which refuses by name when they are absent.
                 calibration_report=None, session_id=None, attempt_id=None, search_start_rad=None) -> None:
        # section 4.2/6: the parsed runtime descriptor travels in the context once, so no later component re-reads the
        # preparation directory; the one shared rule reads it, and an omitted descriptor is a state a caller must be
        # able to see rather than a silent default
        # Astra item 2: required, not optional - a context without a descriptor cannot say which configuration was
        # measured, so the ``None`` default was a bypass rather than a convenience
        from so101_demo.act.task8_artifact_bundle import require_runtime_descriptor

        require_runtime_descriptor(runtime_descriptor)
        self.runtime_descriptor = runtime_descriptor
        if type(resource_binding) is not dict:
            raise ValueError("RESOURCE_BINDING_REQUIRED: the CLI entry must bind resources once")
        if resource_binding.get("bound_at_entry") is not True:
            raise ValueError("RESOURCE_BINDING_REQUIRED: binding must originate at the entry, not an inner component")
        if any(key not in resource_binding for key in self.REQUIRED_BINDING_KEYS):
            raise ValueError("RESOURCE_BINDING_REQUIRED: incomplete resource binding")
        for name, value in (("contract_sha256", contract_sha256),
                            ("measurement_plan_sha256", measurement_plan_sha256),
                            ("candidate_sha256", candidate_sha256), ("policy_sha256", policy_sha256),
                            ("driver_source_sha256", driver_source_sha256)):
            if len(str(value)) != 64:
                raise ValueError(f"CONTEXT_IDENTITY_INVALID: {name}")
        lower, upper = safe_interval_rad
        if not lower < upper:
            raise ValueError("CONTEXT_IDENTITY_INVALID: safe interval")
        self.calibration_report = calibration_report
        self.session_id = session_id
        self.attempt_id = attempt_id
        self.search_start_rad = search_start_rad
        self.generation = generation
        self.contract_sha256 = contract_sha256
        self.measurement_plan_sha256 = measurement_plan_sha256
        self.safe_interval_rad = (float(lower), float(upper))
        self.candidate_sha256 = candidate_sha256
        self.policy_sha256 = policy_sha256
        self.driver_source_sha256 = driver_source_sha256
        self.controller_generation = controller_generation
        self.broker_generation = broker_generation
        self.evidence_root = str(evidence_root)
        self.resource_binding = dict(resource_binding)

    def to_dict(self) -> dict:
        return {"generation": self.generation, "contract_sha256": self.contract_sha256,
                "measurement_plan_sha256": self.measurement_plan_sha256,
                "safe_interval_rad": list(self.safe_interval_rad),
                "candidate_sha256": self.candidate_sha256, "policy_sha256": self.policy_sha256,
                "driver_source_sha256": self.driver_source_sha256,
                "controller_generation": self.controller_generation,
                "broker_generation": self.broker_generation, "evidence_root": self.evidence_root,
                "resource_binding": dict(self.resource_binding),
                # Astra re-review P1-2: the descriptor must survive the round trip, or a context that is
                # serialised and rebuilt silently loses the configuration it was admitted under
                "runtime_descriptor": json.loads(json.dumps(self.runtime_descriptor))}

    def admission(self, *, status: str) -> CalibrationMeasurementAdmission:
        """Build the generation's admission from this context, so both share one identity."""

        return CalibrationMeasurementAdmission(
            generation=self.generation, status=status,
            measurement_plan_sha256=self.measurement_plan_sha256,
            safe_interval_rad=self.safe_interval_rad,
            controller_generation=self.controller_generation, broker_generation=self.broker_generation)
