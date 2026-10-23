"""The closed runtime-role registry must describe what the runtime actually loads.

Source provenance is a claim about the installed artefacts the runtime uses, so each role has to name the
overlay that owns it, the package-owned installed path inside that overlay, and where its sources really live.
The vendored MuJoCo plugin is the case that makes this visible: it is built by its own package in the dependency
overlay, not by `so101_mujoco_support`, so it must not be described as if this worktree produced it.
"""


from so101_demo.act.source_provenance import runtime_role_specs
from paths import PACKAGE_ROOT, REPOSITORY

WORKTREE = PACKAGE_ROOT


def _by_name(name):
    specs = {spec[0]: spec for spec in runtime_role_specs()}
    assert name in specs, f"{name} missing from the registry"
    return specs[name]


def test_every_role_names_the_overlay_that_owns_it():
    for spec in runtime_role_specs():
        # (role, kind, source_rel, install_rel, overlay) - the overlay decides which install root is used
        assert len(spec) == 5, f"{spec[0]} does not declare its owning overlay: {spec}"
        assert spec[4] in ("worktree", "dependency", "external"), spec


def test_the_vendored_plugin_is_owned_by_the_dependency_overlay():
    spec = _by_name("mujoco_ros2_control_plugin")
    assert spec[4] == "dependency"
    # the installed path is package-owned inside that overlay, never relocated into another package's lib dir
    assert spec[3] == "mujoco_ros2_control/lib/libmujoco_ros2_control.so", spec[3]
    assert not spec[3].startswith("so101_mujoco_support/"), spec[3]


def test_the_vendored_plugin_points_at_its_real_submodule_sources():
    spec = _by_name("mujoco_ros2_control_plugin")
    source_rel = spec[2]
    assert source_rel.startswith("third_party/mujoco_ros2_control/"), source_rel
    # the worktree plugin's source must never be recorded as the vendored plugin's source
    assert "so101_mujoco_support/src/simulation_evidence_plugin.cpp" not in source_rel
    assert (REPOSITORY / source_rel).exists(), f"{source_rel} does not exist"


def test_the_worktree_plugins_stay_in_the_worktree_overlay():
    for name in ("simulation_evidence_plugin",):
        spec = _by_name(name)
        assert spec[4] == "worktree", spec
        assert spec[3].startswith("so101_mujoco_support/lib/"), spec[3]


def test_the_broker_rows_are_gone_from_the_registry():
    names = {spec[0] for spec in runtime_role_specs()}
    assert "command" + "_broker" not in names and "broker_owned" + "_controller_plugin" not in names


OVERLAY = "third_party/ros2_controllers/"


def test_the_patched_controller_libraries_are_compiled_roles_of_the_dependency_overlay():
    """The queued-state overlay replaces the apt controllers, so the libraries the stack loads must be pinned."""
    for name, package, library in (
            ("joint_trajectory_controller_plugin", "joint_trajectory_controller", "libjoint_trajectory_controller.so"),
            ("joint_state_broadcaster_plugin", "joint_state_broadcaster", "libjoint_state_broadcaster.so")):
        spec = _by_name(name)
        assert spec[1] == "compiled", spec
        assert spec[4] == "dependency", spec
        assert spec[2] == f"{OVERLAY}{package}/src", spec[2]
        assert spec[3] == f"{package}/lib/{library}", spec[3]
        assert (REPOSITORY / spec[2]).is_dir(), spec[2]


def test_the_header_only_queued_publisher_is_pinned_as_a_verbatim_install():
    spec = _by_name("queued_state_publisher_header")
    header = "so101_queued_state_publisher/queued_state_publisher.hpp"
    assert spec[1] == "verbatim_install" and spec[4] == "dependency", spec
    assert spec[2] == f"{OVERLAY}so101_queued_state_publisher/include/{header}", spec[2]
    assert spec[3] == f"so101_queued_state_publisher/include/so101_queued_state_publisher/{header}", spec[3]
    assert (REPOSITORY / spec[2]).is_file(), spec[2]


def test_the_registry_stays_closed_over_the_overlay_roles():
    names = [spec[0] for spec in runtime_role_specs()]
    assert len(names) == len(set(names)) == 11, names
