"""Canonical qualification-bundle provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class QualificationBundle:
    manifest: Mapping[str, object]
    bundle_sha256: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _source_commit() -> str:
    configured = os.environ.get("SO101_SOURCE_COMMIT")
    if configured:
        return configured
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def installed_bundle() -> QualificationBundle:
    from ament_index_python.packages import get_package_prefix, get_package_share_directory

    share = Path(get_package_share_directory("so101_demo_py"))
    prefix = Path(get_package_prefix("so101_demo_py"))
    return build_bundle_manifest(
        {
            "source_commit": _source_commit(),
            "package_prefix": str(prefix),
            "policy_registry": share / "config" / "policies",
            "geometry_assets": share / "assets",
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
