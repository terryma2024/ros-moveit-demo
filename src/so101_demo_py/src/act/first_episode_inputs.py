"""Frozen non-Head safety inputs for the first diagnostic episode.

The diagnostic mode removes the Head Search prerequisite only. Every non-Head safety value the plan
names still has to exist and have been approved by something other than a candidate file that merely
contains numbers: measured policy values, the activated contact policy and the frozen
scene/anchor/configuration files.

`inspect_inputs` records what exists (read-only, no defaulting). `freeze_inputs` refuses anything
that is missing, ambiguous, unapproved or internally inconsistent, then copies the survivors once
into an immutable directory and returns the manifest that binds their bytes. A missing value is a
blocker code, never a default.

Per the owner amendment recorded in the ledger as CP-1928, an artifact's recorded source/config
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

CANDIDATES_KIND = "ACT_FIRST_EPISODE_INPUT_CANDIDATES"
MANIFEST_KIND = "ACT_FIRST_EPISODE_INPUTS"
SCHEMA_VERSION = 1

# every role the milestone must freeze; a missing one is an exact blocker, not a default
INPUT_ROLES = (
    "anchor_scene", "scene_model", "collection_config", "runtime_config", "path_policy",
    "placement_qc", "rgb_skew", "resource_thresholds", "contact_proposal", "contact_activation",
    "reset_recipe", "reference_interpolation",
)

# the checks the diagnostic mode still requires, and the ones it may leave unmeasured
NONHEAD_CHECKS = frozenset({"collision", "synchronization", "execution", "release", "retreat"})

_CANDIDATE_FIELDS = frozenset({"path", "sha256", "approved", "approval"})
_ROLE_FIELDS = frozenset({"status", "candidates", "selected", "identity", "blocker"})
_REGISTRY_FIELDS = frozenset({"kind", "schema_version", "source_root", "source_commit",
                              "config_sha256", "evidence_root", "roles"})
_MANIFEST_FIELDS = frozenset({"kind", "schema_version", "source_root", "source_commit",
                              "config_sha256", "evidence_root", "roles", "inputs_sha256"})
_MANIFEST_ROLE_FIELDS = frozenset({"path", "sha256", "bytes", "approval", "identity"})
_APPROVALS = frozenset({"source_controlled", "disabled_proposal", "user_activation",
                        "nonhead_calibration", "user_empirical_default"})
_ROLE_APPROVAL = {"contact_proposal": "disabled_proposal",
                  "contact_activation": "user_activation",
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


# ---------------------------------------------------------------------------
# the non-Head safety gate
# ---------------------------------------------------------------------------

def require_nonhead_gate(report) -> dict:
    """Require every non-Head safety measurement, without requiring the Head Search ones.

    A report that claims PASS for any check must carry that check's measurements, so a PASS cannot
    outrun its evidence. The two Head checks (`fov`, `search`) are not required to be anything:
    that is the whole substitution this milestone makes. The report's own recorded identity is
    checked for shape only; per the owner amendment recorded in CP-1928 it is not compared with the
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
    if report["status"] not in ("CALIBRATION_REQUIRED", "TASK8_READY", "QUALIFIED"):
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
    if not isinstance(document, dict) or set(document) != _MANIFEST_FIELDS:
        raise ValueError("INPUTS_MANIFEST_INVALID")
    if document["kind"] != MANIFEST_KIND or document["schema_version"] != SCHEMA_VERSION:
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
    if hashlib.sha256(_canonical(roles)).hexdigest() != document["inputs_sha256"]:
        raise ValueError("INPUTS_MANIFEST_INVALID")
    return document


# only these roles carry a JSON contract this module must read; the rest are frozen as bytes
_JSON_ROLES = frozenset({"contact_proposal", "contact_activation", "path_policy", "placement_qc",
                         "rgb_skew"})


def verify_frozen_inputs(manifest_path: Path) -> dict:
    """Read the manifest and verify every frozen file it names, not only its metadata.

    A self-consistent manifest can describe files that never existed or that changed after the
    freeze, so admission re-reads each role beneath the manifest's own directory and refuses
    anything missing, replaced, resized, symlinked or outside that directory.
    """

    manifest_path = Path(manifest_path)
    document = read_inputs_manifest(manifest_path)
    root = manifest_path.parent.resolve()
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


def _verify_roles(registry: dict) -> dict:
    """Resolve one approved candidate per role, run the semantic cross-checks, return the bytes.

    The verified bytes are handed back so a freeze copies exactly what was approved. Reading the
    candidate a second time would let a file that changed after verification be frozen instead.

    Per the owner amendment recorded in CP-1928 the registry's `source_commit` and `config_sha256`
    are recorded provenance, not a claim about the tree that happens to be running now.
    """

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
        if entry["approval"] == "source_controlled":
            if not Path(entry["path"]).is_relative_to(Path(registry["source_root"])):
                raise ValueError("INPUT_NOT_APPROVED")
    payloads = {role: _read_verified(registry["roles"][role]["selected"]) for role in INPUT_ROLES}
    documents = {role: _parse_json(payloads[role]) for role in _JSON_ROLES}


    # the identity of the anchor and of the resource policy is derived from the verified bytes and
    # compared with what the registry asserts, so a consistent assertion cannot stand in for the
    # bytes it claims to describe
    derived_anchor = anchor_identity_from_bytes(payloads["anchor_scene"])
    asserted_anchor = registry["roles"]["anchor_scene"]["identity"]
    if not isinstance(asserted_anchor, dict) or any(
            asserted_anchor.get(key) != value for key, value in derived_anchor.items()):
        raise ValueError("INPUT_IDENTITY_MISMATCH")

    derived_resource = resource_policy_identity(payloads["runtime_config"],
                                                payloads["collection_config"])
    if (registry["roles"]["resource_thresholds"]["selected"]["sha256"]
            != derived_resource["runtime_config_sha256"]):
        # the resource role must own the verified runtime config, not an unrelated file
        raise ValueError("INPUT_IDENTITY_MISMATCH")
    asserted_resource = registry["roles"]["resource_thresholds"]["identity"]
    if not isinstance(asserted_resource, dict) or any(
            asserted_resource.get(key) != value for key, value in derived_resource.items()):
        raise ValueError("INPUT_IDENTITY_MISMATCH")

    from .contact_calibration import verify_disabled_proposal

    try:
        verify_disabled_proposal(documents["contact_proposal"])
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

    from .contact_policy import verify_activation

    try:
        verify_activation(payload, documents["contact_activation"],
                          expected_model_sha256=identity["model_sha256"],
                          expected_scene_sha256=identity["scene_sha256"],
                          expected_mujoco_version=identity["mujoco_version"])
    except ValueError as error:
        raise ValueError("INPUT_ACTIVATION_STALE") from error
    if documents["contact_activation"]["evidence_root"] != registry["evidence_root"]:
        raise ValueError("INPUT_ACTIVATION_STALE")
    for role in INPUT_ROLES:
        if registry["roles"][role]["selected"]["approval"] in ("nonhead_calibration",
                                                              "user_empirical_default"):
            require_nonhead_gate(documents[role])
    return payloads


def freeze_inputs(candidates_path: Path, output: Path, *, mode: str | None = None,
                  endpoint_policy: Path | None = None, runtime_policy: Path | None = None) -> Path:
    """Copy the uniquely verified candidates into a new directory and bind their bytes.

    The output directory must not exist: a freeze is a new immutable input set, never a merge into
    a previous one.

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
    payloads = _verify_roles(registry)
    roles = {}
    extra = {}
    if mode is not None:
        if mode not in ("formal", "preselected_target_diagnostic"):
            raise ValueError("INPUT_MODE_INVALID")
        extra["mode"] = mode
    if endpoint_policy is not None:
        from .endpoint_pose_acceptance import load_endpoint_policy
        document = load_endpoint_policy(Path(endpoint_policy))
        extra["endpoint_policy"] = {
            "rule_version": document["rule_version"],
            "thresholds": document["thresholds"],
            "sha256": hashlib.sha256(_canonical(document)).hexdigest(),
        }
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
        manifest = {"kind": MANIFEST_KIND, "schema_version": SCHEMA_VERSION,
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
    read_inputs_manifest(manifest_path)
    return manifest_path


# ---------------------------------------------------------------------------
# read-only inspection of the candidates that exist today
# ---------------------------------------------------------------------------

# the frozen default anchor of the milestone: scene id, seed and the two anchor literals
FROZEN_SCENE_ID = "default"
FROZEN_SEED = 0
ANCHOR_FILE = "src/so101_demo_py/config/act/task8-live-anchors.yaml"
ANCHOR_APPROVAL_FILE = "src/so101_demo_py/config/act/task8-calibration-search-candidate-v1.json"
SCENE_FILE = "src/so101_demo_py/assets/mujoco/act/scene.xml"
COLLECTION_CONFIG_FILE = "src/so101_demo_py/config/act/parallel_collection_v3.yaml"
RUNTIME_CONFIG_FILE = "src/so101_demo_py/config/mujoco/parallel_batch_v3.yaml"
RESET_RECIPE_FILE = "src/so101_demo_py/src/adapters/act/pick_place_reset.py"
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


def profile_config_identity(source_root: Path) -> str:
    """The ACT profile digest, computed from the source tree the same way the installed probe does.

    `so101_demo.act.calibration.installed_calibration_identity()` digests every file under the
    installed `assets/mujoco/act` and `config/mujoco/act` keyed by its package-relative path. This
    derives the same value from a named source root so the registry and the manifest can record which
    profile the frozen inputs were inspected against. Per CP-1928 that value is recorded provenance:
    nothing compares it with the tree that is running.
    """

    package = Path(source_root) / "src/so101_demo_py"
    roots = (package / "assets/mujoco/act", package / "config/mujoco/act")
    if any(not root.is_dir() for root in roots):
        raise ValueError("NONHEAD_INPUT_BINDING_REQUIRED")
    files = {str(path.relative_to(package)): _digest(path)
             for root in roots for path in sorted(root.rglob("*")) if path.is_file()}
    if not files:
        raise ValueError("NONHEAD_INPUT_BINDING_REQUIRED")
    return hashlib.sha256(_canonical(files)).hexdigest()


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


def _anchor_identity(root: Path) -> dict:
    import yaml

    document = yaml.safe_load((Path(root) / ANCHOR_FILE).read_text())
    anchors = document.get("anchors") if isinstance(document, dict) else None
    anchor = anchors.get(FROZEN_SCENE_ID) if isinstance(anchors, dict) else None
    if not isinstance(anchor, dict) or set(anchor) != {"cup_start_m", "neck_start_rad"}:
        raise ValueError("NONHEAD_INPUT_BINDING_REQUIRED")
    cup = anchor["cup_start_m"]
    if (not isinstance(cup, list) or len(cup) != 3
            or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in cup)):
        raise ValueError("NONHEAD_INPUT_BINDING_REQUIRED")
    neck = anchor["neck_start_rad"]
    if isinstance(neck, bool) or not isinstance(neck, (int, float)):
        raise ValueError("NONHEAD_INPUT_BINDING_REQUIRED")
    return {"scene_id": FROZEN_SCENE_ID, "seed": FROZEN_SEED,
            "cup_start_m": [float(value) for value in cup], "neck_start_rad": float(neck),
            "anchor_file_sha256": _digest(Path(root) / ANCHOR_FILE),
            "measurement_experiment": document.get("measurement_experiment")}


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


def anchor_identity_from_bytes(payload: bytes) -> dict:
    """Derive the frozen anchor identity from the verified bytes of the anchor file."""

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
            or tuple(float(value) for value in cup) != FROZEN_ANCHOR_CUP_M
            or isinstance(neck, bool) or not isinstance(neck, (int, float))
            or float(neck) != FROZEN_ANCHOR_NECK_RAD):
        raise ValueError("NONHEAD_INPUT_BINDING_REQUIRED")
    return {"scene_id": FROZEN_ANCHOR_SCENE_ID, "seed": FROZEN_ANCHOR_SEED,
            "cup_start_m": list(FROZEN_ANCHOR_CUP_M), "neck_start_rad": FROZEN_ANCHOR_NECK_RAD,
            "anchor_file_sha256": hashlib.sha256(payload).hexdigest(),
            "measurement_experiment": document.get("measurement_experiment")}


def resource_policy_identity(runtime_bytes: bytes, collection_bytes: bytes) -> dict:
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


def _inspect_anchor_scene(root: Path) -> dict:
    path = Path(root) / ANCHOR_FILE
    if not path.is_file() or path.is_symlink():
        return _role("MISSING", "NONHEAD_INPUT_BINDING_REQUIRED", "anchor file absent", None, [])
    try:
        identity = anchor_identity_from_bytes(path.read_bytes())
    except ValueError:
        return _role("MISSING", "NONHEAD_INPUT_BINDING_REQUIRED",
                     "the anchor file does not carry the milestone's frozen default anchor",
                     None, [])
    identity = dict(identity, measurement_experiment=_anchor_identity(root)["measurement_experiment"])
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


def _compiled_model_identity(root: Path) -> dict:
    """The same digest the physics checker uses: the compiled model bytes, not the XML text."""

    import mujoco
    import numpy as np

    scene = Path(root) / SCENE_FILE
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


def _inspect_scene_model(root: Path, activated: dict | None) -> dict:
    identity = _compiled_model_identity(root)
    document = _source_file(root, SCENE_FILE, "scene_model", "source_controlled", identity)
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
        identity = resource_policy_identity(runtime.read_bytes(), collection.read_bytes())
    except ValueError as error:
        return _role("MISSING", "NONHEAD_INPUT_BINDING_REQUIRED",
                     f"no approved resource stop policy: {error}", None, candidates)
    entry = {"path": str(runtime), "sha256": identity["runtime_config_sha256"], "approved": True,
             "approval": "source_controlled"}
    return _selected(_role("READY", None, None, identity, [entry]))


def _inspect_source_role(root: Path, relative: str, role: str, identity=None) -> dict:
    return _selected(_source_file(root, relative, role, "source_controlled", identity))


def _inspect_reset_recipe(root: Path) -> dict:
    import xml.etree.ElementTree as ElementTree

    identity = {"keyframe": "task_start", "keyframe_present": False, "cup_body": "plastic_cup"}
    scene = Path(root) / SCENE_FILE
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
    from .contact_calibration import verify_disabled_proposal

    try:
        verify_disabled_proposal(json.loads(path.read_bytes()))
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
        if not isinstance(document, dict) or "checks" not in document:
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


def inspect_inputs(source_root: Path, ledger: Path) -> dict:
    """Record, read-only, which approved candidate exists for every required non-Head input.

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

    identity = _compiled_model_identity(root)
    proposal_role, activation_role = _inspect_contact(evidence_root, referenced, identity)
    activated = identity if proposal_role["status"] == "READY" else None
    collection_role, runtime_role = _inspect_motion_config(root)
    roles = {
        "anchor_scene": _inspect_anchor_scene(root),
        "scene_model": _inspect_scene_model(root, activated),
        "collection_config": collection_role,
        "runtime_config": runtime_role,
        "resource_thresholds": _inspect_resource_thresholds(root),
        "contact_proposal": proposal_role,
        "contact_activation": activation_role,
        "reset_recipe": _inspect_reset_recipe(root),
        "reference_interpolation": _inspect_reference(root),
    }
    for role in ("path_policy", "placement_qc", "rgb_skew"):
        roles[role] = _inspect_calibration_role(role, referenced)
    document = {"kind": CANDIDATES_KIND, "schema_version": SCHEMA_VERSION, "source_root": str(root),
                "source_commit": commit, "config_sha256": profile_config_identity(root),
                "evidence_root": str(evidence_root), "roles": roles}
    _require_registry(document)
    return document
