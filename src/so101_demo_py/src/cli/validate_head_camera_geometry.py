"""Validate the production head camera and seal the geometry the Head Search task inherits.

The seal is the only thing that lets `generate_yolo_seg_dataset` render head-camera images: it proves
the production camera at all three anchors sees the cup's support geometry, that the neck interval
the search will use is collision-free and contains the required search domain, and that the field of
view union of the bounded coarse stops covers that domain. Every document it consumes is hashed into
the seal, so a later change to the camera, the scene or the contract invalidates it by name instead
of silently resealing.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

SEAL_FILENAME = "head-camera-geometry.json"


def _absolute_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("must be an absolute path")
    return path


def _anchor_names(value: str) -> tuple[str, ...]:
    names = tuple(item.strip() for item in value.split(",") if item.strip())
    if not names:
        raise argparse.ArgumentTypeError("must name at least one anchor")
    return names


def _write_seal(document: dict[str, Any], output_root: Path) -> Path:
    root = Path(output_root)
    if root.exists() and not root.is_dir():
        raise ValueError(f"HEAD_CAMERA_OUTPUT_INVALID: {root} is not a directory")
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    target = root / SEAL_FILENAME
    temporary = root / f".{SEAL_FILENAME}.{os.getpid()}.tmp"
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, target)
    return target


def _verify_owned_view(camera_config: Path, camera_name: str) -> None:
    from so101_demo.core.camera import FixedCameraPreset, load_camera_presets

    presets = load_camera_presets(Path(camera_config))
    owned = [
        preset
        for preset in presets.values()
        if isinstance(preset, FixedCameraPreset) and preset.fixed_camera_name == camera_name
    ]
    if not owned:
        raise ValueError(
            f"HEAD_CAMERA_VIEW_MISSING: {camera_config} owns no fixed view of {camera_name}"
        )


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="validate_head_camera_geometry",
        description="Seal the production head camera's anchor geometry, safe neck interval and FOV",
    )
    parser.add_argument("--scene", required=True, type=_absolute_path)
    parser.add_argument("--camera-config", required=True, type=_absolute_path)
    parser.add_argument("--contract", required=True, type=_absolute_path)
    parser.add_argument("--anchors", required=True, type=_anchor_names)
    parser.add_argument("--output-root", required=True, type=_absolute_path)
    parsed = parser.parse_args(arguments)

    from so101_demo.act.head_camera_geometry.contract import HeadCameraGeometryContract
    from so101_demo.act.head_camera_geometry.validation import validate_head_camera_geometry

    try:
        contract = HeadCameraGeometryContract.from_path(parsed.contract)
        declared = tuple(anchor.name for anchor in contract.anchors)
        if declared != parsed.anchors:
            raise ValueError(
                "HEAD_CAMERA_ANCHOR_SET_MISMATCH: the contract's anchors "
                f"{declared} are not the requested {parsed.anchors}"
            )
        _verify_owned_view(parsed.camera_config, contract.camera_name)
        result = validate_head_camera_geometry(parsed.scene, contract)
        seal_path = _write_seal(result.to_document(), parsed.output_root)
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"status": "ERROR", "failure": str(error)}, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "status": "OK",
                "seal": str(seal_path),
                "seal_sha256": result.sha256,
                "camera_name": result.camera_name,
                "anchors": list(result.anchors),
                "horizontal_fov_rad": result.horizontal_fov_rad,
                "lock_valid_neck_rad": list(result.lock_valid_neck_rad),
                "required_search_domain_rad": list(result.required_search_domain_rad),
                "in_frame_failures": len(result.in_frame_failures),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
