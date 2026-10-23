"""Sealed image-mode campaigns stay verifiable after image mode was retired (design 2026-10-23, M1/M2), and nothing can start from one."""

import re
from pathlib import Path

import pytest

from so101_demo.act.collection_qualification_recompute import _RUN_ERRORS
from so101_demo.act.legacy_image_records import LEGACY_INSTALL_ROOT, image_problem

SRC = Path(__file__).resolve().parents[2] / "src"
IMAGE = {"digest": "sha256:" + "b" * 64, "package_source_sha256": "1" * 64, "install_sha256": "2" * 64}


def image_mode_record(**changes):
    """The container provenance an image-mode shard or Teacher wrote into a sealed run (`actual-container-provenance.json`)."""

    report = dict(schema_version=1, kind="ACT_CONTAINER_IMAGE_READBACK", package_source_sha256=IMAGE["package_source_sha256"],
        install_sha256=IMAGE["install_sha256"], git_commit="a" * 40, submodules={"vendor/controllers": "b" * 40},
        runtime=dict(interpreter="/act/venv/bin/python", dependencies={"numpy": "1.26.4"},
            module_origins={"so101_demo": "/act/install/lib/so101_demo/__init__.py"},
            package_prefixes={"so101_demo_py": "/act/install"}))
    return dict(container_id="c" * 64, docker_started_at="2026-10-12T01:02:03.123Z", image_digest=IMAGE["digest"],
                provenance=report) | changes


def problem(document, mount_build=None):
    return image_problem(document, IMAGE, mount_build, _RUN_ERRORS)


def test_a_sealed_image_mode_record_still_verifies():
    assert problem(image_mode_record()) is False
    assert LEGACY_INSTALL_ROOT == "/act/install"


@pytest.mark.parametrize("change", ["digest", "source_hash", "install_hash", "outside_install", "interpreter", "no_provenance"])
def test_an_image_mode_record_that_differs_from_the_identity_is_refused(change):
    document = image_mode_record()
    if change == "digest": document["image_digest"] = "sha256:" + "0" * 64
    elif change == "source_hash": document["provenance"]["package_source_sha256"] = "3" * 64
    elif change == "install_hash": document["provenance"]["install_sha256"] = "3" * 64
    elif change == "outside_install": document["provenance"]["runtime"]["package_prefixes"]["so101_demo_py"] = "/opt/ros/jazzy"
    elif change == "interpreter": document["provenance"]["runtime"]["interpreter"] = "/usr/bin/python3"
    else: del document["provenance"]
    assert problem(document) is True


def test_an_image_mode_record_that_names_a_mount_is_refused_and_a_mounted_one_needs_its_mount():
    mount = {"commit": "a" * 40, "root": "/build/mount/aaaaaaaaaaaa"}
    assert problem(image_mode_record(mount_build=mount)) is True
    assert problem(image_mode_record(), mount) is True


def test_no_launch_side_module_names_the_image_install_root_or_the_image_bootstrap_files():
    """Every caller of the image-record shape is the legacy verifier or mount-only (the inventory of the migration design)."""

    launch_side = [path for pattern in ("runtime/container_campaign/*.py", "runtime/act_rollout/*.py", "cli/campaign_*.py")
                   for path in SRC.glob(pattern)]
    assert launch_side
    offenders = []
    for path in launch_side:
        text = path.read_text()
        if re.search(r"/act/install|/act/source|/act/image-role|/act/provenance\.json", text):
            offenders.append(path.name)
    assert offenders == [] or set(offenders) <= {"paths.py"}, offenders          # paths.py only refuses these mount targets


def test_the_legacy_copy_of_the_readback_check_does_not_depend_on_the_production_provenance_module():
    source = (SRC / "act" / "legacy_image_records.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(from|import)\s+so101_demo\.runtime", source, re.MULTILINE)
    assert "container_campaign" not in source
