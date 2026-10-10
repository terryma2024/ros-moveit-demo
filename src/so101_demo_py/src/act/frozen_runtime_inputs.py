"""Runtime loading of the frozen input set by the Teacher and the Recorder (Phase A4c).

Both processes read the frozen manifest, never the live installed configuration, and both refuse a mismatch before they act:
the Teacher before its first motion, the Recorder before it listens. Everything here is read-only.
"""

from __future__ import annotations

from pathlib import Path

TEACHER_ENDPOINT_BINDING = "teacher_endpoint"
EXECUTION_POLICY_BINDING = "teacher_execution_policy"
TEACHER_POLICY_BINDINGS = (TEACHER_ENDPOINT_BINDING, EXECUTION_POLICY_BINDING)


def load_teacher_frozen_inputs(manifest_path: Path):
    """(frozen document, execution snapshot, snapshot root) for a Teacher run; refuses a missing or changed policy.

    The Teacher's own policy loader reads `<snapshot root>/config/act`; this proves, before any motion, that those bytes
    are the ones the freeze bound (`verify_frozen_inputs` cross-checks each policy file against the snapshot's copy).
    """
    from .execution_snapshot import verify_execution_snapshot
    from .diagnostic_episode_inputs import validate_execution_snapshot_binding, verify_frozen_inputs

    manifest_path = Path(manifest_path)
    frozen = verify_frozen_inputs(manifest_path)
    binding = frozen.get("execution_snapshot")
    if binding is None or "runtime_policy" not in frozen:
        raise ValueError("EPISODE_EXECUTION_INPUTS_REQUIRED")
    for name in TEACHER_POLICY_BINDINGS:
        if name not in frozen:
            raise ValueError("INPUTS_TEACHER_POLICY_REQUIRED: " + name)
    validate_execution_snapshot_binding(binding)
    root = manifest_path.parent / binding["path"]
    snapshot = verify_execution_snapshot(root, expected_sha256=binding["sha256"])
    for name in TEACHER_POLICY_BINDINGS:
        config_path = f"config/act/{name}.yaml"
        copy = snapshot["files"].get(config_path)
        if copy is None or copy["sha256"] != frozen[name]["file_sha256"]:
            raise ValueError("INPUTS_TEACHER_POLICY_MISMATCH: " + name)
    return frozen, snapshot, root


def load_recorder_frozen_policy(manifest_path: Path) -> dict:
    """The frozen `episode_recorder` policy (values and policy_sha256), or a refusal when it was not frozen."""
    from .diagnostic_episode_inputs import verify_frozen_inputs
    from .offline.policy import RecorderConfigRefused

    try:
        frozen = verify_frozen_inputs(Path(manifest_path))
    except (ValueError, OSError) as error:
        raise RecorderConfigRefused(f"RECORDER_FROZEN_INPUTS_INVALID: {error}") from error
    binding = frozen.get("episode_recorder")
    if binding is None:
        raise RecorderConfigRefused("RECORDER_POLICY_NOT_FROZEN")
    return {**binding["values"], "policy_sha256": binding["policy_sha256"]}
