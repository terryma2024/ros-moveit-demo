"""Capture one synchronized RGB-D evidence set and exit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _exclusive_absolute_directory(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("must be an absolute output directory")
    if path.exists():
        raise argparse.ArgumentTypeError("output directory must not already exist")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rgbd_sensor_capture")
    parser.add_argument(
        "--output-directory",
        type=_exclusive_absolute_directory,
        required=True,
    )
    parser.add_argument("--timeout-s", type=float, default=15.0)
    parser.add_argument("--tf-timeout-s", type=float, default=0.2)
    parser.add_argument("--camera-info-topic", default="/task_camera/camera_info")
    parser.add_argument("--color-topic", default="/task_camera/color")
    parser.add_argument("--depth-topic", default="/task_camera/depth")
    return parser


def main(arguments: list[str] | None = None) -> int:
    options = build_parser().parse_args(arguments)
    source = None
    exit_code = 0
    try:
        options.output_directory.mkdir(parents=True, exist_ok=False)
        from ..ros.rgbd_snapshot import RosRgbdSnapshotSource, capture_rgbd_snapshot

        source = RosRgbdSnapshotSource(
            camera_info_topic=options.camera_info_topic,
            color_topic=options.color_topic,
            depth_topic=options.depth_topic,
        )
        result = capture_rgbd_snapshot(
            source,
            source,
            options.output_directory,
            timeout_s=options.timeout_s,
            tf_timeout_s=options.tf_timeout_s,
        )
        document = dict(result.summary)
        document["output_directory"] = str(options.output_directory)
    except Exception as error:
        document = {
            "status": "ERROR",
            "failure": "RGBD_SENSOR_CAPTURE_FAILED",
            "message": str(error),
        }
        exit_code = 1
    finally:
        if source is not None:
            try:
                source.close()
            except BaseException as error:
                document = {
                    "status": "ERROR",
                    "failure": "RGBD_SENSOR_CAPTURE_CLEANUP_FAILED",
                    "message": str(error),
                }
                exit_code = 1
    print(json.dumps(document, sort_keys=True), flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
