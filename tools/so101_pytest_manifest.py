"""Pytest plugin that records exact collected node IDs for gate verification."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys


def _source_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _atomic_json(path: Path, document: dict[str, object]) -> None:
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def pytest_collection_finish(session) -> None:
    """Persist collection identity before tests can fail or abort."""
    destination = os.environ.get("SO101_PYTEST_NODE_MANIFEST")
    if not destination:
        raise RuntimeError("SO101_PYTEST_NODE_MANIFEST is required")
    node_ids = [item.nodeid for item in session.items]
    package_spec = importlib.util.find_spec("so101_demo")
    package_origin = package_spec.origin if package_spec is not None else None
    digest = hashlib.sha256(("\n".join(sorted(node_ids)) + "\n").encode()).hexdigest()
    _atomic_json(
        Path(destination),
        {
            "schema_version": 1,
            "cwd": str(Path.cwd()),
            "python_executable": sys.executable,
            "so101_demo_origin": package_origin,
            "source_commit": _source_commit(),
            "node_ids": node_ids,
            "collection_sha256": digest,
        },
    )
