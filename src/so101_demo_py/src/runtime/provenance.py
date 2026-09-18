"""Canonical qualification-bundle provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from ..ports.pick_place_executor import ExecutionProvenance, VerifiedArtifact


@dataclass(frozen=True, slots=True)
class QualificationBundle:
    manifest: Mapping[str, object]
    bundle_sha256: str


@dataclass(frozen=True, slots=True)
class InstalledExecutionIdentity:
    """The installed location plus one best-effort DEBUG source observation.

    ``source_commit`` is nullable and is never runtime authority: a deployment may be
    a pure copied install with no Git checkout at all.
    """

    source_commit: str | None
    package_prefix: str | None
    source_commit_source: str = "UNKNOWN"


class ExecutionProvenanceError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


SOURCE_COMMIT_SOURCES = ("OBSERVED", "DECLARED", "UNKNOWN")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verified_artifact(path: Path) -> VerifiedArtifact | None:
    try:
        canonical = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not canonical.is_file():
        return None
    return VerifiedArtifact(str(canonical), _sha256(canonical))


def observed_source_commit(source_root: Path | None) -> str | None:
    """Best-effort Git observation for DEBUG data. It never raises and never gates.

    ``SO101_SOURCE_COMMIT`` takes precedence so a no-Git deployment can still record
    what the builder observed. The value is returned verbatim (stripped); callers must
    treat it as an observation, not as a validated runtime identity.
    """

    configured = os.environ.get("SO101_SOURCE_COMMIT")
    if configured is not None:
        value = configured.strip()
        return value or None
    if source_root is None:
        return None
    try:
        completed = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    return value or None


def resolve_installed_execution_identity() -> InstalledExecutionIdentity:
    """Best-effort DEBUG identity: both fields are optional observations.

    A missing ament index, a relative or vanished prefix, or a package that only exists
    as a direct import path are not runtime failures; callers that genuinely need an
    executable or share resource discover and validate it functionally at use time.
    """

    package_prefix: Path | None = None
    try:
        from ament_index_python.packages import get_package_prefix

        candidate = Path(get_package_prefix("so101_demo_py"))
        if candidate.is_absolute() and candidate.is_dir():
            package_prefix = candidate.resolve()
    except (ImportError, LookupError, OSError, RuntimeError):
        package_prefix = None
    observed = observed_source_commit(package_prefix)
    return InstalledExecutionIdentity(
        source_commit=observed,
        package_prefix=None if package_prefix is None else str(package_prefix),
        source_commit_source="OBSERVED" if observed is not None else "UNKNOWN",
    )


def verify_execution_provenance(
    *,
    declared_source_commit: str | None,
    declared_installed_prefix: str | None,
    session_id: str,
    expected_reset_epoch: int,
    evidence_root: Path,
) -> ExecutionProvenance:
    """Verify session/evidence; source commit and prefix are DEBUG metadata only.

    A declared commit or prefix (any value, including missing, relative, nonexistent or
    mismatched) is recorded as an observation: no Git command runs here, no ament
    lookup is required and no metadata value can refuse execution.
    """

    identity = resolve_installed_execution_identity()
    from ..application import text_agent as runtime_module

    try:
        module_path = Path(runtime_module.__file__).resolve(strict=True)
    except (OSError, RuntimeError, TypeError):
        module_path = None

    try:
        canonical_evidence_root = evidence_root.resolve(strict=True)
    except (OSError, RuntimeError):
        raise ExecutionProvenanceError("EXECUTION_EVIDENCE_ROOT_INVALID") from None
    if not canonical_evidence_root.is_dir():
        raise ExecutionProvenanceError("EXECUTION_EVIDENCE_ROOT_INVALID")

    if identity.source_commit is not None:
        commit, commit_source = identity.source_commit, "OBSERVED"
    elif declared_source_commit is not None:
        commit, commit_source = str(declared_source_commit).strip() or None, "DECLARED"
    else:
        commit, commit_source = None, "UNKNOWN"
    prefix = Path(identity.package_prefix) if identity.package_prefix else None
    if prefix is None and declared_installed_prefix:
        candidate = Path(str(declared_installed_prefix))
        if candidate.is_absolute() and candidate.is_dir():
            prefix = candidate.resolve()
    return ExecutionProvenance(
        source_commit=commit,
        source_commit_source=commit_source,
        installed_prefix=None if prefix is None else str(prefix),
        entrypoint=(
            None if prefix is None
            else _verified_artifact(prefix / "lib/so101_demo_py/text_pick_agent")
        ),
        module=None if module_path is None else _verified_artifact(module_path),
        executable=_verified_artifact(Path(sys.executable)),
        session_id=session_id,
        expected_reset_epoch=expected_reset_epoch,
        evidence_root=str(canonical_evidence_root),
    )


def _canonical(value: object) -> object:
    if isinstance(value, Path):
        if value.is_file():
            return {"path": str(value), "sha256": _sha256(value)}
        if value.is_dir():
            return {
                "path": str(value),
                "files": [
                    {"path": str(path.relative_to(value)), "sha256": _sha256(path)}
                    for path in sorted(value.rglob("*"))
                    if path.is_file() and "__pycache__" not in path.parts
                ],
            }
        raise ValueError(f"bundle path does not exist: {value}")
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) and key for key in value):
            raise ValueError("bundle mapping keys must be non-empty strings")
        return {key: _canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_canonical(item) for item in value]
    if isinstance(value, bool):
        raise ValueError("boolean values are not canonical numeric provenance")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("bundle numeric values must be finite")
        return value
    if isinstance(value, (str, int)) or value is None:
        return value
    raise ValueError(f"unsupported bundle input type: {type(value).__name__}")


def build_bundle_manifest(inputs: Mapping[str, object]) -> QualificationBundle:
    """Return a deterministic manifest and SHA-256 over all named inputs."""

    canonical_inputs = _canonical(inputs)
    manifest = {"schema_version": 1, "inputs": canonical_inputs}
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return QualificationBundle(
        manifest=manifest,
        bundle_sha256=hashlib.sha256(encoded).hexdigest(),
    )


def _source_commit() -> str | None:
    """DEBUG-only bundle input: a no-Git build records null instead of failing."""

    try:
        return observed_source_commit(Path.cwd())
    except Exception:  # noqa: BLE001 - an observation may never break the bundle
        return None


def installed_bundle() -> QualificationBundle:
    from ament_index_python.packages import get_package_prefix, get_package_share_directory

    share = Path(get_package_share_directory("so101_demo_py"))

    def optional_prefix(package: str) -> str | None:
        try:
            candidate = Path(get_package_prefix(package))
        except (LookupError, OSError, RuntimeError):
            return None
        return str(candidate) if candidate.is_absolute() and candidate.is_dir() else None

    prefix = optional_prefix("so101_demo_py")
    mujoco_prefix = optional_prefix("mujoco_ros2_control")
    return build_bundle_manifest(
        {
            "source_commit": _source_commit(),
            "package_prefix": prefix,
            "policy_registry": share / "config" / "policies",
            "geometry_assets": share / "assets",
            "mujoco_ros2_control": {
                "prefix": mujoco_prefix,
                "executable": (
                    None if mujoco_prefix is None
                    else Path(mujoco_prefix)
                    / "lib/mujoco_ros2_control/ros2_control_node"
                ),
            },
            "runner_version": "fusion-v1",
            "lifecycle_version": "fusion-v1",
        }
    )


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-bundle-sha256", action="store_true", required=True)
    options = parser.parse_args(arguments)
    if options.print_bundle_sha256:
        print(installed_bundle().bundle_sha256)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
