"""Frozen non-Head safety inputs for the first diagnostic episode.

The diagnostic mode removes the Head Search prerequisite only. Every non-Head safety value the plan
names still has to exist and have been approved by something other than a candidate file that merely
contains numbers: measured policy values, the activated contact policy and the frozen
scene/anchor/configuration files.

`inspect_inputs` records what exists (read-only, no defaulting). `freeze_inputs` refuses anything
that is missing, ambiguous, unapproved or internally inconsistent, then copies the survivors once
into an immutable directory and returns the manifest that binds their bytes. A missing value is a
blocker code, never a default.

By the owner's decision, an artifact's recorded source/config
identity is provenance, not a claim about the tree that happens to be running: it is validated for
shape and recorded, never compared with the current identity. Byte integrity, report structure,
byte-derived anchor and resource identities, and the payload-to-frozen-role binding are still
enforced.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re

from .calibration import CHECK_MEASUREMENTS, REQUIRED_CHECKS, REQUIRED_MEASUREMENTS
from .contracts import ContractError, fields, finite, integer, sha256, vector

CANDIDATES_KIND = "ACT_DIAGNOSTIC_EPISODE_INPUT_CANDIDATES"
MANIFEST_KIND = "ACT_DIAGNOSTIC_EPISODE_INPUTS"
SCHEMA_VERSION = 1
#: The manifest schema. Version 2 dropped the broker stop policy and the bound-timing roles (design 10-06: no broker); a
#: version 1 manifest - or any manifest still carrying those roles - is refused, never accepted silently.
MANIFEST_SCHEMA_VERSION = 2

# every role the milestone must freeze; a missing one is an exact blocker, not a default
INPUT_ROLES = (
    "anchor_scene", "scene_model", "collection_config", "runtime_config", "path_policy",
    "placement_qc", "rgb_skew", "resource_thresholds", "contact_proposal", "contact_activation",
    "reset_recipe", "reference_interpolation",
)

# the checks the diagnostic mode still requires, and the ones it may leave unmeasured
NONHEAD_CHECKS = frozenset({"collision", "synchronization", "execution", "release", "retreat"})

_CANDIDATE_FIELDS = frozenset({"path", "sha256", "approved", "approval"})
#: the artifact kind that carries the user-authorized empirical values (design section 5.1)
EMPIRICAL_AUTHORIZATION_KIND = "ACT_NONHEAD_EMPIRICAL_AUTHORIZATION"
_ROLE_FIELDS = frozenset({"status", "candidates", "selected", "identity", "blocker"})
_REGISTRY_FIELDS = frozenset({"kind", "schema_version", "source_root", "source_commit",
                              "config_sha256", "evidence_root", "roles"})
#: every manifest carries these
_MANIFEST_REQUIRED = frozenset({"kind", "schema_version", "source_root", "source_commit",
                                "config_sha256", "evidence_root", "roles", "inputs_sha256"})
#: the freezer binds the collection mode, the policies and the development runtime too, but a call that writes none of them
#: keeps its contract - so they are allowed, not required
#: `scene_manifest` binds the scene list of a formal campaign: `{path, sha256, bytes, scene_count}` of the frozen copy at
#: `SCENE_MANIFEST_PATH`. It is a key, not a role, so a set without it keeps the exact role table and hash it always had.
#: `rig_profile` binds the camera rig of the collection (config/act/rig-v*.yaml, `act/rig_profile.py`) the same way a policy is bound:
#: the file under `policies/rig_profile.yaml`, its digests and every effective value. It is a key, not a role, so a set sealed before
#: rig profiles existed keeps its exact table and hash and is read as the default rig (v1); a newly frozen campaign set always has it.
_MANIFEST_OPTIONAL = frozenset({"mode", "runtime_policy", "execution_snapshot",
                                "teacher_endpoint", "teacher_execution_policy", "episode_recorder",
                                "scene_manifest", "rig_profile"})
RIG_PROFILE_BINDING = "rig_profile"
RIG_PROFILE_FILE = "rig_profile.yaml"
SCENE_MANIFEST_PATH = "scene_manifest/scenes.json"
_SCENE_MANIFEST_FIELDS = frozenset({"path", "sha256", "bytes", "scene_count"})
#: The policy bindings (Phase A4c): binding name -> the file
#: name frozen under `policies/` and the package-relative config path the execution snapshot also carries.
POLICY_BINDINGS = {
    "teacher_endpoint": ("teacher_endpoint.yaml", "config/act/teacher_endpoint.yaml"),
    "teacher_execution_policy": ("teacher_execution_policy.yaml", "config/act/teacher_execution_policy.yaml"),
    "episode_recorder": ("episode_recorder.yaml", "config/act/episode_recorder.yaml"),
}
#: the execution policy binding frozen with an attempt
EXECUTION_POLICY_BINDING = "teacher_execution_policy"
_POLICY_BINDING_FIELDS = frozenset({"path", "file_sha256", "bytes", "policy_sha256", "values"})
_MANIFEST_FIELDS = _MANIFEST_REQUIRED | _MANIFEST_OPTIONAL
_MANIFEST_ROLE_FIELDS = frozenset({"path", "sha256", "bytes", "approval", "identity"})
_APPROVALS = frozenset({"source_controlled", "disabled_proposal", "user_activation", "spot_check_candidate",
                        "nonhead_calibration", "user_empirical_default"})
_ROLE_APPROVAL = {"contact_proposal": "disabled_proposal",
                  # a spot_check_candidate receipt is a plan-signed candidate (D4), not a user activation; the freeze
                  # refuses it unless the input set is a preselected_target_diagnostic one
                  "contact_activation": ("user_activation", "spot_check_candidate"),
                  # the amendment replaces the calibration report these three used to demand with the values the
                  # user authorized this round; both kinds are accepted so an old record keeps its reading and a
                  # new candidate carries the authorized provenance
                  "path_policy": ("user_empirical_default", "nonhead_calibration"),
                  "placement_qc": ("user_empirical_default", "nonhead_calibration"),
                  "rgb_skew": ("user_empirical_default", "nonhead_calibration")}
_STATUS_BLOCKERS = {"MISSING": "NONHEAD_INPUT_BINDING_REQUIRED",
                    "AMBIGUOUS": "INPUT_CANDIDATE_AMBIGUOUS",
                    "UNAPPROVED": "INPUT_NOT_APPROVED",
                    "IDENTITY_MISMATCH": "INPUT_IDENTITY_MISMATCH"}
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_HEX40 = re.compile(r"[0-9a-f]{40}\Z")


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode()


def execution_snapshot_binding(snapshot, root):
    """Bind verified compiled dimensions into the immutable input digest for raw readback."""
    import yaml
    from .rig_files import rig_for_scene
    relative = rig_for_scene(snapshot["scene_path"]).plugins
    payload = (Path(root) / relative).read_bytes()
    config_sha = hashlib.sha256(payload).hexdigest()
    if config_sha != snapshot["files"][relative]["sha256"]:
        raise ValueError("INPUTS_EXECUTION_PRODUCER_BYTES_INVALID")
    params = yaml.safe_load(payload)["/**"]["ros__parameters"]
    chunk_size, buffer_size, contacts = (params[key] for key in (
        "physics_step_chunk_size", "physics_step_buffer_capacity", "max_contacts"))
    if (type(chunk_size) is not int or chunk_size < 1 or type(buffer_size) is not int
            or buffer_size < chunk_size or type(contacts) is not int or contacts < 0):
        raise ValueError("INPUTS_EXECUTION_PRODUCER_CONFIG_INVALID")
    return {"kind": "ACT_EXECUTION_SNAPSHOT_BINDING", "schema_version": 2,
            "path": "execution", "sha256": snapshot["snapshot_sha256"],
            "model_identity": {key: snapshot[key] for key in ("model_sha256", "nq", "nv", "mujoco_version")},
            "physics_chunks": {"max_samples": chunk_size, "max_contacts": contacts, "config_sha256": config_sha}}


def validate_execution_snapshot_binding(binding):
    """The verified model identity of an execution snapshot binding (schema 2: it names the compiled model and the producer chunks)."""
    keys = {"kind", "schema_version", "path", "sha256", "model_identity", "physics_chunks"}
    if (not isinstance(binding, dict) or set(binding) != keys
            or binding["kind"] != "ACT_EXECUTION_SNAPSHOT_BINDING"
            or type(binding["schema_version"]) is not int or binding["schema_version"] != 2
            or binding["path"] != "execution" or not isinstance(binding["sha256"], str)
            or not _HEX64.fullmatch(binding["sha256"])):
        raise ValueError("INPUTS_EXECUTION_SNAPSHOT_INVALID")
    model = binding["model_identity"]
    if (not isinstance(model, dict) or set(model) != {"model_sha256", "nq", "nv", "mujoco_version"}
            or not isinstance(model["model_sha256"], str) or not _HEX64.fullmatch(model["model_sha256"])
            or type(model["nq"]) is not int or model["nq"] < 1
            or type(model["nv"]) is not int or model["nv"] < 1
            or not isinstance(model["mujoco_version"], str) or not model["mujoco_version"]):
        raise ValueError("INPUTS_EXECUTION_SNAPSHOT_INVALID")
    chunks = binding["physics_chunks"]
    if (not isinstance(chunks, dict) or set(chunks) != {"max_samples", "max_contacts", "config_sha256"}
            or type(chunks["max_samples"]) is not int or chunks["max_samples"] < 1
            or type(chunks["max_contacts"]) is not int or chunks["max_contacts"] < 0
            or not isinstance(chunks["config_sha256"], str) or not _HEX64.fullmatch(chunks["config_sha256"])):
        raise ValueError("INPUTS_EXECUTION_PRODUCER_CONFIG_INVALID")
    return model


def audit_execution_model_identity(inputs):
    """Authenticate copied frozen model metadata against the input binding digest."""
    binding = inputs.get("execution_snapshot")
    if binding is None:
        return None
    model = validate_execution_snapshot_binding(binding)
    roles = inputs.get("roles")
    extra = {key: inputs[key] for key in _MANIFEST_OPTIONAL if key in inputs}
    if (not isinstance(roles, dict) or set(roles) != set(INPUT_ROLES)
            or hashlib.sha256(_canonical({**roles, **extra})).hexdigest() != inputs.get("inputs_sha256")):
        raise ValueError("INPUTS_MANIFEST_INVALID")
    scene = roles["scene_model"].get("identity")
    if (not isinstance(scene, dict) or scene.get("model_sha256") != model["model_sha256"]
            or scene.get("mujoco_version") != model["mujoco_version"]):
        raise ValueError("INPUTS_EXECUTION_SNAPSHOT_IDENTITY_MISMATCH")
    return model


# ---------------------------------------------------------------------------
# the non-Head safety gate
# ---------------------------------------------------------------------------

def require_nonhead_gate(report) -> dict:
    """Require every non-Head safety measurement, without requiring the Head Search ones.

    A report that claims PASS for any check must carry that check's measurements, so a PASS cannot
    outrun its evidence. The two Head checks (`fov`, `search`) are not required to be anything:
    that is the whole substitution this milestone makes. The report's own recorded identity is
    checked for shape only; by the owner's decision it is not compared with the
    tree that is running.
    """

    try:
        return _require_nonhead_gate(report)
    except ValueError:
        raise
    except (ContractError, KeyError, TypeError, OSError) as error:
        raise ValueError("NONHEAD_SAFETY_NOT_READY") from error


def _require_nonhead_gate(report) -> dict:
    base = ("schema_version", "status", "source_commit", "config_sha256",
            "source_provenance_sha256", "measurements", "checks")
    if not isinstance(report, dict) or any(key not in report for key in base):
        raise ValueError("NONHEAD_SAFETY_NOT_READY")
    if report["schema_version"] != 1 or isinstance(report["schema_version"], bool):
        raise ValueError("NONHEAD_SAFETY_NOT_READY")
    if report["status"] not in ("CALIBRATION_REQUIRED", "PICK_PLACE_CALIBRATION_READY", "QUALIFIED"):
        raise ValueError("NONHEAD_SAFETY_NOT_READY")
    if not isinstance(report["source_commit"], str) or not _HEX40.fullmatch(report["source_commit"]):
        raise ValueError("NONHEAD_SAFETY_NOT_READY")
    provenance = report["source_provenance_sha256"]
    if not isinstance(provenance, str) or not _HEX64.fullmatch(provenance):
        raise ValueError("NONHEAD_SAFETY_NOT_READY")
    sha256(report["config_sha256"])
    fields(report["checks"], REQUIRED_CHECKS)
    if any(value not in ("PASS", "FAIL", "UNMEASURED") for value in report["checks"].values()):
        raise ValueError("NONHEAD_SAFETY_NOT_READY")
    measurements = report["measurements"]
    if not isinstance(measurements, dict) or not set(measurements) <= set(REQUIRED_MEASUREMENTS):
        raise ValueError("NONHEAD_SAFETY_NOT_READY")
    for check, value in report["checks"].items():
        if value == "PASS" and not CHECK_MEASUREMENTS[check] <= set(measurements):
            raise ValueError("NONHEAD_SAFETY_NOT_READY")
    if any(report["checks"][name] != "PASS" for name in NONHEAD_CHECKS):
        raise ValueError("NONHEAD_SAFETY_NOT_READY")
    for name, item in measurements.items():
        unit, size = REQUIRED_MEASUREMENTS[name]
        fields(item, ("value", "unit", "sample_path", "sample_sha256"))
        if item["unit"] != unit:
            raise ValueError("NONHEAD_SAFETY_NOT_READY")
        if size == 1:
            finite(item["value"])
        else:
            vector(item["value"], size)
        if unit == "count":
            integer(item["value"], minimum=1)
        if name in ("min_confidence", "tracking_iou") and not 0 < item["value"] <= 1:
            raise ValueError("NONHEAD_SAFETY_NOT_READY")
        digest = item["sample_sha256"]
        if not isinstance(digest, str) or not _HEX64.fullmatch(digest):
            raise ValueError("NONHEAD_SAFETY_NOT_READY")
        sample = Path(item["sample_path"]) if isinstance(item["sample_path"], str) else None
        if sample is None or not sample.is_absolute() or sample.is_symlink() or not sample.is_file():
            raise ValueError("NONHEAD_SAFETY_NOT_READY")
        if hashlib.sha256(sample.read_bytes()).hexdigest() != digest:
            raise ValueError("NONHEAD_SAFETY_NOT_READY")
    return report


# ---------------------------------------------------------------------------
# candidate registry and frozen manifest
# ---------------------------------------------------------------------------

def read_candidate_registry(path: Path) -> dict:
    """Read and validate the registry `inspect_inputs` writes."""

    try:
        document = json.loads(Path(path).read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("INPUT_CANDIDATES_INVALID") from error
    _require_registry(document)
    return document


def _require_registry(document) -> None:
    if not isinstance(document, dict) or set(document) != _REGISTRY_FIELDS:
        raise ValueError("INPUT_CANDIDATES_INVALID")
    if document["kind"] != CANDIDATES_KIND or document["schema_version"] != SCHEMA_VERSION:
        raise ValueError("INPUT_CANDIDATES_INVALID")
    for name in ("source_root", "evidence_root"):
        value = document[name]
        if not isinstance(value, str) or not Path(value).is_absolute() or ".." in Path(value).parts:
            raise ValueError("INPUT_CANDIDATES_INVALID")
    if not isinstance(document["source_commit"], str) or not _HEX40.fullmatch(document["source_commit"]):
        raise ValueError("INPUT_CANDIDATES_INVALID")
    if not isinstance(document["config_sha256"], str) or not _HEX64.fullmatch(document["config_sha256"]):
        raise ValueError("INPUT_CANDIDATES_INVALID")
    roles = document["roles"]
    if not isinstance(roles, dict) or not set(roles) <= set(INPUT_ROLES):
        raise ValueError("INPUT_CANDIDATES_INVALID")
    for role, item in roles.items():
        if not isinstance(item, dict) or set(item) != _ROLE_FIELDS:
            raise ValueError("INPUT_CANDIDATES_INVALID")
        if item["status"] not in tuple(_STATUS_BLOCKERS) + ("READY",):
            raise ValueError("INPUT_CANDIDATES_INVALID")
        if not isinstance(item["candidates"], list):
            raise ValueError("INPUT_CANDIDATES_INVALID")
        for entry in item["candidates"]:
            _require_entry(entry)
        if item["selected"] is not None:
            _require_entry(item["selected"])
        if item["blocker"] is not None and not isinstance(item["blocker"], str):
            raise ValueError("INPUT_CANDIDATES_INVALID")


def _require_entry(entry) -> None:
    if not isinstance(entry, dict) or set(entry) != _CANDIDATE_FIELDS:
        raise ValueError("INPUT_CANDIDATES_INVALID")
    if not isinstance(entry["path"], str) or not Path(entry["path"]).is_absolute():
        raise ValueError("INPUT_CANDIDATES_INVALID")
    if not isinstance(entry["sha256"], str) or not _HEX64.fullmatch(entry["sha256"]):
        raise ValueError("INPUT_CANDIDATES_INVALID")
    if type(entry["approved"]) is not bool or not isinstance(entry["approval"], str):
        raise ValueError("INPUT_CANDIDATES_INVALID")


def read_inputs_manifest(path: Path) -> dict:
    """Read back the frozen manifest, refusing an edited or unknown-schema document."""

    try:
        document = json.loads(Path(path).read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("INPUTS_MANIFEST_INVALID") from error
    if (not isinstance(document, dict) or not _MANIFEST_REQUIRED <= set(document)
            or not set(document) <= _MANIFEST_FIELDS):
        raise ValueError("INPUTS_MANIFEST_INVALID")
    if document["kind"] != MANIFEST_KIND or document["schema_version"] != MANIFEST_SCHEMA_VERSION:
        raise ValueError("INPUTS_MANIFEST_INVALID")
    if not isinstance(document["source_commit"], str) or not _HEX40.fullmatch(document["source_commit"]):
        raise ValueError("INPUTS_MANIFEST_INVALID")
    if not isinstance(document["config_sha256"], str) or not _HEX64.fullmatch(document["config_sha256"]):
        raise ValueError("INPUTS_MANIFEST_INVALID")
    if not isinstance(document["inputs_sha256"], str) or not _HEX64.fullmatch(document["inputs_sha256"]):
        raise ValueError("INPUTS_MANIFEST_INVALID")
    roles = document["roles"]
    if not isinstance(roles, dict) or set(roles) != set(INPUT_ROLES):
        raise ValueError("INPUTS_MANIFEST_INVALID")
    for item in roles.values():
        if not isinstance(item, dict) or set(item) != _MANIFEST_ROLE_FIELDS:
            raise ValueError("INPUTS_MANIFEST_INVALID")
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValueError("INPUTS_MANIFEST_INVALID")
        if not isinstance(item["sha256"], str) or not _HEX64.fullmatch(item["sha256"]):
            raise ValueError("INPUTS_MANIFEST_INVALID")
        if type(item["bytes"]) is not int or item["bytes"] < 0 or item["approval"] not in _APPROVALS:
            raise ValueError("INPUTS_MANIFEST_INVALID")
    # the writer folds the amendment's three bindings into the same digest the design requires them to be part of,
    # so the reader hashes what was written rather than only the role table
    extra = {key: document[key] for key in _MANIFEST_OPTIONAL if key in document}
    if hashlib.sha256(_canonical({**roles, **extra})).hexdigest() != document["inputs_sha256"]:
        raise ValueError("INPUTS_MANIFEST_INVALID")
    return document


# only these roles carry a JSON contract this module must read; the rest are frozen as bytes
_JSON_ROLES = frozenset({"contact_proposal", "contact_activation", "path_policy", "placement_qc",
                         "rgb_skew"})


def _policy_loader(name: str):
    """The closed loader of one frozen policy; every refusal is a ValueError."""

    if name == "teacher_endpoint":
        from .teacher_endpoint import load_teacher_endpoint_policy as loader
    elif name == EXECUTION_POLICY_BINDING:
        from .teacher_endpoint import load_teacher_execution_policy as loader
    else:
        from .offline.policy import load_recorder_policy as loader
    return loader


def policy_binding(name: str, payload: bytes) -> dict:
    """The manifest binding of one policy file: its bytes, its sha256 and every effective value (policy_sha256 apart)."""

    policy = _policy_loader(name)(payload)
    return {"path": "policies/" + POLICY_BINDINGS[name][0], "file_sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload), "policy_sha256": policy["policy_sha256"],
            "values": {key: value for key, value in policy.items() if key != "policy_sha256"}}


def rig_profile_binding(payload: bytes) -> dict:
    """The manifest binding of one rig profile file: its bytes, its sha256, the profile digest and the validated document."""
    from .rig_profile import load_rig_profile_bytes

    profile = load_rig_profile_bytes(payload)
    return {"path": "policies/" + RIG_PROFILE_FILE, "file_sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload), "policy_sha256": profile.profile_sha256, "values": profile.document}


def verify_rig_profile_binding(document: dict, manifest_path: Path) -> None:
    """Re-read the frozen rig profile file and compare it with its binding; a manifest without one is rig v1 and is not checked."""
    from .rig_profile import load_rig_profile_bytes

    if RIG_PROFILE_BINDING not in document:
        return
    code = "INPUTS_RIG_PROFILE_INVALID"
    root = Path(manifest_path).parent.resolve()
    binding = document[RIG_PROFILE_BINDING]
    if not isinstance(binding, dict) or set(binding) != _POLICY_BINDING_FIELDS:
        raise ValueError(code)
    path = root / binding["path"]
    if (binding["path"] != "policies/" + RIG_PROFILE_FILE or path.is_symlink() or not path.is_file()
            or not path.resolve().is_relative_to(root)):
        raise ValueError(code)
    try:
        payload = path.read_bytes()
        profile = load_rig_profile_bytes(payload)
    except (OSError, ValueError) as error:
        raise ValueError(code) from error
    if (len(payload) != binding["bytes"] or hashlib.sha256(payload).hexdigest() != binding["file_sha256"]
            or profile.profile_sha256 != binding["policy_sha256"] or profile.document != binding["values"]):
        raise ValueError(code)


def verify_policy_bindings(document: dict, manifest_path: Path, snapshot: dict | None = None) -> dict:
    """Re-read each frozen policy file, re-load it through its closed loader and compare every bound value.

    Returns the loaded policies by binding name. A binding whose file, digest, size, values or policy digest disagree is
    refused, and so is one whose bytes differ from the copy the execution snapshot froze from the same source tree.
    """

    root = Path(manifest_path).parent.resolve()
    loaded = {}
    for name, (filename, config_path) in POLICY_BINDINGS.items():
        if name not in document:
            continue
        code = "INPUTS_POLICY_BINDING_INVALID: " + name
        binding = document[name]
        if not isinstance(binding, dict) or set(binding) != _POLICY_BINDING_FIELDS:
            raise ValueError(code)
        path = root / binding["path"]
        if (binding["path"] != "policies/" + filename or path.is_symlink() or not path.is_file()
                or not path.resolve().is_relative_to(root)):
            raise ValueError(code)
        try:
            payload = path.read_bytes()
        except OSError as error:
            raise ValueError(code) from error
        if len(payload) != binding["bytes"] or hashlib.sha256(payload).hexdigest() != binding["file_sha256"]:
            raise ValueError(code)
        try:
            policy = _policy_loader(name)(payload)
        except ValueError as error:
            raise ValueError(code + ": " + str(error)) from error
        if (policy["policy_sha256"] != binding["policy_sha256"]
                or {key: value for key, value in policy.items() if key != "policy_sha256"} != binding["values"]):
            raise ValueError(code + ": values")
        if snapshot is not None:
            frozen_copy = snapshot["files"].get(config_path)
            if frozen_copy is not None and frozen_copy["sha256"] != binding["file_sha256"]:
                raise ValueError(code + ": execution snapshot copy differs")
        loaded[name] = policy
    return loaded


def _scene_rows(payload: bytes, code: str) -> tuple[dict, ...]:
    """The rows of a scene manifest (`scenarios[]`), or `ValueError(code)`: no duplicate JSON key or scene id, no NaN.

    Each row needs the identity the collection scope is built from - a container-valid `scene_id`, a non-negative integer
    `seed` (not a bool, string or float) - and a non-empty `split`, the same contract `scene_ids` reads. Other fields stay.
    """
    from so101_demo.parallel_batch.contracts.common import ContractError, _require_id

    def pairs(items):
        if len({key for key, _ in items}) != len(items):
            raise ValueError(code)
        return dict(items)

    def constant(_name):
        raise ValueError(code)

    try:
        document = json.loads(payload.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeDecodeError, ValueError, RecursionError) as error:
        raise ValueError(code) from error
    rows = document.get("scenarios") if isinstance(document, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError(code)
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or type(row.get("seed")) is not int or row["seed"] < 0:
            raise ValueError(code)
        if not isinstance(row.get("split"), str) or not row["split"]:
            raise ValueError(code)
        try:
            _require_id("scene_id", row.get("scene_id"))
        except ContractError as error:
            raise ValueError(code) from error
        if row["scene_id"] in seen:
            raise ValueError(code)
        seen.add(row["scene_id"])
    return tuple(rows)


def _bound_scene_rows(document: dict, root: Path) -> tuple[dict, ...]:
    """Re-read the bound scene manifest under `root` and return its rows; every fault is `INPUTS_SCENE_MANIFEST_INVALID`.

    The key is legal only on a `formal` set. The binding is closed, the file is the one fixed path (no symlink, inside `root`)
    and its size, hash and row count are the bound ones, so a replaced list cannot reach a scope check unnoticed.
    """
    code = "INPUTS_SCENE_MANIFEST_INVALID"
    binding = document.get("scene_manifest")
    if (document.get("mode") != "formal" or not isinstance(binding, dict) or set(binding) != _SCENE_MANIFEST_FIELDS
            or binding["path"] != SCENE_MANIFEST_PATH or not isinstance(binding["sha256"], str)
            or not _HEX64.fullmatch(binding["sha256"]) or type(binding["bytes"]) is not int or binding["bytes"] < 0
            or type(binding["scene_count"]) is not int or binding["scene_count"] < 1):
        raise ValueError(code)
    path = Path(root) / binding["path"]
    try:
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(Path(root).resolve()):
            raise ValueError(code)
        payload = path.read_bytes()
    except OSError as error:
        raise ValueError(code) from error
    if len(payload) != binding["bytes"] or hashlib.sha256(payload).hexdigest() != binding["sha256"]:
        raise ValueError(code)
    rows = _scene_rows(payload, code)
    if len(rows) != binding["scene_count"]:
        raise ValueError(code)
    return rows


def frozen_scene_rows(frozen: dict, manifest_path: Path) -> tuple[dict, ...]:
    """The rows of the scene manifest a frozen set binds, re-read and re-hashed now; refuses a set that binds none."""
    if "scene_manifest" not in frozen:
        raise ValueError("INPUTS_SCENE_MANIFEST_INVALID")
    return _bound_scene_rows(frozen, Path(manifest_path).parent)


def require_scope_for_inputs(document: dict, frozen: dict, manifest_path: Path) -> None:
    """Refuse a collection scope that is not valid for the frozen input set; the one rule every site shares.

    A set that binds no scene manifest (every diagnostic set, and a formal set that predates the binding) expects exactly the
    anchor scope. A set that binds one (formal only) expects the scope of one of its rows: `formal`, that row's `scene_id` and
    `seed`, and this set's `inputs_sha256`. The anchor scope is then valid only if `default` is itself a row.
    Raises `EPISODE_SCOPE_INPUTS_MISMATCH`, or `INPUTS_SCENE_MANIFEST_INVALID` when the bound file no longer verifies.
    """
    from .collection_scope import build_collection_scope

    if "scene_manifest" not in frozen:
        anchor = frozen["roles"]["anchor_scene"]["identity"]
        expected = [build_collection_scope(frozen["mode"], scene_id=anchor["scene_id"], seed=anchor["seed"],
                                           inputs_sha256=frozen["inputs_sha256"])]
    else:
        expected = [build_collection_scope("formal", scene_id=row["scene_id"], seed=row["seed"],
                                           inputs_sha256=frozen["inputs_sha256"])
                    for row in frozen_scene_rows(frozen, manifest_path)]
    if document not in expected:
        raise ValueError("EPISODE_SCOPE_INPUTS_MISMATCH")


def verify_frozen_inputs(manifest_path: Path) -> dict:
    """Read the manifest and verify every frozen file it names, not only its metadata.

    A self-consistent manifest can describe files that never existed or that changed after the
    freeze, so admission re-reads each role beneath the manifest's own directory and refuses
    anything missing, replaced, resized, symlinked or outside that directory.
    """

    manifest_path = Path(manifest_path)
    document = read_inputs_manifest(manifest_path)
    root = manifest_path.parent.resolve()
    from .endpoint_pose_acceptance import validate_development_runtime
    if "runtime_policy" in document:
        binding = document["runtime_policy"]
        if not isinstance(binding, dict) or set(binding) != {"sha256", "path_policy", "rgb_sync", "safety_release", "hard_stops"}:
            raise ValueError("INPUTS_RUNTIME_POLICY_INVALID")
        policy = validate_development_runtime({"kind": "ACT_ENDPOINT_DEVELOPMENT_RUNTIME", "schema_version": 1,
                                               **{key: value for key, value in binding.items() if key != "sha256"}})
        if hashlib.sha256(_canonical(policy)).hexdigest() != binding["sha256"]:
            raise ValueError("INPUTS_RUNTIME_POLICY_INVALID")
    for role, item in document["roles"].items():
        path = manifest_path.parent / item["path"]
        try:
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"INPUTS_FROZEN_BYTES_INVALID: {role}")
            resolved = path.resolve()
            if not resolved.is_relative_to(root):
                raise ValueError(f"INPUTS_FROZEN_BYTES_INVALID: {role}")
            payload = resolved.read_bytes()
        except OSError as error:
            raise ValueError(f"INPUTS_FROZEN_BYTES_INVALID: {role}") from error
        if len(payload) != item["bytes"] or hashlib.sha256(payload).hexdigest() != item["sha256"]:
            raise ValueError(f"INPUTS_FROZEN_BYTES_INVALID: {role}")
    if "execution_snapshot" in document:
        from .execution_snapshot import verify_execution_snapshot
        binding = document["execution_snapshot"]
        model_identity = validate_execution_snapshot_binding(binding)
        snapshot = verify_execution_snapshot(root / binding["path"], expected_sha256=binding["sha256"])
        if any(snapshot[key] != value for key, value in model_identity.items()):
            raise ValueError("INPUTS_EXECUTION_SNAPSHOT_IDENTITY_MISMATCH")
        if binding != execution_snapshot_binding(snapshot, root / binding["path"]):
            raise ValueError("INPUTS_EXECUTION_PRODUCER_CONFIG_INVALID")
        identity = document["roles"]["scene_model"]["identity"]
        if (not isinstance(identity, dict) or snapshot["model_sha256"] != identity.get("model_sha256")
                or snapshot["mujoco_version"] != identity.get("mujoco_version")
                or snapshot["files"][snapshot["scene_path"]]["sha256"] != identity.get("scene_sha256")
                or document["roles"]["scene_model"]["sha256"] != identity.get("scene_sha256")):
            raise ValueError("INPUTS_EXECUTION_SNAPSHOT_IDENTITY_MISMATCH")
    verify_policy_bindings(document, manifest_path, snapshot if "execution_snapshot" in document else None)
    verify_rig_profile_binding(document, manifest_path)
    if "execution_snapshot" in document:
        from .rig_files import rig_model_files
        from .rig_profile import rig_from_frozen
        # the execution snapshot is recorded against the scene of the frozen rig, never another rig's
        if rig_model_files(rig_from_frozen(document)).scene != snapshot["scene_path"]:
            raise ValueError("INPUTS_RIG_SCENE_MISMATCH")
    if "scene_manifest" in document:
        _bound_scene_rows(document, root)
    return document


def _read_verified(entry: dict) -> bytes:
    """Return the exact approved bytes, refusing a symlink, a missing file or a changed digest."""

    path = Path(entry["path"])
    if path.is_symlink() or not path.is_file():
        raise ValueError("INPUT_IDENTITY_MISMATCH")
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
        raise ValueError("INPUT_IDENTITY_MISMATCH")
    return payload


def _parse_json(payload: bytes) -> dict:
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("INPUT_IDENTITY_MISMATCH") from error
    if not isinstance(document, dict):
        raise ValueError("INPUT_IDENTITY_MISMATCH")
    return document


def verify_contact_activation(payload: dict, receipt: dict, identity: dict, *, mode) -> None:
    """The freeze-side activation check. A spot_check_candidate receipt passes only for a diagnostic freeze."""

    from .contact_policy import spot_check_receipt_allowed, verify_activation

    try:
        verify_activation(payload, receipt, expected_model_sha256=identity["model_sha256"],
                          expected_scene_sha256=identity["scene_sha256"],
                          expected_mujoco_version=identity["mujoco_version"],
                          allow_spot_check_candidate=spot_check_receipt_allowed(mode))
    except ValueError as error:
        raise ValueError("INPUT_ACTIVATION_STALE") from error


def verify_proposal_in_own_mode(proposal) -> None:
    """Verify a disabled proposal under the validation mode its own envelope declares.

    The freeze and the discovery share this one rule so they cannot disagree about which proposals are well formed.
    """

    from .contact_calibration import proposal_validation_mode, verify_disabled_proposal

    verify_disabled_proposal(proposal, validation_mode=proposal_validation_mode(proposal))


def _verify_roles(registry: dict, *, mode=None, rig=None) -> dict:
    """Resolve one approved candidate per role, run the semantic cross-checks, return the bytes.

    The verified bytes are handed back so a freeze copies exactly what was approved. Reading the
    candidate a second time would let a file that changed after verification be frozen instead.

    By the owner's decision the registry's `source_commit` and `config_sha256`
    are recorded provenance, not a claim about the tree that happens to be running now.
    """

    from .contact_policy import spot_check_receipt_allowed

    for role in INPUT_ROLES:
        item = registry["roles"].get(role)
        if item is None:
            raise ValueError("NONHEAD_INPUT_BINDING_REQUIRED")
        if item["status"] != "READY":
            raise ValueError(item["blocker"] or _STATUS_BLOCKERS[item["status"]])
        if len(item["candidates"]) != 1:
            raise ValueError("INPUT_CANDIDATE_AMBIGUOUS")
        entry = item["selected"]
        if entry is None or entry not in item["candidates"]:
            raise ValueError("NONHEAD_INPUT_BINDING_REQUIRED")
        if entry["approved"] is not True:
            raise ValueError("INPUT_NOT_APPROVED")
        required = _ROLE_APPROVAL.get(role, "source_controlled")
        if entry["approval"] not in (required if isinstance(required, tuple) else (required,)):
            raise ValueError("INPUT_NOT_APPROVED")
        if entry["approval"] == "spot_check_candidate" and not spot_check_receipt_allowed(mode):
            raise ValueError("INPUT_NOT_APPROVED")
        if entry["approval"] == "source_controlled":
            if not Path(entry["path"]).is_relative_to(Path(registry["source_root"])):
                raise ValueError("INPUT_NOT_APPROVED")
    payloads = {role: _read_verified(registry["roles"][role]["selected"]) for role in INPUT_ROLES}
    documents = {role: _parse_json(payloads[role]) for role in _JSON_ROLES}


    # the identity of the anchor and of the resource policy is derived from the verified bytes and
    # compared with what the registry asserts, so a consistent assertion cannot stand in for the
    # bytes it claims to describe
    derived_anchor = anchor_identity_from_bytes(payloads["anchor_scene"], rig)
    asserted_anchor = registry["roles"]["anchor_scene"]["identity"]
    if not isinstance(asserted_anchor, dict) or any(
            asserted_anchor.get(key) != value for key, value in derived_anchor.items()):
        raise ValueError("INPUT_IDENTITY_MISMATCH")

    # the two resource stops come from the design's section 5.1 document when the registry's own root carries it,
    # and an older registry whose root does not keeps the call it always had
    development = Path(registry["source_root"]) / DEVELOPMENT_RUNTIME_FILE
    derived_resource = resource_policy_identity(
        payloads["runtime_config"], payloads["collection_config"],
        **({"development_runtime": development} if development.is_file() else {}))
    if (registry["roles"]["resource_thresholds"]["selected"]["sha256"]
            != derived_resource["runtime_config_sha256"]):
        # the resource role must own the verified runtime config, not an unrelated file
        raise ValueError("INPUT_IDENTITY_MISMATCH")
    asserted_resource = registry["roles"]["resource_thresholds"]["identity"]
    if not isinstance(asserted_resource, dict) or any(
            asserted_resource.get(key) != value for key, value in derived_resource.items()):
        raise ValueError("INPUT_IDENTITY_MISMATCH")

    try:
        verify_proposal_in_own_mode(documents["contact_proposal"])
    except ValueError as error:
        raise ValueError("INPUT_NOT_APPROVED") from error
    identity = registry["roles"]["scene_model"]["identity"]
    if not isinstance(identity, dict) or set(identity) != {"model_sha256", "scene_sha256",
                                                           "mujoco_version"}:
        raise ValueError("INPUT_IDENTITY_MISMATCH")
    payload = documents["contact_proposal"]["payload"]
    if (payload["model_sha256"] != identity["model_sha256"]
            or payload["scene_sha256"] != identity["scene_sha256"]
            or payload["mujoco_version"] != identity["mujoco_version"]):
        # the policy was activated for a different scene or model; it does not apply here
        raise ValueError("INPUT_IDENTITY_MISMATCH")

    verify_contact_activation(payload, documents["contact_activation"], identity, mode=mode)
    if documents["contact_activation"]["evidence_root"] != registry["evidence_root"]:
        raise ValueError("INPUT_ACTIVATION_STALE")
    for role in INPUT_ROLES:
        # the amendment's split: a historical calibration report still has to pass the non-Head safety gate, while
        # the values the user authorized this round carry their own provenance and are not a calibration report - the
        # five process-quality fields stop being a precondition here without removing any real safety check
        if registry["roles"][role]["selected"]["approval"] == "nonhead_calibration":
            require_nonhead_gate(documents[role])
    return payloads


def freeze_inputs(candidates_path: Path, output: Path, *, mode: str | None = None,
                  runtime_policy: Path | None = None,
                  execution_inputs: bool = False, teacher_endpoint: Path | None = None,
                  teacher_execution_policy: Path | None = None, episode_recorder_policy: Path | None = None,
                  scene_manifest: Path | None = None, rig_profile: Path | bytes | None = None) -> Path:
    """Copy the uniquely verified candidates into a new directory and bind their bytes.

    The output directory must not exist: a freeze is a new immutable input set, never a merge into
    a previous one.

    `scene_manifest` (formal mode only) binds a campaign's scene list: its bytes are copied to `scene_manifest/scenes.json`
    and `{path, sha256, bytes, scene_count}` enters the inputs hash chain, so a collection scope may name any row of it. A
    call without it writes the same manifest and digest it always did.

    The three keyword-only arguments are the amendment's additions and are optional, so every call that predates
    them keeps its exact behaviour and no caller silently acquires the new policy. When given, the endpoint policy
    and the development runtime are parsed through their own closed loaders and their content enters the inputs hash
    chain - the design requires the policy, the two target poses and the recipe/transform hashes to be bound here,
    because every later gate reads the frozen document rather than the live file.
    """

    registry = read_candidate_registry(candidates_path)
    target = Path(output)
    if target.exists():
        raise ValueError("INPUT_OUTPUT_EXISTS")
    scene_payload = None
    if scene_manifest is not None:
        if mode != "formal":
            raise ValueError("INPUT_SCENE_MANIFEST_REQUIRES_FORMAL")
        source = Path(scene_manifest)
        try:
            if source.is_symlink() or not source.is_file():
                raise ValueError("INPUT_SCENE_MANIFEST_INVALID")
            scene_payload = source.read_bytes()
        except OSError as error:
            raise ValueError("INPUT_SCENE_MANIFEST_INVALID") from error
        scene_count = len(_scene_rows(scene_payload, "INPUT_SCENE_MANIFEST_INVALID"))
    rig_payload = None
    if rig_profile is not None:
        if isinstance(rig_profile, bytes):
            rig_payload = rig_profile
        else:
            path = Path(rig_profile)
            if path.is_symlink() or not path.is_file():
                raise ValueError("INPUTS_RIG_PROFILE_INVALID")
            rig_payload = path.read_bytes()
    # the anchor's neck start is part of the identity only for a rig that has a neck, so the rig is known before the roles are verified
    payloads = _verify_roles(registry, mode=mode,
                             rig=rig_profile_binding(rig_payload)["values"]["rig"] if rig_payload is not None else None)
    roles = {}
    extra = {}
    if mode is not None:
        if mode not in ("formal", "preselected_target_diagnostic"):
            raise ValueError("INPUT_MODE_INVALID")
        extra["mode"] = mode
    if scene_payload is not None:
        extra["scene_manifest"] = {"path": SCENE_MANIFEST_PATH, "sha256": hashlib.sha256(scene_payload).hexdigest(),
                                   "bytes": len(scene_payload), "scene_count": scene_count}
    policy_payloads = {}
    rig = None
    for name, source in (("teacher_endpoint", teacher_endpoint),
                         (EXECUTION_POLICY_BINDING, teacher_execution_policy),
                         ("episode_recorder", episode_recorder_policy)):
        if source is None:
            continue
        path = Path(source)
        if path.is_symlink() or not path.is_file():
            raise ValueError("INPUTS_POLICY_BINDING_INVALID: " + name)
        policy_payloads[name] = path.read_bytes()
        extra[name] = policy_binding(name, policy_payloads[name])
    if rig_payload is not None:
        # the rig of the collection: bound like a policy, and so part of the inputs hash chain every case scope names
        extra[RIG_PROFILE_BINDING] = rig_profile_binding(rig_payload)
        policy_payloads[RIG_PROFILE_BINDING] = rig_payload
        rig = extra[RIG_PROFILE_BINDING]["values"]["rig"]
    if runtime_policy is not None:
        from .endpoint_pose_acceptance import load_development_runtime
        document = load_development_runtime(Path(runtime_policy))
        extra["runtime_policy"] = {
            "sha256": hashlib.sha256(_canonical(document)).hexdigest(),
            "path_policy": document["path_policy"], "rgb_sync": document["rgb_sync"],
            "safety_release": document["safety_release"], "hard_stops": document["hard_stops"],
        }
    try:
        target.mkdir(parents=True)
        for name, payload in policy_payloads.items():
            destination = target / extra[name]["path"]
            destination.parent.mkdir(exist_ok=True)
            with open(destination, "xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        if scene_payload is not None:
            destination = target / SCENE_MANIFEST_PATH
            destination.parent.mkdir(exist_ok=True)
            with open(destination, "xb") as stream:
                stream.write(scene_payload)
                stream.flush()
                os.fsync(stream.fileno())
        for role in INPUT_ROLES:
            entry = registry["roles"][role]["selected"]
            relative = Path(role) / Path(entry["path"]).name
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            # the bytes that were verified, never a second read of the candidate
            payload = payloads[role]
            with open(destination, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            roles[role] = {"path": str(relative),
                           "sha256": hashlib.sha256(payload).hexdigest(),
                           "bytes": len(payload), "approval": entry["approval"],
                           "identity": registry["roles"][role]["identity"]}
        if execution_inputs:
            from .execution_snapshot import freeze_execution_snapshot
            # a rig other than the default names its own scene; the default rig's freeze is the call it always was
            snapshot = freeze_execution_snapshot(Path(registry["source_root"]), target / "execution",
                                                 *(() if rig in (None, "head-wrist") else (rig,)))
            extra["execution_snapshot"] = execution_snapshot_binding(snapshot, target / "execution")
        manifest = {"kind": MANIFEST_KIND, "schema_version": MANIFEST_SCHEMA_VERSION,
                    "source_root": registry["source_root"],
                    "source_commit": registry["source_commit"],
                    "config_sha256": registry["config_sha256"],
                    "evidence_root": registry["evidence_root"], "roles": roles, **extra,
                    "inputs_sha256": hashlib.sha256(_canonical({**roles, **extra})).hexdigest()}
        manifest_path = target / "inputs-manifest.json"
        with open(manifest_path, "wb") as stream:
            stream.write(_canonical(manifest))
            stream.flush()
            os.fsync(stream.fileno())
        descriptor = os.open(target, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise ValueError("INPUT_FREEZE_UNWRITABLE") from error
    verify_frozen_inputs(manifest_path)
    return manifest_path


# ---------------------------------------------------------------------------
# read-only inspection of the candidates that exist today
# ---------------------------------------------------------------------------

# the frozen default anchor of the milestone: scene id, seed and the two anchor literals
FROZEN_SCENE_ID = "default"
FROZEN_SEED = 0
ANCHOR_FILE = "src/so101_demo_py/config/act/pick-place-live-anchors.yaml"
ANCHOR_APPROVAL_FILE = "src/so101_demo_py/config/act/pick-place-calibration-search-candidate.json"
SCENE_FILE = "src/so101_demo_py/assets/mujoco/act/scene.xml"
COLLECTION_CONFIG_FILE = "src/so101_demo_py/config/act/parallel_collection.yaml"
RUNTIME_CONFIG_FILE = "src/so101_demo_py/config/mujoco/parallel_batch_act_offline.yaml"   # stage bounds long enough for offline processing
#: the design's section 5.1 document, which declares the two resource hard stops
DEVELOPMENT_RUNTIME_FILE = "src/so101_demo_py/config/act/endpoint_pose_development_runtime.yaml"
RESET_RECIPE_FILE = "src/so101_demo_py/src/backends/mujoco/reset.py"
REFERENCE_FILE = "src/so101_demo_py/src/act/expert.py"

# which measurements each value group needs; the report that carries them is the same artifact
ROLE_REQUIRED_CHECKS = {"path_policy": ("collision",), "placement_qc": ("release", "retreat"),
                        "rgb_skew": ("synchronization",)}
ROLE_REQUIRED_VALUES = {
    "path_policy": ("path_step_s", "path_clearance_m"),
    "placement_qc": ("grasp_occlusion_window_s", "support_distance_m", "release_stable_s",
                     "retreat_distance_m", "placement_stable_s"),
    "rgb_skew": ("max_age_s", "max_skew_s"),
}
_RESOURCE_KEYS = ("timeout_s", "cpu_busy_warn_fraction", "ram_minimum_bytes",
                  "ram_minimum_fraction", "gpu_minimum_bytes")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def profile_config_identity(source_root: Path, rig=None) -> str:
    """The ACT profile digest, computed from the source tree the same way the installed probe does.

    `so101_demo.act.calibration.installed_calibration_identity()` digests every file under the
    installed `assets/mujoco/act` and `config/mujoco/act` keyed by its package-relative path. This
    derives the same value from a named source root so the registry and the manifest can record which
    profile the frozen inputs were inspected against. That value is recorded provenance:
    nothing compares it with the tree that is running. Files that belong only to another camera rig (`rig_files.foreign_files`)
    are left out, as in the installed probe, so a rig's variants do not change another rig's identity.
    """

    from .rig_files import foreign_files

    package = Path(source_root) / "src/so101_demo_py"
    roots = (package / "assets/mujoco/act", package / "config/mujoco/act")
    if any(not root.is_dir() for root in roots):
        raise ValueError("NONHEAD_INPUT_BINDING_REQUIRED")
    excluded = foreign_files(rig)
    files = {str(path.relative_to(package)): _digest(path)
             for root in roots for path in sorted(root.rglob("*"))
             if path.is_file() and str(path.relative_to(package)) not in excluded}
    if not files:
        raise ValueError("NONHEAD_INPUT_BINDING_REQUIRED")
    return hashlib.sha256(_canonical(files)).hexdigest()



# the milestone's frozen initial state. It is a contract, not metadata a caller may assert: the
# derived identity below is recomputed from the verified anchor bytes and compared against whatever
# the registry claims, so hashing a consistent assertion cannot substitute for describing the bytes.
FROZEN_ANCHOR_SCENE_ID = "default"
FROZEN_ANCHOR_SEED = 0
FROZEN_ANCHOR_CUP_M = (0.02, -0.28, 0.165)
FROZEN_ANCHOR_NECK_RAD = 0.1
_RESOURCE_HARD_STOP_KEYS = ("rtf_min", "disk_free_min_bytes")


def _positive_number(value) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and value > 0)


def anchor_identity_from_bytes(payload: bytes, rig=None) -> dict:
    """Derive the frozen anchor identity from the verified bytes of the anchor file.

    `rig` (a profile, a name or None for the head+wrist default) decides whether the anchor has a neck start: a rig without a
    neck neither requires nor reads the file's `neck_start_rad`, and its identity has no such key.
    """

    from .rig_files import rig_name
    from .rig_profile import known_rig

    has_neck = known_rig(rig_name(rig)).has_neck

    import yaml

    try:
        document = yaml.safe_load(payload)
    except yaml.YAMLError as error:
        raise ValueError("NONHEAD_INPUT_BINDING_REQUIRED") from error
    anchors = document.get("anchors") if isinstance(document, dict) else None
    anchor = anchors.get(FROZEN_ANCHOR_SCENE_ID) if isinstance(anchors, dict) else None
    if not isinstance(anchor, dict):
        raise ValueError("NONHEAD_INPUT_BINDING_REQUIRED")
    cup, neck = anchor.get("cup_start_m"), anchor.get("neck_start_rad")
    if (not isinstance(cup, list) or len(cup) != 3
            or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in cup)
            or tuple(float(value) for value in cup) != FROZEN_ANCHOR_CUP_M):
        raise ValueError("NONHEAD_INPUT_BINDING_REQUIRED")
    identity = {"scene_id": FROZEN_ANCHOR_SCENE_ID, "seed": FROZEN_ANCHOR_SEED, "cup_start_m": list(FROZEN_ANCHOR_CUP_M)}
    if has_neck:
        if isinstance(neck, bool) or not isinstance(neck, (int, float)) or float(neck) != FROZEN_ANCHOR_NECK_RAD:
            raise ValueError("NONHEAD_INPUT_BINDING_REQUIRED")
        identity["neck_start_rad"] = FROZEN_ANCHOR_NECK_RAD
    identity["anchor_file_sha256"] = hashlib.sha256(payload).hexdigest()
    return identity


def resource_policy_identity(runtime_bytes: bytes, collection_bytes: bytes, *,
                             development_runtime: Path | None = None) -> dict:
    """Derive the resource policy from the verified runtime and collection config bytes.

    Every value the plan requires must be present and of the right shape: a positive finite start
    guard, positive finite RTF and disk stops, lossless recording at 10 Hz and watermarks that
    actually order themselves. A missing or malformed value is a blocker, never a default.
    """

    import yaml

    try:
        runtime = yaml.safe_load(runtime_bytes)
        collection = yaml.safe_load(collection_bytes)
    except yaml.YAMLError as error:
        raise ValueError("NONHEAD_INPUT_BINDING_REQUIRED") from error
    runtime = runtime if isinstance(runtime, dict) else {}
    collection = collection if isinstance(collection, dict) else {}
    guard = runtime.get("start_guard")
    guard = guard if isinstance(guard, dict) else {}
    hard = runtime.get("hard_stops")
    hard = hard if isinstance(hard, dict) else {}
    if not hard and development_runtime is not None:
        # the amendment's two stops live in the section 5.1 development runtime document, not in the batch runtime
        # whose own contract is closed; reading them there keeps this file's digest untouched
        try:
            amendment = yaml.safe_load(Path(development_runtime).read_text())
        except (OSError, yaml.YAMLError):
            amendment = None
        section = amendment.get("hard_stops") if isinstance(amendment, dict) else None
        hard = section if isinstance(section, dict) else {}
    recorder = collection.get("recorder")
    recorder = recorder if isinstance(recorder, dict) else {}

    guard_values = {key: guard.get(key) for key in _RESOURCE_KEYS}
    if not all(_positive_number(value) for value in guard_values.values()):
        raise ValueError("NONHEAD_INPUT_BINDING_REQUIRED")
    stops = {key: hard.get(key) for key in _RESOURCE_HARD_STOP_KEYS}
    if not all(_positive_number(value) for value in stops.values()):
        raise ValueError("NONHEAD_INPUT_BINDING_REQUIRED")
    capacity = recorder.get("queue_capacity_samples")
    high = recorder.get("queue_high_watermark_samples")
    recovery = recorder.get("queue_recovery_watermark_samples")
    hold = recorder.get("queue_high_watermark_hold_s")
    if (recorder.get("lossless") is not True or recorder.get("sample_rate_hz") != 10
            or any(type(value) is not int for value in (capacity, high, recovery))
            or not 0 < recovery < high <= capacity or not _positive_number(hold)):
        raise ValueError("NONHEAD_INPUT_BINDING_REQUIRED")
    return {"start_guard": guard_values, "rtf_hard_stop": stops["rtf_min"],
            "disk_hard_stop": stops["disk_free_min_bytes"],
            "queue_hard_stop": {"queue_capacity_samples": capacity,
                                "queue_high_watermark_samples": high,
                                "queue_recovery_watermark_samples": recovery,
                                "queue_high_watermark_hold_s": hold, "lossless": True,
                                "sample_rate_hz": 10, "source": "collection_config.recorder"},
            "runtime_config_sha256": hashlib.sha256(runtime_bytes).hexdigest(),
            "collection_config_sha256": hashlib.sha256(collection_bytes).hexdigest()}


# The read-only candidate inspection moved to `diagnostic_episode_inspection` (this module is over the size limit
# otherwise). It imports this module, so the names resolve on first use instead of at import time.
_INSPECTION_NAMES = frozenset({
    "inspect_inputs", "_activated_identity", "_compiled_model_identity", "_git_commit", "_inspect_anchor_scene",
    "_inspect_calibration_role", "_inspect_contact", "_inspect_motion_config", "_inspect_reference",
    "_inspect_reset_recipe", "_inspect_resource_thresholds", "_inspect_scene_model", "_inspect_source_role",
    "_ledger_head", "_ledger_referenced_json", "_role", "_selected", "_source_file", "_unapproved_source_file",
    "_verify_activation_for", "_verify_disabled",
})


def __getattr__(name: str):
    if name in _INSPECTION_NAMES:
        from . import diagnostic_episode_inspection

        return getattr(diagnostic_episode_inspection, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
