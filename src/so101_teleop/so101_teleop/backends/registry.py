"""Fixed backend ID to installed profile registry."""

from __future__ import annotations

from pathlib import Path

from .profile import BackendProfile, ProfileError, load_profile_file


BACKEND_IDS = ("gazebo_cpp", "gazebo_py", "mujoco_py")


def load_backend_profile(backend_id: str, share_dir: Path | None = None) -> BackendProfile:
    if backend_id not in BACKEND_IDS:
        raise ProfileError(f"BACKEND_ID_INVALID: {backend_id!r}")
    if share_dir is None:
        try:
            from ament_index_python.packages import get_package_share_directory
            root = Path(get_package_share_directory("so101_teleop"))
        except Exception as error:
            raise ProfileError(f"PROFILE_PACKAGE_NOT_FOUND: {error}") from error
    else:
        root = Path(share_dir)
    profile = root / "config" / "backends" / f"{backend_id}.yaml"
    return load_profile_file(profile, expected_backend=backend_id)
