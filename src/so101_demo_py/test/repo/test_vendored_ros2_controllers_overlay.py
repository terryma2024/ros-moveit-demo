"""The vendored ros2_controllers overlay is exactly what its manifest says, and it keeps the lossless state hand-off.

`third_party/ros2_controllers` replaces the apt `joint_trajectory_controller` and `joint_state_broadcaster` (4.42.1)
through `--allow-overriding`. Their stock state publishing goes through `RealtimePublisher::try_publish()`, which loses
a tick whenever the publishing thread is late. The manifest pins every unchanged upstream file by hash and lists each
local change with its reason, so a drift from the pinned upstream is visible.
"""

import hashlib
import json

from paths import REPOSITORY

OVERLAY = REPOSITORY / "third_party" / "ros2_controllers"
LOCAL_PACKAGE = "so101_queued_state_publisher"


def _manifest() -> dict:
    return json.loads((OVERLAY / "source-manifest.json").read_text(encoding="utf-8"))


def _sha(relative: str) -> str:
    return hashlib.sha256((OVERLAY / relative).read_bytes()).hexdigest()


def test_the_manifest_pins_the_upstream_release_the_apt_packages_have() -> None:
    manifest = _manifest()
    assert manifest["upstream_version"] == "4.42.1"
    assert len(manifest["upstream_commit"]) == 40
    for package in ("joint_trajectory_controller", "joint_state_broadcaster"):
        text = (OVERLAY / package / "package.xml").read_text(encoding="utf-8")
        assert "<version>4.42.1</version>" in text


def test_every_vendored_file_is_listed_and_matches_its_recorded_hash() -> None:
    manifest = _manifest()
    recorded = {item["relative"]: item["sha256"] for item in manifest["original_files"]}
    recorded.update({item["relative"]: item["patched_sha256"] for item in manifest["local_changes"]})
    recorded.update({item["relative"]: item["sha256"] for item in manifest["local_test_files"]})
    recorded.update({item["relative"]: item["sha256"] for item in manifest["local_package"]["files"]})
    on_disk = {
        path.relative_to(OVERLAY).as_posix()
        for path in OVERLAY.rglob("*")
        if path.is_file() and path.name not in ("source-manifest.json", "LICENSE")
    }
    assert on_disk == set(recorded)
    for relative, digest in recorded.items():
        assert _sha(relative) == digest, relative


def test_every_local_change_differs_from_upstream_and_says_why() -> None:
    for item in _manifest()["local_changes"]:
        assert item["original_sha256"] != item["patched_sha256"], item["relative"]
        assert item["reason"].strip(), item["relative"]


def test_the_stock_single_slot_state_publish_is_gone_from_the_overlaid_controllers() -> None:
    for relative in (
        "joint_trajectory_controller/src/joint_trajectory_controller.cpp",
        "joint_state_broadcaster/src/joint_state_broadcaster.cpp",
    ):
        text = (OVERLAY / relative).read_text(encoding="utf-8")
        assert "_publisher_->try_publish(" not in text, relative
        assert "_publisher_->push(" in text, relative


def test_the_overlay_depends_on_the_local_queue_package() -> None:
    for package in ("joint_trajectory_controller", "joint_state_broadcaster"):
        assert LOCAL_PACKAGE in (OVERLAY / package / "package.xml").read_text(encoding="utf-8")
        assert LOCAL_PACKAGE in (OVERLAY / package / "CMakeLists.txt").read_text(encoding="utf-8")
