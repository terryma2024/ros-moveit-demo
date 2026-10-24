"""Phase inputs and the small helpers shared by the calibration subcommands."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys

from so101_demo.cli.head_search.flags import (
    HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE,
    RUN_OPTIONAL_DIRECTORY_FLAGS,
    RUN_OPTIONAL_FILE_FLAGS,
    RUN_REQUIRED_FILE_FLAGS,
)


def _refuse_measurement_inputs(parsed, required, optional_file_flags=()) -> str | None:
    """The shared input check of a measurement entry: a missing or absent declaration is refused here."""

    missing = [flag for name, flag in required if getattr(parsed, name) is None]
    if missing:
        return f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}"
    absent = [
        str(getattr(parsed, name))
        for name, _flag in tuple(required) + tuple(optional_file_flags)
        if getattr(parsed, name) is not None
        and name != "output_dir"
        and not Path(getattr(parsed, name)).is_file()
    ]
    if absent:
        return f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}"
    if parsed.output_dir.exists():
        return (
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.output_dir} exists; a measurement is never "
            f"resumed, continued or overwritten"
        )
    return None


def _has_file(value) -> bool:
    """Every declared file must exist: a repeated flag declares one file per candidate."""

    values = value if isinstance(value, list) else [value]
    return bool(values) and all(Path(item).is_file() for item in values)


def _evaluation_arguments(parsed) -> list[str]:
    """The frozen-candidate gate's own argument list, assembled from the declared documents."""

    arguments = ["compare"]
    for path in parsed.frozen_candidate:
        arguments += ["--candidate", str(path)]
    arguments += [
        "--head-dataset",
        str(parsed.dataset),
        "--task-dataset",
        str(parsed.task_dataset),
        "--episode-partitions",
        str(parsed.episode_partitions),
        "--episode-split",
        parsed.episode_split,
        "--bootstrap-repetitions",
        str(parsed.bootstrap_repetitions),
        "--device",
        parsed.device,
    ]
    for flag, value in (
        ("--episode-records", parsed.episode_records),
        ("--weights-dir", parsed.weights_dir),
        ("--head-dataset-root", parsed.head_dataset_root),
        ("--task-dataset-root", parsed.task_dataset_root),
    ):
        if value is not None:
            arguments += [flag, str(value)]
    return arguments


def _declared_paths(parsed) -> list[Path]:
    """Every file a run declares: the required ones, the repeated ones and the optional ones."""

    values: list[Path] = []
    for name in RUN_REQUIRED_FILE_FLAGS:
        value = getattr(parsed, name)
        if value is None:
            continue
        values.extend(value if isinstance(value, list) else [value])
    for name in RUN_OPTIONAL_FILE_FLAGS:
        value = getattr(parsed, name)
        if value is not None:
            values.append(value)
    return [Path(value) for value in values]


def _declared_directories(parsed) -> list[Path]:
    return [
        Path(getattr(parsed, name))
        for name in RUN_OPTIONAL_DIRECTORY_FLAGS
        if getattr(parsed, name) is not None
    ]


def _json_document(path) -> Mapping:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError(f"{path} is not a JSON object")
    return document


def _records(path) -> list:
    """A phase's declared list of measured records, or a document that carries them under `records`."""

    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(document, Mapping):
        document = document.get("records")
    if isinstance(document, (str, bytes)) or not isinstance(document, Sequence):
        raise ValueError(f"{path} declares no list of measured records")
    return list(document)


def _frames(path) -> list:
    """A phase-3 measurement document: a list of frames, or a document that carries them."""

    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(document, Mapping):
        document = document.get("frames")
    if isinstance(document, (str, bytes)) or not isinstance(document, Sequence):
        raise ValueError(f"{path} declares no list of measurement frames")
    return list(document)


def _gpu_device(value: str):
    return int(value) if value.isdigit() else value


def _command_line(arguments: Sequence[str], *, subcommand: str = "run") -> str:
    return (
        f"ros2 run so101_demo_py so101_head_search_calibration {subcommand} "
        + " ".join(shlex.quote(str(item)) for item in arguments)
    )


def _verify_promoted_config(
    run_root: Path, approved: str | None, promoted_config: Path | None
) -> int:
    """Hash the promoted bundle's bytes and record the approval once, immutably.

    The bundle is hashed as bytes, so a formatting-only difference is caught rather than normalised away,
    and the receipt is created exclusively: a second verification cannot overwrite what was approved. The
    receipt belongs to a run root that does not exist yet, so verification obeys the same no-resume rule as
    every other runner.
    """

    from so101_demo.act.head_search.qualification import _require_new_root, write_exclusive

    if not approved:
        print("HEAD_SEARCH_APPROVAL_REQUIRED: pass --approved-bundle-sha256", file=sys.stderr)
        return 2
    if promoted_config is None:
        print("HEAD_SEARCH_BUNDLE_REQUIRED: pass --promoted-config", file=sys.stderr)
        return 2
    promoted = Path(promoted_config)
    if not promoted.is_file():
        print(f"HEAD_SEARCH_BUNDLE_MISSING: {promoted} is absent", file=sys.stderr)
        return 2
    measured = hashlib.sha256(promoted.read_bytes()).hexdigest()
    if measured != approved:
        print(
            f"HEAD_SEARCH_APPROVAL_MISMATCH: promoted {measured} differs from approved {approved}",
            file=sys.stderr,
        )
        return 2
    try:
        root = _require_new_root(run_root)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    try:
        write_exclusive(
            root,
            "approval-receipt.json",
            {
                "approved_bundle_sha256": approved,
                "promoted_bundle_sha256": measured,
                "promoted_config": str(promoted),
                "hashed": "bytes",
                "verified": True,
            },
        )
    except FileExistsError:
        print("APPROVAL_RECEIPT_EXISTS: an approval is immutable", file=sys.stderr)
        return 2
    print(f"HEAD_SEARCH_APPROVED {measured}")
    return 0


def _validate_flight(parsed, flags) -> tuple[list[str], list[str]]:
    """The declared inputs of one measurement flight: the flags it is missing and the paths that are not files."""

    missing = [flag for name, flag, required in flags if required and getattr(parsed, name) is None]
    if missing:
        return missing, []
    absent = [
        str(getattr(parsed, name))
        for name, _flag, required in flags
        if required and not Path(getattr(parsed, name)).is_file()
    ]
    return [], absent


def _transport_runtime_identity(parsed) -> dict:
    """What ran, for the document's provenance: never a measurement, and never allowed to fail the run."""

    identity = {"ros_distro": os.environ.get("ROS_DISTRO"), "python": sys.executable}
    try:
        from ament_index_python.packages import get_package_prefix

        identity["prefix_mujoco_ros2_control"] = get_package_prefix("mujoco_ros2_control")
        identity["prefix_so101_demo_py"] = get_package_prefix("so101_demo_py")
    except Exception as error:  # noqa: BLE001 - provenance is recorded, it never fails a measurement
        identity["prefix_lookup_error"] = str(error)
    for library in sorted(
        Path(identity.get("prefix_mujoco_ros2_control", "/nonexistent")).glob(
            "opt/mujoco_vendor/lib/libmujoco.so.*"
        )
    ):
        identity["mujoco_c_library"] = str(library)
    identity["stack_nodes"] = ["mujoco_ros2_control", "robot_state_publisher", "joint_state_broadcaster"]
    identity["detector_loaded"] = False
    identity["cuda_used"] = False
    identity["motion_commanded"] = False
    identity["frames_requested"] = parsed.frames
    return identity


def _frozen_run_root(final_run) -> Path:
    """The frozen toolchain root, from the flag or from the installed package prefix."""

    if final_run is not None:
        return Path(final_run)
    from ament_index_python.packages import get_package_prefix

    prefix = Path(get_package_prefix("so101_demo_py"))
    if prefix.parent.name != "install":
        raise ValueError(
            f"RUNTIME_IDENTITY_UNREADABLE: {prefix} is not an install prefix of a toolchain root"
        )
    return prefix.parent.parent


# the location is relative to the command module (cli/head_search_calibration.py), not to this helper
_ENTRY_MODULE_PATH = Path(__file__).resolve().parent.parent / "head_search_calibration.py"


def _source_web_dir() -> Path | None:
    """The worktree's own web package, for the case's Bun invocation."""

    override = os.environ.get("SO101_TELEOP_WEB_DIR")
    if override:
        return Path(override)
    candidate = _ENTRY_MODULE_PATH.parents[4] / "so101_teleop" / "web"
    return candidate if (candidate / "package.json").is_file() else None


def _digest(path: Path) -> str:
    if not Path(path).is_file():
        return ""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
