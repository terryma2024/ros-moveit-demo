"""The closed runtime-role registry must describe what the runtime actually loads.

Task 8P1 provenance is a claim about the installed artefacts the runtime uses, so each role has to name the
overlay that owns it, the package-owned installed path inside that overlay, and where its sources really live.
The vendored MuJoCo plugin is the case that makes this visible: it is built by its own package in the dependency
overlay, not by `so101_mujoco_support`, so it must not be described as if this worktree produced it.
"""

from pathlib import Path

from so101_demo.act.source_provenance import runtime_role_specs

WORKTREE = Path(__file__).resolve().parents[1]
REPOSITORY = WORKTREE.parents[1]


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
    for name in ("simulation_evidence_plugin", "broker_owned_controller_plugin"):
        spec = _by_name(name)
        assert spec[4] == "worktree", spec
        assert spec[3].startswith("so101_mujoco_support/lib/"), spec[3]
