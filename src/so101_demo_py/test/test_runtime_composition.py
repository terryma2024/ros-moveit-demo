import ast
from pathlib import Path

import pytest
from so101_demo.runtime.composition import (
    BackendAdapters,
    CompositionRequest,
    RuntimeCompositionError,
    compose_backend,
)


class Port:
    pass


def test_composition_loads_exact_policy_variant_and_bundle(package_share: Path) -> None:
    adapters = BackendAdapters(Port(), Port(), Port(), Port(), Port())
    request = CompositionRequest(
        backend="mujoco",
        policy_id="light_cup_wall_pick",
        policy_version="v1",
        share_dir=package_share,
        source_commit="0" * 40,
        installed_prefix=package_share.parent,
    )
    composition = compose_backend(request, lambda backend: adapters)
    assert composition.backend == "mujoco"
    assert composition.policy.backend == "mujoco"
    assert len(composition.bundle.bundle_sha256) == 64
    assert composition.capabilities.lossless_physics_step_trace


def test_composition_rejects_unknown_backend(package_share: Path) -> None:
    request = CompositionRequest(
        "unknown",
        "light_cup_wall_pick",
        "v1",
        package_share,
        "0" * 40,
        package_share.parent,
    )
    with pytest.raises(RuntimeCompositionError, match="unsupported backend"):
        compose_backend(request, lambda backend: BackendAdapters(Port(), Port(), Port(), Port()))


def test_core_and_application_do_not_import_backend_implementations() -> None:
    root = Path(__file__).parents[1] / "src"
    forbidden = {"so101_demo.backends", "mujoco", "gazebo", "ros_gz"}
    violations = []
    for area in (root / "core", root / "application"):
        for path in area.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for name in names:
                    if any(name == item or name.startswith(f"{item}.") for item in forbidden):
                        violations.append(f"{path}:{node.lineno}:{name}")
    assert violations == []


@pytest.fixture
def package_share() -> Path:
    return Path(__file__).parents[1]
