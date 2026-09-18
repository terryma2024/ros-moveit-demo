from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
TELEOP = ROOT / "src" / "so101_teleop"
DEMO = ROOT / "src" / "so101_demo_py"

EXPERT_VALIDATION_TESTS = {
    "test_expert_validation_adaptive_events",
    "test_expert_validation_adaptive_owner",
    "test_expert_validation_api",
    "test_expert_validation_artifacts",
    "test_expert_validation_catalog",
    "test_expert_validation_control",
    "test_expert_validation_coordinator_events",
    "test_expert_validation_e2e_fixtures",
    "test_expert_validation_e2e_installed_port",
    "test_expert_validation_executor_registry",
    "test_expert_validation_frozen_manifest",
    "test_expert_validation_lease",
    "test_expert_validation_main",
    "test_expert_validation_operator_recovery",
    "test_expert_validation_preflight",
    "test_expert_validation_process_owner",
    "test_expert_validation_process_owner_integration",
    "test_expert_validation_production_projection",
    "test_expert_validation_projection",
    "test_expert_validation_service",
    "test_expert_validation_statistics",
    "test_expert_validation_store",
    "test_expert_validation_supervisor",
}


def test_cmake_registers_every_expert_validation_python_gate():
    cmake = (TELEOP / "CMakeLists.txt").read_text(encoding="utf-8")
    registered = set(
        re.findall(r"so101_add_pytest_test\((test_expert_validation_[a-z0-9_]+)", cmake)
    )
    assert registered == EXPERT_VALIDATION_TESTS | {
        "test_expert_validation_package_layout"
    }


def test_e2e_launcher_helpers_and_scenarios_are_not_installed():
    cmake = (TELEOP / "CMakeLists.txt").read_text(encoding="utf-8")
    install_blocks = re.findall(r"install\((.*?)\)", cmake, re.DOTALL)
    assert install_blocks
    for block in install_blocks:
        assert "test/e2e" not in block
        assert "process_helpers" not in block
        assert "expert_validation_e2e" not in block
    # The E2E launcher, execution port, helpers, and scenario fixtures live
    # outside the installed python package and installed script set.
    assert not (TELEOP / "so101_teleop" / "expert_validation" / "installed_test_launcher.py").exists()
    scripts_block = re.search(r"install\(\s*PROGRAMS(.*?)\)", cmake, re.DOTALL)
    assert scripts_block is not None
    assert "installed_test_launcher" not in scripts_block.group(1)


def test_generated_cmake_registry_includes_backend_result_gate(tmp_path):
    build = tmp_path / "cmake-registry"
    configured = subprocess.run(
        [
            "cmake", "-S", str(TELEOP), "-B", str(build),
            "-DBUILD_TESTING=ON",
            f"-DPython3_EXECUTABLE={sys.executable}",
            f"-DPYTHON_EXECUTABLE={sys.executable}",
        ],
        capture_output=True, text=True,
    )
    assert configured.returncode == 0, configured.stdout + configured.stderr
    generated = (build / "CTestTestfile.cmake").read_text(encoding="utf-8")
    pytest_paths = set(re.findall(
        r'^add_test\(.*? "-m" "pytest" "([^"]+)"', generated, re.MULTILINE,
    ))

    assert str(TELEOP / "test/teleop/test_backend_result.py") in pytest_paths


def test_teleop_install_contract_contains_validation_server_fixture_and_spa():
    cmake = (TELEOP / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "ament_python_install_package(so101_teleop)" in cmake
    assert "scripts/so101_expert_validation_server.py" in cmake
    assert "config docs launch" in cmake
    assert "web/dist/" in cmake
    assert (
        TELEOP / "config" / "expert_validation" / "top_view_projection_v1.json"
    ).is_file()
    assert (
        TELEOP / "so101_teleop" / "expert_validation" / "catalog.py"
    ).is_file()
    assert (TELEOP / "web" / "src" / "expert-validation-app.tsx").is_file()


def test_upstream_adaptive_runtime_and_catalog_are_installable():
    setup = (DEMO / "setup.py").read_text(encoding="utf-8")
    assert "find_packages(where=\"src\")" in setup
    assert "installed_resources()" in setup
    assert "so101_parallel_batch =" in setup
    assert "so101_parallel_batch_cleanup =" in setup
    assert "run_so101_adaptive_batch.zsh" in setup
    for relative in (
        "src/parallel_batch/adaptive_runner.py",
        "src/parallel_batch/adaptive_pool.py",
        "src/cli/parallel_batch_cleanup.py",
        "config/mujoco/parallel_adaptive_workers_v1.yaml",
        "config/mujoco/parallel_batch_v1.yaml",
        "config/mujoco/moveit_expert_validation_points_v1.yaml",
    ):
        assert (DEMO / relative).is_file(), relative


def test_teleop_imports_the_packaged_upstream_runtime_namespace():
    statistics = (
        TELEOP / "so101_teleop/expert_validation/statistics.py"
    ).read_text(encoding="utf-8")

    assert "from so101_demo.parallel_batch" in statistics
    assert "from parallel_batch" not in statistics
