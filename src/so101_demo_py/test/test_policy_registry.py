import shutil
from pathlib import Path

import pytest
import yaml
from so101_demo.core.policy_registry import PolicyValidationError, load_policy_variant

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPOSITORY_ROOT / "src" / "so101_demo_py"
LEGACY_POLICY = (
    REPOSITORY_ROOT
    / "src"
    / "so101_mujoco_demo_py"
    / "config"
    / "motion_policies"
    / "light_cup_wall_pick.yaml"
)
POLICY_ROOT = PACKAGE_ROOT / "config" / "policies" / "light_cup_wall_pick" / "v1"


def test_v1_simulator_variants_are_exact_frozen_bytes() -> None:
    """Catch any edit, formatting pass, or backend tuning of either frozen v1 variant."""

    frozen = LEGACY_POLICY.read_bytes()
    assert (POLICY_ROOT / "mujoco.yaml").read_bytes() == frozen
    assert (POLICY_ROOT / "gazebo.yaml").read_bytes() == frozen


def test_registry_loads_explicit_backend_without_fallback() -> None:
    """Catch selecting another backend's file or silently defaulting a missing variant."""

    mujoco = load_policy_variant("light_cup_wall_pick", "v1", "mujoco", PACKAGE_ROOT)
    gazebo = load_policy_variant("light_cup_wall_pick", "v1", "gazebo", PACKAGE_ROOT)
    assert mujoco.backend == "mujoco"
    assert gazebo.backend == "gazebo"
    assert mujoco.policy_sha256 == gazebo.policy_sha256
    assert gazebo.qualification_status == "NOT_QUALIFIED"
    with pytest.raises(PolicyValidationError, match="backend"):
        load_policy_variant("light_cup_wall_pick", "v1", "unknown", PACKAGE_ROOT)


@pytest.mark.parametrize("mutation", ["unknown_field", "missing_field", "nan", "boolean_number"])
def test_loader_rejects_noncanonical_simulator_variant(tmp_path: Path, mutation: str) -> None:
    """Catch accepting a policy whose schema or numeric types no longer match the frozen contract."""

    package = tmp_path / "share"
    variant_root = package / "config" / "policies" / "light_cup_wall_pick" / "v1"
    variant_root.mkdir(parents=True)
    shutil.copyfile(POLICY_ROOT / "manifest.yaml", variant_root / "manifest.yaml")
    document = yaml.safe_load(LEGACY_POLICY.read_bytes())
    if mutation == "unknown_field":
        document["unexpected"] = True
    elif mutation == "missing_field":
        document.pop("tcp_link")
    elif mutation == "nan":
        document["safety_limits"]["maximum_diagnostic_force_n"] = float("nan")
    else:
        document["safety_limits"]["maximum_diagnostic_force_n"] = True
    (variant_root / "mujoco.yaml").write_text(yaml.safe_dump(document), encoding="utf-8")
    with pytest.raises(PolicyValidationError):
        load_policy_variant("light_cup_wall_pick", "v1", "mujoco", package)


def test_real_stub_variant_contains_no_simulation_contact_threshold() -> None:
    """Catch leaking simulator contact policy into the real-hardware safety stub."""

    loaded = load_policy_variant("light_cup_wall_pick", "v1", "real_stub", PACKAGE_ROOT)
    assert loaded.backend == "real_stub"
    assert loaded.policy is None
    assert "contact" not in loaded.configuration
    assert "threshold" not in loaded.configuration
