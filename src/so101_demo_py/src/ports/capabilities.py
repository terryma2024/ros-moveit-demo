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
