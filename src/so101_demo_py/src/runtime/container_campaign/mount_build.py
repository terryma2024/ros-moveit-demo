"""Mount mode: the build of one commit is bind-mounted into containers of a dependency-only base image.

The campaign config's `mount_build` key (`{commit, root}`) switches it on; absent, every container runs a self-contained image as before.
The host builds `<root>/install` and `<root>/source` from a clean worktree of the commit (`scripts/images/build_mount_tree.zsh`) and
writes a `BUILD-COMMIT` record into each tree last. A launch trusts a tree only through that record, so what is compared is the commit,
never a per-file hash. The image records of the config keep their shape: `digest` is the base image, and `package_source_sha256` and
`install_sha256` are the sha256 of the two trees' records, which makes the commit part of the identity without a schema change.
"""

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re

from so101_demo.runtime.inference.config import _open_regular, validate_mount_build

RECORD_NAME = "BUILD-COMMIT"
#: the environment a mounted container gets (`docker/mount-base/bootstrap.bash` reads the three of them)
INSTALL_ENV, SOURCE_ENV, COMMIT_ENV = "SO101_MOUNT_INSTALL", "SO101_MOUNT_SOURCE", "SO101_EXPECTED_COMMIT"
ENTRY_SCRIPT = "/act/bootstrap.bash"
INTERPRETER = "/act/venv/bin/python"
#: the base image has the vendor `ros2`; the image path carries its own copy under the install
ROS2_EXECUTABLE = Path("/opt/ros/jazzy/bin/ros2")


@dataclass(frozen=True, slots=True)
class MountBuild:
    commit: str
    root: Path

    @property
    def install(self):
        return self.root / "install"

    @property
    def package_prefix(self):
        """The prefix of the `so101_demo_py` package inside the isolated install: what the instance program takes as its install prefix."""
        return self.install / "so101_demo_py"

    @property
    def source(self):
        return self.root / "source"

    def document(self):
        return dict(commit=self.commit, root=str(self.root))


def mount_from_config(config):
    """The `MountBuild` a campaign config names. Every run starts from a mount tree: a config without the key is refused
    (image mode is retired; the sealed image-mode records are read by `legacy_image_records`, never launched)."""
    document = config.get("mount_build")
    if document is None:
        raise ValueError("MOUNT_BUILD_REQUIRED")
    validate_mount_build(document)
    return MountBuild(commit=document["commit"], root=Path(document["root"]))


def read_record(directory):
    """The record bytes and the commit of one mounted tree; ValueError names the first fault (the codes of check-mount-commit.bash)."""
    path = Path(directory) / RECORD_NAME
    try:
        with _open_regular(path) as stream:
            payload = stream.read(256)
    except (OSError, ValueError) as error:
        raise ValueError(f"MOUNT_COMMIT_MISSING: {path}") from error
    if re.fullmatch(rb"[0-9a-f]{40}\n?", payload) is None:
        raise ValueError(f"MOUNT_COMMIT_MISMATCH: {path} is not a commit record")
    return payload, payload.decode("ascii").strip()


def record_sha256(directory):
    return hashlib.sha256(read_record(directory)[0]).hexdigest()


def verify_records(mount):
    """Both trees carry the commit of the launch; returns the image record fields they imply."""
    for directory in (mount.install, mount.source):
        _payload, commit = read_record(directory)
        if commit != mount.commit:
            raise ValueError(f"MOUNT_COMMIT_MISMATCH: {directory / RECORD_NAME} holds {commit}, the launch asked for {mount.commit}")
    return dict(package_source_sha256=record_sha256(mount.source), install_sha256=record_sha256(mount.install))


def verify_images(config, mount):
    """The config's three image records are the one base image plus the two record hashes of the trees on this host."""
    expected = verify_records(mount)
    for name, record in (("shard_image", config["shard_image"]), ("head_service", config["head_service"]["image"]),
                         ("teacher_service", config["teacher_service"]["image"])):
        if record["digest"] != config["shard_image"]["digest"] or any(record[key] != value for key, value in expected.items()):
            raise ValueError(f"MOUNT_IMAGE_RECORD_MISMATCH: {name}")
    return expected


def container_environment(mount):
    return [f"{INSTALL_ENV}={mount.install}", f"{SOURCE_ENV}={mount.source}", f"{COMMIT_ENV}={mount.commit}"]


def container_mounts(mount):
    """The two read-only bind mounts, each at its own host path."""
    return [f"type=bind,src={directory},dst={directory},readonly" for directory in (mount.install, mount.source)]


# ---- the environment check before a start --------------------------------------------------------------------------------------
# `scripts/env/image_env.py check-image --preflight` compares this host with the base image's manifest for the mounted install
# (apt packages, closure, linked-library owners, python minor, venv pins) and writes this record beside the campaign's evidence roots.
# A start refuses without a passing record for its own commit and base image; the run keeps a copy in `host/`, which the seal covers, and
# the qualification recompute and the merge read that copy.

PREFLIGHT_KIND = "MOUNT_PREFLIGHT"
PREFLIGHT_KEYS = frozenset({"schema_version", "kind", "result", "commit", "base_image_id", "base_manifest_sha256",
                            "install_record_sha256", "must_failures", "warnings", "exceptions", "host"})
PREFLIGHT_COPY = "mount-preflight.json"


def preflight_path(evidence_root, mount):
    return Path(evidence_root) / f"mount-preflight-{mount.commit[:12]}.json"


def preflight_problem(record, mount_document, image):
    """None when `record` is a passing environment check of this commit against this base image, else the first fault. `mount_document` is
    the identity's `{commit, root}`; `image` the image record (digest and the install record hash)."""
    if type(record) is not dict or set(record) != PREFLIGHT_KEYS:
        return "shape"
    if record["schema_version"] != 1 or record["kind"] != PREFLIGHT_KIND:
        return "kind"
    if record["result"] != "PASS" or record["must_failures"] != 0 or type(record["must_failures"]) is not int:
        return "result"
    for key, expected in (("commit", mount_document["commit"]), ("base_image_id", image["digest"]),
                          ("install_record_sha256", image["install_sha256"])):
        if record[key] != expected:
            return key
    if not _hex(record["base_manifest_sha256"], 64) or type(record["warnings"]) is not int or type(record["exceptions"]) is not dict:
        return "shape"
    return None


def _hex(value, length):
    return type(value) is str and re.fullmatch("[0-9a-f]{%d}" % length, value) is not None


def read_preflight(evidence_root, mount, config):
    """The record bytes and document of the host check for this start; ValueError `MOUNT_PREFLIGHT_*` when absent or not passing."""
    import json

    path = preflight_path(evidence_root, mount)
    try:
        with _open_regular(path) as stream:
            payload = stream.read(1024 * 1024)
        record = json.loads(payload.decode("utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"MOUNT_PREFLIGHT_MISSING: {path}") from error
    problem = preflight_problem(record, mount.document(), config["shard_image"])
    if problem is not None:
        raise ValueError(f"MOUNT_PREFLIGHT_REFUSED: {path}: {problem}")
    return payload, record
