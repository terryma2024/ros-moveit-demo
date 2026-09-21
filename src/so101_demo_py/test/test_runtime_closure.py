"""Contract tests for the macOS task runtime closure (design section 4.1).

These tests drive the RED/GREEN boundary of Task 1 of the macOS service campaign closure
plan. They import the module under test lazily so that a missing implementation is reported
as a failed assertion (a real RED) instead of a collection error, and they never start a
process: every child, identity and loaded-image probe is injected.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE_COMMIT = "a" * 40
SUBMODULE_COMMIT = "b" * 40


def _closure_module():
    spec = importlib.util.find_spec("so101_demo.runtime.runtime_closure")
    assert spec is not None, "so101_demo.runtime.runtime_closure is not implemented yet"
    return importlib.import_module("so101_demo.runtime.runtime_closure")


def _stack_module():
    spec = importlib.util.find_spec("so101_demo.runtime.task_stack")
    assert spec is not None
    return importlib.import_module("so101_demo.runtime.task_stack")


def _install_tree(root: Path) -> Path:
    """A synthetic copied install prefix with one file of every inventory class."""

    (root / "lib" / "so101_demo_py").mkdir(parents=True)
    (root / "share" / "so101_demo_py" / "config" / "mujoco").mkdir(parents=True)
    (root / "lib" / "so101_demo_py" / "runtime").mkdir(parents=True)
    executable = root / "lib" / "so101_demo_py" / "so101_macos_service_campaign"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    library = root / "lib" / "libmujoco_ros2_control.dylib"
    library.write_bytes(b"dylib-bytes-a")
    config = (
        root
        / "share"
        / "so101_demo_py"
        / "config"
        / "mujoco"
        / "parallel_batch_v4_macos_mps_w2.yaml"
    )
    config.write_text("schema_version: 4\n", encoding="utf-8")
    module = root / "lib" / "so101_demo_py" / "runtime" / "runtime_closure.py"
    module.write_text("# installed module\n", encoding="utf-8")
    plugin = root / "share" / "so101_demo_py" / "config" / "mujoco_plugins.yaml"
    plugin.write_text("plugin: mujoco\n", encoding="utf-8")
    return root


def _install_tree_with_vendor_alias(root: Path) -> Path:
    install = _install_tree(root)
    vendor = install / "opt" / "mujoco_vendor" / "lib"
    vendor.mkdir(parents=True)
    target = vendor / "libmujoco.3.4.0.dylib"
    target.write_bytes(b"mujoco-3.4.0")
    (vendor / "libmujoco.dylib").symlink_to(target.name)
    return install


def _closure(module, install: Path, *, environment=None, forbidden=()):
    from collections.abc import Mapping

    return module.build_runtime_closure_identity(
        install_root=install,
        source_commit=SOURCE_COMMIT,
        mujoco_ros2_control_commit=SUBMODULE_COMMIT,
        environment=environment if environment is not None else {"DYLD_LIBRARY_PATH": "/x"},
        forbidden_roots=tuple(forbidden),
    )


def _binding(module, tmp_path: Path, *, suffix: str = "a", domain: int = 41, generation: int = 1):
    return module.build_run_binding(
        campaign_id=f"campaign-{suffix}",
        batch_id=f"batch-{suffix}",
        ros_domain_id=domain,
        station_session_id=f"session-{suffix}",
        evidence_root=tmp_path / f"evidence-{suffix}",
        owner_generation=generation,
        started_monotonic_ns=1_000 + generation,
    )


# --------------------------------------------------------------------------------------
# Stable closure identity, per-run binding, per-run attestation
# --------------------------------------------------------------------------------------


def test_closure_identity_is_stable_across_fresh_domain_session_and_evidence_root(
    tmp_path: Path,
) -> None:
    module = _closure_module()
    install = _install_tree(tmp_path / "install")
    first = _closure(
        module,
        install,
        environment={
            "DYLD_LIBRARY_PATH": "/frozen/lib",
            "ROS_DOMAIN_ID": "41",
            "GZ_PARTITION": "partition-a",
            "ROS_HOME": "/run/a/ros",
            "TMPDIR": "/run/a/tmp",
            "PATH": "/usr/bin:/bin",
        },
    )
    second = _closure(
        module,
        install,
        environment={
            "DYLD_LIBRARY_PATH": "/frozen/lib",
            "ROS_DOMAIN_ID": "77",
            "GZ_PARTITION": "partition-b",
            "ROS_HOME": "/run/b/ros",
            "TMPDIR": "/run/b/tmp",
            "PATH": "/usr/bin:/bin",
        },
    )

    assert first.sha256 == second.sha256
    assert first.install_inventory_sha256 == second.install_inventory_sha256
    assert first.normalized_environment_sha256 == second.normalized_environment_sha256
    assert "ROS_DOMAIN_ID" not in str(first.as_document())
    assert "partition-a" not in str(first.as_document())


def test_environment_replacements_change_the_closure_only_when_semantic(
    tmp_path: Path,
) -> None:
    module = _closure_module()
    install = _install_tree(tmp_path / "install")
    base = _closure(module, install, environment={"DYLD_LIBRARY_PATH": "/frozen/lib"})
    moved = _closure(module, install, environment={"DYLD_LIBRARY_PATH": "/other/lib"})
    absent = _closure(module, install, environment={})

    assert base.normalized_environment_sha256 != moved.normalized_environment_sha256
    assert base.normalized_environment_sha256 != absent.normalized_environment_sha256
    assert base.sha256 != moved.sha256


def test_run_binding_and_attestation_hashes_are_unique_per_run(tmp_path: Path) -> None:
    module = _closure_module()
    install = _install_tree(tmp_path / "install")
    closure = _closure(module, install)
    first_binding = _binding(module, tmp_path, suffix="a", domain=41, generation=1)
    second_binding = _binding(module, tmp_path, suffix="b", domain=77, generation=2)

    assert first_binding.sha256 != second_binding.sha256

    library = install / "lib" / "libmujoco_ros2_control.dylib"
    first = module.build_runtime_attestation(
        closure=closure,
        run_binding=first_binding,
        install_root=install,
        process_identities=_identities(module, 101, generation=1),
        loaded_images=(library,),
        observed_ros_domain_id=41,
    )
    second = module.build_runtime_attestation(
        closure=closure,
        run_binding=second_binding,
        install_root=install,
        process_identities=_identities(module, 202, generation=2),
        loaded_images=(library,),
        observed_ros_domain_id=77,
    )

    assert first.sha256 != second.sha256
    assert first.closure_sha256 == second.closure_sha256 == closure.sha256
    assert first.run_binding_sha256 == first_binding.sha256
    assert second.run_binding_sha256 == second_binding.sha256


def _identities(module, pid: int, *, generation: int):
    stack = _stack_module()
    return (
        stack.OwnedProcessIdentity(
            role="task-station",
            pid=pid,
            pgid=pid,
            cmdline=("ros2", "launch", "so101_demo_py"),
            start_time_ticks=1_000 + generation,
        ),
    )


# --------------------------------------------------------------------------------------
# Inventory shape, drift, origin and contamination
# --------------------------------------------------------------------------------------


def test_installed_inventory_is_relative_and_classified(tmp_path: Path) -> None:
    module = _closure_module()
    install = _install_tree(tmp_path / "install")
    closure = _closure(module, install)

    everything = (
        closure.executable_inventory + closure.library_inventory + closure.config_inventory
    )
    assert everything
    for entry in everything:
        assert not Path(entry.relative_path).is_absolute()
        assert ".." not in Path(entry.relative_path).parts
        assert (install / entry.relative_path).is_file()

    assert [entry.relative_path for entry in closure.executable_inventory] == [
        "lib/so101_demo_py/so101_macos_service_campaign"
    ]
    assert [entry.relative_path for entry in closure.library_inventory] == [
        "lib/libmujoco_ros2_control.dylib"
    ]
    assert sorted(entry.relative_path for entry in closure.config_inventory) == [
        "share/so101_demo_py/config/mujoco/parallel_batch_v4_macos_mps_w2.yaml",
        "share/so101_demo_py/config/mujoco_plugins.yaml",
    ]


def test_unclassified_installed_bytes_still_change_the_install_inventory(tmp_path: Path) -> None:
    module = _closure_module()
    install = _install_tree(tmp_path / "install")
    before = _closure(module, install)
    module_file = install / "lib" / "so101_demo_py" / "runtime" / "runtime_closure.py"
    module_file.write_text("# installed module, edited\n", encoding="utf-8")
    after = _closure(module, install)

    assert before.install_inventory_sha256 != after.install_inventory_sha256
    assert before.sha256 != after.sha256


def test_config_drift_is_refused_by_verify_runtime_closure(tmp_path: Path) -> None:
    module = _closure_module()
    install = _install_tree(tmp_path / "install")
    expected = _closure(module, install)
    config = (
        install
        / "share"
        / "so101_demo_py"
        / "config"
        / "mujoco"
        / "parallel_batch_v4_macos_mps_w2.yaml"
    )
    config.write_text("schema_version: 4\nworker_count: 2\n", encoding="utf-8")

    with pytest.raises(module.RuntimeClosureError) as error:
        module.verify_runtime_closure(
            expected,
            install_root=install,
            source_commit=SOURCE_COMMIT,
            mujoco_ros2_control_commit=SUBMODULE_COMMIT,
            environment={"DYLD_LIBRARY_PATH": "/x"},
        )
    assert error.value.code == "CLOSURE_INVENTORY_DRIFT"


def test_verify_runtime_closure_returns_the_matching_identity(tmp_path: Path) -> None:
    module = _closure_module()
    install = _install_tree(tmp_path / "install")
    expected = _closure(module, install)
    observed = module.verify_runtime_closure(
        expected,
        install_root=install,
        source_commit=SOURCE_COMMIT,
        mujoco_ros2_control_commit=SUBMODULE_COMMIT,
        environment={"DYLD_LIBRARY_PATH": "/x"},
    )
    assert observed.sha256 == expected.sha256


def test_source_and_submodule_commit_drift_are_distinct_failures(tmp_path: Path) -> None:
    module = _closure_module()
    install = _install_tree(tmp_path / "install")
    expected = _closure(module, install)

    with pytest.raises(module.RuntimeClosureError) as source_error:
        module.verify_runtime_closure(
            expected,
            install_root=install,
            source_commit="c" * 40,
            mujoco_ros2_control_commit=SUBMODULE_COMMIT,
            environment={"DYLD_LIBRARY_PATH": "/x"},
        )
    assert source_error.value.code == "CLOSURE_SOURCE_COMMIT_MISMATCH"

    with pytest.raises(module.RuntimeClosureError) as submodule_error:
        module.verify_runtime_closure(
            expected,
            install_root=install,
            source_commit=SOURCE_COMMIT,
            mujoco_ros2_control_commit="d" * 40,
            environment={"DYLD_LIBRARY_PATH": "/x"},
        )
    assert submodule_error.value.code == "CLOSURE_SUBMODULE_COMMIT_MISMATCH"


def test_missing_submodule_commit_is_refused(tmp_path: Path) -> None:
    module = _closure_module()
    install = _install_tree(tmp_path / "install")
    with pytest.raises(module.RuntimeClosureError) as error:
        module.build_runtime_closure_identity(
            install_root=install,
            source_commit=SOURCE_COMMIT,
            mujoco_ros2_control_commit="",
            environment={"DYLD_LIBRARY_PATH": "/x"},
        )
    assert error.value.code == "CLOSURE_SUBMODULE_COMMIT_MISSING"


def test_environment_drift_is_refused(tmp_path: Path) -> None:
    module = _closure_module()
    install = _install_tree(tmp_path / "install")
    expected = _closure(module, install, environment={"DYLD_LIBRARY_PATH": "/x"})
    with pytest.raises(module.RuntimeClosureError) as error:
        module.verify_runtime_closure(
            expected,
            install_root=install,
            source_commit=SOURCE_COMMIT,
            mujoco_ros2_control_commit=SUBMODULE_COMMIT,
            environment={"DYLD_LIBRARY_PATH": "/y"},
        )
    assert error.value.code == "CLOSURE_ENVIRONMENT_DRIFT"


def test_canonical_checkout_prefix_contamination_is_refused(tmp_path: Path) -> None:
    module = _closure_module()
    checkout = tmp_path / "canonical"
    (checkout / "src").mkdir(parents=True)
    install = _install_tree(checkout / "install" / "so101_demo_py")

    with pytest.raises(module.RuntimeClosureError) as error:
        module.build_runtime_closure_identity(
            install_root=install,
            source_commit=SOURCE_COMMIT,
            mujoco_ros2_control_commit=SUBMODULE_COMMIT,
            environment={"DYLD_LIBRARY_PATH": "/x"},
            forbidden_roots=(checkout,),
        )
    assert error.value.code == "CLOSURE_PREFIX_CONTAMINATION"


def test_symlinked_install_root_and_symlinked_files_are_refused(tmp_path: Path) -> None:
    module = _closure_module()
    real = _install_tree(tmp_path / "real-install")
    linked = tmp_path / "linked-install"
    linked.symlink_to(real, target_is_directory=True)

    with pytest.raises(module.RuntimeClosureError) as root_error:
        _closure(module, linked)
    assert root_error.value.code == "CLOSURE_INSTALL_ROOT_INVALID"

    escape = tmp_path / "outside.dylib"
    escape.write_bytes(b"outside-bytes")
    (real / "lib" / "libescape.dylib").symlink_to(escape)
    with pytest.raises(module.RuntimeClosureError) as file_error:
        _closure(module, real)
    assert file_error.value.code == "CLOSURE_SYMLINK"


def test_only_the_pinned_mujoco_vendor_alias_is_accepted(tmp_path: Path) -> None:
    module = _closure_module()
    install = _install_tree_with_vendor_alias(tmp_path / "install")

    closure = _closure(module, install)

    assert closure.install_root == install.resolve()
    assert [item.relative_path for item in closure.dylib_alias_inventory] == [
        "opt/mujoco_vendor/lib/libmujoco.dylib"
    ]
    alias = closure.dylib_alias_inventory[0]
    assert alias.link_text == "libmujoco.3.4.0.dylib"
    assert alias.target_relative_path == (
        "opt/mujoco_vendor/lib/libmujoco.3.4.0.dylib"
    )
    assert alias.target_sha256 == next(
        item.sha256
        for item in closure.library_inventory
        if item.relative_path == alias.target_relative_path
    )


@pytest.mark.parametrize(
    ("damage", "link_text"),
    [
        ("absolute", "/tmp/libmujoco.3.4.0.dylib"),
        ("escape", "../libmujoco.3.4.0.dylib"),
        ("dangling", "missing.dylib"),
        ("cycle", "libmujoco.dylib"),
        ("wrong", "libmujoco.3.3.0.dylib"),
    ],
)
def test_mujoco_alias_rejects_invalid_link_shapes(
    tmp_path: Path, damage: str, link_text: str
) -> None:
    module = _closure_module()
    install = _install_tree_with_vendor_alias(tmp_path / "install")
    alias = install / "opt/mujoco_vendor/lib/libmujoco.dylib"
    alias.unlink()
    alias.symlink_to(link_text)

    with pytest.raises(module.RuntimeClosureError) as error:
        _closure(module, install)

    assert error.value.code == "CLOSURE_SYMLINK", damage


def test_alias_target_and_alias_replacement_are_detected(tmp_path: Path) -> None:
    module = _closure_module()
    install = _install_tree_with_vendor_alias(tmp_path / "install")
    expected = _closure(module, install)
    target = install / "opt/mujoco_vendor/lib/libmujoco.3.4.0.dylib"
    target.write_bytes(b"replacement")

    with pytest.raises(module.RuntimeClosureError) as target_error:
        module.verify_runtime_closure(
            expected,
            install_root=install,
            source_commit=SOURCE_COMMIT,
            mujoco_ros2_control_commit=SUBMODULE_COMMIT,
            environment={"DYLD_LIBRARY_PATH": "/x"},
        )
    assert target_error.value.code == "CLOSURE_INVENTORY_DRIFT"

    target.write_bytes(b"mujoco-3.4.0")
    alias = install / "opt/mujoco_vendor/lib/libmujoco.dylib"
    alias.unlink()
    alias.write_bytes(b"materialized")
    with pytest.raises(module.RuntimeClosureError) as alias_error:
        module.verify_runtime_closure(
            expected,
            install_root=install,
            source_commit=SOURCE_COMMIT,
            mujoco_ros2_control_commit=SUBMODULE_COMMIT,
            environment={"DYLD_LIBRARY_PATH": "/x"},
        )
    assert alias_error.value.code == "CLOSURE_SYMLINK"


def test_extra_file_and_directory_symlinks_remain_closed(tmp_path: Path) -> None:
    module = _closure_module()
    install = _install_tree_with_vendor_alias(tmp_path / "install")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "extra.dylib").write_bytes(b"extra")
    (install / "lib/extra.dylib").symlink_to(outside / "extra.dylib")

    with pytest.raises(module.RuntimeClosureError) as file_error:
        _closure(module, install)
    assert file_error.value.code == "CLOSURE_SYMLINK"

    (install / "lib/extra.dylib").unlink()
    (install / "share/linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(module.RuntimeClosureError) as directory_error:
        _closure(module, install)
    assert directory_error.value.code == "CLOSURE_SYMLINK"


def test_replacement_race_is_refused(tmp_path: Path, monkeypatch) -> None:
    module = _closure_module()
    install = _install_tree(tmp_path / "install")
    target = install / "lib" / "libmujoco_ros2_control.dylib"
    replacement = tmp_path / "replacement.dylib"
    replacement.write_bytes(b"dylib-bytes-b")
    swapped: list[Path] = []

    def hook(path: Path) -> None:
        if Path(path) == target and not swapped:
            swapped.append(Path(path))
            os.replace(replacement, target)

    monkeypatch.setattr(module, "_READ_HOOK", hook, raising=False)
    with pytest.raises(module.RuntimeClosureError) as error:
        _closure(module, install)
    assert error.value.code == "CLOSURE_FILE_REPLACED"
    assert swapped == [target]


# --------------------------------------------------------------------------------------
# Attestation: process identity, loaded images, ROS domain
# --------------------------------------------------------------------------------------


def test_darwin_loaded_image_probe_ignores_blank_vmmap_lines(
    tmp_path: Path, monkeypatch
) -> None:
    module = _closure_module()
    library = tmp_path / "libexample.dylib"
    library.write_bytes(b"example")
    inaccessible = Path("/private/var/db/analyticsd/events.allowlist")
    output = (
        "Process: Python [123]\n\n"
        "__DATA 2000-3000 [ 4K 4K 0K 0K] r--/r-- SM=COW  "
        f"{inaccessible}\n"
        "__TEXT 1000-2000 [ 4K 4K 0K 0K] r-x/r-x SM=COW  "
        f"{library}\n\n"
    )
    real_is_file = module.Path.is_file

    def is_file(path):
        if path == inaccessible:
            raise PermissionError(str(path))
        return real_is_file(path)

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout=output, stderr=""
        ),
    )
    monkeypatch.setattr(module.Path, "is_file", is_file)

    assert module._darwin_loaded_images(123) == (library,)


def test_attestation_refuses_loaded_image_outside_the_copied_install(tmp_path: Path) -> None:
    module = _closure_module()
    install = _install_tree(tmp_path / "install")
    closure = _closure(module, install)
    binding = _binding(module, tmp_path)
    outside = tmp_path / "canonical" / "libmujoco_ros2_control.dylib"
    outside.parent.mkdir(parents=True)
    outside.write_bytes(b"dylib-bytes-a")

    with pytest.raises(module.RuntimeClosureError) as error:
        module.build_runtime_attestation(
            closure=closure,
            run_binding=binding,
            install_root=install,
            process_identities=_identities(module, 301, generation=1),
            loaded_images=(outside,),
            observed_ros_domain_id=41,
        )
    assert error.value.code == "LOADED_IMAGE_OUTSIDE_INSTALL"


def test_attestation_refuses_loaded_image_bytes_drift(tmp_path: Path) -> None:
    module = _closure_module()
    install = _install_tree(tmp_path / "install")
    closure = _closure(module, install)
    binding = _binding(module, tmp_path)
    library = install / "lib" / "libmujoco_ros2_control.dylib"
    library.write_bytes(b"dylib-bytes-b")

    with pytest.raises(module.RuntimeClosureError) as error:
        module.build_runtime_attestation(
            closure=closure,
            run_binding=binding,
            install_root=install,
            process_identities=_identities(module, 302, generation=1),
            loaded_images=(library,),
            observed_ros_domain_id=41,
        )
    assert error.value.code == "LOADED_IMAGE_DIGEST_MISMATCH"


def test_attestation_refuses_a_different_ros_domain(tmp_path: Path) -> None:
    module = _closure_module()
    install = _install_tree(tmp_path / "install")
    closure = _closure(module, install)
    binding = _binding(module, tmp_path, domain=41)
    library = install / "lib" / "libmujoco_ros2_control.dylib"

    with pytest.raises(module.RuntimeClosureError) as error:
        module.build_runtime_attestation(
            closure=closure,
            run_binding=binding,
            install_root=install,
            process_identities=_identities(module, 303, generation=1),
            loaded_images=(library,),
            observed_ros_domain_id=42,
        )
    assert error.value.code == "ATTESTATION_ROS_DOMAIN_MISMATCH"


def test_attestation_requires_at_least_one_process_identity(tmp_path: Path) -> None:
    module = _closure_module()
    install = _install_tree(tmp_path / "install")
    closure = _closure(module, install)
    binding = _binding(module, tmp_path)
    with pytest.raises(module.RuntimeClosureError) as error:
        module.build_runtime_attestation(
            closure=closure,
            run_binding=binding,
            install_root=install,
            process_identities=(),
            loaded_images=(),
            observed_ros_domain_id=41,
        )
    assert error.value.code == "ATTESTATION_PROCESS_IDENTITIES"


def _process_attestation_tree(tmp_path: Path):
    install = _install_tree_with_vendor_alias(tmp_path / "install")
    executable = install / "lib/mujoco_ros2_control/ros2_control_node"
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    return install, executable


def test_controller_process_attestation_requires_the_real_role_and_both_images(
    tmp_path: Path,
) -> None:
    module = _closure_module()
    install, executable = _process_attestation_tree(tmp_path)
    closure = _closure(module, install)
    plugin = install / "lib/libmujoco_ros2_control.dylib"
    vendor = install / "opt/mujoco_vendor/lib/libmujoco.3.4.0.dylib"

    attestation = module.build_runtime_process_attestation(
        closure=closure,
        install_root=install,
        role="controller_runtime",
        pid=9123,
        birth_identity_before=77,
        birth_identity_after=77,
        executable=executable,
        loaded_images=(plugin, vendor),
        required_relative_paths=(
            "lib/libmujoco_ros2_control.dylib",
            "opt/mujoco_vendor/lib/libmujoco.3.4.0.dylib",
        ),
    )

    assert attestation.role == "controller_runtime"
    assert attestation.executable == executable.resolve()
    assert {item.relative_path for item in attestation.loaded_images} == {
        "lib/libmujoco_ros2_control.dylib",
        "opt/mujoco_vendor/lib/libmujoco.3.4.0.dylib",
    }


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("wrong-role", "PROCESS_ATTESTATION_ROLE"),
        ("identity-drift", "PROCESS_ATTESTATION_IDENTITY_DRIFT"),
        ("launcher", "PROCESS_ATTESTATION_EXECUTABLE"),
        ("empty-images", "PROCESS_ATTESTATION_REQUIRED_IMAGE_MISSING"),
    ],
)
def test_controller_process_attestation_rejects_wrong_child_or_incomplete_readback(
    tmp_path: Path, mutation: str, expected_code: str
) -> None:
    module = _closure_module()
    install, executable = _process_attestation_tree(tmp_path)
    closure = _closure(module, install)
    plugin = install / "lib/libmujoco_ros2_control.dylib"
    vendor = install / "opt/mujoco_vendor/lib/libmujoco.3.4.0.dylib"
    outside = tmp_path / "ros2-launch"
    outside.write_text("#!/bin/sh\n", encoding="utf-8")
    outside.chmod(0o755)

    with pytest.raises(module.RuntimeClosureError) as error:
        module.build_runtime_process_attestation(
            closure=closure,
            install_root=install,
            role="task-station" if mutation == "wrong-role" else "controller_runtime",
            pid=9123,
            birth_identity_before=77,
            birth_identity_after=78 if mutation == "identity-drift" else 77,
            executable=outside if mutation == "launcher" else executable,
            loaded_images=() if mutation == "empty-images" else (plugin, vendor),
            required_relative_paths=(
                "lib/libmujoco_ros2_control.dylib",
                "opt/mujoco_vendor/lib/libmujoco.3.4.0.dylib",
            ),
        )
    assert error.value.code == expected_code


# --------------------------------------------------------------------------------------
# Stack integration: verify before spawn, attest only after read-back
# --------------------------------------------------------------------------------------


class _FakeChild:
    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.alive = True

    def poll(self):
        return None if self.alive else 0

    def wait(self, timeout: float):
        self.alive = False
        return 0


def _station_config(module, stack, tmp_path: Path, install: Path, binding, closure):
    return stack.PersistentStackConfig(
        session_id="session-a",
        headless=False,
        evidence_root=tmp_path / "evidence-a",
        processes=(stack.StackProcessSpec("task-station", ("ros2", "launch")),),
        closure=closure,
        run_binding=binding,
        install_root=install,
    )


def _station_environment() -> dict:
    """The merged environment the station children really run under.

    The runtime closure is built from this exact environment, because the frozen identity
    describes the constraints the station executes with -- not a test-local subset.
    """

    return dict(os.environ, DYLD_LIBRARY_PATH="/x", ROS_DOMAIN_ID="41")


def _stack(module, stack, tmp_path: Path, install: Path, *, loaded_images, spawned, signals):
    def popen(argv, **kwargs):
        child = _FakeChild(801 + len(spawned))
        spawned.append((argv, kwargs))
        return child

    return stack.PersistentTaskStack(
        popen=popen,
        killpg=lambda pid, sig: signals.append((pid, sig)),
        birth_identity_probe=lambda pid: 5_000 + pid,
        loaded_image_probe=lambda pid: tuple(loaded_images),
    )


def test_stack_verifies_the_closure_before_any_spawn(tmp_path: Path) -> None:
    module = _closure_module()
    stack = _stack_module()
    install = _install_tree(tmp_path / "install")
    closure = _closure(module, install, environment=_station_environment())
    binding = _binding(module, tmp_path)
    config = _station_config(module, stack, tmp_path, install, binding, closure)
    (
        install
        / "share"
        / "so101_demo_py"
        / "config"
        / "mujoco"
        / "parallel_batch_v4_macos_mps_w2.yaml"
    ).write_text("schema_version: 5\n", encoding="utf-8")

    spawned: list = []
    signals: list = []
    task_stack = _stack(
        module,
        stack,
        tmp_path,
        install,
        loaded_images=[install / "lib" / "libmujoco_ros2_control.dylib"],
        spawned=spawned,
        signals=signals,
    )
    with pytest.raises(module.RuntimeClosureError) as error:
        task_stack.start(config, environment={"DYLD_LIBRARY_PATH": "/x"})

    assert error.value.code == "CLOSURE_INVENTORY_DRIFT"
    assert spawned == []
    assert task_stack.attestation is None


def test_stack_attests_only_after_identity_and_loaded_image_readback(tmp_path: Path) -> None:
    module = _closure_module()
    stack = _stack_module()
    install = _install_tree(tmp_path / "install")
    closure = _closure(module, install, environment=_station_environment())
    binding = _binding(module, tmp_path, domain=41)
    config = _station_config(module, stack, tmp_path, install, binding, closure)
    library = install / "lib" / "libmujoco_ros2_control.dylib"

    spawned: list = []
    signals: list = []
    task_stack = _stack(
        module,
        stack,
        tmp_path,
        install,
        loaded_images=[library],
        spawned=spawned,
        signals=signals,
    )
    task_stack.start(
        config, environment={"DYLD_LIBRARY_PATH": "/x", "ROS_DOMAIN_ID": "41"}
    )

    assert len(spawned) == 1
    attestation = task_stack.attestation
    assert attestation is not None
    assert attestation.closure_sha256 == closure.sha256
    assert attestation.run_binding_sha256 == binding.sha256
    assert [identity.pid for identity in attestation.process_identities] == [801]
    assert [identity.start_time_ticks for identity in attestation.process_identities] == [5801]
    assert [entry.relative_path for entry in attestation.loaded_images] == [
        "lib/libmujoco_ros2_control.dylib"
    ]
    assert attestation.observed_ros_domain_id == 41
    task_stack.shutdown()


def test_stack_refuses_to_attest_an_outside_loaded_image_and_reaps_children(
    tmp_path: Path,
) -> None:
    module = _closure_module()
    stack = _stack_module()
    install = _install_tree(tmp_path / "install")
    closure = _closure(module, install, environment=_station_environment())
    binding = _binding(module, tmp_path)
    config = _station_config(module, stack, tmp_path, install, binding, closure)
    outside = tmp_path / "canonical" / "libmujoco_ros2_control.dylib"
    outside.parent.mkdir(parents=True)
    outside.write_bytes(b"dylib-bytes-a")

    spawned: list = []
    signals: list = []
    task_stack = _stack(
        module,
        stack,
        tmp_path,
        install,
        loaded_images=[outside],
        spawned=spawned,
        signals=signals,
    )
    with pytest.raises(module.RuntimeClosureError) as error:
        task_stack.start(
        config, environment={"DYLD_LIBRARY_PATH": "/x", "ROS_DOMAIN_ID": "41"}
    )

    assert error.value.code == "LOADED_IMAGE_OUTSIDE_INSTALL"
    assert len(spawned) == 1
    assert signals and signals[0][0] == 801
    assert task_stack.attestation is None


def test_stack_config_requires_closure_and_run_binding_together(tmp_path: Path) -> None:
    module = _closure_module()
    stack = _stack_module()
    install = _install_tree(tmp_path / "install")
    closure = _closure(module, install)
    binding = _binding(module, tmp_path)

    with pytest.raises(ValueError):
        stack.PersistentStackConfig(
            session_id="session-a",
            headless=False,
            evidence_root=tmp_path / "evidence-a",
            processes=(stack.StackProcessSpec("task-station", ("ros2", "launch")),),
            closure=closure,
        )
    with pytest.raises(ValueError):
        stack.PersistentStackConfig(
            session_id="session-a",
            headless=False,
            evidence_root=tmp_path / "evidence-a",
            processes=(stack.StackProcessSpec("task-station", ("ros2", "launch")),),
            run_binding=binding,
            install_root=install,
        )
