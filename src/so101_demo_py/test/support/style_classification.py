"""Classification and rename proposals for the code-style inventory.

``style_inventory`` finds the hits. This module assigns each one a classification, a proposed target name
and a confidence, from the decisions in ``docs/superpowers/specs/2026-10-10-so101-code-style-refactor-design.md``
(revision 2.1 with its section 9 amendments, which supersede the earlier rows).

Classifications
    ``family``                  successive versions of one thing; the latest is kept, older ones are deleted
    ``profile``                 parallel variants that stay, renamed by meaning (target names the meaning)
    ``single-version-rename``   the only version that exists; the version leaves the name
    ``process-rename``          a process name (task, worker step, experiment id) becomes a business name
    ``shim-delete``             an alias or forwarding shim that phase A deletes
    ``wire-rename``             a wire or sealed identifier renamed in phase D
    ``permanent``               not a version or process name of ours (model ids, vendor parts, frozen history)

Confidence
    ``design``      the target is named in the design or follows it directly
    ``mechanical``  derived by a rule (strip the segment, or substitute the profile or step phrase)
    ``strip``       a test identifier: only the token is removed; phase C renames it by the behaviour it tests
    ``uncertain``   the root should review this proposal

``python style_classification.py --check`` re-derives every row and compares it with the allowlist.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import style_inventory as inventory
from style_inventory import Hit, segments

CLASSIFICATIONS = (
    "family",
    "profile",
    "single-version-rename",
    "process-rename",
    "shim-delete",
    "wire-rename",
    "permanent",
)
CONFIDENCES = ("design", "mechanical", "strip", "uncertain", "decided")
DELETE = "(delete)"


@dataclass(frozen=True)
class Row:
    hit: Hit
    classification: str
    target: str
    confidence: str
    reason: str


# --------------------------------------------------------------------------------------------------
# Name surgery
# --------------------------------------------------------------------------------------------------

_SPLIT = re.compile(r"([^0-9A-Za-z]+)")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _style(stem: str) -> str:
    stem = stem.lstrip("_")
    letters = re.sub(r"[^A-Za-z]", "", stem)
    if "-" in stem and "_" not in stem:
        return "kebab"
    if letters and letters == letters.upper():
        return "upper"
    if "_" not in stem and "-" not in stem and re.search(r"[A-Z]", stem) and re.search(r"[a-z]", stem):
        return "pascal"
    return "snake"


def _render(phrase: str, style: str) -> str:
    parts = [p for p in re.split(r"[_\-]+", phrase) if p]
    if style == "upper":
        return "_".join(p.upper() for p in parts)
    if style == "pascal":
        return "".join(p.capitalize() for p in parts)
    if style == "kebab":
        return "-".join(p.lower() for p in parts)
    return "_".join(p.lower() for p in parts)


def _split_name(stem: str) -> tuple[list[str], list[str]]:
    """Return (segments, separators) where separators[i] precedes segments[i]."""

    segs: list[str] = []
    seps: list[str] = []
    pending = ""
    for piece in _SPLIT.split(stem):
        if not piece:
            continue
        if _SPLIT.fullmatch(piece):
            pending += piece
            continue
        parts = [p for p in _CAMEL.split(piece) if p]
        for index, part in enumerate(parts):
            segs.append(part)
            seps.append(pending if index == 0 else "")
            pending = ""
    return segs, seps


def transform(stem: str, replace) -> str:
    """Rewrite the segments of ``stem``. ``replace(i, segs)`` returns None (keep), "" (strip) or a phrase."""

    segs, seps = _split_name(stem)
    style = _style(stem)
    out: list[tuple[str, str]] = []
    carry: str | None = None  # separator inherited from a stripped leading segment
    for index, segment in enumerate(segs):
        separator = seps[index] if carry is None else carry
        carry = None
        decision = replace(index, segs)
        if decision is None:
            out.append((separator, segment))
        elif decision == "":
            if not out:
                carry = separator
        else:
            out.append((separator, _render(decision, style)))
    return "".join(separator + segment for separator, segment in out)


def _split_ext(name: str) -> tuple[str, str]:
    for ext in (".tar.gz",):
        if name.endswith(ext):
            return name[: -len(ext)], ext
    if "." in name and not name.startswith("."):
        stem, ext = name.rsplit(".", 1)
        if re.fullmatch(r"[A-Za-z0-9]{1,6}", ext):
            return stem, "." + ext
    return name, ""


def _number_word(digits: str) -> str:
    return {"1": "single", "2": "two", "4": "four", "6": "six", "8": "eight"}.get(digits, digits)


# --------------------------------------------------------------------------------------------------
# Versioned names
# --------------------------------------------------------------------------------------------------

# parallel_batch execution profiles by the schema number they used to carry
PROFILE_BY_VERSION = {
    3: "linux_cuda",
    4: "macos_mps_two_worker",
    5: "macos_mps_single_worker_retry",
    6: "macos_mps_single_worker_first_pass",
}

PARALLEL_FILES = {
    "parallel_batch_v1.yaml": ("family", DELETE, "design", "history: deleted once its live uses (frozen model constants, adaptive and expert-validation defaults) are replaced (design B, N1, U3)"),
    "parallel_batch_v2.yaml": ("family", DELETE, "design", "history: deleted with v1; resource_identity (its only live carrier) is deleted by N1"),
    "parallel_batch_v3.yaml": ("profile", "parallel_batch_linux_cuda.yaml", "uncertain", "Linux CUDA profile `linux_cuda` (design B); the file name is a proposal"),
    "parallel_batch_v3_act_offline.yaml": ("profile", "parallel_batch_act_offline.yaml", "uncertain", "profile `act_offline` (design B); the file name is a proposal"),
    "parallel_batch_v4_macos_mps_w2.yaml": ("profile", "parallel_batch_macos_mps_two_worker.yaml", "uncertain", "profile `macos_mps_two_worker` (design B); the file name is a proposal"),
    "parallel_batch_v5_macos_mps_w1_retry.yaml": ("profile", "parallel_batch_macos_mps_single_worker_retry.yaml", "uncertain", "profile `macos_mps_single_worker_retry` (design B); the file name is a proposal"),
    "parallel_batch_v6_macos_mps_w1_first_pass.yaml": ("profile", "parallel_batch_macos_mps_single_worker_first_pass.yaml", "uncertain", "profile `macos_mps_single_worker_first_pass` (design B); the file name is a proposal"),
}

# Config, asset and module files with a decision of their own: file name -> (classification, target, confidence, reason)
VERSIONED_FILES = {
    **PARALLEL_FILES,
    "v5_multi_object_scene.xml": ("single-version-rename", "multi_object_scene.xml", "uncertain", "only scene file with this number; confirm no v1 to v4 scenes are intended"),
    "endpoint_pose_acceptance_v1.yaml": ("single-version-rename", "endpoint_pose_acceptance.yaml", "design", "design B: renamed, or deleted if only the legacy QC used it"),
    "endpoint_pose_development_runtime_v1.yaml": ("single-version-rename", "endpoint_pose_development_runtime.yaml", "design", "design B: renamed, or deleted if only the legacy QC used it"),
    "episode_recorder_v1.yaml": ("single-version-rename", "episode_recorder.yaml", "design", "design B single-version names"),
    "feedback-quantisation-declaration-v1.json": ("single-version-rename", "feedback-quantisation-declaration.json", "mechanical", "single version; digest-bound, so renamed with a fresh freeze (phase D)"),
    "head-camera-geometry-contract-v1.json": ("single-version-rename", "head-camera-geometry-contract.json", "mechanical", "single version; digest-bound (phase D)"),
    "head-search-calibration-contract-v1.json": ("single-version-rename", "head-search-calibration-contract.json", "mechanical", "single version; digest-bound (phase D)"),
    "head-search-scenario-partitions-v1.json": ("single-version-rename", "head-search-scenario-partitions.json", "mechanical", "single version; digest-bound (phase D)"),
    "parallel-collection-v3-schema.json": ("single-version-rename", "parallel-collection-schema.json", "mechanical", "schema document of parallel_collection_v3.yaml"),
    "parallel_collection_v3.yaml": ("single-version-rename", "parallel_collection.yaml", "design", "design B: schema 1 under a v3 file name"),
    "task8-calibration-measurement-contract-v1.json": ("family", DELETE, "design", "measurement contract v1 is deleted; v2 is kept (design B)"),
    "task8-calibration-measurement-contract-v2.json": ("family", "pick-place-calibration-measurement-contract.json", "design", "kept measurement contract (design B, phase D)"),
    "task8-calibration-search-candidate-v1.json": ("single-version-rename", "pick-place-calibration-search-candidate.json", "mechanical", "single version (design B, phase D)"),
    "task8-calibration-search-policy-v1.json": ("single-version-rename", "pick-place-calibration-search-policy.json", "mechanical", "single version (design B, phase D)"),
    "task8-phase-camera-matrix-v1.json": ("single-version-rename", "pick-place-phase-camera-matrix.json", "mechanical", "single version (design B, phase D)"),
    "teacher_endpoint_v2.yaml": ("single-version-rename", "teacher_endpoint.yaml", "design", "design B: rule string becomes `teacher_endpoint`"),
    "teacher_execution_policy_v1.yaml": ("family", DELETE, "design", "N2: Teacher policy v1 is the superseded constant-offset policy"),
    "teacher_execution_policy_v2.yaml": ("family", DELETE, "design", "N2: Teacher policy v2 is superseded"),
    "teacher_execution_policy_v3.yaml": ("profile", "teacher_execution_policy.yaml", "design", "N2: the Teacher profile"),
    "head_search_v2.json": ("single-version-rename", "head_search_runtime.json", "design", "design B single-version names"),
    "moveit_expert_validation_points_v1.yaml": ("single-version-rename", "moveit_expert_validation_points.yaml", "design", "design B single-version names"),
    "parallel_adaptive_workers_v1.yaml": ("single-version-rename", "adaptive_worker_pool.yaml", "uncertain", "U3 migrates it to a business name; ADAPTIVE_POOL may instead be folded into the linux_cuda profile (N4)"),
    "grounded_sam_nonpenetrating_candidate_v1.json": ("single-version-rename", "grounded_sam_nonpenetrating_candidate.json", "uncertain", "may be a candidate round rather than a version; confirm before renaming"),
    "plastic_cup_grounding_dino_nonpenetrating_test_v1.yaml": ("single-version-rename", "plastic_cup_grounding_dino_nonpenetrating_test.yaml", "uncertain", "may be a dataset id rather than a version; confirm before renaming"),
    "plastic_cup_grounding_dino_nonpenetrating_train_val_v1.yaml": ("single-version-rename", "plastic_cup_grounding_dino_nonpenetrating_train_val.yaml", "uncertain", "may be a dataset id rather than a version; confirm before renaming"),
    "top_view_projection_v1.json": ("single-version-rename", "top_view_projection.json", "design", "design B single-version names"),
    "teacher_collection_v2.py": ("family", "teacher_collection.py", "design", "Teacher events V0/V1/V2: V2 kept as SO101_TEACHER_EVENT, module renamed teacher_collection.py (design B)"),
    "parallel_ipc_v4.py": ("profile", "parallel_ipc_darwin.py", "design", "Darwin IPC profile (design B)"),
}

DIRECTORY_VERSIONS = {
    "v1": ("single-version-rename", "(flatten into the policy directory)", "uncertain", "policy-variant directory with a single version; the registry layout decides whether it flattens"),
}

# Rules for module-level names and test identifiers: (regex over "path|kind|name" lowercased, spec)
# spec = (classification-for-kept, {version: action}, reason, confidence)
# action: "strip" keep the thing and drop the version; "delete"; otherwise the profile/step phrase to substitute.
_P = PROFILE_BY_VERSION
RULES: list[tuple[str, tuple]] = [
    # exact design names first
    (r"core/workflow\.py\|const\|so101_workflow_v3$", ("profile", {3: "@TEACHER_WORKFLOW"}, "design B: V3 is renamed TEACHER_WORKFLOW", "design")),
    (r"core/workflow\.py", ("profile", {3: "teacher"}, "workflow V3 is the Teacher profile (U1, design B)", "mechanical")),
    (r"batchrequestv2$|batchkindv2$", ("family", {2: "strip"}, "design B: the live request contract keeps its V2 shape under the plain name", "design")),
    (r"batchrequestv3$|batchkindv3$|request_v3_fields$", ("family", {3: "delete"}, "N4/design B: BatchRequestV3 and its document helpers are deleted", "design")),
    (r"frozen_linux_values_v4$", ("family", {4: "delete"}, "design B: v4's deferred Linux-CUDA combination is deleted", "design")),
    # parallel_batch contract family
    (r"parallel_batch/contracts\.py", ("profile", {2: "delete", **_P}, "parallel_batch execution profiles (design B): v2 is history; v3..v6 are named by what they run; v2 classes may be bases of later ones, so verify before deleting", "mechanical")),
    (r"runtime/parallel_ipc_v4\.py|test_parallel_ipc_v4|start_guard_probe\.py\|def\|_v4", ("profile", {4: "darwin"}, "Darwin IPC profile (design B)", "mechanical")),
    (r"parallel_batch/w1_composition\.py\|const\|v5_|parallel_batch/w1_composition\.py\|const\|v6_", ("profile", {5: _P[5], 6: _P[6]}, "macOS single-worker profile (design B)", "mechanical")),
    (r"parallel_batch/w2_composition\.py\|const\|v4_", ("profile", {4: _P[4]}, "macOS two-worker profile (design B)", "mechanical")),
    (r"parallel_batch/dynamic_manifest\.py\|const\|schema_v1", ("family", {1: "delete"}, "N4: manifest v1 readers are deleted", "design")),
    (r"parallel_batch/dynamic_manifest\.py\|const\|schema_v2", ("profile", {2: "general"}, "manifest v2 is the general profile `so101-dynamic-execute` (design B)", "uncertain")),
    (r"parallel_batch/dynamic_manifest\.py\|const\|schema_v3", ("profile", {3: "teacher"}, "manifest v3 is the Teacher profile `so101-teacher-execute` (design B)", "uncertain")),
    (r"dynamic_manifest\.py\|def\|_place_height_contract_v3", ("family", {3: "strip"}, "N3: place-height v3 is kept without a version", "design")),
    (r"ros/dynamic_mujoco_execution\.py|act/teacher_process\.py", ("profile", {3: "teacher"}, "Teacher manifest profile (N4)", "mechanical")),
    # teacher policy and endpoint
    (r"act/teacher_endpoint\.py", ("family", {2: "delete", 3: "strip"}, "N2: Teacher policy v2 is deleted; v3 is the only Teacher policy", "mechanical")),
    # place height (N3)
    (r"place_height", ("family", {1: "delete", 2: "delete", 3: "strip"}, "N3: the v3 strategy is kept without a version; the v1/v2 compensation paths are deleted", "mechanical")),
    # sealed and result families (U2): keep latest
    (r"act/result_store\.py", ("family", {3: "strip"}, "ACT result 1/2/3: the latest is kept (design B)", "design")),
    (r"act/episode_qc\.py", ("family", {2: "delete"}, "QC report 2/3: the older reader is deleted (design B)", "design")),
    (r"act/native_endpoints\.py", ("family", {2: "strip"}, "Teacher events: V2 is kept (design B)", "mechanical")),
    (r"act/head_run_audit\.py|test_act_head_run_audit|head_run_audit", ("family", {1: "delete", 2: "strip"}, "HFA-009 v1/v2: v2 is kept (design B)", "mechanical")),
    (r"act/head_simulation_policy\.py|test_act_head_simulation_policy", ("family", {2: "delete", 3: "strip"}, "HeadSimulationPolicy 2/3: schema 3 is kept (design B)", "mechanical")),
    (r"act/training_config\.py|test_act_training_config|test_act_lerobot_preprocessing", ("family", {1: "delete", 2: "strip"}, "training config 1/2: v2 is kept (design B)", "mechanical")),
    (r"task8_measurement_(contract|schema)|test_act_task8_measurement_contract|test_act_task8_calibration_aggregator|test_act_task8_live_evidence", ("family", {1: "delete", 2: "strip"}, "measurement contract v1/v2: v2 is kept (design B)", "mechanical")),
    (r"application/e2e_acceptance\.py|test_e2e_acceptance", ("family", {1: "delete", 2: "delete", 3: "strip"}, "acceptance manifest versions are not in the design table; the latest is proposed", "uncertain")),
    # tests that follow a family (before the generic parallel/teacher keyword rules)
    (r"test_parallel_batch_journal", ("family", {1: "delete", 2: "strip"}, "coordinator journal 1/2: v2 is kept (design B)", "mechanical")),
    (r"test_b2_|test_act_episode_recorder_sources|test_act_head_campaign_v2|test_act_head_local_runtime|test_act_recorder|b2_collection_fixtures|test_act_head_search_startup|test_act_result_qc_v2|test_act_reserved_result|test_act_qc_report|test_act_training_whitelist|test_act_policy_freeze|test_act_teacher_endpoint_v2", ("family", {1: "delete", 2: "strip", 3: "strip"}, "sealed or result family (U2): the latest is kept (design B)", "mechanical")),
    (r"test_dynamic_manifest|test_dynamic_teacher_result|test_parallel_ros_runtime|test_parallel_batch_artifacts|test_act_task8_calibration", ("profile", {1: "delete", 2: "general", 3: "teacher"}, "manifest profiles: v2 general, v3 Teacher (design B)", "mechanical")),
    (r"test_teacher_|test_workflow_v3|test_underactuated", ("profile", {1: "delete", 2: "delete", 3: "strip"}, "Teacher profile (N2): policy v1/v2 are deleted, v3 is the Teacher policy", "mechanical")),
    (r"test_grounded_sam_finetuned|test_grounding_dino_dataset|test_yolo_seg_dataset|test_act_parallel_collection", ("family", {1: "delete", 2: "strip", 3: "strip"}, "dataset or collection schema: the latest is kept (design B)", "mechanical")),
    (r"parallel|macos|start_guard|campaign_point|expert_validation|unified_(guard|budget)|launch_composition|retry|accelerator|w1_|w2_|adaptive", ("profile", {1: "delete", 2: "delete", **_P}, "parallel_batch profile in a test (design B)", "mechanical")),
]

_VERSION_NUMBER = re.compile(r"v(\d+)", re.IGNORECASE)


def _version_of(name: str) -> int | None:
    for segment in segments(name):
        match = _VERSION_NUMBER.fullmatch(segment)
        if match:
            return int(match.group(1))
    return None


def _apply_versions(stem: str, action_for) -> str:
    """Replace each version segment by the phrase ``action_for(number)`` returns ("" strips it)."""

    def decide(index: int, segs: list[str]):
        match = _VERSION_NUMBER.fullmatch(segs[index])
        if not match:
            return None
        return action_for(int(match.group(1)))

    return transform(stem, decide)


def _is_test_path(path: str) -> bool:
    return "/test/" in path or "/benchmark_test/" in path


def classify_versioned(hit: Hit, context: "Context") -> Row:
    key = f"{hit.path}|{hit.kind}|{hit.name}".lower()
    if hit.kind == "dir":
        spec = DIRECTORY_VERSIONS.get(hit.name.lower())
        return Row(hit, spec[0], spec[1], spec[2], spec[3])
    if hit.kind == "file":
        base = hit.path.rsplit("/", 1)[-1]
        if "/assets/" in hit.path and base.endswith(".stl"):
            return Row(hit, "permanent", "-", "design", "vendor SO-101 CAD part revision; the MJCF/URDF reference the file name (design B, not versions)")
        if base in VERSIONED_FILES:
            cls, target, conf, reason = VERSIONED_FILES[base]
            return Row(hit, cls, target, conf, reason)
    version = _version_of(hit.name)
    for pattern, (cls, actions, reason, conf) in RULES:
        if not re.search(pattern, key):
            continue
        action = actions.get(version, actions.get(0))
        if version is None:
            break
        if action is None:
            # a version the rule does not name: treat as an older, superseded one
            action = "delete"
        if isinstance(action, str) and action.startswith("@"):
            return Row(hit, cls, action[1:], conf, reason)
        if action == "delete":
            return Row(hit, "family", DELETE, conf, reason + " (older version)")
        stem, ext = _split_ext(hit.name) if hit.kind == "file" else (hit.name, "")
        if action == "strip":
            target = _apply_versions(stem, lambda n: "") + ext
            kept_cls = "family" if cls == "profile" and action == "strip" and "profile" not in reason else cls
        else:
            if action in segments(stem.lower()) or action.replace("_", "") in stem.lower().replace("_", ""):
                target = _apply_versions(stem, lambda n: "") + ext  # the name already says it
            else:
                target = _apply_versions(stem, lambda n, a=action: a) + ext
            kept_cls = cls
        target, note = _check_collision(hit, target, context)
        target, generic = _generic_note(hit, target)
        confidence = "uncertain" if note or generic else conf
        return Row(hit, kept_cls, target, confidence, reason + note + generic)
    # fallback: group logic. A name that exists in several versions in one module is a family, otherwise a single version.
    stem, ext = _split_ext(hit.name) if hit.kind == "file" else (hit.name, "")
    stripped = _apply_versions(stem, lambda n: "") + ext
    siblings = context.versions_of(hit, stripped)
    if len(siblings) > 1:
        latest = max(siblings)
        if version == latest:
            target, note = _check_collision(hit, stripped, context)
            return Row(hit, "family", target, "uncertain" if note else "mechanical", f"successive versions {sorted(siblings)} in one place: the latest is kept" + note)
        return Row(hit, "family", DELETE, "mechanical", f"successive versions {sorted(siblings)} in one place: older versions are deleted")
    target, note = _check_collision(hit, stripped, context)
    target, generic = _generic_note(hit, target)
    if hit.kind in {"def", "const", "class"} and _is_test_path(hit.path):
        return Row(hit, "single-version-rename", target, "uncertain" if note else "strip", "test identifier: the version wording is dropped with the code it describes (phase C renames by behaviour)" + note)
    return Row(hit, "single-version-rename", target, "uncertain" if note or generic else "mechanical", "only version present: the version number leaves the name (R6)" + note + generic)


COLLISION_NOTE = "; the target name already exists here, so the existing definition goes or merges first"


def _check_collision(hit: Hit, target: str, context: "Context") -> tuple[str, str]:
    """Return (target, note); the note is non-empty when the target would collide with an existing name."""

    if target in {DELETE, "-"}:
        return target, ""
    if hit.kind == "file":
        folder = hit.path.rsplit("/", 1)[0]
        other = f"{folder}/{target}"
        if other != hit.path and other in context.file_paths:
            return target, COLLISION_NOTE
    elif hit.kind in {"def", "const", "class"}:
        if target != hit.name and target in context.names_in(hit.path):
            return target, COLLISION_NOTE
    return target, ""


def _generic_note(hit: Hit, target: str) -> tuple[str, str]:
    """A one-word remainder (``FIELDS``, ``SCHEMA``) no longer says what it is."""

    if target in {DELETE, "-"} or hit.kind == "file":
        return target, ""
    if not target:
        return "(needs a name)", "; the name was only a version, so it needs a name that says what it holds"
    if len(segments(target)) <= 1 and len(segments(hit.name)) >= 2:
        return target, "; the remaining name is generic, so qualify it with what it describes"
    return target, ""


# --------------------------------------------------------------------------------------------------
# Process names
# --------------------------------------------------------------------------------------------------

SHIM_FILES = {
    "src/so101_demo_py/src/act/task8.py",
    "src/so101_demo_py/src/act/task8_live_campaign.py",
    "src/so101_demo_py/src/act/task8_manifest.py",
    "src/so101_demo_py/src/adapters/act/task6_capture.py",
    "src/so101_demo_py/src/cli/act_task8_live.py",
    "src/so101_demo_py/src/cli/act_capture_task6.py",
    "src/so101_demo_py/src/cli/act_prepare_task8_live_artifacts.py",
    "src/so101_demo_py/src/cli/act_prepare_task8_live.py",
} | {
    f"src/so101_teleop/so101_teleop/unified/task8_{name}.py"
    for name in ("case_execution", "case_owner", "child_startup", "full_restart_campaign", "startup_issuer", "startup_proof")
}
SHIM_SCRIPTS = {"act_task8_live", "act_prepare_task8_live", "act_prepare_task8_live_artifacts", "act_capture_task6"}
SHIM_ALIASES = {
    "Task8Runner", "Task8Error", "Task8Port", "Task8LiveError", "Task8LiveCampaign", "Task8ReadbackError",
    "Task8PhysicalReadback", "Task8ContactPairs",
}

PROCESS_FILES = {
    "task8_artifact_bundle.py": ("pick_place_validation_artifact_bundle.py", "design", "design C module names"),
    "task8_live_evidence.py": ("pick_place_live_evidence.py", "design", "design C module names"),
    "task8_phase_camera.py": ("pick_place_phase_camera.py", "design", "design C module names"),
    "task8_production_composition.py": ("calibration_production_composition.py", "design", "design C module names"),
    "w8_qualification.py": ("parallel_qualification_verifier.py", "design", "design C: w8_qualification becomes parallel_qualification_verifier"),
    "macos_n1_first_pass.py": ("macos_mps_single_worker_first_pass.py", "uncertain", "design C: single-worker names; the profile name is `macos_mps_single_worker_first_pass`"),
    "macos_n1_retry.py": ("macos_mps_single_worker_retry.py", "uncertain", "design C: single-worker names; the profile name is `macos_mps_single_worker_retry`"),
    "macos_w2_worker.py": ("macos_two_worker_process.py", "uncertain", "design C: two-worker names; this is the per-worker process entry"),
    "task6_route_plugins.yaml": ("route_plugins.yaml", "uncertain", "route plugin list for the synchronized-capture route; the business name is a proposal"),
    "plastic_cup_grounding_dino_augmented_r3.yaml": ("-", "design", "design B: a dataset round, renamed in phase C only if it can be without retraining"),
}
PROCESS_SCRIPTS = {
    "so101_macos_n1_first_pass": ("so101_macos_single_worker_first_pass", "uncertain", "console script of macos_n1_first_pass"),
    "so101_macos_n1_retry": ("so101_macos_single_worker_retry", "uncertain", "console script of macos_n1_retry"),
}


def _task_phrase(context_text: str) -> str:
    text = context_text.lower()
    if re.search(r"calibration|measurement|bottom_io|ready", text):
        return "pick_place_calibration"
    return "pick_place_validation"


def _process_phrase(segment: str, previous: str | None, following: str | None, context_text: str) -> str | None:
    low = segment.lower()
    if re.fullmatch(r"task8", low):
        nxt = following.lower() if following else ""
        if nxt in {"calibration", "live", "phase", "validation"}:
            return "pick_place"  # the next word already says which kind
        if nxt in {"measurement", "bottom"}:
            return "pick_place_calibration"
        return _task_phrase(context_text)
    if re.fullmatch(r"task(1|6|11|12|14)", low):
        return ""
    match = re.fullmatch(r"w(\d)", low)
    if match:
        word = _number_word(match.group(1))
        if following and following.lower() in {"worker", "workers"}:
            return word
        return f"{word}_worker"
    if low == "n1":
        return "single_worker"
    if re.fullmatch(r"(hs\d+|cp\d+|exp\d+|p\d|b\d+b?|d\d|rec\d+b?|r\d+b?|t8)", low):
        return ""
    return None


def _process_target(stem: str, context_text: str) -> str:
    def decide(index: int, segs: list[str]):
        if not inventory.process_segments(segs[index]):
            return None
        previous = segs[index - 1] if index else None
        following = segs[index + 1] if index + 1 < len(segs) else None
        return _process_phrase(segs[index], previous, following, context_text)

    return transform(stem, decide)


def _is_alias_assignment(hit: Hit, context: "Context") -> bool:
    return context.is_alias(hit.path, hit.name)


def classify_process(hit: Hit, context: "Context") -> Row:
    base = hit.path.rsplit("/", 1)[-1]
    if hit.kind == "file" and hit.path in SHIM_FILES:
        return Row(hit, "shim-delete", DELETE, "design", "alias shim: deleted in phase A after its importers migrate")
    if hit.kind == "script":
        if hit.name in SHIM_SCRIPTS:
            return Row(hit, "shim-delete", DELETE, "design", "console script of a shim: deleted in phase A")
        if hit.name in PROCESS_SCRIPTS:
            target, conf, reason = PROCESS_SCRIPTS[hit.name]
            return Row(hit, "process-rename", target, conf, reason)
        return Row(hit, "process-rename", _process_target(hit.name, hit.name), "mechanical", "console script renamed with its module (phase C), together with setup.py")
    if hit.kind == "const" and hit.name in SHIM_ALIASES:
        return Row(hit, "shim-delete", DELETE, "design", "alias deleted in phase A (design A)")
    if hit.kind == "const" and _is_alias_assignment(hit, context):
        return Row(hit, "shim-delete", DELETE, "mechanical", "plain alias of another name: deleted with the shims in phase A")
    if hit.kind == "file" and base in PROCESS_FILES:
        target, conf, reason = PROCESS_FILES[base]
        if base == "plastic_cup_grounding_dino_augmented_r3.yaml":
            return Row(hit, "permanent", target, conf, reason)
        return Row(hit, "process-rename", target, conf, reason)
    stem, ext = _split_ext(hit.name) if hit.kind == "file" else (hit.name, "")
    context_text = f"{hit.path}/{hit.name}"
    target = _process_target(stem, context_text) + ext
    target, note = _check_collision(hit, target, context)
    target, generic = _generic_note(hit, target)
    note += generic
    collided = bool(note)
    if _is_test_path(hit.path):
        return Row(hit, "process-rename", target, "uncertain" if collided else "strip", "test identifier: only the process token is removed; phase C renames it by the behaviour it tests" + note)
    confidence = "uncertain" if collided else "mechanical"
    reason = "process token replaced by its business phrase (R1/R6); module names follow design C" + note
    if re.search(r"task(6|14)|_w8_|w8_|task11|task12", hit.name.lower()):
        confidence = "uncertain"
        reason = "the business meaning of this step name is not in the design; the proposal strips or paraphrases it" + note
    return Row(hit, "process-rename", target, confidence, reason)


# --------------------------------------------------------------------------------------------------
# Wire strings
# --------------------------------------------------------------------------------------------------

_PERMANENT_WIRE = re.compile(
    r"yolo\d*[a-z]?-seg-v\d+|nonpenetrating-(train-val|test)-v\d+|task-visual-nonpenetration|plastic-cup-|"
    r"^docs/superpowers/|/docs/superpowers/|^so101-head-search-yolo-seg-v\d+$|^fusion-v1$"
)
_WIRE_KINDS = {
    "so101-dynamic-mujoco-execute-v1": ("family", DELETE, "design", "manifest v1 readers are deleted (N4)"),
    "so101-dynamic-mujoco-execute-v2": ("profile", "so101-dynamic-execute", "design", "manifest v2 becomes `so101-dynamic-execute` (design B)"),
    "so101-dynamic-mujoco-execute-v3": ("profile", "so101-teacher-execute", "design", "manifest v3 becomes `so101-teacher-execute` (design B/N4)"),
    "head-search-v2": ("single-version-rename", "head-search-runtime", "uncertain", "kind of head_search_v2.json (renamed head_search_runtime.json)"),
}


def _wire_phrase(value: str) -> str:
    text = value.lower()
    if re.search(r"calibration|measurement|ready|phase_camera|bottom_io", text):
        return "PICK_PLACE_CALIBRATION"
    return "PICK_PLACE_VALIDATION"


_STEP_WORDS = {"task6": "synchronized_capture", "task14": "headroom"}
_UNNAMED_STEPS = re.compile(r"(?i)task(1|10|11|12)(?=[_-]|\b)")


class _Shim:
    """Adapter so the TASK8 rewrite sees (token, separator, following word) as groups 1, 2, 3."""

    def __init__(self, match: re.Match):
        self._match = match

    def group(self, index: int):
        return self._match.group(index)


def _wire_target(value: str, context: "Context") -> tuple[str, str, str]:
    """(target text, confidence, reason) for a wire string that carries a process name."""

    confidence, reason = "mechanical", "process name replaced by its business phrase (phase D)"
    target = value
    renamed = context.rename_basenames(target)
    if renamed != target:
        target, reason = renamed, "reference to a renamed file: follows the file's new name"
    if value == "ACT_TASK8_LIVE":
        return "ACT_PICK_PLACE_VALIDATION", "design", "design D: ACT_TASK8_LIVE becomes ACT_PICK_PLACE_VALIDATION"
    if "SO101_TASK12" in target:
        return target.replace("SO101_TASK12", "SO101_<needs-a-name>"), "uncertain", "design D: SO101_TASK12_* gets a name for what it does; the meaning must be confirmed from its reader"
    def task8(match: re.Match) -> str:
        following = (match.group(3) or "").lower()
        if following in {"live", "calibration", "phase", "validation"}:
            words = "pick_place"
        elif following in {"measurement", "bottom", "ready"}:
            words = "pick_place_calibration"
        else:
            words = _wire_phrase(value).lower()
        separator = match.group(2)
        upper = match.group(1).isupper()
        text = words.upper() if upper else words
        text = text.replace("_", separator) if separator == "-" else text
        return text + separator + (match.group(3) or "")

    target = re.sub(r"(?<![A-Za-z0-9])(TASK8|task8)([_-])([A-Za-z]*)", lambda m: task8(_Shim(m)), target)
    for step, word in _STEP_WORDS.items():
        upper = word.upper()
        prefix = f"{upper}_"
        target = re.sub(rf"{step.upper()}_(CAPTURE_)?", prefix, target) if step == "task6" else re.sub(rf"{step.upper()}_", prefix, target)
        target = re.sub(rf"{step}([_-])(?!{word.split('_')[0]})", lambda m, w=word: w.replace("_", m.group(1)) + m.group(1), target)
        if target != value and step in value.lower():
            confidence, reason = "uncertain", "domain prefix proposal; the design asks for domain prefixes but does not name them"
    if _UNNAMED_STEPS.search(target):
        return _UNNAMED_STEPS.sub("<needs-a-name>", target), "uncertain", "the business meaning of this step name is not in the design"
    if target == value:
        confidence, reason = "uncertain", "matched a wire pattern but no rewrite rule applies"
    return target, confidence, reason


def classify_wire(hit: Hit, context: "Context") -> Row:
    value = hit.name
    if value in _WIRE_KINDS:
        cls, target, conf, reason = _WIRE_KINDS[value]
        return Row(hit, cls, target, conf, reason)
    if _PERMANENT_WIRE.search(value):
        if value.startswith(("docs/", "src/so101_demo_py/docs")) or "/docs/superpowers/" in value:
            reason = "reference to a frozen historical document (R5): history is not rewritten"
        else:
            reason = "model or dataset identifier (design B, not versions)"
        return Row(hit, "permanent", "-", "design", reason)
    if re.fullmatch(r"[\w.\-]+-v\d+", value) and not re.search(r"task\d", value, re.IGNORECASE):
        target = re.sub(r"-v\d+$", "", value)
        return Row(hit, "single-version-rename", target, "uncertain", "kind literal carrying a version: the version moves into a `schema_version` field (R6); confirm the wire kind with its reader")
    target, confidence, reason = _wire_target(value, context)
    return Row(hit, "wire-rename", target, confidence, reason)


# --------------------------------------------------------------------------------------------------
# Context and driver
# --------------------------------------------------------------------------------------------------


class Context:
    """Repository facts the classifier needs: module-level names per file, file set, version groups."""

    def __init__(self, repository: Path):
        self.repository = repository
        self.file_paths = {path for path, _p, _r in inventory.package_files(repository)}
        self._names: dict[str, set[str]] = {}
        self._aliases: dict[str, set[str]] = {}
        self._groups: dict[tuple[str, str], set[int]] = {}
        self._versioned_rows: dict[Hit, Row] = {}
        self._file_targets: dict[str, str] | None = None
        self._versioned_keys: set[Hit] = set(inventory.scan(inventory.SCAN_VERSIONED, repository))
        for scan_hit in self._versioned_keys:
            number = _version_of(scan_hit.name)
            if number is None:
                continue
            stem, ext = _split_ext(scan_hit.name) if scan_hit.kind == "file" else (scan_hit.name, "")
            stripped = _apply_versions(stem, lambda n: "") + ext
            self._groups.setdefault((scan_hit.path.rsplit("/", 1)[0] if scan_hit.kind == "file" else scan_hit.path, stripped), set()).add(number)
            if scan_hit.kind != "file":
                self._groups.setdefault((scan_hit.path, stripped), set()).add(number)

    def _load(self, path: str) -> None:
        if path in self._names:
            return
        names: set[str] = set()
        aliases: set[str] = set()
        try:
            tree = ast.parse((self.repository / path).read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            self._names[path] = names
            self._aliases[path] = aliases
            return
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        names.add(target.id)
                        if isinstance(node.value, ast.Name):
                            aliases.add(target.id)
        self._names[path] = names
        self._aliases[path] = aliases

    def rename_basenames(self, text: str) -> str:
        """Replace every renamed file base name that appears in ``text`` by its proposed new name."""

        if self._file_targets is None:
            self._file_targets = {}
            for which in (inventory.SCAN_VERSIONED, inventory.SCAN_PROCESS):
                for file_hit in inventory.scan(which, self.repository):
                    if file_hit.kind != "file":
                        continue
                    row = classify(file_hit, self)
                    if row.target not in {DELETE, "-"} and not row.target.startswith("(") and row.classification not in {"permanent", "shim-delete"}:
                        self._file_targets[file_hit.name] = row.target
        for old in sorted(self._file_targets, key=len, reverse=True):
            if old in text:
                text = text.replace(old, self._file_targets[old])
        return text

    def versioned_row(self, hit: Hit) -> Row | None:
        """The versioned-scan classification of the same file or name, when it has one."""

        key = Hit(inventory.SCAN_VERSIONED, hit.path, hit.kind, hit.name)
        if key not in self._versioned_keys:
            return None
        if key not in self._versioned_rows:
            self._versioned_rows[key] = classify(key, self)
        return self._versioned_rows[key]

    def names_in(self, path: str) -> set[str]:
        self._load(path)
        return self._names[path]

    def is_alias(self, path: str, name: str) -> bool:
        self._load(path)
        return name in self._aliases[path]

    def versions_of(self, hit: Hit, stripped: str) -> set[int]:
        folder = hit.path.rsplit("/", 1)[0] if hit.kind == "file" else hit.path
        return self._groups.get((folder, stripped), set())


def classify(hit: Hit, context: Context) -> Row:
    if hit.scan == inventory.SCAN_VERSIONED:
        row = classify_versioned(hit, context)
        if row.target not in {DELETE, "-"} and inventory.process_segments(hit.name) and not row.target.startswith("("):
            stem, ext = _split_ext(row.target) if hit.kind == "file" else (row.target, "")
            return Row(hit, row.classification, _process_target(stem, f"{hit.path}/{hit.name}") + ext, row.confidence, row.reason + "; also carries a process name, renamed in the same step")
        return row
    if hit.scan == inventory.SCAN_PROCESS:
        sibling = context.versioned_row(hit)
        if sibling is not None and sibling.classification != "permanent":
            if sibling.target == DELETE:
                return Row(hit, sibling.classification, DELETE, sibling.confidence, sibling.reason + "; same hit as the versioned scan")
            return Row(hit, "process-rename", sibling.target, sibling.confidence, "same name as its versioned-scan hit, so one final name: " + sibling.reason)
        return classify_process(hit, context)
    return classify_wire(hit, context)


def all_rows(repository: Path = inventory.REPOSITORY) -> list[Row]:
    context = Context(repository)
    rows: list[Row] = []
    for which in (inventory.SCAN_VERSIONED, inventory.SCAN_PROCESS, inventory.SCAN_WIRE):
        rows.extend(classify(hit, context) for hit in inventory.scan(which, repository))
    return rows


def allowlist_text(rows: list[Row]) -> str:
    header = (
        "# Style-guard allowlist (refactor step 0, 2026-10-10): every current hit of the three guards.\n"
        "# Tab-separated: " + " | ".join(inventory.ALLOWLIST_COLUMNS) + "\n"
        "# An entry may only be removed (when its phase renames or deletes the name); the guards fail on a hit that is\n"
        "# not listed and on an entry no hit uses. Classification and confidence are defined in style_classification.py.\n"
    )
    lines = []
    for row in sorted(rows, key=lambda r: (r.hit.scan, r.hit.path, r.hit.kind, r.hit.name)):
        reason = " ".join(row.reason.split())
        lines.append("\t".join([row.hit.scan, row.hit.path, row.hit.kind, row.hit.name, row.classification, row.target, row.confidence, reason]))
    return header + "\n".join(lines) + "\n"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def rename_map_text(allowlist: Path, repository: Path = inventory.REPOSITORY) -> str:
    entries, problems = inventory.load_allowlist(allowlist)
    if problems:
        raise SystemExit("\n".join(problems))
    parsed = []
    for key, entry in entries.items():
        scan_name, path, kind, name = key.split("|", 3)
        parsed.append((scan_name, path, kind, name, entry))
    parsed.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    counts: dict[tuple[str, str], int] = {}
    for scan_name, _p, _k, _n, entry in parsed:
        counts[(scan_name, entry.classification)] = counts.get((scan_name, entry.classification), 0) + 1
    uncertain = [item for item in parsed if item[4].confidence == "uncertain"]
    out: list[str] = []
    w = out.append
    w("# SO-101 code-style refactor: rename map (2026-10-10)")
    w("")
    w("Generated by `python src/so101_demo_py/test/support/style_classification.py --write-map` from the step-0 allowlist")
    w("(`src/so101_demo_py/test/repo/style_allowlist.tsv`). It is the R5 record of every old name and its proposed new name; it")
    w("is a history document, so it is not regenerated after the phases remove entries from the allowlist. The proposals are")
    w("root-reviewed: rows marked `uncertain` are the ones the root should decide.")
    w("")
    w("Design: `docs/superpowers/specs/2026-10-10-so101-code-style-refactor-design.md` (revision 2.1, with the section 9 amendments).")
    w("")
    w("## Method")
    w("")
    w("- Three guards find the hits mechanically (`style_inventory.py`):")
    w("  - **versioned**: a whole snake_case, kebab-case or CamelCase segment `v<digits>` in a file or directory name, a module-level")
    w("    `def`, `class` or constant name, or a console script name.")
    w("  - **process**: a whole segment equal to `task<n>`, `t8`, `w<d>`, `n1`, `hs<n>`, `cp<n>`, `exp<n>`, `p<d>`, `b<n>[b]`, `d<d>`,")
    w("    `rec<n>[b]` or `r<n>[b]`, in the same places.")
    w("  - **wire**: string values in package source and `config/` (not docstrings) matching `TASK<n>_`, `SO101_TASK<n>`,")
    w("    `task<n>[-_]`, or a whole-string kind literal `...-v<n>`.")
    w("- Scope: the four Python packages `so101_demo_py`, `so101_teleop`, `so101_quik` and `so101_mujoco_support`. File names are")
    w("  inventoried under each package's source root, `test`, `benchmark_test`, `config`, `launch`, `scripts`, `docker`, `assets`,")
    w("  `cmake`, `include` and `msg`; symbols only in Python files. Repository-level `scripts/` and `tools/` are active external")
    w("  callers (design section 5) and are updated in lockstep by the phase that renames what they call.")
    w("- Classifications: `family` (successive versions, latest kept), `profile` (parallel variants, renamed by meaning),")
    w("  `single-version-rename`, `process-rename`, `shim-delete` (phase A), `wire-rename` (phase D), `permanent` (not ours).")
    w("  The design names four classes (family, profile, single-version rename, permanent); `process-rename`, `shim-delete` and")
    w("  `wire-rename` are the same idea applied to the other two guards.")
    w("- Confidence: `design` (named in the design), `mechanical` (a rule), `strip` (a test identifier: only the token is removed;")
    w("  phase C renames it by the behaviour it tests), `uncertain` (root review).")
    w("- Target `(delete)` means the thing disappears with its family or shim. `-` means it is not renamed.")
    w("- The same file can appear under two scans (for example `parallel_batch_v4_macos_mps_w2.yaml`); both rows carry the same")
    w("  final name.")
    w("")
    w("## Known gaps in the specified guard patterns")
    w("")
    w("- The wire kind `paired_camera_truth_v2_original` has an embedded `_v2_` and is not matched by the specified")
    w("  `\"...-v\\d+\"` kind-literal pattern. Proposed: extend the wire guard to `[-_]v\\d+(?=[-_]|$)` inside kind-like literals when")
    w("  phase D starts (root decision; not done in step 0).")
    w("- Names that do not use a `v<digits>` segment but are still successive versions (for example `SCHEMA_VERSION_2`,")
    w("  `RESULT_SCHEMA_3`) are outside the specified guard. They are handled by the family rows in phase B by reading the code.")
    w("- Docstring and comment mentions of `Task N`, `CP-#` and `EXP-#` are outside every guard; phase C rewrites them by hand.")
    w("")
    w("## Summary")
    w("")
    w("| Scan | Classification | Hits |")
    w("|---|---|---|")
    for (scan_name, cls), number in sorted(counts.items()):
        w(f"| {scan_name} | {cls} | {number} |")
    w(f"| **total** |  | **{len(parsed)}** |")
    w("")
    w(f"## Rows still marked uncertain ({len(uncertain)})")
    w("")
    w("Rows the root decision section did not settle. Rows with confidence `decided` carry the number of the decision in their reason.")
    w("")
    w("")
    w("| Scan | Location | Kind | Old name | Proposed | Why uncertain |")
    w("|---|---|---|---|---|---|")
    for scan_name, path, kind, name, entry in uncertain:
        w(f"| {scan_name} | `{_cell(path)}` | {kind} | `{_cell(name)}` | `{_cell(entry.target)}` | {_cell(entry.reason)} |")
    w("")
    w("## Full inventory")
    w("")
    for scan_name in (inventory.SCAN_VERSIONED, inventory.SCAN_PROCESS, inventory.SCAN_WIRE):
        subset = [item for item in parsed if item[0] == scan_name]
        w(f"### {scan_name} ({len(subset)})")
        w("")
        w("| Location | Kind | Old name | Classification | Proposed | Confidence | Reason |")
        w("|---|---|---|---|---|---|---|")
        for _s, path, kind, name, entry in subset:
            w(f"| `{_cell(path)}` | {kind} | `{_cell(name)}` | {entry.classification} | `{_cell(entry.target)}` | {entry.confidence} | {_cell(entry.reason)} |")
        w("")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    allowlist = inventory.REPOSITORY / "src/so101_demo_py/test/repo/style_allowlist.tsv"
    rows = all_rows()
    if "--seed" in argv:
        if allowlist.exists():
            raise SystemExit("the allowlist holds root decisions and is the source of truth; edit it, do not re-seed")
        allowlist.parent.mkdir(parents=True, exist_ok=True)
        allowlist.write_text(allowlist_text(rows), encoding="utf-8")
        print("wrote", allowlist, len(rows), "entries")
        return 0
    if "--write-map" in argv:
        target = inventory.REPOSITORY / "docs/experiments/so101-code-style-rename-map-20261010.md"
        text = rename_map_text(allowlist)
        if target.exists():
            old = target.read_text(encoding="utf-8")
            marker = "## Root decisions on the 128 uncertain rows"
            if marker in old:
                section = old[old.index(marker):]
                section = section[: section.index("\n## ", 1) + 1] if "\n## " in section[1:] else section
                text = text.replace("## Rows still marked uncertain", section + "\n## Rows still marked uncertain", 1)
        target.write_text(text, encoding="utf-8")
        print("wrote", target)
        return 0
    counts: dict[tuple[str, str], int] = {}
    for row in rows:
        counts[(row.hit.scan, row.classification)] = counts.get((row.hit.scan, row.classification), 0) + 1
    for (scan_name, cls), number in sorted(counts.items()):
        print(f"{scan_name:10} {cls:24} {number}")
    print("total", len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
