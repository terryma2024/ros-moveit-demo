"""Prepare a new pick-place validation live manifest without starting ROS or motion."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import stat

import yaml

from so101_demo.act.pick_place_validation_manifest import build_pick_place_validation_manifest, write_new_manifest


def _digest_regular_file(path: Path) -> str:
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("TASK8_ARTIFACT_PATH_INVALID")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("TASK8_ARTIFACT_NOT_REGULAR")
            return hashlib.file_digest(stream, "sha256").hexdigest()
    except OSError as error:
        raise ValueError("TASK8_ARTIFACT_UNREADABLE") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Atomically prepare a frozen ACT pick-place validation live manifest")
    parser.add_argument("--anchors", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--runtime-config", required=True, type=Path)
    parser.add_argument("--collection-config", required=True, type=Path)
    parser.add_argument("--policy-fingerprint", required=True)
    parser.add_argument("--calibration-report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    _digest_regular_file(args.anchors)
    anchors_config = yaml.safe_load(args.anchors.read_bytes())
    if (not isinstance(anchors_config, dict)
            or set(anchors_config) != {"schema_version", "measurement_experiment", "anchors"}
            or anchors_config["schema_version"] != 1
            or anchors_config["measurement_experiment"] != "EXP-115"):
        raise ValueError("TASK8_ANCHOR_CONFIG_INVALID")
    document = build_pick_place_validation_manifest(
        anchors_config["anchors"],
        source_sha256=_digest_regular_file(args.source),
        runtime_config_sha256=_digest_regular_file(args.runtime_config),
        collection_config_sha256=_digest_regular_file(args.collection_config),
        contact_policy_fingerprint=args.policy_fingerprint,
        calibration_report_path=args.calibration_report.name,
        calibration_report_sha256=_digest_regular_file(args.calibration_report),
    )
    write_new_manifest(args.output, document)
    print(document["manifest_document_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
