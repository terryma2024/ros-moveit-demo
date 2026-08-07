"""Standalone Python implementation of the SO-101 Gazebo demo."""


def require_gazebo_bindings() -> None:
    """Fail with an actionable message when Gazebo Python bindings are absent."""
    try:
        import gz.msgs10  # noqa: F401
        import gz.transport13  # noqa: F401
    except ImportError as error:
        raise RuntimeError(
            "Gazebo Python bindings gz.transport13 and gz.msgs10 are required; "
            "install the matching Ubuntu bindings for this Gazebo runtime."
        ) from error
