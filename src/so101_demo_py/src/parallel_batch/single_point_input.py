"""One Worker lease executes exactly one hash-bound point (plan Task 3, design section 8).

The campaign never hands a Worker the installed catalog. Each lease becomes one immutable
single-point YAML under the batch root, written through an fsynced temporary file and an atomic
rename, and its SHA-256 travels with the lease. The Worker reads the file's id and digest back
before it runs the batch, and a business result can only be constructed once the station, the
MoveIt/physics decision, the evidence manifest and the cleanup ownership are all durable.

The batch runner is invoked with `--points <single point file>`; `rgbd_task_points.yaml` (the
installed catalog) is refused by name, so a Worker cannot silently fall back to walking the whole
catalog.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import yaml

from .queue import PointLease
from .selection import FirstPassSelectionBinding, RetrySelectionBinding, SelectedPoint
from ..runtime.task_artifacts import fsync_directory

POINTS_SCHEMA_VERSION = 1
POINTS_DIRNAME = "points"
BUSINESS_OUTCOMES: tuple[str, ...] = ("PASSED", "FAILED", "INDETERMINATE")
INSTALLED_CATALOG_BASENAME = "rgbd_task_points.yaml"


class SinglePointInputError(RuntimeError):
    """The single-point input or the result it produced violated its contract."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _require_sha256(name: str, value: object, *, code: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise SinglePointInputError(code, f"{name}={value!r}")
    return value


def _binding_points(
    binding: FirstPassSelectionBinding | RetrySelectionBinding,
) -> dict[str, SelectedPoint]:
    if isinstance(binding, FirstPassSelectionBinding):
        return {point.point_id: point for point in binding.points}
    if isinstance(binding, RetrySelectionBinding):
        return {binding.point.point_id: binding.point}
    raise SinglePointInputError("SINGLE_POINT_BINDING_TYPE", type(binding).__name__)


def _point_document(point: SelectedPoint) -> dict[str, object]:
    return {
        "schema_version": POINTS_SCHEMA_VERSION,
        "points": [
            {
                "id": point.point_id,
                "label": point.point_id.replace("_", " "),
                "cup_position_world_m": list(point.position_xyz_m),
            }
        ],
    }


@dataclass(frozen=True, slots=True)
class PointExecutionInput:
    """The one immutable point file a lease is allowed to execute."""

    point_id: str
    attempt_id: str
    relative_points_path: str
    points_sha256: str
    point_sha256: str
    campaign_id: str
    batch_id: str

    def __post_init__(self) -> None:
        for name in ("point_id", "attempt_id", "campaign_id", "batch_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise SinglePointInputError("SINGLE_POINT_INPUT_SHAPE", name)
        relative = Path(self.relative_points_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise SinglePointInputError(
                "SINGLE_POINT_INPUT_SHAPE", self.relative_points_path
            )
        _require_sha256("points_sha256", self.points_sha256, code="SINGLE_POINT_INPUT_SHAPE")
        _require_sha256("point_sha256", self.point_sha256, code="SINGLE_POINT_INPUT_SHAPE")

    def as_document(self) -> dict[str, object]:
        return {
            "point_id": self.point_id,
            "attempt_id": self.attempt_id,
            "relative_points_path": self.relative_points_path,
            "points_sha256": self.points_sha256,
            "point_sha256": self.point_sha256,
            "campaign_id": self.campaign_id,
            "batch_id": self.batch_id,
        }

    def absolute_path(self, root: Path) -> Path:
        return Path(root) / self.relative_points_path


def _write_bytes_atomically(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def write_single_point_input(
    *,
    binding: FirstPassSelectionBinding | RetrySelectionBinding,
    lease: PointLease,
    root: Path,
) -> PointExecutionInput:
    """Write the lease's one point under ``root``/points and bind its digest.

    Rewriting the same lease is idempotent; a file at that path with different bytes is refused
    rather than overwritten, because it would silently change what the lease executes.
    """

    if not isinstance(lease, PointLease):
        raise SinglePointInputError("SINGLE_POINT_LEASE_TYPE", type(lease).__name__)
    points = _binding_points(binding)
    point = points.get(lease.point_id)
    if point is None:
        raise SinglePointInputError("SINGLE_POINT_LEASE_UNSELECTED", lease.point_id)
    if lease.point_sha256 != point.point_sha256:
        raise SinglePointInputError(
            "SINGLE_POINT_LEASE_MISMATCH",
            f"{lease.point_sha256} != {point.point_sha256}",
        )
    if lease.campaign_id != binding.campaign_id or lease.batch_id != binding.batch_id:
        raise SinglePointInputError(
            "SINGLE_POINT_LEASE_BINDING_MISMATCH",
            f"{lease.campaign_id}/{lease.batch_id}",
        )

    relative_path = f"{POINTS_DIRNAME}/{point.point_id}.yaml"
    path = Path(root) / relative_path
    payload = yaml.safe_dump(_point_document(point), sort_keys=False).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    if path.exists():
        existing = path.read_bytes()
        if hashlib.sha256(existing).hexdigest() != digest:
            raise SinglePointInputError("SINGLE_POINT_INPUT_CONFLICT", str(path))
    else:
        _write_bytes_atomically(path, payload)
    return PointExecutionInput(
        point_id=point.point_id,
        attempt_id=lease.attempt_id,
        relative_points_path=relative_path,
        points_sha256=digest,
        point_sha256=point.point_sha256,
        campaign_id=binding.campaign_id,
        batch_id=binding.batch_id,
    )


def read_single_point_input(
    path: Path, *, expected_sha256: str, expected_point_id: str
) -> dict[str, object]:
    """Read back the one point file and refuse any drift, extra point or wrong id."""

    path = Path(path)
    _require_sha256("expected_sha256", expected_sha256, code="SINGLE_POINT_INPUT_SHAPE")
    if not isinstance(expected_point_id, str) or not expected_point_id:
        raise SinglePointInputError("SINGLE_POINT_INPUT_SHAPE", "expected_point_id")
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise SinglePointInputError("SINGLE_POINT_INPUT_UNREADABLE", f"{path}: {error}") from error
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise SinglePointInputError("SINGLE_POINT_INPUT_DRIFT", str(path))
    try:
        document = yaml.safe_load(raw)
    except yaml.YAMLError as error:
        raise SinglePointInputError("SINGLE_POINT_INPUT_SHAPE", f"{path}: {error}") from error
    if not isinstance(document, Mapping) or document.get("schema_version") != POINTS_SCHEMA_VERSION:
        raise SinglePointInputError("SINGLE_POINT_INPUT_SHAPE", str(path))
    entries = document.get("points")
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)) or len(entries) != 1:
        raise SinglePointInputError("SINGLE_POINT_INPUT_SHAPE", "exactly one point is required")
    entry = entries[0]
    if not isinstance(entry, Mapping) or entry.get("id") != expected_point_id:
        raise SinglePointInputError(
            "SINGLE_POINT_POINT_MISMATCH",
            f"{entry.get('id') if isinstance(entry, Mapping) else entry!r} != {expected_point_id}",
        )
    return {"schema_version": POINTS_SCHEMA_VERSION, "points": [dict(entry)]}


def batch_argv(
    *,
    binary: Path,
    execution_input: PointExecutionInput,
    root: Path,
    batch_id: str,
    session_id: str,
    evidence_root: Path,
    mujoco_pid: int | None = None,
) -> tuple[str, ...]:
    """The closed batch command line: the single point file, never the installed catalog."""

    if Path(execution_input.relative_points_path).name == INSTALLED_CATALOG_BASENAME:
        raise SinglePointInputError(
            "SINGLE_POINT_INSTALLED_CATALOG_REFUSED", execution_input.relative_points_path
        )
    argv = [
        str(binary),
        "--points",
        str(execution_input.absolute_path(root)),
        "--batch-id",
        str(batch_id),
        "--session-id",
        str(session_id),
        "--evidence-root",
        str(evidence_root),
        "--attach-existing-stack",
    ]
    if mujoco_pid is not None:
        argv.extend(["--mujoco-pid", str(int(mujoco_pid))])
    return tuple(argv)


def pick_place_request(
    *,
    lease_document: Mapping[str, object],
    batch_binary: Path,
    session_id: str,
    evidence_root: Path,
    mujoco_pid: int | None = None,
) -> dict[str, object]:
    """Decide whether this lease may run pick-place, and with which exact input.

    A lease without a verified single-point input is refused; there is no fallback to the
    installed catalog.
    """

    points_path = lease_document.get("points_path")
    points_sha256 = lease_document.get("points_sha256")
    point_id = lease_document.get("point_id")
    if not isinstance(points_path, str) or not isinstance(points_sha256, str) or not isinstance(
        point_id, str
    ):
        return {"requested": False, "error": "POINTS_PATH_MISSING"}
    if Path(points_path).name == INSTALLED_CATALOG_BASENAME:
        return {"requested": False, "error": "INSTALLED_CATALOG_REFUSED"}
    binary = Path(batch_binary)
    if not binary.is_file():
        return {"requested": False, "error": "BATCH_BINARY_MISSING", "binary": str(binary)}
    document = read_single_point_input(
        Path(points_path), expected_sha256=points_sha256, expected_point_id=point_id
    )
    root = Path(points_path).parent.parent
    execution_input = PointExecutionInput(
        point_id=point_id,
        attempt_id=str(lease_document.get("attempt_id") or "attempt"),
        relative_points_path=Path(points_path).relative_to(root).as_posix(),
        points_sha256=points_sha256,
        point_sha256=str(lease_document.get("point_sha256") or points_sha256),
        campaign_id=str(lease_document.get("campaign_id") or "campaign"),
        batch_id=str(lease_document.get("batch_id") or "batch"),
    )
    argv = batch_argv(
        binary=binary,
        execution_input=execution_input,
        root=root,
        batch_id=execution_input.batch_id,
        session_id=session_id,
        evidence_root=evidence_root,
        mujoco_pid=mujoco_pid,
    )
    return {
        "requested": True,
        "binary": str(binary),
        "points": str(points_path),
        "points_sha256": points_sha256,
        "point_id": point_id,
        "attempt_id": execution_input.attempt_id,
        "argv": list(argv),
        "points_document": document,
    }


@dataclass(frozen=True, slots=True)
class PointExecutionResult:
    """The durable facts one attempt must have before a business result may be committed."""

    lease_identity: tuple[str, str, str, str, int, str]
    point_id: str
    attempt_id: str
    outcome: str
    business_decision: str
    evidence_manifest_relative_path: str
    evidence_manifest_sha256: str
    station_ready: bool
    moveit_executed: bool
    cleanup_owned: bool

    def __post_init__(self) -> None:
        if self.outcome not in BUSINESS_OUTCOMES:
            raise SinglePointInputError("POINT_RESULT_OUTCOME_INVALID", f"{self.outcome!r}")
        if self.business_decision not in BUSINESS_OUTCOMES:
            raise SinglePointInputError(
                "POINT_RESULT_OUTCOME_INVALID", f"decision={self.business_decision!r}"
            )
        if self.business_decision != self.outcome:
            raise SinglePointInputError(
                "POINT_RESULT_DECISION_MISMATCH",
                f"{self.business_decision} != {self.outcome}",
            )
        identity = tuple(self.lease_identity)
        if len(identity) != 6 or any(not isinstance(item, (str, int)) for item in identity):
            raise SinglePointInputError("POINT_RESULT_LEASE_IDENTITY", repr(self.lease_identity))
        if self.point_id != identity[2] or self.attempt_id != identity[3]:
            raise SinglePointInputError(
                "POINT_RESULT_LEASE_IDENTITY",
                f"{self.point_id}/{self.attempt_id} != {identity[2]}/{identity[3]}",
            )
        relative = Path(self.evidence_manifest_relative_path)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise SinglePointInputError(
                "POINT_RESULT_DURABILITY_INCOMPLETE", self.evidence_manifest_relative_path
            )
        _require_sha256(
            "evidence_manifest_sha256",
            self.evidence_manifest_sha256,
            code="POINT_RESULT_DURABILITY_INCOMPLETE",
        )
        if not (self.station_ready and self.moveit_executed and self.cleanup_owned):
            raise SinglePointInputError(
                "POINT_RESULT_DURABILITY_INCOMPLETE",
                f"station_ready={self.station_ready} moveit_executed={self.moveit_executed} "
                f"cleanup_owned={self.cleanup_owned}",
            )

    def as_document(self) -> dict[str, object]:
        return {
            "lease_identity": list(self.lease_identity),
            "point_id": self.point_id,
            "attempt_id": self.attempt_id,
            "outcome": self.outcome,
            "business_decision": self.business_decision,
            "evidence_manifest_relative_path": self.evidence_manifest_relative_path,
            "evidence_manifest_sha256": self.evidence_manifest_sha256,
            "station_ready": self.station_ready,
            "moveit_executed": self.moveit_executed,
            "cleanup_owned": self.cleanup_owned,
        }
