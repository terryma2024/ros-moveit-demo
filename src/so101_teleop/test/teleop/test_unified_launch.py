"""Launch contract tests: one installed entry point, legacy scripts only delegate."""

from __future__ import annotations

import ast
import re
from pathlib import Path

PACKAGE = Path(__file__).parents[2]

UNIFIED_SCRIPT = PACKAGE / "scripts/so101_unified_web_server.py"
LEGACY_SCRIPTS = (
    PACKAGE / "scripts/so101_teleop_server.py",
    PACKAGE / "scripts/so101_expert_validation_server.py",
)


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def test_unified_entry_module_and_script_exist_and_delegate_to_the_same_module():
    assert "so101_teleop.unified.main" in imported_modules(UNIFIED_SCRIPT)
    for script in LEGACY_SCRIPTS:
        assert "so101_teleop.unified.main" in imported_modules(script), script.name


def test_legacy_scripts_no_longer_start_a_web_listener_of_their_own():
    forbidden = {"so101_teleop.main", "so101_teleop.expert_validation.main"}
    for script in LEGACY_SCRIPTS:
        modules = imported_modules(script)
        assert not (modules & forbidden), (script.name, sorted(modules & forbidden))
        source = script.read_text()
        assert "DEPRECATION_NOTICE" in source, script.name


def test_exactly_one_uvicorn_entry_point_and_one_port_configuration():
    from so101_teleop.unified.main import build_parser

    parser = build_parser()
    port = [action for action in parser._actions if action.dest == "port"]
    assert len(port) == 1
    assert port[0].default == 8000
    # Only the unified module may import uvicorn or bind a port.
    assert "uvicorn" in (PACKAGE / "so101_teleop/unified/main.py").read_text()
    for script in LEGACY_SCRIPTS:
        modules = imported_modules(script)
        assert "uvicorn" not in modules, script.name
        assert "so101_teleop.unified.main" in modules, script.name


def test_install_manifest_registers_the_unified_launcher():
    cmake = (PACKAGE / "CMakeLists.txt").read_text()
    assert "scripts/so101_unified_web_server.py" in cmake
    programs = cmake.split("install(", 2)[2]
    assert programs.index("scripts/so101_unified_web_server.py") < programs.index(
        "scripts/so101_teleop_server.py"
    )
    for name in (
        "test_unified_gate",
        "test_unified_arbiter",
        "test_unified_instances",
        "test_unified_safety",
        "test_unified_ipc",
        "test_unified_bridge",
        "test_unified_two_channel",
        "test_unified_parents",
        "test_unified_admission",
        "test_unified_api",
        "test_unified_lifecycle",
        "test_unified_budget_adapter",
        "test_unified_live_fixture",
        "test_unified_launch",
    ):
        assert f"so101_add_pytest_test({name} " in cmake, name


def test_legacy_entry_modules_are_not_reachable_from_the_unified_module():
    unified_source = (PACKAGE / "so101_teleop/unified/main.py").read_text()
    assert "so101_teleop.main" not in unified_source
    assert "expert_validation.main" not in unified_source


def test_every_unified_test_module_is_registered_and_every_registration_exists():
    """A test file that is not registered silently never runs, and a registration that points at a
    missing file breaks the build. Both directions are checked here."""
    package = PACKAGE
    cmake = (package / "CMakeLists.txt").read_text()
    registered = dict(
        re.findall(r"so101_add_pytest_test\((test_unified_[a-z_]+) ([^)]+)\)", cmake)
    )
    on_disk = {
        f"test_unified_{path.stem.removeprefix('test_unified_')}": str(
            path.relative_to(package)
        )
        for path in package.rglob("test_unified_*.py")
    }
    missing_registration = sorted(set(on_disk) - set(registered))
    missing_file = sorted(
        name for name, rel in registered.items() if not (package / rel).is_file()
    )
    assert missing_registration == [], f"unregistered unified tests: {missing_registration}"
    assert missing_file == [], f"registered test files that do not exist: {missing_file}"
    for name, rel in registered.items():
        assert on_disk.get(name) == rel, (name, rel, on_disk.get(name))


def test_every_script_is_installed_and_every_install_entry_exists():
    """Packaging drift guard, the same shape as the pytest-registration one.

    A script on disk that is not in `install(PROGRAMS ...)` never reaches an installed prefix, and an
    entry pointing at a missing file breaks the install step. Both directions are checked.
    """
    package = PACKAGE
    cmake = (package / "CMakeLists.txt").read_text()
    block = cmake[cmake.index("install(\n  PROGRAMS"):]
    installed = set(re.findall(r"scripts/([A-Za-z0-9_]+\.py)", block[: block.index(")")]))
    on_disk = {path.name for path in (package / "scripts").glob("*.py")}
    assert sorted(on_disk - installed) == [], "scripts that are never installed"
    assert sorted(installed - on_disk) == [], "install entries with no file"
