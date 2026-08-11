"""Command-line interface for listing, applying, and reading viewer cameras."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import yaml

from .camera_presets import CameraPresetConfigError, load_camera_presets
from .viewer_camera_client import (
    RosViewerCameraGateway,
    ViewerCameraGateway,
    ViewerCameraServiceError,
    ViewerCameraState,
    viewer_camera_state_to_yaml_fields,
)


def _default_config_file() -> Path:
    from ament_index_python.packages import get_package_share_directory

    return Path(get_package_share_directory("so101_mujoco_demo_py")) / "config/camera_views.yaml"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="camera_preset")
    parser.add_argument("preset", nargs="?")
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--list", action="store_true", dest="list_presets")
    operation.add_argument("--current", action="store_true")
    parser.add_argument("--format", choices=("human", "yaml"), default="human")
    return parser


def _print_state(state: ViewerCameraState, output_format: str) -> None:
    fields = viewer_camera_state_to_yaml_fields(state)
    if output_format == "yaml":
        print(yaml.safe_dump(fields, sort_keys=False).rstrip())
        return
    for key, value in fields.items():
        if isinstance(value, list):
            rendered = ",".join(str(item) for item in value)
        elif isinstance(value, bool):
            rendered = str(value).lower()
        else:
            rendered = str(value)
        print(f"{key}={rendered}")


def run(
    argv: Sequence[str] | None = None,
    *,
    gateway_factory: Callable[[], ViewerCameraGateway] = RosViewerCameraGateway,
    config_file: Path | None = None,
) -> int:
    options = _parser().parse_args(argv)
    if not options.list_presets and not options.current and options.preset is None:
        print("error: specify a preset, --list, or --current", file=sys.stderr)
        return 2
    if (options.list_presets or options.current) and options.preset is not None:
        print("error: a preset cannot be combined with --list or --current", file=sys.stderr)
        return 2

    presets = None
    if not options.current:
        try:
            presets = load_camera_presets(config_file or _default_config_file())
        except CameraPresetConfigError as error:
            print(f"camera preset config error: {error}", file=sys.stderr)
            return 2
        if options.list_presets:
            print("\n".join(presets))
            return 0
        if options.preset not in presets:
            print(f"unknown preset: {options.preset}", file=sys.stderr)
            return 2

    gateway: ViewerCameraGateway | None = None
    try:
        gateway = gateway_factory()
        state = (
            gateway.get_camera() if options.current else gateway.set_camera(presets[options.preset])
        )
        _print_state(state, options.format)
        return 0
    except ViewerCameraServiceError as error:
        print(f"viewer camera error: {error}", file=sys.stderr)
        return 1
    finally:
        if gateway is not None:
            gateway.close()


def main(argv: Sequence[str] | None = None) -> int:
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
