"""Read-only inspection of the candidate inputs that exist today (the registry `freeze_inputs` consumes).

`inspect_inputs` records, for every role the diagnostic mode must freeze, which approved candidate exists. It
defaults nothing and selects nothing by recency. The freeze, verification and identity derivations live in
`diagnostic_episode_inputs`, which this module imports; that module resolves the names moved here lazily (module
`__getattr__`), so callers and tests keep importing them from `diagnostic_episode_inputs`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from .diagnostic_episode_inputs import (
    ANCHOR_APPROVAL_FILE,
    ANCHOR_FILE,
    CANDIDATES_KIND,
    COLLECTION_CONFIG_FILE,
    DEVELOPMENT_RUNTIME_FILE,
    EMPIRICAL_AUTHORIZATION_KIND,
    FROZEN_SCENE_ID,
    REFERENCE_FILE,
    RESET_RECIPE_FILE,
    ROLE_REQUIRED_CHECKS,
    ROLE_REQUIRED_VALUES,
    RUNTIME_CONFIG_FILE,
    SCENE_FILE,
    SCHEMA_VERSION,
    _HEX40,
    _digest,
    _require_registry,
    anchor_identity_from_bytes,
    profile_config_identity,
    require_nonhead_gate,
    resource_policy_identity,
    verify_proposal_in_own_mode,
)


def _source_file(root: Path, relative: str, role: str, approval: str, identity=None) -> dict:
    path = Path(root) / relative
    if not path.is_file() or path.is_symlink():
        return _role("MISSING", "NONHEAD_INPUT_BINDING_REQUIRED", f"{role} source file absent",
                     identity, candidates=[])
    entry = {"path": str(path), "sha256": _digest(path), "approved": True, "approval": approval}
    return _role("READY", None, None, identity, candidates=[entry])


def _unapproved_source_file(root: Path, relative: str, approval: str, identity, blocker: str,
                            note: str) -> dict:
    """Record the file that exists so a reviewer can see what is missing, not just that it is."""

    path = Path(root) / relative
    candidates = []
    if path.is_file() and not path.is_symlink():
        candidates.append({"path": str(path), "sha256": _digest(path), "approved": True,
                           "approval": approval})
    return _role("UNAPPROVED", blocker, note, identity, candidates)


def _role(status: str, blocker: str | None, note: str | None, identity, candidates) -> dict:
    return {"status": status, "candidates": list(candidates), "selected": None, "identity": identity,
            "blocker": blocker}


def _selected(role_document: dict) -> dict:
    candidates = role_document["candidates"]
    if len(candidates) == 1:
        role_document["selected"] = candidates[0]
    elif len(candidates) > 1:
        role_document["status"] = "AMBIGUOUS"
        role_document["blocker"] = "INPUT_CANDIDATE_AMBIGUOUS"
    return role_document


def _ledger_head(ledger: Path, field: str) -> str | None:
    try:
        with open(ledger, "rb") as stream:
            head = stream.read(16384).decode("utf-8", "replace")
    except OSError:
        return None
    match = re.search(rf"^{field}:\s*(\S+)\s*$", head, re.M)
    return match.group(1) if match else None


def _ledger_referenced_json(ledger: Path, evidence_root: Path) -> tuple[Path, ...]:
    """Absolute JSON paths under the registered evidence root that the ledger names."""

    try:
        text = Path(ledger).read_text(errors="replace")
    except OSError as error:
        raise ValueError("INPUT_LEDGER_INVALID") from error
    root = Path(evidence_root).resolve()
    found = set()
    for match in re.finditer(r"[^\s`\"'()\[\],;:]*[^\s`\"'()\[\],;:]+\.json", text):
        token = match.group(0)
        path = Path(token)
        if ".." in path.parts:
            continue
        # an absolute reference stays absolute; only a genuinely relative one is resolved against
        # the registered root, and containment is decided on the canonical paths so a symlink or a
        # traversal cannot smuggle a file from outside the root into the candidate set
        candidate = path if path.is_absolute() else root / token
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.is_relative_to(root) and resolved.is_file():
            found.add(resolved)
    return tuple(sorted(found))


def _git_commit(root: Path) -> str:
    import subprocess

    try:
        top = subprocess.check_output(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                                      text=True, stderr=subprocess.DEVNULL).strip()
        commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                         text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("INPUT_SOURCE_ROOT_INVALID") from error
    if Path(top).resolve() != Path(root).resolve() or not _HEX40.fullmatch(commit):
        raise ValueError("INPUT_SOURCE_ROOT_INVALID")
    return commit


def _inspect_anchor_scene(root: Path, rig=None) -> dict:
    path = Path(root) / ANCHOR_FILE
    if not path.is_file() or path.is_symlink():
        return _role("MISSING", "NONHEAD_INPUT_BINDING_REQUIRED", "anchor file absent", None, [])
    try:
        identity = anchor_identity_from_bytes(path.read_bytes(), rig)
    except ValueError:
        return _role("MISSING", "NONHEAD_INPUT_BINDING_REQUIRED",
                     "the anchor file does not carry the milestone's frozen default anchor",
                     None, [])
    approval_path = Path(root) / ANCHOR_APPROVAL_FILE
    approval = None
    if approval_path.is_file() and not approval_path.is_symlink():
        document = json.loads(approval_path.read_bytes())
        anchors = document.get("anchors") if isinstance(document, dict) else None
        anchor = anchors.get(FROZEN_SCENE_ID) if isinstance(anchors, dict) else None
        approved_sha = anchor.get("source_sha256") if isinstance(anchor, dict) else None
        status = document.get("status") if isinstance(document, dict) else None
        if isinstance(status, str) and "ANCHORS" in status \
                and approved_sha == identity["anchor_file_sha256"]:
            approval = approval_path
    if approval is None:
        return _unapproved_source_file(root, ANCHOR_FILE, "source_controlled", identity,
                                       "INPUT_NOT_APPROVED",
                                       "no approved-anchor document names this anchor digest")

    document = _source_file(root, ANCHOR_FILE, "anchor_scene", "source_controlled",
                            dict(identity, approved_by=str(approval.relative_to(root))))
    return _selected(document)


def _scene_file(rig=None) -> str:
    """The source-root-relative scene of a rig (the head+wrist scene, `SCENE_FILE`, when no rig is named)."""
    if rig is None:
        return SCENE_FILE
    from .rig_files import rig_model_files

    return "src/so101_demo_py/" + rig_model_files(rig).scene


def _compiled_model_identity(root: Path, rig=None) -> dict:
    """The same digest the physics checker uses: the compiled model bytes, not the XML text."""

    import mujoco
    import numpy as np

    scene = Path(root) / _scene_file(rig)
    model = mujoco.MjModel.from_xml_path(str(scene))
    buffer = np.empty(mujoco.mj_sizeModel(model), dtype=np.uint8)
    mujoco.mj_saveModel(model, None, buffer)
    return {"model_sha256": hashlib.sha256(buffer.tobytes()).hexdigest(),
            "scene_sha256": _digest(scene), "mujoco_version": mujoco.__version__}


def _activated_identity(proposal_path: Path | None) -> dict | None:
    if proposal_path is None:
        return None
    document = json.loads(Path(proposal_path).read_bytes())
    payload = document.get("payload") if isinstance(document, dict) else None
    if not isinstance(payload, dict):
        return None
    return {"model_sha256": payload.get("model_sha256"), "scene_sha256": payload.get("scene_sha256"),
            "mujoco_version": payload.get("mujoco_version")}


def _inspect_scene_model(root: Path, activated: dict | None, rig=None) -> dict:
    identity = _compiled_model_identity(root, rig)
    document = _source_file(root, _scene_file(rig), "scene_model", "source_controlled", identity)
    if activated is None:
        return _role("UNAPPROVED", "INPUT_ACTIVATION_STALE",
                     "no activated contact policy binds this scene identity", identity, [])
    if any(identity[key] != activated.get(key) for key in identity):
        return _role("IDENTITY_MISMATCH", "INPUT_IDENTITY_MISMATCH",
                     "the activated policy names another scene/model/version", identity, [])
    return _selected(document)


def _inspect_motion_config(root: Path) -> tuple[dict, dict]:
    """The collection config and the runtime config it binds, each as its own frozen role."""

    import yaml

    collection = Path(root) / COLLECTION_CONFIG_FILE
    runtime = Path(root) / RUNTIME_CONFIG_FILE
    missing = _role("MISSING", "NONHEAD_INPUT_BINDING_REQUIRED", "runtime/collection config absent",
                    None, [])
    if not collection.is_file() or not runtime.is_file():
        return missing, missing
    document = yaml.safe_load(collection.read_text())
    bound = (document.get("parallel_runtime") or {}).get("sha256") if isinstance(document, dict) else None
    binding = {"parallel_runtime_sha256": bound, "runtime_config_sha256": _digest(runtime)}
    if bound != binding["runtime_config_sha256"]:
        mismatch = _role("IDENTITY_MISMATCH", "INPUT_IDENTITY_MISMATCH",
                         "the collection config does not bind this runtime config's digest",
                         binding, [])
        return mismatch, mismatch
    collection_role = _selected(_source_file(
        root, COLLECTION_CONFIG_FILE, "collection_config", "source_controlled", binding))
    runtime_role = _selected(_source_file(
        root, RUNTIME_CONFIG_FILE, "runtime_config", "source_controlled",
        {"bound_by": COLLECTION_CONFIG_FILE}))
    return collection_role, runtime_role


def _inspect_resource_thresholds(root: Path) -> dict:
    """The start guard, the motion and disk hard stops and the queue backpressure stop.

    The policy is derived from the two verified config files by the same function the freeze and
    admission gates use, so an inspector that reports READY and a gate that accepts a READY registry
    cannot disagree about what the values are.
    """

    runtime = Path(root) / RUNTIME_CONFIG_FILE
    collection = Path(root) / COLLECTION_CONFIG_FILE
    candidates = []
    for path in (runtime, collection):
        if path.is_file() and not path.is_symlink():
            candidates.append({"path": str(path), "sha256": _digest(path), "approved": True,
                               "approval": "source_controlled"})
    if not runtime.is_file() or not collection.is_file():
        return _role("MISSING", "NONHEAD_INPUT_BINDING_REQUIRED", "runtime/collection config absent",
                     None, candidates)
    try:
        development = Path(root) / DEVELOPMENT_RUNTIME_FILE
        identity = resource_policy_identity(
            runtime.read_bytes(), collection.read_bytes(),
            **({"development_runtime": development} if development.is_file() else {}))
    except ValueError as error:
        return _role("MISSING", "NONHEAD_INPUT_BINDING_REQUIRED",
                     f"no approved resource stop policy: {error}", None, candidates)
    entry = {"path": str(runtime), "sha256": identity["runtime_config_sha256"], "approved": True,
             "approval": "source_controlled"}
    return _selected(_role("READY", None, None, identity, [entry]))


def _inspect_source_role(root: Path, relative: str, role: str, identity=None) -> dict:
    return _selected(_source_file(root, relative, role, "source_controlled", identity))


def _inspect_reset_recipe(root: Path, rig=None) -> dict:
    import xml.etree.ElementTree as ElementTree

    identity = {"keyframe": "task_start", "keyframe_present": False, "cup_body": "plastic_cup"}
    scene = Path(root) / _scene_file(rig)
    if scene.is_file():
        tree = ElementTree.parse(scene)
        for element in tree.getroot().iter("key"):
            if element.get("name") == "task_start":
                identity["keyframe_present"] = True
                identity["qpos"] = element.get("qpos")
                identity["ctrl"] = element.get("ctrl")
    return _inspect_source_role(root, RESET_RECIPE_FILE, "reset_recipe", identity)


def _inspect_reference(root: Path) -> dict:
    path = Path(root) / REFERENCE_FILE
    identity = {"reference_lead_s": 0.1, "source": "CONTROLLER_REFERENCE"}
    if not path.is_file():
        return _role("MISSING", "NONHEAD_INPUT_BINDING_REQUIRED", "reference tap absent", identity, [])
    if "reference(at_s" not in path.read_text() and "dt_s" not in path.read_text():
        return _role("MISSING", "NONHEAD_INPUT_BINDING_REQUIRED",
                     "the reference tap does not name its t+0.1s lead", identity, [])
    return _inspect_source_role(root, REFERENCE_FILE, "reference_interpolation", identity)


def _verify_disabled(path: Path) -> bool:
    try:
        verify_proposal_in_own_mode(json.loads(path.read_bytes()))
    except (ValueError, KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return True


def _verify_activation_for(path: Path, proposal_path: Path, identity: dict) -> bool:
    from .contact_policy import verify_activation

    try:
        document = json.loads(path.read_bytes())
        payload = json.loads(proposal_path.read_bytes())["payload"]
        verify_activation(payload, document, expected_model_sha256=identity["model_sha256"],
                          expected_scene_sha256=identity["scene_sha256"],
                          expected_mujoco_version=identity["mujoco_version"])
    except (ValueError, KeyError, TypeError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return True


def _inspect_contact(evidence_root: Path, referenced: tuple[Path, ...], identity: dict) -> tuple[dict, dict]:
    proposals = [path for path in referenced
                 if _verify_disabled(path) and _activated_identity(path) == identity]
    proposal_role = _role("MISSING", "NONHEAD_INPUT_BINDING_REQUIRED",
                          "no DISABLED proposal names this scene identity", identity, [])
    activation_role = _role("MISSING", "NONHEAD_INPUT_BINDING_REQUIRED",
                            "no activation receipt approves this scene identity", identity, [])
    if proposals:
        proposal_role = _selected(_role("READY", None, None, identity, [
            {"path": str(path), "sha256": _digest(path), "approved": True,
             "approval": "disabled_proposal"} for path in proposals]))
    if len(proposals) == 1:
        receipts = [path for path in referenced
                    if path.name.startswith("activation") or "receipt" in path.name]
        verified = [path for path in receipts
                    if _verify_activation_for(path, proposals[0], identity)]
        if verified:
            activation_role = _selected(_role("READY", None, None, identity, [
                {"path": str(path), "sha256": _digest(path), "approved": True,
                 "approval": "user_activation"} for path in verified]))
    return proposal_role, activation_role


def _inspect_calibration_role(role: str, referenced: tuple[Path, ...]) -> dict:
    identity = {"required_checks": list(ROLE_REQUIRED_CHECKS[role]),
                "required_values": list(ROLE_REQUIRED_VALUES[role])}
    candidates, unapproved = [], []
    for path in referenced:
        if not any(token in path.name for token in ("calibration", "report", "policy")):
            continue
        try:
            document = json.loads(path.read_bytes())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(document, dict):
            continue
        if (document.get("kind") == EMPIRICAL_AUTHORIZATION_KIND
                and document.get("approval") == "user_empirical_default"
                and isinstance(document.get("roles"), dict) and role in document["roles"]):
            # the amendment's route: the user-authorized empirical values for this role, carried with their own
            # provenance rather than a calibration report the amendment exists to stop demanding
            candidates.append({"path": str(path), "sha256": _digest(path), "approved": True,
                               "approval": "user_empirical_default"})
            continue
        if "checks" not in document:
            continue
        try:
            require_nonhead_gate(document)
        except ValueError:
            unapproved.append(path)
            continue
        candidates.append({"path": str(path), "sha256": _digest(path), "approved": True,
                           "approval": "nonhead_calibration"})
    if candidates:
        return _selected(_role("READY", None, None, identity, candidates))
    blocker = "NONHEAD_INPUT_BINDING_REQUIRED"
    return _role("MISSING", blocker,
                 "no ledger-referenced report measures " + ",".join(ROLE_REQUIRED_VALUES[role]),
                 dict(identity, rejected_candidates=[str(path) for path in unapproved]), [])


def inspect_inputs(source_root: Path, ledger: Path, rig=None) -> dict:
    """Record, read-only, which approved candidate exists for every required non-Head input.

    `rig` (a rig profile, a rig name or None for the head+wrist default) selects the scene the model identity and the reset recipe
    are read from, and the profile digest of the rig.

    Nothing is selected by recency and nothing is defaulted: a role with no approved, identity-
    matching candidate is reported with the blocker `freeze_inputs` will raise.
    """

    root = Path(source_root)
    if not root.is_dir():
        raise ValueError("INPUT_SOURCE_ROOT_INVALID")
    root = root.resolve()
    commit = _git_commit(root)
    evidence = _ledger_head(Path(ledger), "evidence_root")
    if evidence is None or not Path(evidence).is_absolute() or not Path(evidence).is_dir():
        raise ValueError("INPUT_LEDGER_INVALID")
    evidence_root = Path(evidence).resolve()
    referenced = _ledger_referenced_json(Path(ledger), evidence_root)

    identity = _compiled_model_identity(root, rig)
    proposal_role, activation_role = _inspect_contact(evidence_root, referenced, identity)
    activated = identity if proposal_role["status"] == "READY" else None
    collection_role, runtime_role = _inspect_motion_config(root)
    roles = {
        "anchor_scene": _inspect_anchor_scene(root, rig),
        "scene_model": _inspect_scene_model(root, activated, rig),
        "collection_config": collection_role,
        "runtime_config": runtime_role,
        "resource_thresholds": _inspect_resource_thresholds(root),
        "contact_proposal": proposal_role,
        "contact_activation": activation_role,
        "reset_recipe": _inspect_reset_recipe(root, rig),
        "reference_interpolation": _inspect_reference(root),
    }
    for role in ("path_policy", "placement_qc", "rgb_skew"):
        roles[role] = _inspect_calibration_role(role, referenced)
    document = {"kind": CANDIDATES_KIND, "schema_version": SCHEMA_VERSION, "source_root": str(root),
                "source_commit": commit, "config_sha256": profile_config_identity(root, rig),
                "evidence_root": str(evidence_root), "roles": roles}
    _require_registry(document)
    return document
