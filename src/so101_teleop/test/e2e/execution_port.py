"""Typed L2 execution port: replaces only the spawned argv target.

Only the repository-local installed test launcher injects this port.  The
production entry point never receives it, so installed production composition
always targets the installed upstream executables.  Everything else in the L2
assembly (SQLite store, writer lock, lease/fencing, preflight, supervisor,
process owner, signals, artifact registry, cleanup) remains production code.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Protocol


TEST_PORT_MARKER = "e2e-test-execution-port-v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class TestQualificationManifest:
    schema_version: int
    marker: str
    python: str
    fixed_helper: str
    fixed_helper_sha256: str
    adaptive_helper: str
    adaptive_helper_sha256: str
    descendant_helper: str
    descendant_helper_sha256: str
    spec_path: str
    spec_sha256: str


class ValidationExecutionPort(Protocol):
    def fixed_argv(self, request) -> tuple[str, ...]: ...
    def adaptive_argv(self, request) -> tuple[str, ...]: ...
    def qualification_manifest(self) -> TestQualificationManifest: ...


class HelperExecutionPort:
    """Map typed production start requests to the real OS helper executables."""

    def __init__(self, *, python: str, helpers_dir: Path, spec_path: Path) -> None:
        self._python = python
        self._helpers_dir = Path(helpers_dir)
        self._spec_path = Path(spec_path)
        for path in (
            self._helpers_dir / "fixed_helper.py",
            self._helpers_dir / "adaptive_helper.py",
            self._helpers_dir / "descendant_helper.py",
            self._spec_path,
        ):
            if not path.is_file() or path.is_symlink():
                raise RuntimeError(f"HELPER_PORT_INPUT_INVALID:{path.name}")
        self._qualification = TestQualificationManifest(
            schema_version=1,
            marker=TEST_PORT_MARKER,
            python=self._python,
            fixed_helper=str(self._helpers_dir / "fixed_helper.py"),
            fixed_helper_sha256=_sha256(self._helpers_dir / "fixed_helper.py"),
            adaptive_helper=str(self._helpers_dir / "adaptive_helper.py"),
            adaptive_helper_sha256=_sha256(self._helpers_dir / "adaptive_helper.py"),
            descendant_helper=str(self._helpers_dir / "descendant_helper.py"),
            descendant_helper_sha256=_sha256(self._helpers_dir / "descendant_helper.py"),
            spec_path=str(self._spec_path),
            spec_sha256=_sha256(self._spec_path),
        )

    def fixed_argv(self, request) -> tuple[str, ...]:
        argv = [
            self._python,
            str(self._helpers_dir / "fixed_helper.py"),
            "--batch-id", request.batch_id,
            "--campaign-id", request.campaign_id,
            "--batch-root", str(request.batch_root),
            "--spec", str(self._spec_path),
            "--worker-count", str(request.worker_count),
        ]
        for point_id in request.selected_point_ids:
            argv.extend(("--point-id", point_id))
        return tuple(argv)

    def adaptive_argv(self, request) -> tuple[str, ...]:
        argv = [
            self._python,
            str(self._helpers_dir / "adaptive_helper.py"),
            "--batch-id", request.batch_id,
            "--campaign-id", request.campaign_id,
            "--runtime-root", str(request.runtime_root),
            "--spec", str(self._spec_path),
            "--preferred-worker-count", str(request.preferred_worker_count),
        ]
        for point_id in request.selected_point_ids:
            argv.extend(("--point-id", point_id))
        return tuple(argv)

    def descendant_argv(self) -> tuple[str, ...]:
        return (self._python, str(self._helpers_dir / "descendant_helper.py"))

    def qualification_manifest(self) -> TestQualificationManifest:
        return self._qualification
