"""Explicit backend capability declaration."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BackendCapabilities:
    atomic_snapshot: bool
    snapshot_with_receipt: bool
    reset_epoch: bool
    pause: bool
    viewer_camera: bool
    physical_contact_force: bool
    lossless_physics_step_trace: bool


@dataclass(frozen=True, slots=True)
class CapabilityValidation:
    accepted: bool
    missing: tuple[str, ...] = ()
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class CapabilityRequirements:
    required: tuple[str, ...]

    @classmethod
    def base_execute(cls) -> "CapabilityRequirements":
        return cls(("snapshot_with_receipt", "reset_epoch", "physical_contact_force"))

    @classmethod
    def mujoco_qualification(cls) -> "CapabilityRequirements":
        return cls((*cls.base_execute().required, "lossless_physics_step_trace"))

    def validate(self, capabilities: BackendCapabilities) -> CapabilityValidation:
        missing = tuple(name for name in self.required if not getattr(capabilities, name, False))
        return CapabilityValidation(
            not missing,
            missing,
            "CAPABILITY_MISSING" if missing else None,
        )
