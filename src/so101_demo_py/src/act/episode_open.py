"""Open the Recorder's episode from the frozen inputs and the full issued lease (Phase A4c).

This is the opener the Teacher child used to carry inside its own CLI; it lives here so that only the offline episode
processor owns it. It reads the frozen manifest, never the live configuration.
"""

from __future__ import annotations

from pathlib import Path


def diversity_arguments(frozen: dict, scene_id: str, start_draw) -> dict:
    """R3-a: the `open_point_episode` arguments that put a frozen schema 6 policy's derived values, with the start pose draw the reset
    applied, into the episode identity (episode.json); {} for a freeze without a diversity block. A schema 6 freeze without the draw
    is refused: the identity would otherwise claim draw 0 for an episode that started from another pose."""

    from .teacher_diversity import values_for_policy

    binding = frozen.get("teacher_execution_policy")
    policy_values = None if not isinstance(binding, dict) else binding.get("values")
    if not isinstance(policy_values, dict) or policy_values.get("diversity") is None:
        return {}
    if start_draw is None:
        raise ValueError("TEACHER_DIVERSITY_START_DRAW_REQUIRED")
    return {"diversity": values_for_policy(policy_values, scene_id, start_draw), "diversity_policy": policy_values}


def appearance_arguments(frozen: dict, manifest_path, scene_id: str, teacher_record, *, share=None) -> dict:
    """Indoor P3: the `open_point_episode` arguments that put the scene's appearance and Teacher source into the episode identity
    (episode.json); {} for a freeze whose scene list has no appearance plan.

    The row of the frozen scene list is re-derived from its plan (`frozen_appearance.scene_entry`), the Teacher manifest's own record of the
    source and draw must be that row's (the Teacher read the same list), and a variant is realized again here, on this host's install, so the
    identity carries the realized hash and the stripped physics fingerprint that this host computes (equal to the nominal one, or refused)."""

    import tempfile

    from . import appearance_plan as ap
    from . import frozen_appearance, scene_variant_run

    if "scene_manifest" not in frozen:
        return {}
    if share is None:
        from ament_index_python.packages import get_package_share_directory
        share = get_package_share_directory("so101_demo_py")
    entry = frozen_appearance.scene_entry(frozen, manifest_path, scene_id,
                                          inventory=lambda: ap.scene_inventory(scene_variant_run.nominal_dir(share)))
    if entry is None:
        return {}
    appearance = entry["appearance"]
    if (not isinstance(teacher_record, dict) or teacher_record.get("source") != entry["teacher_source"]
            or teacher_record.get("draw_sha256") != appearance["draw_sha256"] or teacher_record.get("plan_sha256") != appearance["plan_sha256"]):
        raise ValueError("APPEARANCE_TEACHER_MANIFEST_MISMATCH")
    realized = None
    if appearance["variant"] is not None:
        with tempfile.TemporaryDirectory(prefix="so101-appearance-") as scratch:
            realized = scene_variant_run.realize_into(scratch + "/variant", share, appearance["variant"])
    return {"scene_appearance": frozen_appearance.identity_record(entry, realized=realized), "teacher_source": entry["teacher_source"]}


def open_recorder_episode(options, *, offline: bool = False):
    """Bind the actual frozen bytes and full issued lease before opening the Recorder's episode.

    `offline` is the after-the-fact processor (act/offline/processor.py): the lease was issued to a run that has ended, so its
    currency against the current monotonic clock and the live `working/` location are not asserted; the episode must still sit
    in a directory named `episode`, and every other binding (frozen bytes, scope, activation, full lease fields) is unchanged.
    """
    scope_path = getattr(options, "episode_scope", None)
    if scope_path is None:
        raise ValueError("EPISODE_SCOPE_REQUIRED")
    from dataclasses import asdict
    import hashlib
    import json
    import time

    from .collection_orchestration import FAULT_SANDBOX_COMPONENT
    from .episode_assembly import episode_audit_pair, open_point_episode
    from .collection_scope import read_collection_scope
    from .contact_calibration import proposal_validation_mode, verify_disabled_proposal
    from .contact_policy import policy_fingerprint, spot_check_receipt_allowed, verify_activation
    from .execution_snapshot import verify_execution_snapshot
    from .diagnostic_episode_inputs import (
        POLICY_BINDINGS, require_scope_for_inputs, verify_frozen_inputs, validate_execution_snapshot_binding)
    from .collection_config import validate_recorder_policy
    from so101_demo.parallel_batch.contracts.common import ContractError
    from so101_demo.parallel_batch.contracts.identity import LeaseIdentity

    manifest_path = getattr(options, "episode_inputs_manifest", None)
    if manifest_path is None:
        raise ValueError("EPISODE_FROZEN_INPUTS_REQUIRED")
    manifest_path = Path(manifest_path)
    frozen = verify_frozen_inputs(manifest_path)
    binding = frozen.get("execution_snapshot")
    if binding is None or "runtime_policy" not in frozen or "episode_recorder" not in frozen:
        raise ValueError("EPISODE_EXECUTION_INPUTS_REQUIRED")
    validate_execution_snapshot_binding(binding)
    snapshot = verify_execution_snapshot(manifest_path.parent / binding["path"],
                                         expected_sha256=binding["sha256"])
    document = read_collection_scope(Path(scope_path))
    require_scope_for_inputs(document, frozen, manifest_path)
    lease_names = ("batch_id", "coordinator_epoch", "worker_id", "worker_generation", "point_id",
                   "attempt_id", "lease_generation", "lease_issued_monotonic_s", "lease_deadline_monotonic_s")
    try:
        lease = LeaseIdentity(**{name: getattr(options, name, None) for name in lease_names})
    except (ContractError, TypeError, ValueError) as error:
        raise ValueError("EPISODE_FULL_LEASE_REQUIRED") from error
    if not offline and not lease.lease_issued_monotonic_s <= time.monotonic() < lease.lease_deadline_monotonic_s:
        raise ValueError("EPISODE_LEASE_NOT_CURRENT")
    proposal = json.loads((manifest_path.parent / frozen["roles"]["contact_proposal"]["path"]).read_bytes())
    activation = json.loads((manifest_path.parent / frozen["roles"]["contact_activation"]["path"]).read_bytes())
    verify_disabled_proposal(proposal, validation_mode=proposal_validation_mode(proposal))
    verify_activation(proposal["payload"], activation, expected_model_sha256=snapshot["model_sha256"],
                      expected_scene_sha256=frozen["roles"]["scene_model"]["sha256"],
                      expected_mujoco_version=snapshot["mujoco_version"],
                      allow_spot_check_candidate=spot_check_receipt_allowed(frozen.get("mode")))
    if activation["evidence_root"] != frozen["evidence_root"]:
        raise ValueError("EPISODE_ACTIVATION_ROOT_MISMATCH")
    config_binding = {"roles": {name: item["sha256"] for name, item in frozen["roles"].items()},
                      **{name: frozen[name] for name in POLICY_BINDINGS if name in frozen},
                      # the episode's provenance names its rig (a set without a rig binding is rig v1 and keeps its hash)
                      **({"rig_profile": frozen["rig_profile"]} if "rig_profile" in frozen else {}),
                      "runtime_policy": frozen["runtime_policy"],
                      "motion_policy_sha256": snapshot["files"][snapshot["motion_policy_path"]]["sha256"]}
    provenance = {"source_sha256": snapshot["source_sha256"],
                  "scene_sha256": frozen["roles"]["scene_model"]["sha256"],
                  "config_sha256": hashlib.sha256(json.dumps(config_binding, sort_keys=True, separators=(",", ":"),
                                                             ensure_ascii=False, allow_nan=False).encode()).hexdigest(),
                  "policy_fingerprint": policy_fingerprint(proposal["payload"]), "seed": document["seed"]}
    import yaml
    collection = yaml.safe_load((manifest_path.parent / frozen["roles"]["collection_config"]["path"]).read_bytes())
    recorder_policy = validate_recorder_policy(collection.get("recorder") if type(collection) is dict else None)
    evidence_root = Path(options.evidence_root)
    if not evidence_root.is_absolute() or ".." in evidence_root.parts or evidence_root.is_symlink():
        raise ValueError("EPISODE_ROOT_INVALID")
    episode_root = getattr(options, "episode_root", None)
    if episode_root is None:
        raise ValueError("EPISODE_ROOT_REQUIRED")
    episode_root = Path(episode_root)
    working = evidence_root.parent
    if offline:
        if (episode_root.name != "episode" or not episode_root.is_absolute() or ".." in episode_root.parts
                or any(path.is_symlink() for path in (episode_root, *episode_root.parents))):
            raise ValueError("EPISODE_LOCATION_MISMATCH")
    elif FAULT_SANDBOX_COMPONENT in episode_root.parts[:-1]:
        # A sandbox fault run records beside the run, never in an attempt workspace (the orchestrator guarantees the
        # sandbox location; the Recorder re-checks it when a fault is injected).
        if (episode_root != working / "episode"
                or any(path.is_symlink() for path in (episode_root, *episode_root.parents))):
            raise ValueError("EPISODE_LOCATION_MISMATCH")
    elif (episode_root != working / "episode" or evidence_root.name != "dynamic"
            or working.name != "working" or working.parent.name != lease.attempt_id
            or working.parent.parent.name != lease.point_id
            or working.parent.parent.parent.name != "attempts"
            or any(path.is_symlink() for path in (episode_root, *episode_root.parents))):
        raise ValueError("EPISODE_LOCATION_MISMATCH")
    evidence_root.mkdir(parents=True, exist_ok=True)
    # R3-a: a frozen schema 6 Teacher policy derives this scene's values; they enter the episode identity (episode.json)
    episode = open_point_episode(
        **diversity_arguments(frozen, document["scene_id"], getattr(options, "start_pose_draw", None)),
        **appearance_arguments(frozen, manifest_path, document["scene_id"], getattr(options, "teacher_source_record", None)),
        episode_root=episode_root, session_id=options.session_id, attempt_id=lease.attempt_id,
        reset_epoch=options.expected_reset_epoch, release_epoch=0, lease=asdict(lease),
        scene_id=document["scene_id"], seed=document["seed"], mode=document["mode"],
        scope=document, scope_path=str(episode_audit_pair(episode_root)[1]), inputs=frozen,
        provenance=provenance, max_age_s=frozen["runtime_policy"]["rgb_sync"]["max_age_s"],
        max_skew_s=frozen["runtime_policy"]["rgb_sync"]["max_skew_s"], recorder_policy=recorder_policy)
    episode.frozen_inputs_manifest = manifest_path
    episode.execution_inputs = snapshot
    return episode
