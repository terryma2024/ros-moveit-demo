"""The frozen Teacher execution policy as the dynamic execute runtime reads it: schema, DESCEND distance, policy file, state age, and the
early telemetry-safety load. Split out of `dynamic_runtime` to keep that module under the module size limit; behaviour unchanged."""

from __future__ import annotations

from pathlib import Path


def _frozen_teacher_schema(frozen) -> int:
    """The schema of the frozen Teacher execution policy (3 for a freeze that does not say)."""

    try:
        version = frozen["teacher_execution_policy"]["values"]["schema_version"]
    except (KeyError, TypeError):
        return 3
    return version if type(version) is int else 3


def _frozen_descend_final_distance_m(frozen):
    """The frozen schema 5 `descend_final_distance_m` (m), or None for a freeze that is not schema 5 (the reachability preflight then
    checks the six interpolated DESCEND segments). A schema 5 freeze without the key is not a policy this build can run."""

    if _frozen_teacher_schema(frozen) < 5:
        return None
    from ..act.teacher_endpoint import DESCEND_DISTANCE_FIELD

    try:
        return float(frozen["teacher_execution_policy"]["values"][DESCEND_DISTANCE_FIELD])
    except (KeyError, TypeError, ValueError):
        raise RuntimeError("TEACHER_POLICY_UNAVAILABLE: " + DESCEND_DISTANCE_FIELD) from None


def _frozen_run_inputs(frozen, point_id, template, start_draw=None):
    """R3-a: (episode values, template of the run, carry via offset) of a schema 6 freeze, derived from the frozen diversity block, the
    scene id (the lease point id) and the start pose draw the reset applied; (None, ``template``, None) for a freeze that is not
    schema 6, which changes nothing (and ignores the draw).

    A schema 6 freeze without a scene id or without the applied draw, or whose block does not re-parse, is refused before any motion."""

    if _frozen_teacher_schema(frozen) < 6:
        return None, template, None
    from ..act.teacher_diversity import episode_template, parse_diversity, values_for_policy

    if not isinstance(point_id, str) or not point_id:
        raise RuntimeError("TEACHER_DIVERSITY_SCENE_ID_REQUIRED")
    if start_draw is None:
        raise RuntimeError("TEACHER_DIVERSITY_START_DRAW_REQUIRED")
    policy = dict(frozen["teacher_execution_policy"]["values"])
    policy["diversity"] = parse_diversity(policy.get("diversity"))
    values = values_for_policy(policy, point_id, start_draw)
    return values, episode_template(template, values), tuple(values["carry_via_offset_m"])


def _frozen_policy_file(frozen, snapshot) -> str:
    """The file name, under the snapshot's `config/act`, of the Teacher execution policy the freeze bound: the default file, or the
    `teacher_execution_policy_*.yaml` variant whose bytes the freeze carries."""

    from ..act.diagnostic_episode_inputs import snapshot_policy_path
    from ..act.teacher_endpoint import EXECUTION_POLICY_FILE

    try:
        path = snapshot_policy_path(snapshot["files"], "teacher_execution_policy", frozen["teacher_execution_policy"]["file_sha256"])
    except (KeyError, TypeError):
        return EXECUTION_POLICY_FILE
    return EXECUTION_POLICY_FILE if path is None else path.rsplit("/", 1)[-1]


def _load_safety_inputs(teacher_safety, manifest_path: Path, mark):
    """(inputs, error) of `teacher_safety.load_frozen_safety`, marked as the phase events `load_frozen_safety.begin/end`. The load is
    telemetry only: a failure is returned, never raised."""

    mark("load_frozen_safety.begin")
    try:
        return teacher_safety.load_frozen_safety(manifest_path), None
    except Exception as error:  # noqa: BLE001 - non-gating
        return None, error
    finally:
        mark("load_frozen_safety.end")


def _execution_state_max_age_s(share_dir, *, teacher_run: bool, file_name: str | None = None):
    """The execution policy's state age (the Teacher policy of a Teacher run, else the general runtime policy), or None when it
    cannot be read.

    An unreadable policy is refused where the execution loads it (no motion without it); this only sizes the
    scene observer the release preflight joins against.
    """
    from ..act.general_runtime_policy import GENERAL_RUNTIME_FILE, load_general_runtime_policy
    from ..act.teacher_endpoint import EXECUTION_POLICY_FILE, load_teacher_execution_policy

    loader, file_name = ((load_teacher_execution_policy, file_name or EXECUTION_POLICY_FILE) if teacher_run
                         else (load_general_runtime_policy, GENERAL_RUNTIME_FILE))
    try:
        return loader(Path(share_dir) / "config/act" / file_name)["state_max_age_s"]
    except (OSError, ValueError):
        return None
