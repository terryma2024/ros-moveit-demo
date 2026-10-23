"""Select a pose IK implementation without changing the caller's solver contract."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .deterministic_horizon import PoseIk
from .underactuated_ik import UnderactuatedPoseIk


def resolve_ik_backend(backend: str | None = None) -> str:
    selected = os.environ.get("SO101_IK_BACKEND", "native") if backend is None else backend
    if selected not in ("native", "quik"):
        raise ValueError(f"IK_BACKEND_UNSUPPORTED: {selected!r}")
    return selected


def create_pose_ik(
    urdf_path: Path, joint_names: tuple[str, ...], root_link: str,
    tip_link: str, *, backend: str | None = None,
) -> PoseIk:
    selected = resolve_ik_backend(backend)
    reference = UnderactuatedPoseIk.from_urdf(urdf_path, joint_names, root_link, tip_link)
    if selected == "native":
        # Retain exact-type optimizations and the original native numerical behavior.
        return reference
    from .quik_ik import QuikPoseIk

    return QuikPoseIk(reference)


def describe_pose_ik(solver) -> dict[str, object]:
    """Record the actual implementation outside the IK hot loop."""
    from .quik_ik import QuikPoseIk

    if type(solver) is QuikPoseIk:
        return solver.provenance()
    if type(solver) is UnderactuatedPoseIk:
        from . import underactuated_ik

        paths = {"python": Path(underactuated_ik.__file__)}
        if solver._numeric is not None:
            from . import _ik_numeric

            paths["kernel"] = Path(_ik_numeric.__file__)
        return {"backend": "native", "artifacts": {
            key: {"path": str(path.resolve()),
                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for key, path in paths.items()
        }}
    return {"backend": "injected", "class": type(solver).__qualname__}


def cacheable_pose_ik(solver) -> bool:
    """Opt in only known deterministic implementations, preserving injected semantics."""
    if type(solver) is UnderactuatedPoseIk:
        return True
    from .quik_ik import QuikPoseIk

    return type(solver) is QuikPoseIk
