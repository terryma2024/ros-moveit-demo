"""Unit tests for scripts/env/so101_env.py: fixture manifests only, no real apt."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "env" / "so101_env.py"


def _load():
    spec = importlib.util.spec_from_file_location("so101_env", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["so101_env"] = module
    spec.loader.exec_module(module)
    return module


env = _load()


def _manifest():
    return {
        "os": {"codename": "noble", "version_id": "24.04"},
        "python3": "3.12.3",
        "kernel": "7.0.0",
        "nvidia": {"driver": "595.99", "gpu_model": "A", "gpu_uuid": "GPU-1"},
        "docker": {"version": "29.1.3"},
        "host": {"cpu": "cpu-a", "memory_kb": 100},
        "apt_sources_sha256": "aaa",
        "apt": {
            "ros-jazzy-rclpy": "7.1.12-1noble.20260915.100000",
            "ros-jazzy-foo": "1.0.0-1noble.20260915.100000",
            "rsync": "3.2.7-1ubuntu1",
        },
        "venvs": {
            "so101-act-train": {
                "python_version": "3.12.3",
                "system_site_packages": False,
                "freeze": ["numpy==2.2.6", "torch==2.11.0+cu128"],
                "freeze_sha256": "f1",
                "torch": "2.11.0+cu128 12.8",
            }
        },
        "tools": {"gate/run.zsh": "h1", "README.md": "h2"},
    }


def _same_host():
    return copy.deepcopy(_manifest())


def _classes(rows):
    return {(r["class"], r["key"], r["relation"]) for r in rows}


# -- version comparison ------------------------------------------------------

@pytest.mark.parametrize("a,b,expected", [
    ("7.1.12-1noble.20260915.100000", "7.1.11-1noble.20260601.100000", 1),
    ("7.1.12-1noble.20260915.100000", "7.1.12-1noble.20261001.100000", -1),
    ("1:1.0-1", "2.0-1", 1),                  # epoch dominates
    ("1.0~rc1-1", "1.0-1", -1),               # tilde sorts before release
    ("1.0-1", "1.0-1", 0),
    ("1.0+dfsg-1", "1.0-1", 1),
    ("2.10-1", "2.9-1", 1),                   # numeric, not lexical
    ("1.0a-1", "1.0-1", 1),
    ("4.45.2-1noble.20260610.1", "4.48.1-1noble.20260901.1", -1),
])
def test_compare_versions(a, b, expected):
    assert env.compare_versions(a, b) == expected
    assert env.compare_versions(b, a) == -expected


# -- diff classification -----------------------------------------------------

def test_identical_hosts_have_no_differences():
    assert env.diff_manifests(_manifest(), _same_host()) == []


def test_apt_difference_is_must_match_and_reports_direction():
    actual = _same_host()
    actual["apt"]["ros-jazzy-rclpy"] = "7.1.13-1noble.20261010.100000"
    actual["apt"]["ros-jazzy-foo"] = "0.9.0-1noble.20260101.100000"
    del actual["apt"]["rsync"]
    rows = env.diff_manifests(_manifest(), actual)
    assert (env.MUST, "apt:ros-jazzy-rclpy", "newer") in _classes(rows)
    assert (env.MUST, "apt:ros-jazzy-foo", "older") in _classes(rows)
    assert (env.MUST, "apt:rsync", "missing") in _classes(rows)
    assert len(env.must_failures(rows)) == 3


def test_extra_ros_package_is_a_warning_only():
    actual = _same_host()
    actual["apt"]["ros-jazzy-extra"] = "1.0-1"
    actual["apt"]["vim"] = "9.0"
    rows = env.diff_manifests(_manifest(), actual)
    assert _classes(rows) == {(env.SHOULD, "apt:ros-jazzy-extra", "extra")}
    assert env.must_failures(rows) == []


def test_driver_docker_and_patch_python_are_should_match():
    actual = _same_host()
    actual["nvidia"]["driver"] = "595.84"
    actual["docker"]["version"] = "28.0"
    actual["python3"] = "3.12.4"
    rows = env.diff_manifests(_manifest(), actual)
    assert {r["class"] for r in rows} == {env.SHOULD}
    assert env.must_failures(rows) == []


def test_python_minor_and_codename_are_must_match():
    actual = _same_host()
    actual["python3"] = "3.13.0"
    actual["os"]["codename"] = "jammy"
    keys = {r["key"] for r in env.must_failures(env.diff_manifests(_manifest(), actual))}
    assert keys == {"python3.minor", "os.codename"}


def test_gpu_cpu_memory_kernel_sources_are_host_specific():
    actual = _same_host()
    actual["nvidia"].update(gpu_model="B", gpu_uuid="GPU-2")
    actual["host"] = {"cpu": "cpu-b", "memory_kb": 200}
    actual["kernel"] = "6.8.0"
    actual["apt_sources_sha256"] = "bbb"
    rows = env.diff_manifests(_manifest(), actual)
    assert {r["class"] for r in rows} == {env.HOST}
    assert len(rows) == 6


def test_venv_freeze_difference_lists_packages():
    actual = _same_host()
    venv = actual["venvs"]["so101-act-train"]
    venv["freeze"] = ["numpy==2.3.0", "torch==2.11.0+cu128"]
    venv["freeze_sha256"] = "f2"
    rows = env.diff_manifests(_manifest(), actual)
    keys = _classes(rows)
    assert (env.MUST, "venv:so101-act-train.freeze_sha256", "differ") in keys
    assert (env.MUST, "venv:so101-act-train.pkg", "missing") in keys
    assert (env.MUST, "venv:so101-act-train.pkg", "extra") in keys


def test_missing_venv_and_extra_venv():
    actual = _same_host()
    actual["venvs"] = {"other": copy.deepcopy(_manifest()["venvs"]["so101-act-train"])}
    keys = _classes(env.diff_manifests(_manifest(), actual))
    assert (env.MUST, "venv:so101-act-train", "missing") in keys
    assert (env.SHOULD, "venv:other", "extra") in keys


def test_tools_hash_difference_missing_and_extra_are_must_match():
    actual = _same_host()
    actual["tools"] = {"gate/run.zsh": "CHANGED", "new.txt": "h9"}
    keys = _classes(env.diff_manifests(_manifest(), actual))
    assert (env.MUST, "tools:gate/run.zsh", "differ") in keys
    assert (env.MUST, "tools:README.md", "missing") in keys
    assert (env.MUST, "tools:new.txt", "extra") in keys


def test_format_table_groups_by_class_and_truncates():
    actual = _same_host()
    for i in range(5):
        actual["apt"][f"ros-jazzy-n{i}"] = "1"
    text = env.format_table(env.diff_manifests(_manifest(), actual), limit=2)
    assert "MUST MATCH: 0" in text
    assert "SHOULD MATCH (warnings): 5" in text
    assert "3 more" in text


# -- apply planning ------------------------------------------------------------

def _stale_host():
    state = copy.deepcopy(_manifest())
    state["apt"]["ros-jazzy-rclpy"] = "7.1.11-1noble.20260601.100000"
    return state


def test_plan_noop_when_host_matches():
    plan = env.plan_apply(_manifest(), _same_host())
    assert [a["kind"] for a in plan] == ["apt_hold", "check"]


def test_plan_refuses_other_lts_codename():
    state = _same_host()
    state["os"]["codename"] = "jammy"
    with pytest.raises(env.ApplyRefused, match="codename"):
        env.plan_apply(_manifest(), state)


def test_plan_installs_exact_versions_then_holds_then_checks():
    available = {"ros-jazzy-rclpy": ["7.1.12-1noble.20260915.100000"]}
    plan = env.plan_apply(_manifest(), _stale_host(), available)
    kinds = [a["kind"] for a in plan]
    assert kinds == ["apt_simulate", "apt_install", "apt_hold", "check"]
    assert plan[1]["specs"] == ["ros-jazzy-rclpy=7.1.12-1noble.20260915.100000"]
    assert plan[2]["packages"] == sorted(_manifest()["apt"])


def test_plan_downgrade_is_planned_like_an_upgrade():
    state = _same_host()
    state["apt"]["ros-jazzy-foo"] = "2.0.0-1noble.20261001.1"
    plan = env.plan_apply(_manifest(), state, {"ros-jazzy-foo": ["1.0.0-1noble.20260915.100000"]})
    assert plan[1]["specs"] == ["ros-jazzy-foo=1.0.0-1noble.20260915.100000"]


def test_plan_stops_when_version_unavailable_without_snapshot():
    with pytest.raises(env.ApplyRefused, match="snapshot"):
        env.plan_apply(_manifest(), _stale_host(), {"ros-jazzy-rclpy": ["7.1.13-1"]})


def test_plan_adds_snapshot_source_when_requested():
    plan = env.plan_apply(_manifest(), _stale_host(), {}, snapshot_date="2026-09-16")
    assert plan[0]["kind"] == "add_snapshot_source"
    assert "snapshots.ros.org/jazzy/2026-09-16/ubuntu noble main" in plan[0]["line"]
    assert plan[1]["kind"] == "apt_update"


def test_plan_rebuilds_only_differing_venvs_and_moves_old_aside():
    state = _same_host()
    state["venvs"]["so101-act-train"]["freeze_sha256"] = "other"
    plan = env.plan_apply(_manifest(), state, work_root="/w", stamp="T1")
    venv = [a for a in plan if a["kind"] == "venv_rebuild"][0]
    assert venv["path"] == "/w/venvs/so101-act-train"
    assert venv["move_aside_to"] == "/w/venvs/so101-act-train.pre-align-T1"
    state["venvs"] = {}
    venv = [a for a in env.plan_apply(_manifest(), state, work_root="/w")
            if a["kind"] == "venv_rebuild"][0]
    assert venv["move_aside_to"] is None


def test_plan_replaces_tools_only_when_hashes_differ():
    state = _same_host()
    assert "tools_replace" not in [a["kind"] for a in env.plan_apply(_manifest(), state)]
    state["tools"] = {}
    plan = env.plan_apply(_manifest(), state, work_root="/w", stamp="T1")
    tools = [a for a in plan if a["kind"] == "tools_replace"][0]
    assert tools["move_aside_to"] is None
    state["tools"] = {"old": "x"}
    tools = [a for a in env.plan_apply(_manifest(), state, work_root="/w", stamp="T1")
             if a["kind"] == "tools_replace"][0]
    assert tools["move_aside_to"] == "/w/so101-tools.pre-align-T1"


# -- parsers -------------------------------------------------------------------

def test_parse_dpkg_query_keeps_installed_and_held_only():
    text = ("ii \tros-jazzy-a\t1.0-1\nhi \tros-jazzy-b\t2.0-1\n"
            "rc \tgone\t3\nii \tlibc6:amd64\t2.39\n")
    assert env.parse_dpkg_query(text) == {
        "ros-jazzy-a": "1.0-1", "ros-jazzy-b": "2.0-1", "libc6": "2.39"}


def test_parse_os_release_and_nvidia():
    parsed = env.parse_os_release('ID=ubuntu\nVERSION_ID="24.04"\nVERSION_CODENAME=noble\n')
    assert parsed["codename"] == "noble" and parsed["version_id"] == "24.04"
    smi = env.parse_nvidia_smi("595.99.02, NVIDIA GeForce RTX 5060 Ti, GPU-abc\n")
    assert smi == {"driver": "595.99.02", "gpu_model": "NVIDIA GeForce RTX 5060 Ti",
                   "gpu_uuid": "GPU-abc"}


def test_freeze_is_sorted_and_hash_is_order_independent():
    a = env.normalize_freeze("b==1\n# c\na==2\n\n")
    assert a == ["a==2", "b==1"]
    assert env.freeze_sha(a) == env.freeze_sha(env.normalize_freeze("a==2\nb==1"))


def test_package_xml_dependencies_and_scope():
    xml = ("<package><name>x</name><depend>rclpy</depend><exec_depend>python3-numpy"
           "</exec_depend><test_depend>ament_lint</test_depend></package>")
    assert env.package_xml_dependencies(xml) == {"rclpy", "python3-numpy", "ament_lint"}
    installed = {"ros-jazzy-rclpy": "1", "python3-numpy": "2", "rsync": "3",
                 "libgz-math7": "4", "vim": "5"}
    scope = env.select_apt_scope(installed, {"python3-numpy"})
    assert set(scope) == {"ros-jazzy-rclpy", "python3-numpy", "rsync", "libgz-math7"}


def test_removals_and_wheel_indexes():
    out = "Inst a\nRemv ros-jazzy-old [1]\nRemv other (2)\n"
    assert env.removals_in_simulation(out) == ["ros-jazzy-old", "other"]
    assert env.wheel_extra_indexes(["torch==2.11.0+cu128", "x==1", "tv==2+cu128"]) == [
        "https://download.pytorch.org/whl/cu128"]


def test_collect_tools_hashes_files_and_symlinks_and_skips_caches(tmp_path):
    (tmp_path / "gate").mkdir()
    (tmp_path / "gate" / "a.zsh").write_text("x")
    (tmp_path / "gate" / "__pycache__").mkdir()
    (tmp_path / "gate" / "__pycache__" / "a.pyc").write_text("y")
    (tmp_path / "link").symlink_to("/somewhere")
    hashes = env.collect_tools(tmp_path)
    assert set(hashes) == {"gate/a.zsh", "link"}
    assert hashes["link"] == "symlink:/somewhere"


def test_capture_accepts_no_rosdep_flag():
    args = env.build_parser().parse_args(["capture", "--no-rosdep"])
    assert args.no_rosdep is True


def test_select_apt_scope_includes_wanted_names():
    chosen = env.select_apt_scope({"foo": "1", "bar": "2", "ros-jazzy-x": "3"}, {"foo"})
    assert set(chosen) == {"foo", "ros-jazzy-x"}


def test_gl_apt_prefixes_in_scope_and_nvidia_excluded():
    chosen = env.select_apt_scope({"libegl1": "1", "libgl1-mesa-dri": "2", "libglvnd0": "3", "libnvidia-gl-595": "4", "vim": "5"}, set())
    assert set(chosen) == {"libegl1", "libgl1-mesa-dri", "libglvnd0"}


def test_glvnd_vendor_file_missing_is_must_hash_differ_is_should():
    expected = _manifest()
    expected["gl"] = {"egl_vendor_files": {"a.json": "h", "b.json": "h"}, "nvidia_userland": {"libnvidia-gl-595": "1"}}
    actual = copy.deepcopy(expected)
    actual["gl"]["egl_vendor_files"] = {"b.json": "other"}
    actual["gl"]["nvidia_userland"] = {}
    rows = {r["key"]: r["class"] for r in env.diff_manifests(expected, actual)}
    assert rows["glvnd:a.json"] == "must"
    assert rows["glvnd:b.json"] == "should"
    assert rows["nvidia-userland:libnvidia-gl-595"] == "should"


def test_gl_probe_fails_closed_without_venv(tmp_path):
    ok, detail = env.gl_probe(tmp_path)
    assert ok is False and "missing" in detail


def test_reference_source_changes_only_ros_and_gazebo_files():
    manifest = {"apt_sources": {
        "ros2.list": "deb [signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://mirror/ros2 noble main\n",
        "ubuntu.sources": "Types: deb\n", "sources.list": "x"}}
    state = {"apt_sources": {"ros2.list": "deb [signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2 noble main\n", "ubuntu.sources": "other"}}
    assert list(env.reference_source_changes(manifest, state)) == ["ros2.list"]
    state["apt_sources"]["ros2.list"] = manifest["apt_sources"]["ros2.list"]
    assert env.reference_source_changes(manifest, state) == {}
