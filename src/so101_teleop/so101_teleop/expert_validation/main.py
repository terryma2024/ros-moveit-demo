"""Process entry point for the ROS-free expert-validation Web service."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from .api import create_expert_validation_app
from so101_teleop.api import validate_bind_address


def configured_evidence_root(environment: Mapping[str, str]) -> Path:
    value = environment.get("SO101_VALIDATION_EVIDENCE_ROOT")
    if not value:
        raise RuntimeError("SO101_VALIDATION_EVIDENCE_ROOT_REQUIRED")
    path = Path(value)
    if not path.is_absolute() or path != path.absolute():
        raise RuntimeError("EVIDENCE_ROOT_ABSOLUTE")
    if path.is_symlink():
        raise RuntimeError("EVIDENCE_ROOT_SYMLINK")
    if not path.is_dir():
        raise RuntimeError("EVIDENCE_ROOT_NOT_DIRECTORY")
    return path


def main(service_factory=None) -> None:
    import uvicorn

    root = configured_evidence_root(os.environ)
    address = validate_bind_address(
        os.environ.get("SO101_VALIDATION_BIND", "127.0.0.1")
    )
    if service_factory is None:
        raise RuntimeError("SO101_VALIDATION_SERVICE_FACTORY_REQUIRED")
    service = service_factory(root)
    static_dir = os.environ.get("SO101_VALIDATION_WEB_ROOT")
    uvicorn.run(
        create_expert_validation_app(
            service,
            static_dir,
            bind_address=address,
        ),
        host=address,
        port=int(os.environ.get("SO101_VALIDATION_PORT", "8010")),
    )
