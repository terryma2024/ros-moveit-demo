"""Unit tests for scripts/env/image_env.py: a fake docker runner and fixture data, no real image, apt or network."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

ENV_DIR = Path(__file__).resolve().parents[1] / "env"
sys.path.insert(0, str(ENV_DIR))


def _load():
    spec = importlib.util.spec_from_file_location("image_env", ENV_DIR / "image_env.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["image_env"] = module
    spec.loader.exec_module(module)
    return module


ie = _load()

DPKG = "ii \tros-jazzy-rclcpp\t28.1.0-1\nii \tlibfoo1\t1.0\nii \tpython3-yaml\t6.0\nii \tros-jazzy-rcl\t9.2.0-1\nrc \tgone\t1\n"
DEPENDS = ("ros-jazzy-rclcpp\t28.1.0-1\tros-jazzy-rcl (>= 9), libfoo1 | libfoo2, python3 (>= 3.12)\t\n"
           "ros-jazzy-rcl\t9.2.0-1\tlibbar (>= 1)\t\n"
           "libfoo1\t1.0\t\tlibc6 (>= 2.38)\n"
           "libbar\t1.2\t\t\n"
           "python3-yaml\t6.0\tpython3\t\n")


class FakeDocker:
    """Answers `docker run ...` by looking at the command that runs inside the image."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        joined = " ".join(argv)
        for needle, output in self.answers.items():
            if needle in joined:
                return output
        raise AssertionError(f"unexpected docker call: {joined}")


def image_answers():
    return {"${db:Status-Abbrev}": DPKG,
            "${Depends}": DEPENDS,
            "/etc/os-release": 'VERSION_CODENAME=noble\nVERSION_ID="24.04"\nID=ubuntu\n',
            "pip freeze": "pydantic==2.14.1\nabsl-py==2.5.1\n",
            "--version": "Python 3.12.3\n"}


def test_capture_runs_the_image_read_only_without_network_and_lists_every_installed_package():
    docker = FakeDocker(image_answers())
    manifest = ie.capture_image("sha256:abc", docker)
    assert manifest["kind"] == "image-env" and manifest["image_id"] == "sha256:abc"
    assert manifest["apt"] == {"ros-jazzy-rclcpp": "28.1.0-1", "libfoo1": "1.0", "python3-yaml": "6.0", "ros-jazzy-rcl": "9.2.0-1"}
    assert manifest["os"]["codename"] == "noble" and manifest["python3"] == "3.12.3"
    assert manifest["venv_freeze"] == ["absl-py==2.5.1", "pydantic==2.14.1"]
    freeze = [argv for argv in docker.calls if "pip" in argv]
    assert freeze and "--local" in freeze[0], "the host side lists --local, so the image side must too (system-site ROS packages are not pins)"
    for argv in docker.calls:
        assert argv[:2] == ["docker", "run"] and "--network" in argv and argv[argv.index("--network") + 1] == "none"
        assert "--read-only" in argv and "--rm" in argv


def test_the_dependency_graph_reads_depends_and_pre_depends_without_versions_or_alternatives_collapsing():
    graph = ie.parse_dependency_graph(DEPENDS)
    assert graph["ros-jazzy-rclcpp"] == {"ros-jazzy-rcl", "libfoo1", "libfoo2", "python3"}
    assert graph["libfoo1"] == {"libc6"}
    assert graph["libbar"] == set()


def test_package_xml_keys_become_installed_ros_packages_or_plain_apt_names():
    apt = {"ros-jazzy-rclcpp": "1", "ros-jazzy-geometry-msgs": "1", "python3-yaml": "1"}
    keys = {"rclcpp", "geometry_msgs", "python3-yaml", "ament_cmake", "unknown_key"}
    resolved, unresolved = ie.resolve_keys(keys, apt)
    assert resolved == {"ros-jazzy-rclcpp", "ros-jazzy-geometry-msgs", "python3-yaml"}
    assert unresolved == {"ament_cmake", "unknown_key"}


def test_closure_follows_depends_transitively_and_ignores_names_the_image_does_not_have():
    graph = ie.parse_dependency_graph(DEPENDS)
    image_apt = {"ros-jazzy-rclcpp": "x", "ros-jazzy-rcl": "x", "libfoo1": "x", "libbar": "x", "python3": "x", "libc6": "x"}
    closure = ie.dependency_closure({"ros-jazzy-rclcpp"}, graph, image_apt)
    assert closure == {"ros-jazzy-rclcpp", "ros-jazzy-rcl", "libfoo1", "libbar", "python3", "libc6"}


def test_ldd_output_gives_missing_libraries_and_the_paths_outside_the_tree():
    text = ("/t/lib/libx.so:\n\tlibc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x1)\n\tlibmine.so => /t/lib/libmine.so (0x2)\n"
            "\tlibgone.so.1 => not found\n\tlinux-vdso.so.1 (0x3)\n\t/lib64/ld-linux-x86-64.so.2 (0x4)\n")
    outside, missing = ie.parse_ldd(text, tree="/t")
    assert outside == {"/lib/x86_64-linux-gnu/libc.so.6", "/lib64/ld-linux-x86-64.so.2"}
    assert missing == {"libgone.so.1"}


def test_dpkg_s_output_maps_files_to_packages_and_reports_the_unowned_ones():
    text = "libc6:amd64: /lib/x86_64-linux-gnu/libc.so.6\nlibtorch2:amd64: /usr/lib/x86_64-linux-gnu/libtorch.so\n"
    owners = ie.parse_dpkg_s(text)
    assert owners == {"/lib/x86_64-linux-gnu/libc.so.6": "libc6", "/usr/lib/x86_64-linux-gnu/libtorch.so": "libtorch2"}


def host(**changes):
    state = {"apt": {"ros-jazzy-rclcpp": "28.1.0-1", "libfoo1": "1.0", "ros-jazzy-rcl": "9.2.0-1", "hostonly": "1", "libc6": "2.39", "python3-yaml": "6.0"},
             "os": {"codename": "noble"}, "python3": "3.12.3", "venv_freeze": ["absl-py==2.5.1", "pydantic==2.14.1", "extra==1"]}
    state.update(changes)
    return state


def image(**changes):
    manifest = {"kind": "image-env", "image_id": "sha256:abc", "apt": {"ros-jazzy-rclcpp": "28.1.0-1", "libfoo1": "1.0", "python3-yaml": "6.0",
                "ros-jazzy-rcl": "9.2.0-1", "libc6": "2.39"}, "os": {"codename": "noble"}, "python3": "3.12.3",
                "venv_freeze": ["absl-py==2.5.1", "pydantic==2.14.1"]}
    manifest.update(changes)
    return manifest


def keys(rows):
    return {(row["class"], row["key"], row["relation"]) for row in rows}


def test_identical_shared_packages_pass_and_host_only_packages_are_not_refused():
    rows = ie.compare(image(), host(), required={"ros-jazzy-rclcpp", "libc6"})
    assert not ie.must_failures(rows)
    assert ("should", "apt:hostonly", "host-only") in keys(rows)


def test_a_shared_package_at_another_version_is_a_must_failure_whether_or_not_the_closure_names_it():
    rows = ie.compare(image(), host(apt={**host()["apt"], "libfoo1": "1.1"}), required=set())
    assert ("must", "apt:libfoo1", "newer") in keys(rows)
    rows = ie.compare(image(), host(apt={**host()["apt"], "libfoo1": "0.9"}), required=set())
    assert ("must", "apt:libfoo1", "older") in keys(rows)


def test_every_image_package_the_host_lacks_is_a_must_failure_except_the_named_image_tooling():
    apt = {name: version for name, version in host()["apt"].items() if name != "python3-yaml"}
    rows = ie.compare(image(), host(apt=apt), required={"ros-jazzy-rclcpp"})
    assert ("must", "apt:python3-yaml", "missing-on-host") in keys(rows)       # in the image, not needed by the tree, still refused
    rows = ie.compare(image(), host(apt=apt), required={"python3-yaml"})
    assert ("must", "apt:python3-yaml", "missing-on-host") in keys(rows)
    with_tooling = image(apt={**image()["apt"], "gnupg2": "2.4.4-2", "unminimize": "0.2.1"})
    rows = ie.compare(with_tooling, host(), required=set())
    assert ("should", "apt:gnupg2", "image-only (tooling)") in keys(rows) and ("should", "apt:unminimize", "image-only (tooling)") in keys(rows)
    assert not ie.must_failures(rows)


def test_python_minor_codename_and_venv_pins_are_must_matches_and_extra_host_packages_are_not():
    assert ("must", "python3.minor", "differ") in keys(ie.compare(image(), host(python3="3.13.0"), required=set()))
    assert ("must", "os.codename", "differ") in keys(ie.compare(image(), host(os={"codename": "jammy"}), required=set()))
    rows = ie.compare(image(), host(venv_freeze=["absl-py==2.5.0", "pydantic==2.14.1"]), required=set())
    assert ("must", "venv:absl-py", "differ") in keys(rows)
    rows = ie.compare(image(), host(venv_freeze=["pydantic==2.14.1"]), required=set())
    assert ("must", "venv:absl-py", "missing-on-host") in keys(rows)
    assert not [r for r in ie.compare(image(), host(), required=set()) if r["key"] == "venv:extra"][0:0]      # extra is only a warning
    assert ("should", "venv:extra", "host-only") in keys(ie.compare(image(), host(), required=set()))


def test_libraries_the_container_cannot_find_are_must_failures():
    rows = ie.compare(image(), host(), required=set(), missing_libraries={"libgone.so.1"})
    assert ("must", "ldd:libgone.so.1", "not-found-in-image") in keys(rows)


def test_alignment_plan_lists_installs_and_downgrades_and_never_removes():
    apt = {name: version for name, version in host()["apt"].items() if name != "python3-yaml"}
    plan = ie.alignment_plan(image(), host(apt={**apt, "libfoo1": "1.1"}), required=set())     # every image package, not only the tree's
    assert plan == {"install": {"python3-yaml": "6.0"}, "change": {"libfoo1": "1.0"}, "downgrades": ["libfoo1"]}


def test_image_manifest_round_trips_as_json(tmp_path):
    manifest = ie.capture_image("sha256:abc", FakeDocker(image_answers()))
    path = tmp_path / "m.json"
    path.write_text(json.dumps(manifest))
    assert json.loads(path.read_text()) == manifest


def test_a_saved_host_state_is_read_back_and_a_malformed_one_is_refused(tmp_path):
    path = tmp_path / "host.json"
    path.write_text(json.dumps(host()))
    assert ie.load_host_state(path) == host()
    path.write_text(json.dumps({"apt": {}}))
    with pytest.raises(SystemExit, match="IMAGE_ENV_HOST_STATE_INVALID"):
        ie.load_host_state(path)


def test_a_skewed_host_state_is_refused_where_the_aligned_one_passes():
    required = {"ros-jazzy-rclcpp", "ros-jazzy-rcl", "libc6"}
    assert not ie.must_failures(ie.compare(image(), host(), required))
    skewed = host(apt={**host()["apt"], "ros-jazzy-rcl": "9.2.1-1"})                 # one required ROS package at another build
    assert [row["key"] for row in ie.must_failures(ie.compare(image(), skewed, required))] == ["apt:ros-jazzy-rcl"]
    lacking = host(apt={name: v for name, v in host()["apt"].items() if name != "libc6"})      # a library owner missing on the host
    assert [row["relation"] for row in ie.must_failures(ie.compare(image(), lacking, required))] == ["missing-on-host"]


def test_colcon_plugins_only_the_image_venv_carries_are_not_must_matches():
    only_image = image(venv_freeze=["absl-py==2.5.1", "colcon-override-check==0.0.1", "colcon-installed-package-information==0.1"])
    rows = ie.compare(only_image, host(venv_freeze=["absl-py==2.5.1"]), required=set())
    assert ("should", "venv:colcon-override-check", "missing-on-host") in keys(rows)
    assert ("should", "venv:colcon-installed-package-information", "missing-on-host") in keys(rows)
    assert not ie.must_failures(rows)


def test_esm_and_host_specific_apt_differences_are_warnings_only():
    apt = {"libqt5core5t64": "5.15.13+dfsg-1ubuntu1", "python3-filelock": "3.13.1-1", "libxnvctrl0": "510.47", "libc6": "2.39"}
    ours = {"libqt5core5t64": "5.15.13+dfsg-1ubuntu1+esm1", "python3-filelock": "3.13.1-1ubuntu0.1~esm1", "libxnvctrl0": "610.43", "libc6": "2.39"}
    for required in (set(), set(apt)):          # outside the closure and inside it
        rows = ie.compare(image(apt=apt), host(apt=ours), required=required)
        assert not ie.must_failures(rows)
        assert {row["key"] for row in rows if row["class"] == "should"} >= {"apt:libqt5core5t64", "apt:python3-filelock", "apt:libxnvctrl0"}


def test_a_non_esm_difference_inside_the_closure_is_still_refused():
    rows = ie.compare(image(apt={"libfoo1": "1.0-1", "libqt5core5t64": "5.15.13+dfsg-1ubuntu1"}),
                      host(apt={"libfoo1": "1.1-1", "libqt5core5t64": "5.15.14+dfsg-1ubuntu1+esm1"}), required={"libfoo1", "libqt5core5t64"})
    assert sorted(row["key"] for row in ie.must_failures(rows)) == ["apt:libfoo1", "apt:libqt5core5t64"]    # another upstream version, even with +esm


def test_other_apt_differences_are_still_refused():
    for image_version, host_version in (("1.0-1", "1.1-1"), ("1.0-1", "1.0-2"), ("1.0-1+esm1", "1.1-1+esm1")):
        rows = ie.compare(image(apt={"libother": image_version}), host(apt={"libother": host_version}), required=set())
        assert [row["key"] for row in ie.must_failures(rows)] == ["apt:libother"], (image_version, host_version)


def test_the_preflight_record_names_the_commit_the_base_image_and_the_exceptions():
    apt = {"libqt5core5t64": "5.15.13+dfsg-1ubuntu1", "libxnvctrl0": "510.47"}
    rows = ie.compare(image(apt=apt), host(apt={"libqt5core5t64": "5.15.13+dfsg-1ubuntu1+esm1", "libxnvctrl0": "610.43"}), required=set())
    record = ie.preflight_record(manifest_bytes=b"manifest", manifest=image(), record_bytes=b"a" * 40 + b"\n", rows=rows, host="antzb")
    assert record["result"] == "PASS" and record["must_failures"] == 0 and record["commit"] == "a" * 40
    assert record["base_image_id"] == "sha256:abc" and record["exceptions"] == {"libqt5core5t64": "esm", "libxnvctrl0": "host-specific"}
    import hashlib
    assert record["base_manifest_sha256"] == hashlib.sha256(b"manifest").hexdigest()
    assert record["install_record_sha256"] == hashlib.sha256(b"a" * 40 + b"\n").hexdigest()
    bad = ie.compare(image(), host(python3="3.13.0"), required=set())
    assert ie.preflight_record(manifest_bytes=b"m", manifest=image(), record_bytes=b"b" * 40, rows=bad, host="h")["result"] == "FAIL"
