"""Task 8 measurement protocol v2: the closed identity, the sealed batch, and closed JSON writes.

The approved protocol requires every measurement to be recomputed from raw evidence, so the batch is the only
source of truth: `validate_closed_batch` compares the recursive regular-file set against `batch.json.files`
*before* any raw file is opened, refuses traversal and links, and verifies every digest. The identity is a closed
ten-member set, so a consumer can never read a dangling extra field.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

BATCH_KIND = "task8_calibration_batch"
BATCH_STATUSES = ("CLOSED", "INVALID")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SOURCE_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
# the one canonical batch document: exactly what the production seal writes, so the writer and the validator cannot
# disagree about the shape of a sealed batch (they did: the seal wrote anchors and its own digest, the validator allowed
# five keys, and every sealed batch was refused as BATCH_INVALID)
# the measurement driver seals cleanup and contamination beside the seal's fields, so the one canonical shape has to
# include them - otherwise a driver-sealed batch can never validate (the same writer/validator disagreement as the
# anchors/digest pair, one layer along)
_BATCH_REQUIRED = frozenset({"schema_version", "kind", "status", "identity", "files", "anchors", "batch_sha256"})
# the driver adds its cleanup receipt and contamination verdict; nothing else may appear, so the shape stays exact
_BATCH_KEYS = _BATCH_REQUIRED | {"cleanup", "contamination"}
_ROOT = Path(__file__).resolve().parents[2]
_CONFIG = _ROOT / "config/act"


class MeasurementIdentity:
    """The closed identity every driver, batch seal and aggregator must share."""

    MEMBERS = (
        "source_commit", "config_sha256", "source_provenance_sha256", "runtime_config_sha256",
        "anchors_sha256", "contact_policy_fingerprint", "act_profile_sha256",
        "measurement_contract_sha256", "phase_camera_matrix_sha256", "driver_source_sha256",
    )

    @staticmethod
    def require(document: object) -> dict:
        if type(document) is not dict or tuple(sorted(document)) != tuple(sorted(MeasurementIdentity.MEMBERS)):
            raise ValueError("MEASUREMENT_IDENTITY_INVALID")
        if _SOURCE_COMMIT.fullmatch(str(document["source_commit"])) is None:
            raise ValueError("MEASUREMENT_IDENTITY_INVALID")
        for name in MeasurementIdentity.MEMBERS:
            if name == "source_commit":
                continue
            if _SHA256.fullmatch(str(document[name])) is None:
                raise ValueError("MEASUREMENT_IDENTITY_INVALID")
        return dict(document)


def _canonical(document: object) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_closed_json(path: Path, document: object) -> Path:
    """Write canonical JSON atomically; an existing target is never overwritten."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=".closed-")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_canonical(document))
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, str(path))
    except FileExistsError as error:
        raise ValueError("CLOSED_JSON_EXISTS") from error
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def _load(path: Path, code: str) -> dict:
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError(code)
    try:
        document = json.loads(path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(code) from error
    if type(document) is not dict:
        raise ValueError(code)
    return document


def load_contract_v2(path: Path | None = None) -> dict:
    document = _load(path or _CONFIG / "task8-calibration-measurement-contract-v2.json",
                     "MEASUREMENT_CONTRACT_V2_INVALID")
    for section in ("measurements", "support"):
        if type(document.get(section)) is not dict or not document[section]:
            raise ValueError("MEASUREMENT_CONTRACT_V2_INVALID")
        for name, entry in document[section].items():
            if type(entry) is not dict or type(entry.get("unit")) is not str:
                raise ValueError("MEASUREMENT_CONTRACT_V2_INVALID")
    return document


def load_phase_camera_matrix(path: Path | None = None) -> dict:
    document = _load(path or _CONFIG / "task8-phase-camera-matrix-v1.json",
                     "PHASE_CAMERA_MATRIX_INVALID")
    occluders = document.get("occluders")
    if occluders != EXPECTED_OCCLUDERS:
        raise ValueError("PHASE_CAMERA_OCCLUDERS_INVALID")
    return document


EXPECTED_OCCLUDERS = [
    "fixed_fingertip_pad_visual",
    "gripper_visual_00",
    "gripper_visual_01",
    "jaw_visual_00",
    "moving_fingertip_pad_visual",
]


class BatchIndex:
    """The sealed, indexed view of one raw batch."""

    def __init__(self, root: Path, identity: dict, files: dict) -> None:
        self.root = Path(root)
        self.identity = identity
        self.files = files

    def path(self, relative: str) -> Path:
        if relative not in self.files:
            raise ValueError("BATCH_INDEX_INVALID")
        return self.root / relative


def _regular_files(root: Path) -> dict:
    found = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("BATCH_PATH_INVALID")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("BATCH_PATH_INVALID")
        relative = path.relative_to(root).as_posix()
        if relative == "batch.json":
            continue
        if ".." in Path(relative).parts:
            raise ValueError("BATCH_PATH_INVALID")
        found[relative] = sha256_file(path)
    return found


def validate_closed_batch(root: Path, contract: dict | None = None) -> BatchIndex:
    """Closure first, then digests: nothing is opened that the index does not name."""

    root = Path(root)
    recorded = _load(root / "batch.json", "BATCH_INVALID")
    # P1-3 of the re-review: the driver records an ``error_code`` on an INVALID seal, so a batch that is not
    # CLOSED may carry it - otherwise an INVALID batch could never be validated, and the entry is required to
    # read one back. A CLOSED batch stays exactly as strict as before.
    allowed = _BATCH_KEYS | ({"error_code"} if recorded.get("status") != "CLOSED" else set())
    if not _BATCH_REQUIRED <= set(recorded) <= allowed or recorded.get("kind") != BATCH_KIND:
        raise ValueError("BATCH_INVALID")
    if recorded.get("status") not in BATCH_STATUSES:
        raise ValueError("BATCH_INVALID")
    identity = MeasurementIdentity.require(recorded.get("identity"))
    files = recorded.get("files")
    if type(files) is not dict:
        raise ValueError("BATCH_INVALID")
    if _SHA256.fullmatch(str(recorded.get("batch_sha256"))) is None:
        raise ValueError("BATCH_INVALID")
    # the seal computes this digest over the document minus itself, which is what makes a sealed batch uneditable, so
    # the validator recomputes it with the seal's own canonicalisation instead of trusting the field's shape
    from so101_demo.act.task8_measurement_contract import _canonical as _seal_canonical

    recomputed = hashlib.sha256(_seal_canonical({key: value for key, value in recorded.items()
                                                if key != "batch_sha256"})).hexdigest()
    if recorded["batch_sha256"] != recomputed:
        raise ValueError("BATCH_INVALID")
    # a contaminated batch is a failed cleanup: it keeps its evidence but must never feed a published report
    if recorded.get("contamination") is not None:
        raise ValueError("BATCH_INVALID")
    found = _regular_files(root)
    if set(found) != set(files):
        raise ValueError("BATCH_CLOSURE_INVALID")
    # the index closes over the anchors the batch declares, and the tree has two conventions for evidencing one: the
    # driver writes anchors/<anchor>/... and the aggregator consumes fov|search|sync/<anchor>.json. Either counts as
    # coverage; neither alone may be assumed.
    anchors = recorded["anchors"]
    if not isinstance(anchors, (list, tuple)) or not anchors:
        raise ValueError("BATCH_INVALID")
    indexed = {str(relative) for relative in files}
    for anchor in anchors:
        directory = f"anchors/{anchor}/"
        per_topic = {f"fov/{anchor}.json", f"search/{anchor}.json", f"sync/{anchor}.json"}
        if not any(entry.startswith(directory) for entry in indexed) and not (per_topic & indexed):
            raise ValueError("BATCH_ANCHOR_MISSING")

    # when an anchor is evidenced the way the driver writes it, the index also closes over the nine phases: the phase
    # rows are the coverage the contract's matrix depends on, and a missing one is invisible to the closure check
    phases = ("search", "approach", "close", "micro_lift", "transport", "align", "release", "radial_retreat",
              "final_check")
    for anchor in anchors:
        rows = {entry for entry in indexed if entry.startswith(f"anchors/{anchor}/")}
        if not rows:
            continue          # the aggregator's per-topic convention carries no phase dimension
        for name in phases:
            if not any(entry.endswith(f"-{name}.json") for entry in rows):
                raise ValueError("BATCH_PHASE_MISSING")

    # and it closes over source time: phase rows are read in phase order and their stamps must not go backwards, which
    # is the only way a reversal can be seen from an index of digests. Rows without a stamp prove nothing and are
    # skipped rather than silently passing as ordered.
    for anchor in anchors:
        ordered = sorted(entry for entry in indexed if entry.startswith(f"anchors/{anchor}/") and "/phase-" in entry)
        stamps = []
        for entry in ordered:
            row = _load(root / entry, "BATCH_INVALID")
            stamp = row.get("source_stamp")
            if isinstance(stamp, bool) or not isinstance(stamp, (int, float)):
                continue
            stamps.append(float(stamp))
        if any(later < earlier for earlier, later in zip(stamps, stamps[1:])):
            raise ValueError("BATCH_TIME_REVERSED")

    for relative, digest in files.items():
        if _SHA256.fullmatch(str(digest)) is None or found[relative] != digest:
            raise ValueError("BATCH_CLOSURE_INVALID")
    return BatchIndex(root, identity, dict(files))
