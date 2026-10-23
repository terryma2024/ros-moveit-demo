"""Control schema constants and the filtered ROS dylib farm identity and builder."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import secrets
import shutil

from so101_demo.parallel_batch.canonical_json import canonical_sha256

CONTROL_SCHEMA_VERSION = 2


_REQUIRED_ROS_DYLIB_BASENAMES = frozenset(
    {"libhardware_interface.dylib", "librosidl_typesupport_c.dylib"}
)


_SESSION_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


_ALL_PHASES = (
    "PLUGIN_RESOLVED",
    "SIMULATION_ENDPOINT_READY",
    "HARDWARE_INITIALIZING",
    "HARDWARE_READY",
    "CONTROLLER_MANAGER_SERVICES_READY",
    "CONTROLLERS_ACTIVE",
)


_SEMANTIC_ENVIRONMENT_KEYS = (
    "AMENT_PREFIX_PATH",
    "CMAKE_PREFIX_PATH",
    "COLCON_PREFIX_PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "PYTHONNOUSERSITE",
    "PYTHONPATH",
    "RMW_IMPLEMENTATION",
    "ROS_DISTRO",
    "ROS_PYTHON_VERSION",
    "ROS_VERSION",
)


class GateAControlError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True, slots=True)
class FilteredDylibFarmEntry:
    basename: str
    target_path: Path
    target_sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        if (
            not self.basename
            or Path(self.basename).name != self.basename
            or not self.basename.endswith(".dylib")
        ):
            raise GateAControlError("CONTROL_ROS_DYLIB_FARM_INVALID", self.basename)
        target = Path(self.target_path)
        if not target.is_absolute():
            raise GateAControlError(
                "CONTROL_ROS_DYLIB_FARM_INVALID", str(self.target_path)
            )
        if len(self.target_sha256) != 64 or any(
            character not in "0123456789abcdef"
            for character in self.target_sha256
        ):
            raise GateAControlError(
                "CONTROL_ROS_DYLIB_FARM_INVALID", self.basename
            )
        if self.size_bytes < 0:
            raise GateAControlError(
                "CONTROL_ROS_DYLIB_FARM_INVALID", self.basename
            )
        object.__setattr__(self, "target_path", target)

    def as_document(self) -> dict[str, object]:
        return {
            "basename": self.basename,
            "target_path": str(self.target_path),
            "target_sha256": self.target_sha256,
            "size_bytes": self.size_bytes,
        }

    @classmethod
    def from_document(
        cls, document: Mapping[str, object]
    ) -> "FilteredDylibFarmEntry":
        return cls(
            basename=str(document["basename"]),
            target_path=Path(str(document["target_path"])),
            target_sha256=str(document["target_sha256"]),
            size_bytes=int(document["size_bytes"]),
        )


@dataclass(frozen=True, slots=True)
class FilteredRosDylibFarmIdentity:
    source_farm: Path
    source_directory: Path
    directory: Path
    entries: tuple[FilteredDylibFarmEntry, ...]

    def __post_init__(self) -> None:
        for value in (self.source_farm, self.source_directory, self.directory):
            if not isinstance(value, Path) or not value.is_absolute():
                raise GateAControlError(
                    "CONTROL_ROS_DYLIB_FARM_INVALID", str(value)
                )
        if not self.entries:
            raise GateAControlError("CONTROL_ROS_DYLIB_FARM_INVALID", "empty")
        names = tuple(entry.basename for entry in self.entries)
        if names != tuple(sorted(names)) or len(names) != len(set(names)):
            raise GateAControlError(
                "CONTROL_ROS_DYLIB_FARM_INVALID", "inventory order"
            )

    @property
    def inventory(self) -> dict[str, FilteredDylibFarmEntry]:
        return {entry.basename: entry for entry in self.entries}

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.as_document())

    def as_document(self) -> dict[str, object]:
        return {
            "source_farm": str(self.source_farm),
            "source_directory": str(self.source_directory),
            "directory": str(self.directory),
            "entries": [entry.as_document() for entry in self.entries],
        }

    @classmethod
    def from_document(
        cls, document: Mapping[str, object]
    ) -> "FilteredRosDylibFarmIdentity":
        entries = document.get("entries")
        if not isinstance(entries, list):
            raise GateAControlError(
                "CONTROL_ROS_DYLIB_FARM_INVALID", "entries"
            )
        return cls(
            source_farm=Path(str(document["source_farm"])),
            source_directory=Path(str(document["source_directory"])),
            directory=Path(str(document["directory"])),
            entries=tuple(FilteredDylibFarmEntry.from_document(item) for item in entries),
        )


def _source_farm_snapshot(
    source_farm: Path,
) -> tuple[Path, Path, tuple[int, int, int, int], str | None]:
    source = Path(source_farm)
    if not source.is_absolute():
        raise GateAControlError("CONTROL_ROS_DYLIB_FARM_INVALID", str(source))
    try:
        before = os.lstat(source)
        link_text = os.readlink(source) if source.is_symlink() else None
        directory = source.resolve(strict=True)
    except OSError as error:
        raise GateAControlError(
            "CONTROL_ROS_DYLIB_FARM_INVALID", f"{source}: {error}"
        ) from error
    if not directory.is_dir():
        raise GateAControlError(
            "CONTROL_ROS_DYLIB_FARM_INVALID", str(directory)
        )
    identity = (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_size)
    return source, directory, identity, link_text


def _verify_source_farm_snapshot(
    source: Path,
    directory: Path,
    identity: tuple[int, int, int, int],
    link_text: str | None,
) -> None:
    try:
        after = os.lstat(source)
        after_link = os.readlink(source) if source.is_symlink() else None
        after_directory = source.resolve(strict=True)
    except OSError as error:
        raise GateAControlError(
            "CONTROL_ROS_DYLIB_FARM_DRIFT", f"{source}: {error}"
        ) from error
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_mtime_ns,
        after.st_size,
    )
    if (
        after_identity != identity
        or after_link != link_text
        or after_directory != directory
    ):
        raise GateAControlError("CONTROL_ROS_DYLIB_FARM_DRIFT", str(source))


def build_filtered_ros_dylib_farm(
    *,
    source_farm: Path,
    output_directory: Path,
    excluded_basenames: set[str] | frozenset[str],
) -> FilteredRosDylibFarmIdentity:
    source, source_directory, source_identity, source_link = _source_farm_snapshot(
        source_farm
    )
    output = Path(output_directory)
    if not output.is_absolute() or output.exists() or output.is_symlink():
        raise GateAControlError("CONTROL_ROS_DYLIB_FARM_INVALID", str(output))
    excluded = frozenset(excluded_basenames)
    entries: list[FilteredDylibFarmEntry] = []
    for library in sorted(source_directory.iterdir(), key=lambda path: path.name):
        if not library.name.endswith(".dylib"):
            continue
        if library.name in excluded:
            continue
        if not library.is_symlink():
            raise GateAControlError(
                "CONTROL_ROS_DYLIB_FARM_INVALID", str(library)
            )
        try:
            target = library.resolve(strict=True)
        except OSError as error:
            raise GateAControlError(
                "CONTROL_ROS_DYLIB_FARM_INVALID", f"{library}: {error}"
            ) from error
        if not target.is_file():
            raise GateAControlError(
                "CONTROL_ROS_DYLIB_FARM_INVALID", str(target)
            )
        payload = target.read_bytes()
        entries.append(
            FilteredDylibFarmEntry(
                basename=library.name,
                target_path=target,
                target_sha256=hashlib.sha256(payload).hexdigest(),
                size_bytes=len(payload),
            )
        )
    _verify_source_farm_snapshot(
        source, source_directory, source_identity, source_link
    )
    names = {entry.basename for entry in entries}
    missing = _REQUIRED_ROS_DYLIB_BASENAMES - names
    if missing:
        raise GateAControlError(
            "CONTROL_ROS_DYLIB_FARM_INVALID",
            f"missing required: {','.join(sorted(missing))}",
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.with_name(f".{output.name}.{secrets.token_hex(8)}.tmp")
    staging.mkdir()
    try:
        for entry in entries:
            (staging / entry.basename).symlink_to(entry.target_path)
        os.replace(staging, output)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    identity = FilteredRosDylibFarmIdentity(
        source_farm=source,
        source_directory=source_directory,
        directory=output,
        entries=tuple(entries),
    )
    verify_filtered_ros_dylib_farm(identity, excluded_basenames=excluded)
    return identity


def verify_filtered_ros_dylib_farm(
    identity: FilteredRosDylibFarmIdentity,
    *,
    excluded_basenames: set[str] | frozenset[str],
) -> None:
    if not isinstance(identity, FilteredRosDylibFarmIdentity):
        raise GateAControlError(
            "CONTROL_ROS_DYLIB_FARM_INVALID", type(identity).__name__
        )
    try:
        if identity.source_farm.resolve(strict=True) != identity.source_directory:
            raise GateAControlError(
                "CONTROL_ROS_DYLIB_FARM_DRIFT", str(identity.source_farm)
            )
    except OSError as error:
        raise GateAControlError(
            "CONTROL_ROS_DYLIB_FARM_DRIFT", f"{identity.source_farm}: {error}"
        ) from error
    directory = identity.directory
    if directory.is_symlink() or not directory.is_dir():
        raise GateAControlError("CONTROL_ROS_DYLIB_FARM_DRIFT", str(directory))
    expected = identity.inventory
    actual = {path.name: path for path in directory.iterdir()}
    if set(actual) != set(expected):
        raise GateAControlError(
            "CONTROL_ROS_DYLIB_FARM_DRIFT", "inventory names"
        )
    if set(expected).intersection(excluded_basenames):
        raise GateAControlError(
            "CONTROL_ROS_DYLIB_FARM_INVALID", "excluded basename present"
        )
    missing = _REQUIRED_ROS_DYLIB_BASENAMES - set(expected)
    if missing:
        raise GateAControlError(
            "CONTROL_ROS_DYLIB_FARM_INVALID",
            f"missing required: {','.join(sorted(missing))}",
        )
    for basename, entry in expected.items():
        link = actual[basename]
        try:
            if not link.is_symlink() or os.readlink(link) != str(entry.target_path):
                raise GateAControlError(
                    "CONTROL_ROS_DYLIB_FARM_DRIFT", basename
                )
            target = link.resolve(strict=True)
            payload = target.read_bytes()
        except OSError as error:
            raise GateAControlError(
                "CONTROL_ROS_DYLIB_FARM_DRIFT", f"{link}: {error}"
            ) from error
        if (
            target != entry.target_path
            or len(payload) != entry.size_bytes
            or hashlib.sha256(payload).hexdigest() != entry.target_sha256
        ):
            raise GateAControlError("CONTROL_ROS_DYLIB_FARM_DRIFT", basename)
