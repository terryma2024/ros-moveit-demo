"""Bind the Task 8 measurement contract to frozen identities before any measurement runs.

The repository template is a closed threshold document with no identity. Binding copies it into
the evidence root, records the raw hash of every threshold source, and stamps the contract hash;
the unbound template is never accepted as a contract for a run.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path

SCHEMA_VERSION = 1
KIND = "task8_calibration_measurement_contract"
TEMPLATE_KIND = "task8_calibration_measurement_contract_template"
BATCH_KIND = "task8_calibration_batch"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_IDENTITIES = ("source_provenance_sha256", "runtime_config_sha256", "anchors_sha256",
               "contact_policy_fingerprint", "act_profile_sha256")
_TEMPLATE_KEYS = ("schema_version", "kind", "anchors", "measurements", "camera_measurements",
                  "thresholds", "verdicts")
_BOUND_KEYS = ("schema_version", "kind", "identities", "source_hashes", "anchors",
               "measurements", "camera_measurements", "thresholds", "verdicts",
               "contract_sha256")
# protocol v2 (approved measurement-protocol amendment): the contract carries the ten-member identity, the
# bound-file list and the per-measurement metadata, and every field is recomputed from raw evidence
SCHEMA_VERSION_V2 = 2
IDENTITIES_V2 = ("source_commit", "config_sha256", "source_provenance_sha256", "runtime_config_sha256",
                 "anchors_sha256", "contact_policy_fingerprint", "act_profile_sha256",
                 "measurement_contract_sha256", "phase_camera_matrix_sha256", "driver_source_sha256")
_V2_TEMPLATE_KEYS = ("schema_version", "kind", "status", "source_design", "source_plan", "bound_files",
                     "measurements", "support", "notes")
_V2_BOUND_KEYS = ("schema_version", "kind", "identities", "source_hashes", "bound_files", "measurements",
                  "support", "contract_sha256")
_SOURCE_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


def require_v2_identity(identities: object) -> dict:
    """The ten-member identity: `source_commit` is a git SHA, every other member a 64-hex digest."""

    if type(identities) is not dict or tuple(sorted(identities)) != tuple(sorted(IDENTITIES_V2)):
        raise ValueError("MEASUREMENT_CONTRACT_IDENTITY_INVALID")
    if _SOURCE_COMMIT.fullmatch(str(identities["source_commit"])) is None:
        raise ValueError("MEASUREMENT_CONTRACT_IDENTITY_INVALID")
    for name in IDENTITIES_V2:
        if name == "source_commit":
            continue
        if _SHA.fullmatch(str(identities[name])) is None:
            raise ValueError("MEASUREMENT_CONTRACT_IDENTITY_INVALID")
    return dict(identities)


def _digest(path: Path) -> str:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _regular(path: Path, code: str) -> None:
    try:
        info = path.stat(follow_symlinks=False)
    except OSError as error:
        raise ValueError(code) from error
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(code)


def _canonical(document: dict) -> bytes:
    return (json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n").encode("utf-8")


#: The BOUND DOCUMENT's own self-digest, over the document minus this key. It is an INTEGRITY value: a member of the
#: ten-field identity can never equal it, because the identities live inside the document the digest is computed over,
#: so requiring equality would demand a hash fixed point that does not exist (CP-1673).
BOUND_DOCUMENT_DIGEST_KEY = "contract_sha256"
#: The ten-field identity's own name for the contract this run was ADMITTED under. The bound document carries it
#: verbatim in its `identities` field - which `load_measurement_contract` already requires to equal the caller's
#: mapping - so "the batch was measured under this contract" means "the batch's identity equals the contract's
#: admitted identities", and that is the single rule every layer states (rereview4 P1-2).
IDENTITY_CONTRACT_MEMBER = "measurement_contract_sha256"


def bound_document_digest(document: dict) -> str:
    """The bound document's self-digest - integrity, never an identity."""

    return document[BOUND_DOCUMENT_DIGEST_KEY]


def admitted_identity(document: dict) -> dict:
    """The ten-field identity the bound contract admits; the only contract identity a seal may be compared against."""

    return dict(document["identities"])


def _contract_sha256(document: dict) -> str:
    payload = {key: value for key, value in document.items() if key != "contract_sha256"}
    return hashlib.sha256(_canonical(payload)).hexdigest()


def bind_measurement_contract(template_path: Path, identities: dict, output: Path) -> Path:
    """Publish a bound contract for this run; an existing target is never overwritten."""

    template_path, output = Path(template_path), Path(output)
    _regular(template_path, "MEASUREMENT_CONTRACT_TEMPLATE_MISSING")
    try:
        template = json.loads(template_path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("MEASUREMENT_CONTRACT_TEMPLATE_INVALID") from error
    if type(template) is not dict:
        raise ValueError("MEASUREMENT_CONTRACT_TEMPLATE_INVALID")
    if template.get("schema_version") == SCHEMA_VERSION_V2:
        if (tuple(sorted(template)) != tuple(sorted(_V2_TEMPLATE_KEYS))
                or template.get("kind") != TEMPLATE_KIND):
            raise ValueError("MEASUREMENT_CONTRACT_TEMPLATE_INVALID")
        document = {
            "schema_version": SCHEMA_VERSION_V2, "kind": KIND,
            "identities": require_v2_identity(identities),
            "source_hashes": {"template": _digest(template_path)},
            "bound_files": dict(template["bound_files"]),
            "measurements": dict(template["measurements"]), "support": dict(template["support"]),
        }
    else:
        if (type(identities) is not dict or tuple(sorted(identities)) != tuple(sorted(_IDENTITIES))
                or any(_SHA.fullmatch(str(value)) is None for value in identities.values())):
            raise ValueError("MEASUREMENT_CONTRACT_IDENTITY_INVALID")
        if (tuple(sorted(template)) != tuple(sorted(_TEMPLATE_KEYS))
                or template["schema_version"] != SCHEMA_VERSION
                or template["kind"] != TEMPLATE_KIND):
            raise ValueError("MEASUREMENT_CONTRACT_TEMPLATE_INVALID")
        document = {
            "schema_version": SCHEMA_VERSION, "kind": KIND, "identities": dict(identities),
            "source_hashes": {"template": _digest(template_path)},
            "anchors": list(template["anchors"]), "measurements": dict(template["measurements"]),
            "camera_measurements": dict(template["camera_measurements"]),
            "thresholds": dict(template["thresholds"]), "verdicts": list(template["verdicts"]),
        }
    document["contract_sha256"] = _contract_sha256(document)
    payload = _canonical(document)
    partial = Path(str(output) + ".partial")
    descriptor = os.open(str(partial), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.link(str(partial), str(output))
    except FileExistsError as error:
        os.unlink(str(partial))
        raise ValueError("MEASUREMENT_CONTRACT_OUTPUT_EXISTS") from error
    os.unlink(str(partial))
    return output


def load_measurement_contract(path: Path, *, expected_hashes: dict) -> dict:
    """Return the bound contract, refusing the unbound template or a foreign identity."""

    path = Path(path)
    _regular(path, "MEASUREMENT_CONTRACT_MISSING")
    try:
        document = json.loads(path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("MEASUREMENT_CONTRACT_INVALID") from error
    if type(document) is not dict:
        raise ValueError("MEASUREMENT_CONTRACT_INVALID")
    keys = tuple(sorted(document))
    version = document.get("schema_version")
    if keys == tuple(sorted(_V2_BOUND_KEYS)) and version == SCHEMA_VERSION_V2:
        if document.get("kind") != KIND:
            raise ValueError("MEASUREMENT_CONTRACT_INVALID")
    elif keys == tuple(sorted(_BOUND_KEYS)) and version == SCHEMA_VERSION:
        if document.get("kind") != KIND:
            raise ValueError("MEASUREMENT_CONTRACT_INVALID")
    else:
        if document.get("kind") == TEMPLATE_KIND:
            raise ValueError("MEASUREMENT_CONTRACT_UNBOUND")
        raise ValueError("MEASUREMENT_CONTRACT_INVALID")
    if document["contract_sha256"] != _contract_sha256(document):
        raise ValueError("MEASUREMENT_CONTRACT_HASH_INVALID")
    if (type(expected_hashes) is not dict
            or document["identities"] != dict(expected_hashes)):
        raise ValueError("MEASUREMENT_CONTRACT_IDENTITY_MISMATCH")
    if type(document["source_hashes"]) is not dict or not document["source_hashes"]:
        raise ValueError("MEASUREMENT_CONTRACT_INVALID")
    return document


def close_measurement_batch(root: Path, identity: dict, *, status: str = "CLOSED", cleanup=None,
                            contamination=None, error_code=None) -> Path:
    """Seal one raw measurement batch with every raw file hash; never reopened."""

    root = Path(root)
    if type(identity) is not dict or not identity:
        raise ValueError("MEASUREMENT_BATCH_IDENTITY_INVALID")
    # the batch's identity is the contract's ten-member identity, not whatever mapping the caller happens to hold:
    # the same schema that admitted the measurement is the one that seals it
    try:
        require_v2_identity(identity)
    except ValueError as error:
        raise ValueError("MEASUREMENT_BATCH_IDENTITY_INVALID") from error
    if status not in ("CLOSED", "INVALID"):
        raise ValueError("MEASUREMENT_BATCH_STATUS_INVALID")
    # these two members are the ones a sealed batch must be able to name; the contract's own name for itself is
    # measurement_contract_sha256, while contract_sha256 belongs to the bound document - using the wrong one here
    # was the naming fissure between the identity schema and the batch seal
    for name in ("source_provenance_sha256", "measurement_contract_sha256"):
        if _SHA.fullmatch(str(identity.get(name))) is None:
            raise ValueError("MEASUREMENT_BATCH_IDENTITY_INVALID")
    root.mkdir(parents=True, exist_ok=True)
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "batch.json":
            files[path.relative_to(root).as_posix()] = _digest(path)
    document = {"schema_version": SCHEMA_VERSION, "kind": BATCH_KIND, "status": status,
                "identity": dict(identity), "files": files,
                "anchors": ["default", "left", "forward"]}
    # the same optional fields the production seal carries: a CLOSED batch must be able to name its cleanup proof,
    # and a refused one its error code - so this helper produces documents the validator accepts rather than ones it
    # must refuse (CP-1619)
    if cleanup is not None:
        document["cleanup"] = cleanup
    if contamination is not None:
        document["contamination"] = contamination
    if error_code is not None:
        document["error_code"] = error_code
    # the batch document seals itself too, so its identity and status cannot be edited later
    document["batch_sha256"] = hashlib.sha256(
        _canonical({key: value for key, value in document.items()
                    if key != "batch_sha256"})).hexdigest()
    target = root / "batch.json"
    descriptor = os.open(str(target) + ".partial", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(_canonical(document))
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.link(str(target) + ".partial", target)
    except FileExistsError as error:
        os.unlink(str(target) + ".partial")
        raise ValueError("MEASUREMENT_BATCH_ALREADY_CLOSED") from error
    os.unlink(str(target) + ".partial")
    return target
