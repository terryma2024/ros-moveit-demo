"""Resolve the Task 12 training lock from a recorded uv install report.

The lock is a claim about what was actually installed, so every package must arrive with the SHA of the
artifact that was resolved and the resolver must record the interpreter and the indexes that produced it.
A report entry without an artifact hash is refused rather than written with an empty pin.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

_PREFIX = "sha256="
_LOCK_PATH = Path(__file__).resolve().parents[2] / "config/act/requirements.lock"


def _artifact_hash(entry: dict) -> str:
    download = entry.get("download_info")
    if not isinstance(download, dict):
        raise ValueError("TRAINING_REPORT_INVALID")
    archive = download.get("archive_info")
    if not isinstance(archive, dict) or "hash" not in archive:
        raise ValueError("TRAINING_REPORT_UNHASHED")
    value = archive["hash"]
    if not isinstance(value, str) or not value.startswith(_PREFIX):
        raise ValueError("TRAINING_REPORT_UNHASHED")
    digest = value[len(_PREFIX):]
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest.lower()):
        raise ValueError("TRAINING_REPORT_UNHASHED")
    return digest.lower()


def build_lock_document(report: object, *, python: str, resolved_at: str, index_sha256: str) -> dict:
    """Turn one uv install report into the closed lock document."""

    if not isinstance(report, dict) or not isinstance(report.get("install"), list) or not report["install"]:
        raise ValueError("TRAINING_REPORT_INVALID")
    packages = []
    for entry in report["install"]:
        if not isinstance(entry, dict):
            raise ValueError("TRAINING_REPORT_INVALID")
        metadata = entry.get("metadata")
        if (not isinstance(metadata, dict) or not isinstance(metadata.get("name"), str)
                or not metadata["name"] or not isinstance(metadata.get("version"), str)
                or not metadata["version"]):
            raise ValueError("TRAINING_REPORT_INVALID")
        packages.append({"name": metadata["name"], "version": metadata["version"],
                         "sha256": _artifact_hash(entry)})
    names = [package["name"] for package in packages]
    if len(set(names)) != len(names):
        raise ValueError("TRAINING_REPORT_INVALID")
    return {"schema_version": 1, "kind": "act_training_requirements", "status": "RESOLVED",
            "resolver": {"python": python, "resolved_at": resolved_at, "index_sha256": index_sha256},
            "packages": sorted(packages, key=lambda package: package["name"])}


def index_digest(indexes) -> str:
    """One digest over the exact index set, so a lock names what resolved it."""

    if not indexes:
        raise ValueError("TRAINING_INDEX_REQUIRED")
    joined = "\n".join(sorted(str(index) for index in indexes))
    return hashlib.sha256(joined.encode()).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write the Task 12 training lock from a uv install report.")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--lock", type=Path, default=_LOCK_PATH)
    parser.add_argument("--python", required=True)
    parser.add_argument("--index", action="append", default=[])
    return parser


def main(arguments: list[str] | None = None) -> int:
    options = build_parser().parse_args(arguments)
    report = json.loads(Path(options.report).read_bytes())
    document = build_lock_document(
        report,
        python=options.python,
        resolved_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        index_sha256=index_digest(options.index),
    )
    target = Path(options.lock)
    target.write_text(yaml.safe_dump(document, sort_keys=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
