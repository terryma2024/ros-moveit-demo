"""Read-only bridge from accepted upstream manifests to opaque Web artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path, PurePosixPath
import re
import stat

from so101_teleop.task_artifacts import (
    ArtifactAccessError,
    validate_artifact_media_type,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _identifier(name: str, value: str | None, *, optional: bool = False) -> None:
    if value is None and optional:
        return
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ArtifactAccessError(f"{name.upper()}_INVALID")


@dataclass(frozen=True, slots=True)
class ArtifactManifestEntry:
    relative_path: str
    role: str
    media_type: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.relative_path, str):
            raise ArtifactAccessError("ARTIFACT_PATH_INVALID")
        if not isinstance(self.role, str) or not self.role:
            raise ArtifactAccessError("ARTIFACT_ROLE_INVALID")
        if type(self.size_bytes) is not int or self.size_bytes < 0:
            raise ArtifactAccessError("ARTIFACT_SIZE_INVALID")
        if not isinstance(self.sha256, str) or _SHA256.fullmatch(self.sha256) is None:
            raise ArtifactAccessError("ARTIFACT_SHA256_INVALID")


@dataclass(frozen=True, slots=True)
class SealedArtifactManifest:
    manifest_id: str
    manifest_sha256: str
    campaign_id: str
    batch_id: str
    pool_generation: int | None
    worker_id: str | None
    worker_generation: int | None
    attempt_id: str | None
    committed: bool
    entries: tuple[ArtifactManifestEntry, ...]

    def __post_init__(self) -> None:
        for name in ("manifest_id", "campaign_id", "batch_id"):
            _identifier(name, getattr(self, name))
        if _SHA256.fullmatch(self.manifest_sha256) is None:
            raise ArtifactAccessError("MANIFEST_SHA256_INVALID")
        _identifier("worker_id", self.worker_id, optional=True)
        _identifier("attempt_id", self.attempt_id, optional=True)
        for name in ("pool_generation", "worker_generation"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value <= 0):
                raise ArtifactAccessError(f"{name.upper()}_INVALID")
        if not isinstance(self.committed, bool):
            raise ArtifactAccessError("RESULT_COMMIT_INVALID")
        entries = tuple(self.entries)
        if not entries or any(not isinstance(item, ArtifactManifestEntry) for item in entries):
            raise ArtifactAccessError("MANIFEST_ENTRIES_INVALID")
        if len({entry.relative_path for entry in entries}) != len(entries):
            raise ArtifactAccessError("MANIFEST_ENTRY_DUPLICATE")
        object.__setattr__(self, "entries", entries)


@dataclass(frozen=True, slots=True)
class CampaignBatchBinding:
    campaign_id: str
    batch_id: str
    batch_root: Path
    owner_kind: str
    current_pool_generation: int | None
    accepted_manifest_sha256s: frozenset[str]

    def __post_init__(self) -> None:
        _identifier("campaign_id", self.campaign_id)
        _identifier("batch_id", self.batch_id)
        root = Path(self.batch_root)
        if not root.is_absolute() or root != root.resolve(strict=False) or root.is_symlink():
            raise ArtifactAccessError("ARTIFACT_ROOT_INVALID")
        object.__setattr__(self, "batch_root", root)
        if self.owner_kind not in {"COORDINATOR", "ADAPTIVE_RUNNER"}:
            raise ArtifactAccessError("ARTIFACT_OWNER_KIND")
        accepted = frozenset(self.accepted_manifest_sha256s)
        if any(_SHA256.fullmatch(value) is None for value in accepted):
            raise ArtifactAccessError("MANIFEST_SHA256_INVALID")
        object.__setattr__(self, "accepted_manifest_sha256s", accepted)


@dataclass(frozen=True, slots=True)
class ArtifactView:
    artifact_id: str
    campaign_id: str
    batch_id: str
    pool_generation: int | None
    worker_id: str | None
    worker_generation: int | None
    attempt_id: str | None
    role: str
    media_type: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class VerifiedArtifact:
    view: ArtifactView
    path: Path

    def read_bytes(self) -> bytes:
        path = _safe_regular(self.path, self.path.parent if not self.path.is_absolute() else None)
        payload = path.read_bytes()
        if (
            len(payload) != self.view.size_bytes
            or hashlib.sha256(payload).hexdigest() != self.view.sha256
        ):
            raise ArtifactAccessError("ARTIFACT_CHECKSUM_MISMATCH")
        return payload

    @property
    def media_type(self) -> str:
        return self.view.media_type


def _relative(value: str) -> PurePosixPath:
    if not value or "\\" in value or "\x00" in value:
        raise ArtifactAccessError("ARTIFACT_PATH_INVALID")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ArtifactAccessError("ARTIFACT_PATH_INVALID")
    return path


def _safe_regular(path: Path, root: Path | None) -> Path:
    path = Path(path)
    if root is None:
        root = path.parent
    root = Path(root)
    try:
        relative = path.absolute().relative_to(root.absolute())
    except ValueError as error:
        raise ArtifactAccessError("ARTIFACT_PATH_INVALID") from error
    current = root
    if current.is_symlink():
        raise ArtifactAccessError("ARTIFACT_PATH_INVALID")
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ArtifactAccessError("ARTIFACT_PATH_INVALID")
    try:
        resolved_root = root.resolve(strict=True)
        resolved = path.resolve(strict=True)
        resolved.relative_to(resolved_root)
        if not stat.S_ISREG(resolved.stat().st_mode):
            raise ArtifactAccessError("ARTIFACT_PATH_INVALID")
    except (OSError, ValueError) as error:
        raise ArtifactAccessError("ARTIFACT_PATH_INVALID") from error
    return resolved


class ValidationArtifactRegistry:
    def __init__(self) -> None:
        self._artifacts: dict[str, tuple[ArtifactView, Path, Path]] = {}

    def register_manifest(
        self, manifest: SealedArtifactManifest, binding: CampaignBatchBinding
    ) -> tuple[ArtifactView, ...]:
        if not isinstance(manifest, SealedArtifactManifest) or not isinstance(
            binding, CampaignBatchBinding
        ):
            raise ArtifactAccessError("ARTIFACT_MANIFEST_INVALID")
        if manifest.campaign_id != binding.campaign_id or manifest.batch_id != binding.batch_id:
            raise ArtifactAccessError("ARTIFACT_IDENTITY_MISMATCH")
        if manifest.manifest_sha256 not in binding.accepted_manifest_sha256s:
            raise ArtifactAccessError("MANIFEST_NOT_ACCEPTED")
        if not manifest.committed:
            raise ArtifactAccessError("RESULT_NOT_COMMITTED")
        if (
            binding.owner_kind == "ADAPTIVE_RUNNER"
            and manifest.pool_generation != binding.current_pool_generation
        ):
            raise ArtifactAccessError("POOL_GENERATION_MISMATCH")
        views = []
        for entry in manifest.entries:
            relative = _relative(entry.relative_path)
            validate_artifact_media_type(entry.media_type)
            path = binding.batch_root.joinpath(*relative.parts)
            resolved = _safe_regular(path, binding.batch_root)
            payload = resolved.read_bytes()
            if (
                len(payload) != entry.size_bytes
                or hashlib.sha256(payload).hexdigest() != entry.sha256
            ):
                raise ArtifactAccessError("ARTIFACT_CHECKSUM_MISMATCH")
            opaque_source = "\0".join(
                (
                    manifest.campaign_id,
                    manifest.batch_id,
                    manifest.manifest_id,
                    entry.relative_path,
                    entry.sha256,
                )
            )
            artifact_id = hashlib.sha256(opaque_source.encode("utf-8")).hexdigest()[:32]
            view = ArtifactView(
                artifact_id=artifact_id,
                campaign_id=manifest.campaign_id,
                batch_id=manifest.batch_id,
                pool_generation=manifest.pool_generation,
                worker_id=manifest.worker_id,
                worker_generation=manifest.worker_generation,
                attempt_id=manifest.attempt_id,
                role=entry.role,
                media_type=entry.media_type,
                size_bytes=entry.size_bytes,
                sha256=entry.sha256,
            )
            prior = self._artifacts.get(artifact_id)
            record = (view, resolved, binding.batch_root)
            if prior is not None and prior != record:
                raise ArtifactAccessError("ARTIFACT_ID_COLLISION")
            self._artifacts[artifact_id] = record
            views.append(view)
        return tuple(views)

    def resolve_opaque_id(
        self,
        artifact_id: str,
        *,
        expected_campaign_id: str | None = None,
        expected_batch_id: str | None = None,
        expected_worker_id: str | None = None,
        expected_attempt_id: str | None = None,
        expected_pool_generation: int | None = None,
    ) -> VerifiedArtifact:
        try:
            view, path, root = self._artifacts[artifact_id]
        except KeyError as error:
            raise ArtifactAccessError("ARTIFACT_NOT_FOUND") from error
        checks = (
            (expected_campaign_id, view.campaign_id),
            (expected_batch_id, view.batch_id),
            (expected_worker_id, view.worker_id),
            (expected_attempt_id, view.attempt_id),
            (expected_pool_generation, view.pool_generation),
        )
        if any(expected is not None and expected != actual for expected, actual in checks):
            raise ArtifactAccessError("ARTIFACT_IDENTITY_MISMATCH")
        resolved = _safe_regular(path, root)
        payload = resolved.read_bytes()
        if len(payload) != view.size_bytes or hashlib.sha256(payload).hexdigest() != view.sha256:
            raise ArtifactAccessError("ARTIFACT_CHECKSUM_MISMATCH")
        return VerifiedArtifact(view, resolved)
